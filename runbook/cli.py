"""runbook CLI

    runbook run  手順書.md              一括実行(失敗で即中断)
    runbook run  -i 手順書.md           逐次インタラクティブ実行
    runbook run  --only 3 手順書.md     ステップ指定実行(例: --only 1,3-5)
    runbook run  --from 2 --to 4 ...    範囲指定
    runbook run  --rollback 手順書.md   切り戻しセクション(# RB-ROLLBACK)の実行
    runbook run  --start-from 5 ...     ステップ5から再開(share_env なら環境変数も復元)
    runbook run  --yes --operator 名前  実行前確認・作業者入力の省略(非対話実行用)
    runbook list 手順書.md              ステップ一覧表示
    runbook check 手順書.md             書式・基準式・変数・参照パスの検証のみ
    runbook check --preview 手順書.md   検証 + 展開後の実行コマンドを全文表示

実行開始前にはサマリー(タイトル・対象ステップ・変数・インベントリ)を表示して
確認を挟み(--yes でスキップ)、作業者名(必須)・確認者名(任意)を記録する。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from rich import box

from . import __version__, criteria, parser
from .executor import StepRecord, parse_ansible_host_results, run_command
from .logger import RunLogger

# soft_wrap: 長い行に強制改行を入れない(tee 等でテキスト保存しても行が崩れない)
console = Console(highlight=False, soft_wrap=True)


def parse_step_selection(spec: str, max_n: int) -> set[int]:
    """'1,3-5' → {1,3,4,5}"""
    selected: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            raise ValueError(f"ステップ指定の書式が不正です: {part!r} (例: 1,3-5)")
        lo = int(m.group(1))
        hi = int(m.group(2) or m.group(1))
        if not (1 <= lo <= hi <= max_n):
            raise ValueError(f"ステップ番号が範囲外です: {part!r} (1〜{max_n})")
        selected.update(range(lo, hi + 1))
    return selected


def parse_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--var は KEY=VALUE 形式で指定してください: {pair!r}")
        k, v = pair.split("=", 1)
        out[k.strip()] = v
    return out


MASK = "*****"


def make_mask(proc):
    """シークレットマスキング関数を作る(提案4)。

    共通設定 secrets: [VAR] で宣言された変数の「値」を、表示・ログの
    あらゆるテキストから MASK に置換する。値が別の値の部分文字列である
    場合の取りこぼしを防ぐため、長い値から順に置換する。
    """
    values = sorted((proc.vars[name] for name in proc.secrets if proc.vars.get(name)),
                    key=len, reverse=True)
    if not values:
        return lambda t: t

    def mask(text: str) -> str:
        for v in values:
            text = text.replace(v, MASK)
        return text

    return mask


def print_tree_item(header: str, text: str, style: str = "") -> None:
    lines = text.splitlines()
    if not lines:
        return
    if style:
        console.print(f"  ├ {header}: [{style}]{escape(lines[0])}[/]")
        for line in lines[1:]:
            console.print(f"  │   [{style}]{escape(line)}[/]")
    else:
        console.print(f"  ├ {header}: {escape(lines[0])}")
        for line in lines[1:]:
            console.print(f"  │   {escape(line)}")


def show_step_header(step, total: int, mask=lambda t: t) -> None:
    console.print()
    console.print(f"・ ステップ {step.number}/{total}: [bold #cfd3ea]{escape(step.title)}[/]")
    if step.description:
        print_tree_item("説明", step.description)
    if step.runner == "manual":
        console.print("  └ [bold #f2b94d]手動ステップ[/](コマンドなし。上記の作業を実施してください)")
        return
    if step.runner == "ansible":
        console.print("  ├ コマンド (ansible ad-hoc / shellモジュール):")
        for line in mask(step.remote_command).splitlines():
            console.print(f"  │   $ {escape(line)}", style="cyan")
        print_tree_item("実行コマンド", mask(step.command), style="dim")
    elif step.runner == "playbook":
        console.print("  ├ プレイブック (ansible-playbook):")
        for line in mask(step.remote_command).splitlines():
            console.print(f"  │   {escape(line)}", style="cyan")
        print_tree_item("実行コマンド", mask(step.command), style="dim")
    else:
        console.print("  ├ コマンド:")
        for line in mask(step.command).splitlines():
            console.print(f"  │   $ {escape(line)}", style="cyan")
    print_tree_item("正常性基準", mask(step.criteria), style="bold #8ea7ff")


# ホスト別結果マトリックスのマーク: 状態 → (表示文字, スタイル)
_MATRIX_MARKS = {
    "ok": ("O", "bold #5fd9a4"),
    "failed": ("X", "bold #ff6b60"),
    "unreachable": ("!", "bold #f2b94d"),
}
_MATRIX_LEGEND = "[bold #5fd9a4]O[/]=成功  [bold #ff6b60]X[/]=失敗  [bold #f2b94d]![/]=到達不能  [dim]-[/]=対象外"
_LOG_MARKS = {
    "ok": "O",
    "failed": "X",
    "unreachable": "!",
}


def print_host_matrix(rows: list[tuple[str, dict]], label_header: str = "", indent: str = "") -> None:
    """列=ホスト名、値=成功/失敗マークのマトリックスを表示する。

    rows: (行ラベル, {ホスト名: 状態}) のリスト。1行なら単一ステップの結果、
    複数行ならステップ×ホストの集約マトリックス。
    """
    hosts = sorted({h for _, results in rows for h in results})
    table = Table(
        box=box.SIMPLE,
        border_style="#4a4f78",
        header_style="bold #cfd3ea",
        pad_edge=True,
    )
    table.add_column(label_header, style="bold")
    for host in hosts:
        table.add_column(Text(host), justify="center")
    for label, results in rows:
        cells = [Text(label)]
        for host in hosts:
            mark, style = _MATRIX_MARKS.get(results.get(host, ""), ("-", ""))
            cells.append(Text(mark, style=style))
        table.add_row(*cells)

    with console.capture() as cap:
        console.print(table)
    for line in cap.get().splitlines():
        console.print(f"{indent}{line}", markup=False)


def host_results_logline(results: dict) -> str:
    return " ".join(f"{h}={_LOG_MARKS.get(s, '-')}" for h, s in sorted(results.items()))


def confirm_interactive(step) -> str:
    """戻り値: run / skip / quit"""
    while True:
        console.print(
            f"[bold cyan]▶ 上記ステップ {step.number}「{escape(step.title)}」を実行しますか？ "
            f"\\[Enter]=実行  s=スキップ  q=中断[/bold cyan] > ",
            end="",
        )
        try:
            ans = input().strip().lower()
        except EOFError:
            console.print("\n[bold red]対話端末がありません(逐次実行 -i は端末から実行してください)[/]")
            return "quit"
        if ans in ("", "r", "run", "y"):
            return "run"
        if ans in ("s", "skip"):
            return "skip"
        if ans in ("q", "quit", "abort"):
            return "quit"


def confirm_manual(step, allow_skip: bool) -> str:
    """手動ステップの完了確認。戻り値: done / skip / quit

    完了は必ず y の明示入力を要求する(Enter 空打ちでの誤続行を防ぐ)。
    """
    choices = "y=完了して続行  " + ("s=スキップ  " if allow_skip else "") + "q=中断"
    while True:
        console.print(
            f"[bold #f2b94d]▶ 手動ステップ {step.number}「{escape(step.title)}」: "
            f"作業を実施し、完了したら y を入力してください \\[{choices}][/] > ",
            end="",
        )
        try:
            ans = input().strip().lower()
        except EOFError:
            console.print("\n[bold red]対話端末がありません(手動ステップを含む手順書は端末から実行してください)[/]")
            return "quit"
        if ans in ("y", "yes", "done"):
            return "done"
        if allow_skip and ans in ("s", "skip"):
            return "skip"
        if ans in ("q", "quit", "abort"):
            return "quit"


def show_onfail_guidance(step, log) -> None:
    """RB-ONFAIL(失敗時ガイダンス)を表示・記録する(提案B)"""
    if not step.onfail:
        return
    console.print()
    console.print("[bold #f2b94d]▶ 失敗時ガイダンス (RB-ONFAIL):[/]")
    for line in step.onfail.splitlines():
        console.print(f"  {escape(line)}", style="#f2b94d")
    log.log("失敗時ガイダンス(RB-ONFAIL):")
    log.log(step.onfail)


def show_rollback_hint(proc) -> None:
    """中断時に切り戻しセクションの実行方法を案内する(提案C。自動では実行しない)"""
    console.print(
        f"[bold #f2b94d]▶ この手順書には切り戻しセクションがあります"
        f"({len(proc.rollback_steps)} ステップ)。切り戻す場合は次を実行:[/]")
    console.print(f"    runbook run --rollback {proc.path}", markup=False)


def show_run_summary(proc, steps, selected: set[int], mode: str, rollback: bool,
                     mask=lambda t: t, start_from: int | None = None,
                     resume_env_src=None) -> None:
    """実行前サマリー(提案E)。手順書・対象・変数・インベントリの取り違えに気付くためのゲート"""
    inventories = sorted({inv for s in steps if s.number in selected for inv in s.inventories})
    n_manual = sum(1 for s in steps if s.number in selected and s.runner == "manual")
    console.print()
    console.print("・ 実行前確認")
    console.print(f"  ├ 手順書: [bold #cfd3ea]{escape(proc.title)}[/] ({proc.path})")
    if rollback:
        console.print("  ├ [bold #ff6b60]切り戻し実行(--rollback): 切り戻しセクションのステップを実行します[/]")
    console.print(f"  ├ モード: {mode}", markup=False)
    label = f"  ├ 実行対象: {len(selected)}/{len(steps)} ステップ"
    if n_manual:
        label += f"(うち手動 {n_manual})"
    console.print(label, markup=False)
    for s in steps:
        if s.number in selected:
            tag = "(手動)" if s.runner == "manual" else ""
            console.print(f"  │   {s.number}. {s.title}{tag}", markup=False)
    if proc.vars:
        console.print("  ├ 変数:")
        for k, v in proc.vars.items():
            disp = MASK if k in proc.secrets else mask(v)
            console.print(f"  │   {k} = {disp}", markup=False)
    if proc.secrets:
        console.print(f"  ├ 秘匿変数(値は表示・ログでマスク): {', '.join(proc.secrets)}", markup=False)
        if proc.share_env:
            console.print("  ├ [bold #f2b94d]注意: share_env が有効なため、export した値は "
                          "shared_env.sh に平文で残ります(保管・削除ルールに注意)[/]")
    if inventories:
        console.print("  ├ 使用インベントリ:")
        for inv in inventories:
            console.print(f"  │   {inv}", markup=False)
    if start_from is not None:
        console.print(f"  ├ 再開実行(--start-from): ステップ {start_from} から", markup=False)
        if resume_env_src:
            console.print(f"  ├ 環境変数の復元元: {resume_env_src}", markup=False)
    if not rollback:
        rb = f"あり({len(proc.rollback_steps)} ステップ。中断時に案内)" if proc.rollback_steps else "なし"
        console.print(f"  └ 切り戻しセクション: {rb}", markup=False)
    else:
        console.print("  └ (切り戻し実行)", markup=False)


def confirm_gate() -> bool:
    """実行前サマリーの確認ゲート。y の明示入力のみ実行(それ以外は中止)"""
    console.print("[bold cyan]▶ 上記の内容で実行しますか？ \\[y=実行  それ以外=中止][/] > ", end="")
    try:
        ans = input().strip().lower()
    except EOFError:
        console.print("\n[bold red]対話端末がありません(非対話実行では --yes を指定してください)[/]")
        return False
    return ans in ("y", "yes")


def ask_names(args) -> tuple[str, str]:
    """作業者・確認者名の取得(提案D)。--operator 指定時はプロンプトを出さない"""
    if args.operator:
        return args.operator, args.checker or ""
    while True:
        console.print("[bold cyan]▶ 作業者名を入力してください(必須)[/] > ", end="")
        try:
            operator = input().strip()
        except EOFError:
            raise ValueError("作業者名が必要です(非対話実行では --operator で指定してください)")
        if operator:
            break
    if args.checker is not None:
        return operator, args.checker
    console.print("[bold cyan]▶ 確認者名を入力してください(任意。Enter でスキップ)[/] > ", end="")
    try:
        checker = input().strip()
    except EOFError:
        checker = ""
    return operator, checker


def _find_latest_shared_env(base_dir: str, log_name: str) -> Path | None:
    """--start-from の環境復元用に、直近の実行ログディレクトリの shared_env.sh を探す。

    ディレクトリ名は <log_name>_YYYYMMDD_HHMMSS(同一秒の連続実行では _2 等の
    連番付き)形式なので名前の降順 = 新しい順。
    log_name を厳密に照合するため、"proc" の検索で "proc_rollback_..." は拾わない。
    """
    base = Path(base_dir)
    if not base.is_dir():
        return None
    pat = re.compile(re.escape(log_name) + r"_\d{8}_\d{6}(_\d+)?$")
    for d in sorted((d for d in base.iterdir() if d.is_dir() and pat.fullmatch(d.name)),
                    reverse=True):
        f = d / "shared_env.sh"
        if f.is_file():
            return f
    return None


def cmd_run(args: argparse.Namespace) -> int:
    proc = parser.parse_file(args.file, parse_vars(args.var))
    if args.rollback:
        if not proc.rollback_steps:
            raise ValueError(f"{proc.path}: 切り戻しセクション(# RB-ROLLBACK)がありません")
        steps = proc.rollback_steps
    else:
        steps = proc.steps
    total = len(steps)

    # 提案8軽量版: --start-from N(中断したステップからの再開)
    if args.start_from is not None:
        if args.only or args.from_ or args.to:
            raise ValueError("--start-from は --only / --from / --to と併用できません")
        if not (1 <= args.start_from <= total):
            raise ValueError(f"--start-from が範囲外です (1〜{total})")

    selected = parse_step_selection(args.only, total) if args.only else set(range(1, total + 1))
    if args.start_from is not None:
        selected = set(range(args.start_from, total + 1))
    if args.from_ or args.to:
        lo = args.from_ or 1
        hi = args.to or total
        if not (1 <= lo <= hi <= total):
            raise ValueError(f"--from/--to が範囲外です (1〜{total})")
        selected &= set(range(lo, hi + 1))
    if not selected:
        raise ValueError("実行対象のステップがありません")

    log_name = proc.path.stem + ("_rollback" if args.rollback else "")

    # --start-from + share_env: 前回実行の環境変数(shared_env.sh)を復元する。
    # 途中再開するステップが前段の export に依存している可能性があるため、
    # 復元元が見つからなければ実行前にエラーにする(fail-loud)。
    resume_env_src: Path | None = None
    if args.start_from is not None and proc.share_env:
        resume_env_src = _find_latest_shared_env(args.log_dir, log_name)
        if resume_env_src is None:
            raise ValueError(
                f"--start-from: 環境変数の復元元(過去実行の shared_env.sh)が "
                f"{args.log_dir} に見つかりません。前段の環境変数なしで実行してよい場合は "
                f"--from {args.start_from} を使ってください")

    mask = make_mask(proc)

    # 提案E: 実行前サマリー確認(手順書・インベントリの取り違え防止ゲート)
    mode = "逐次インタラクティブ" if args.interactive else "一括"
    show_run_summary(proc, steps, selected, mode, args.rollback, mask,
                     start_from=args.start_from, resume_env_src=resume_env_src)
    if not args.yes and not confirm_gate():
        console.print("[red]→ 実行を中止しました[/red]")
        return 130

    # 提案D: 作業者・確認者の記録
    operator, checker = ask_names(args)

    log = RunLogger(log_name, base_dir=args.log_dir, mask=mask)
    log.meta = {
        "file": str(proc.path),
        "title": proc.title,
        "mode": "interactive" if args.interactive else "batch",
        "rollback": args.rollback,
        "operator": operator,
        "checker": checker,
        "selected_steps": sorted(selected),
        "vars": {k: (MASK if k in proc.secrets else v) for k, v in proc.vars.items()},
        "secrets": proc.secrets,
        "share_env": proc.share_env,
    }
    if args.start_from is not None:
        log.meta["start_from"] = args.start_from
        log.meta["resumed_env_from"] = str(resume_env_src) if resume_env_src else None
    env_file = str(log.dir / "shared_env.sh") if proc.share_env else None
    if resume_env_src:
        shutil.copy(resume_env_src, env_file)
    console.print()
    console.print(f"・ 実行開始: [bold #cfd3ea]{escape(proc.title)}[/]"
                  + (" [bold #ff6b60](切り戻し)[/]" if args.rollback else ""))
    console.print(f"  ├ 作業者: {operator}" + (f" / 確認者: {checker}" if checker else " / 確認者: (なし)"),
                  markup=False)
    if proc.share_env:
        console.print(f"  ├ 環境変数共有: 有効 ({env_file})", markup=False)
    if resume_env_src:
        console.print(f"  ├ 環境変数を復元: {resume_env_src}", markup=False)
    console.print(f"  └ ログ保存先: {log.dir}", markup=False)
    log.log(f"手順書「{proc.title}」実行開始 ({proc.path})" + (" [切り戻し実行]" if args.rollback else ""))
    log.log(f"作業者: {operator}  確認者: {checker or '(なし)'}")
    log.log(f"対象ステップ: {sorted(selected)}")
    if args.start_from is not None:
        log.log(f"再開実行(--start-from): ステップ {args.start_from} から"
                + (f"(環境変数を {resume_env_src} から復元)" if resume_env_src else ""))

    status = "completed"
    exit_code = 0
    for step in steps:
        rec = StepRecord(step.number, step.title, step.command, step.criteria)
        if step.number not in selected:
            continue
        show_step_header(step, total, mask)
        log.log(f"--- ステップ {step.number}: {step.title} ---")

        # 提案A: 手動ステップ(RB-CMD なし)。説明を表示して作業者の完了確認を待つ
        if step.runner == "manual":
            log.log("手動ステップ(作業者の完了確認待ち)")
            rec.started_at = datetime.now().isoformat(timespec="seconds")
            action = confirm_manual(step, allow_skip=args.interactive)
            rec.finished_at = datetime.now().isoformat(timespec="seconds")
            if action == "done":
                rec.status = "ok"
                rec.detail = f"作業者({operator})が完了を確認"
                log.add_record(rec)
                log.log(f"手動確認: 完了(作業者: {operator}, 確認時刻: {rec.finished_at})")
                console.print(f"  └ 結果: [bold #5fd9a4]✓ Completed[/] (手動確認 {rec.finished_at})")
                continue
            if action == "skip":
                rec.status = "skipped"
                rec.detail = "操作者がスキップ"
                log.add_record(rec)
                log.log("→ スキップ(操作者判断)")
                console.print("[yellow]→ スキップしました[/yellow]")
                continue
            rec.status = "skipped"
            rec.detail = "操作者が中断(手動ステップ未完了)"
            log.add_record(rec)
            log.log("→ 操作者が中断(手動ステップ未完了)")
            console.print("[red]→ 中断しました[/red]")
            show_onfail_guidance(step, log)
            status = "aborted"
            exit_code = 130
            break

        log.log(f"コマンド: {step.command}")

        if args.interactive:
            action = confirm_interactive(step)
            if action == "skip":
                rec.status = "skipped"
                rec.detail = "操作者がスキップ"
                log.add_record(rec)
                log.log("→ スキップ(操作者判断)")
                console.print("[yellow]→ スキップしました[/yellow]")
                continue
            if action == "quit":
                rec.status = "skipped"
                rec.detail = "操作者が中断"
                log.add_record(rec)
                log.log("→ 操作者が中断")
                console.print("[red]→ 中断しました[/red]")
                status = "aborted"
                exit_code = 130
                break

        started = datetime.now()
        rec.started_at = started.isoformat(timespec="seconds")
        console.print(f"  ├ 開始: {started:%Y-%m-%d %H:%M:%S}")

        def echo(line: str, is_stderr: bool) -> None:
            console.print(f"  │   {mask(line)}", style="red" if is_stderr else None, markup=False)

        result = run_command(step.command, timeout=step.timeout, cwd=step.cwd,
                             on_line=echo, env_file=env_file)
        finished = datetime.now()
        rec.finished_at = finished.isoformat(timespec="seconds")
        rec.rc = result.rc
        rec.duration = round(result.duration, 3)
        rec.stdout = result.stdout
        rec.stderr = result.stderr
        log.log(f"終了コード: {result.rc}  所要時間: {rec.duration}s")

        if result.timed_out:
            rec.status = "error"
            rec.detail = f"タイムアウト({step.timeout}s)により強制終了"
        else:
            try:
                ok = criteria.evaluate(step.criteria, result.rc, result.stdout, result.stderr)
                rec.status = "ok" if ok else "ng"
                if not ok:
                    rec.detail = "正常性基準を満たしませんでした"
            except criteria.CriteriaError as e:
                rec.status = "error"
                rec.detail = str(e)

        if step.runner in ("ansible", "playbook"):
            rec.host_results = parse_ansible_host_results(result.stdout + "\n" + result.stderr)
            rec.host_matrix = step.host_matrix
            if step.host_matrix and rec.host_results:
                console.print("  ├ ホスト別結果:")
                print_host_matrix([("", rec.host_results)], indent="  │   ")
                console.print(f"  │   {_MATRIX_LEGEND}")
                log.log("ホスト別結果: " + host_results_logline(rec.host_results))

        log.add_record(rec)
        finished_disp = f"{finished:%Y-%m-%d %H:%M:%S}"
        if rec.status == "ok":
            log.log("判定: OK")
            console.print(f"  ├ 終了: {finished_disp}")
            console.print(f"  └ 結果: [bold #5fd9a4]✓ Completed[/] (rc={result.rc}, {rec.duration}s)")
        else:
            log.log(f"判定: NG ({rec.detail})")
            console.print(f"  ├ 終了: {finished_disp}")
            print_tree_item("詳細", rec.detail, style="bold #ff6b60")
            # 提案1: 判定の詳細診断(どの条件で落ちたかの内訳)
            if rec.status == "ng":
                breakdown = criteria.diagnose(step.criteria, result.rc, result.stdout, result.stderr)
                if len(breakdown) >= 2:  # 条件が1つだけなら基準式そのものと同じ情報なので出さない
                    rec.criteria_breakdown = [{"expr": t, "ok": ok} for t, ok in breakdown]
                    console.print("  ├ 判定内訳:")
                    log.log("判定内訳:")
                    for text, ok in breakdown:
                        mark = "[bold #5fd9a4]OK[/]" if ok else "[bold #ff6b60]NG[/]"
                        console.print(f"  │   \\[{mark}] {escape(mask(text))}")
                        log.log(f"  [{'OK' if ok else 'NG'}] {text}")
            console.print(f"  └ 結果: [bold #ff6b60]✘ Failed[/] (rc={result.rc}, {rec.duration}s)")
            console.print("[bold red]失敗したため、実行を中断します。[/]")
            show_onfail_guidance(step, log)  # 提案B: 失敗時ガイダンス
            status = "aborted"
            exit_code = 1
            break

    # 集約マトリックス(host_matrix 有効なステップが2つ以上あるとき)
    matrix_records = [r for r in log.records if r.host_matrix and r.host_results]
    if len(matrix_records) >= 2:
        console.print()
        console.print("・ 最終ホスト別結果マトリックス")
        print_host_matrix(
            [(f"{r.number}: {r.title}", r.host_results) for r in matrix_records],
            label_header="ステップ",
            indent="  "
        )
        console.print(f"  └ 記号解説: {_MATRIX_LEGEND}")

    show_hint = status == "aborted" and not args.rollback and bool(proc.rollback_steps)
    if show_hint:
        log.log(f"切り戻し案内: runbook run --rollback {proc.path}")
    log_dir = log.finalize(status)
    console.print()
    n_skipped = sum(1 for r in log.records if r.status == "skipped")
    if status == "completed":
        if n_skipped:
            lbl = f"完了 (スキップ {n_skipped} ステップあり)"
            style = "bold #f2b94d"
        else:
            lbl = "全ステップ正常終了"
            style = "bold #5fd9a4"
    else:
        lbl = "実行中断"
        style = "bold #ff6b60"
    console.print(f"・ 実行結果: [{style}]{lbl}[/]")
    console.print(f"  └ ログ保存先: {log_dir}")
    if show_hint:
        # 提案C: 中断時に切り戻しの実行方法を案内する(自動では実行しない)
        show_rollback_hint(proc)
    return exit_code


def _step_table(title: str, steps, mask=lambda t: t) -> Table:
    table = Table(title=title)
    table.add_column("No.", justify="right")
    table.add_column("ステップ")
    table.add_column("コマンド", overflow="fold")
    table.add_column("正常性基準", overflow="fold")
    for s in steps:
        if s.runner == "manual":
            table.add_row(str(s.number), s.title, "(手動ステップ)", "作業者の完了確認")
            continue
        cmd = mask(s.command)
        cmd = cmd if len(cmd) <= 60 else cmd[:57] + "..."
        table.add_row(str(s.number), s.title, cmd, mask(s.criteria))
    return table


def cmd_list(args: argparse.Namespace) -> int:
    proc = parser.parse_file(args.file, parse_vars(args.var))
    mask = make_mask(proc)
    console.print(_step_table(f"{proc.title} ({proc.path})", proc.steps, mask))
    if proc.rollback_steps:
        console.print(_step_table("切り戻しセクション (runbook run --rollback で実行)",
                                  proc.rollback_steps, mask))
    return 0


def _playbook_paths(line: str) -> list[str]:
    """playbook 行からファイルパスらしきトークン(*.yml / *.yaml)を取り出す。

    引数列の完全解釈はしない(ansible-playbook のオプション仕様に依存するため)。
    -e @vars.yml の @ は外して扱う。存在チェック用のヒューリスティック。
    """
    paths = []
    for tok in parser._tokenize(line):
        tok = tok.lstrip("@")
        if tok.endswith((".yml", ".yaml")):
            paths.append(tok)
    return paths


def _check_paths(label: str, steps) -> list[str]:
    """ステップが参照するパス(インベントリ / playbook / cwd)の存在を確認し、
    見つからないものを警告文のリストで返す。

    実行時と check 時でカレントディレクトリが違う場合は誤検知になり得るため、
    エラーではなく警告とする(check は実行するディレクトリで行うこと)。
    """
    warns = []
    for s in steps:
        ctx = f"{label}ステップ{s.number}「{s.title}」"
        for inv in s.inventories:
            # "web01," のようなカンマ入りはインラインホストリストなのでパスではない
            if "," in inv:
                continue
            if not Path(inv).exists():
                warns.append(f"{ctx}: インベントリ {inv} が見つかりません")
        if s.runner == "playbook":
            for line in s.remote_command.splitlines():
                for p in _playbook_paths(line):
                    if not Path(p).exists():
                        warns.append(f"{ctx}: プレイブック {p} が見つかりません")
        if s.cwd and not Path(s.cwd).is_dir():
            warns.append(f"{ctx}: cwd {s.cwd} が存在しません")
    return list(dict.fromkeys(warns))  # 同一ファイルを複数行が参照する場合の重複を除去


def cmd_check(args: argparse.Namespace) -> int:
    errors: list[str] = []
    try:
        proc = parser.parse_file(args.file, parse_vars(args.var))
    except parser.ParseError as e:
        console.print(f"[bold red]NG[/bold red] {e}")
        return 1
    sections = [("", proc.steps), ("切り戻し", proc.rollback_steps)]
    for label, steps in sections:
        for s in steps:
            if s.runner == "manual":
                continue  # 手動ステップに基準式はない
            try:
                criteria.validate(s.criteria)
            except criteria.CriteriaError as e:
                errors.append(f"{label}ステップ{s.number}「{s.title}」(L{s.line}): {e}")
    if errors:
        for e in errors:
            console.print(f"[bold red]NG[/bold red] {e}")
        return 1
    warnings_: list[str] = []
    for label, steps in sections:
        for s in steps:
            if s.heading_number is not None and s.heading_number != s.number:
                warnings_.append(
                    f"{label}ステップ{s.number}「{s.title}」: "
                    f"見出しの番号 {s.heading_number} が実際の順序 {s.number} と不一致です"
                    f"(runbook renumber で振り直せます)")
        warnings_ += _check_paths(label, steps)
    for w in warnings_:
        console.print(f"[bold yellow]警告[/bold yellow] {escape(w)}")
    summary = f"{len(proc.steps)} ステップ"
    if proc.rollback_steps:
        summary += f" + 切り戻し {len(proc.rollback_steps)} ステップ"
    note = f"(警告 {len(warnings_)} 件)" if warnings_ else ""
    console.print(f"[bold green]OK[/bold green] {proc.path}: {summary}、書式・基準式に問題ありません{note}")

    if args.preview:
        mask = make_mask(proc)
        for label, steps in sections:
            if not steps:
                continue
            console.print()
            console.print(f"・ 展開後コマンド プレビュー{'(切り戻しセクション)' if label else ''}")
            for s in steps:
                console.print(f"・ ステップ {s.number}: {s.title}", markup=False)
                if s.runner == "manual":
                    console.print("    (手動ステップ: 作業者の完了確認のみ)")
                    continue
                for line in mask(s.command).splitlines():
                    console.print(f"    $ {escape(line)}", style="cyan")
                console.print(f"    基準: {escape(mask(s.criteria))}", style="#8ea7ff")
    return 0


def cmd_renumber(args: argparse.Namespace) -> int:
    """## 見出しに実行順の連番(1. 2. ...)を付与/振り直す。

    一般的な Markdown プレビューでステップが番号付きで表示されるようにする。
    フェンス内の ## は対象外。既存の先頭番号は正しい順序に置き換わる。
    """
    path = Path(args.file)
    parser.parse_file(path, parse_vars(args.var))  # まず書式検証(不正なら書き換えない)
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    in_fence = False
    n = 0
    total = 0
    changed = 0
    for line in lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
        if not in_fence and parser._ROLLBACK_PATTERN.match(line):
            n = 0  # 切り戻しセクションは独立して 1 から採番
            out.append(line)
            continue
        m = None if in_fence else re.match(r"^##\s+(.+?)\s*$", line)
        if m and not m.group(1).startswith("#"):
            n += 1
            total += 1
            _, title = parser.split_heading_number(m.group(1))
            new_line = f"## {n}. {title}"
            if new_line != line:
                changed += 1
            out.append(new_line)
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    console.print(f"[bold green]OK[/bold green] {path}: {total} ステップ中 {changed} 見出しを更新しました")
    return 0


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="runbook", description="Markdown手順書 自動実行フレームワーク")
    ap.add_argument("--version", action="version", version=f"runbook {__version__}")
    sub = ap.add_subparsers(dest="subcommand", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("file", help="手順書 Markdown ファイル")
        p.add_argument("--var", action="append", default=[], metavar="KEY=VALUE",
                       help="変数の指定/上書き(複数可)")

    p_run = sub.add_parser("run", help="手順書を実行する")
    add_common(p_run)
    p_run.add_argument("-i", "--interactive", action="store_true",
                       help="各ステップ実行前に確認する(逐次インタラクティブ実行)")
    p_run.add_argument("--only", metavar="SPEC", help="実行するステップ番号(例: 1,3-5)")
    p_run.add_argument("--from", dest="from_", type=int, metavar="N", help="開始ステップ番号")
    p_run.add_argument("--to", type=int, metavar="N", help="終了ステップ番号")
    p_run.add_argument("--start-from", dest="start_from", type=int, metavar="N",
                       help="ステップ N から最後まで再開実行する。share_env: true の手順書では"
                            "直近実行の環境変数(shared_env.sh)を復元する(見つからなければエラー)")
    p_run.add_argument("--rollback", action="store_true",
                       help="切り戻しセクション(# RB-ROLLBACK 以降)のステップを実行する")
    p_run.add_argument("-y", "--yes", action="store_true",
                       help="実行前サマリーの確認をスキップする(非対話実行用)")
    p_run.add_argument("--operator", metavar="NAME",
                       help="作業者名(省略時は実行開始時に入力を求める)")
    p_run.add_argument("--checker", metavar="NAME",
                       help="確認者名(任意。--operator 指定時は省略可)")
    p_run.add_argument("--log-dir", default="logs", help="ログ保存先ディレクトリ(既定: ./logs)")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="ステップ一覧を表示する")
    add_common(p_list)
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser(
        "check",
        help="手順書の書式・基準式・参照パス(インベントリ/playbook/cwd)を検証する(実行しない)")
    add_common(p_check)
    p_check.add_argument("--preview", action="store_true",
                         help="変数展開・ansibleコマンド組み立て後の実行コマンドを全文表示する")
    p_check.set_defaults(func=cmd_check)

    p_renum = sub.add_parser("renumber",
                             help="## 見出しに実行順の連番(1. 2. ...)を付与/振り直す")
    add_common(p_renum)
    p_renum.set_defaults(func=cmd_renumber)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    try:
        return args.func(args)
    except (parser.ParseError, ValueError) as e:
        console.print(f"[bold red]エラー:[/bold red] {e}")
        return 2
    except KeyboardInterrupt:
        console.print("\n[red]中断されました[/red]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
