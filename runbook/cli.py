"""runbook CLI

    runbook run  手順書.md              一括実行(失敗で即中断)
    runbook run  -i 手順書.md           逐次インタラクティブ実行
    runbook run  --only 3 手順書.md     ステップ指定実行(例: --only 1,3-5)
    runbook run  --from 2 --to 4 ...    範囲指定
    runbook run  --start-from 5 ...     ステップ5から再開(直近実行の env_overlay.sh から環境変数も復元)
    runbook run  --yes --operator 名前  実行前確認・作業者入力の省略(非対話実行用)
    runbook list 手順書.md              ステップ一覧表示
    runbook check 手順書.md             書式・基準式・変数・参照パスの検証のみ
    runbook check --preview 手順書.md   検証 + 展開後の実行コマンドを全文表示

実行開始前にはサマリー(タイトル・対象ステップ・変数・インベントリ)を表示して
確認を挟み(--yes でスキップ)、作業者名(必須)・確認者名(任意)を記録する。

ステップ間の環境変数引き継ぎ(export/unset の差分オーバーレイ)は設定なしで
常時有効。中断シグナル(SIGINT/SIGTERM/SIGHUP)は実行中の子プロセスへ転送し、
証跡(run.log/result.json)を確定してから終了する。切り戻し実行機能は v0.5.0 で
削除された(切り戻しは別ファイルの手順書として運用する。04 章 §3.6)。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import signal
import sys
from datetime import datetime
from pathlib import Path

from rich.cells import cell_len
from rich.markup import escape

from . import __version__, criteria, parser
from .artifacts import RunArtifacts, atomic_write_text
from .envstate import EnvManager
from .executor import StepRecord, parse_ansible_host_results, run_command
from .render import (
    MASK,
    _MATRIX_LEGEND,
    console,
    host_results_logline,
    output_line_style,
    print_host_matrix,
    print_tree_item,
    result_table,
    show_step_header,
    step_table,
)


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


def show_onfail_guidance(step, art) -> None:
    """RB-ONFAIL(失敗時ガイダンス)を表示・記録する(提案B)"""
    if not step.onfail:
        return
    console.print()
    console.print("[bold #f2b94d]▶ 失敗時ガイダンス (RB-ONFAIL):[/]")
    for line in step.onfail.splitlines():
        console.print(f"  {escape(line)}", style="#f2b94d")
    art.log("失敗時ガイダンス(RB-ONFAIL):")
    art.log(step.onfail)


def show_run_summary(proc, steps, selected: set[int], mode: str, mask=lambda t: t,
                     start_from: int | None = None, resume_env_src=None) -> None:
    """実行前サマリー(提案E)。手順書・対象・変数・インベントリの取り違えに気付くためのゲート"""
    inventories = sorted({inv for s in steps if s.number in selected for inv in s.inventories})
    n_manual = sum(1 for s in steps if s.number in selected and s.runner == "manual")

    has_vars = bool(proc.vars)
    has_secrets = bool(proc.secrets)
    has_inventories = bool(inventories)
    has_start_from = start_from is not None
    # 最後に表示するブロックだけ "└" にする(それ以外は "├")。優先順位は表示順の逆。
    last = ("start_from" if has_start_from else
            "inventories" if has_inventories else
            "secrets" if has_secrets else
            "vars" if has_vars else
            "target")

    def conn(name: str) -> str:
        return "└" if name == last else "├"

    def sub(name: str) -> str:
        # そのブロックが最後(└)なら、続く行は "│" ではなく空白で揃える
        return "  │   " if name != last else "      "

    console.print()
    console.print("・ 実行前確認")
    console.print(f"  ├ 手順書: [bold #cfd3ea]{escape(proc.title)}[/] ({proc.path})")
    console.print(f"  ├ モード: {mode}", markup=False)

    label = f"  {conn('target')} 実行対象: {len(selected)}/{len(steps)} ステップ"
    if n_manual:
        label += f"(うち手動 {n_manual})"
    console.print(label, markup=False)
    for s in steps:
        if s.number in selected:
            tag = "(手動)" if s.runner == "manual" else ""
            console.print(f"{sub('target')}{s.number}. {s.title}{tag}", markup=False)

    if has_vars:
        console.print(f"  {conn('vars')} 変数:")
        for k, v in proc.vars.items():
            disp = MASK if k in proc.secrets else mask(v)
            console.print(f"{sub('vars')}{k} = {disp}", markup=False)

    if has_secrets:
        console.print(f"  {conn('secrets')} 秘匿変数(値は表示・ログでマスク): {', '.join(proc.secrets)}",
                      markup=False)
        console.print(f"{sub('secrets')}[bold #f2b94d]注意: export した値は env_overlay.sh に平文で残ります"
                      "(保管・削除ルールに注意)[/]")

    if has_inventories:
        console.print(f"  {conn('inventories')} 使用インベントリ:")
        for inv in inventories:
            console.print(f"{sub('inventories')}{inv}", markup=False)

    if has_start_from:
        console.print(f"  {conn('start_from')} 再開実行(--start-from): ステップ {start_from} から", markup=False)
        if resume_env_src:
            console.print(f"{sub('start_from')}環境変数の復元元: {resume_env_src}", markup=False)


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


def _find_latest_env_overlay(base_dir: str, log_name: str) -> Path | None:
    """--start-from の環境復元用に、直近の実行ログディレクトリの env_overlay.sh を探す。

    ディレクトリ名は <log_name>_YYYYMMDD_HHMMSS(同一秒の連続実行では _2 等の
    連番付き)形式なので名前の降順 = 新しい順。log_name を厳密に照合する
    (例えば "proc" で検索したときに "proc2_..." のような無関係なディレクトリを
    拾わないようにするため)。
    """
    base = Path(base_dir)
    if not base.is_dir():
        return None
    pat = re.compile(re.escape(log_name) + r"_\d{8}_\d{6}(_\d+)?$")
    for d in sorted((d for d in base.iterdir() if d.is_dir() and pat.fullmatch(d.name)),
                    reverse=True):
        f = d / "env_overlay.sh"
        if f.is_file():
            return f
    return None


class SignalInterrupt(Exception):
    """SIGTERM / SIGHUP 受信を表す例外(SIGINT は既定の KeyboardInterrupt のまま扱う)"""

    def __init__(self, signum: int):
        self.signum = signum
        super().__init__(f"signal {signum} received")


def _raise_signal_interrupt(signum: int, frame) -> None:
    raise SignalInterrupt(signum)


def cmd_run(args: argparse.Namespace) -> int:
    proc = parser.parse_file(args.file, parse_vars(args.var))
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

    log_name = proc.path.stem

    # --start-from: 環境変数引き継ぎは設定キーなしで常時有効なので、直近実行の
    # env_overlay.sh を無条件で復元元として検索する。途中再開するステップが
    # 前段の export に依存している可能性があるため、復元元が見つからなければ
    # 実行前にエラーにする(fail-loud)。
    resume_src: Path | None = None
    if args.start_from is not None:
        resume_src = _find_latest_env_overlay(args.log_dir, log_name)
        if resume_src is None:
            raise ValueError(
                f"--start-from: 環境変数の復元元(過去実行の env_overlay.sh)が "
                f"{args.log_dir} に見つかりません。前段の環境変数なしで実行してよい場合は "
                f"--from {args.start_from} を使ってください")

    envman = EnvManager()
    mask = make_mask(proc)

    # 提案E: 実行前サマリー確認(手順書・インベントリの取り違え防止ゲート)
    mode = "逐次インタラクティブ" if args.interactive else "一括"
    show_run_summary(proc, steps, selected, mode, mask,
                     start_from=args.start_from, resume_env_src=resume_src)
    if not args.yes and not confirm_gate():
        console.print("[red]→ 実行を中止しました[/red]")
        return 130

    # 提案D: 作業者・確認者の記録
    operator, checker = ask_names(args)

    art = RunArtifacts(log_name, base_dir=args.log_dir, mask=mask)
    art.meta = {
        "file": str(proc.path),
        "title": proc.title,
        "mode": "interactive" if args.interactive else "batch",
        "operator": operator,
        "checker": checker,
        "selected_steps": sorted(selected),
        "vars": {k: (MASK if k in proc.secrets else v) for k, v in proc.vars.items()},
        "secrets": proc.secrets,
    }
    if args.start_from is not None:
        art.meta["start_from"] = args.start_from
        art.meta["resumed_env_from"] = str(resume_src)

    if resume_src:
        shutil.copy(resume_src, art.dir / "env_overlay.sh")
        envman.load_overlay_script((art.dir / "env_overlay.sh").read_text(encoding="utf-8"))
    else:
        art.write_env_overlay(envman.overlay_script())
    # D5: 最初のステップが終わる前でも result.json が整形式で読めるよう、
    # 実行開始時点で status="running" の初期状態を書いておく
    art.save_result("running")

    console.print()
    console.print(f"・ 実行開始: [bold #cfd3ea]{escape(proc.title)}[/]")
    console.print(f"  ├ 作業者: {operator}" + (f" / 確認者: {checker}" if checker else " / 確認者: (なし)"),
                  markup=False)
    if resume_src:
        console.print(f"  ├ 環境変数を復元: {resume_src}", markup=False)
    console.print(f"  └ ログ保存先: {art.dir}", markup=False)
    art.log(f"手順書「{proc.title}」実行開始 ({proc.path})")
    art.log(f"作業者: {operator}  確認者: {checker or '(なし)'}")
    art.log(f"対象ステップ: {sorted(selected)}")
    if args.start_from is not None:
        art.log(f"再開実行(--start-from): ステップ {args.start_from} から"
                f"(環境変数を {resume_src} から復元)")

    status = "completed"
    exit_code = 0
    aborted_at: int | None = None  # 中断が起きたステップ番号(案R1 の一覧で「← 中断」を出す)
    legend_shown = False  # 案R3: ホスト別結果の凡例は最初の1回だけ出す
    try:
        for step in steps:
            rec = StepRecord(step.number, step.title, step.command, step.criteria)
            if step.number not in selected:
                continue
            aborted_at = step.number  # 中断された場合はこのステップ位置(正常終了時は最後にクリアする)
            show_step_header(step, total, mask)
            art.log(f"--- ステップ {step.number}: {step.title} ---")

            # 提案A: 手動ステップ(RB-CMD なし)。説明を表示して作業者の完了確認を待つ
            if step.runner == "manual":
                art.log("手動ステップ(作業者の完了確認待ち)")
                rec.started_at = datetime.now().isoformat(timespec="seconds")
                action = confirm_manual(step, allow_skip=args.interactive)
                rec.finished_at = datetime.now().isoformat(timespec="seconds")
                if action == "done":
                    rec.status = "ok"
                    rec.detail = f"作業者({operator})が完了を確認"
                    art.add_record(rec)
                    art.log(f"手動確認: 完了(作業者: {operator}, 確認時刻: {rec.finished_at})")
                    console.print(f"  └ 結果: [bold #5fd9a4]✓ Completed[/] (手動確認 {rec.finished_at})")
                    continue
                if action == "skip":
                    rec.status = "skipped"
                    rec.detail = "操作者がスキップ"
                    art.add_record(rec)
                    art.log("→ スキップ(操作者判断)")
                    console.print("[yellow]→ スキップしました[/yellow]")
                    continue
                rec.status = "skipped"
                rec.detail = "操作者が中断(手動ステップ未完了)"
                art.add_record(rec)
                art.log("→ 操作者が中断(手動ステップ未完了)")
                console.print("[red]→ 中断しました[/red]")
                show_onfail_guidance(step, art)
                status = "aborted"
                exit_code = 130
                break

            art.log(f"コマンド: {step.command}")

            if args.interactive:
                action = confirm_interactive(step)
                if action == "skip":
                    rec.status = "skipped"
                    rec.detail = "操作者がスキップ"
                    art.add_record(rec)
                    art.log("→ スキップ(操作者判断)")
                    console.print("[yellow]→ スキップしました[/yellow]")
                    continue
                if action == "quit":
                    rec.status = "skipped"
                    rec.detail = "操作者が中断"
                    art.add_record(rec)
                    art.log("→ 操作者が中断")
                    console.print("[red]→ 中断しました[/red]")
                    status = "aborted"
                    exit_code = 130
                    break

            started = datetime.now()
            rec.started_at = started.isoformat(timespec="seconds")
            console.print(f"  ├ 開始: {started:%Y-%m-%d %H:%M:%S}")

            # D5: 逐次書き込み。シグナル中断時にも必ず close する。
            files = art.open_step_files(step.number)
            try:
                def echo(line: str, is_stderr: bool) -> None:
                    text = mask(line.rstrip(chr(10)))
                    # 案R5: stderr は赤。stdout は構造行(ホスト区切り・プレイ見出し・
                    # 失敗行)だけ色を付け、本文は既定のまま流す。
                    style = "red" if is_stderr else output_line_style(text)
                    console.print(f"  │   {text}", style=style, markup=False)
                    files.write(mask(line), is_stderr)

                result = run_command(step.command, timeout=step.timeout, cwd=step.cwd,
                                     on_line=echo, env=envman.child_env(), capture_env=True)
            finally:
                files.close()

            # D3: ステップ終了直後の export 済み変数一式でオーバーレイを再生成
            if result.env_snapshot is not None:
                envman.update_from_snapshot(result.env_snapshot)
                art.write_env_overlay(envman.overlay_script())

            finished = datetime.now()
            rec.finished_at = finished.isoformat(timespec="seconds")
            rec.rc = result.rc
            rec.duration = round(result.duration, 3)
            rec.stdout = result.stdout
            rec.stderr = result.stderr
            art.log(f"終了コード: {result.rc}  所要時間: {rec.duration}s")
            # 案R4: 終了時刻は結果行にまとめる(独立行をやめて1行削減)。
            # 日付は「実行開始」ヘッダに出ているので時刻のみ。日を跨いだ場合だけ日付を併記する。
            finished_disp = (f"{finished:%H:%M:%S}" if finished.date() == started.date()
                             else f"{finished:%Y-%m-%d %H:%M:%S}")
            result_note = f"rc={result.rc}, {rec.duration}s, 終了 {finished_disp}"

            # D4: 中断シグナルにより子プロセスが終了した場合(操作者の意図的中断のため
            # RB-ONFAIL は表示せず、判定・内訳もスキップする)
            if result.interrupted is not None:
                rec.status = "error"
                rec.detail = f"シグナル ({signal.Signals(result.interrupted).name}) により中断"
                art.log(f"判定: エラー ({rec.detail})")
                print_tree_item("詳細", rec.detail, style="bold #ff6b60")
                console.print(f"  └ 結果: [bold #ff6b60]✘ Failed[/] ({result_note})")
                console.print("[bold red]中断シグナルを受信したため、実行を中断します。[/]")
                art.add_record(rec)
                status = "aborted"
                exit_code = 128 + result.interrupted
                break

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
                    # 案R2: 1ステップ分は1次元なので表を組まず1行で出す
                    # (run.log と同じ表記になり、5行 → 1行に収まる)
                    line = host_results_logline(rec.host_results)
                    if len("  ├ ホスト別結果: ") + len(line) <= console.width:
                        console.print(f"  ├ ホスト別結果: {escape(line)}")
                    else:  # ホスト数が多く1行に収まらない場合のみ表にフォールバック
                        console.print("  ├ ホスト別結果:")
                        print_host_matrix([("", rec.host_results)], indent="  │   ")
                    # 案R3: 凡例は最初のステップだけ(最終マトリックスでも再掲される)
                    if not legend_shown:
                        console.print(f"  │   {_MATRIX_LEGEND}")
                        legend_shown = True
                    art.log("ホスト別結果: " + line)

            art.add_record(rec)
            if rec.status == "ok":
                art.log("判定: OK")
                console.print(f"  └ 結果: [bold #5fd9a4]✓ Completed[/] ({result_note})")
            else:
                art.log(f"判定: NG ({rec.detail})")
                print_tree_item("詳細", rec.detail, style="bold #ff6b60")
                # 提案1: 判定の詳細診断(どの条件で落ちたかの内訳)
                if rec.status == "ng":
                    breakdown = criteria.diagnose(step.criteria, result.rc, result.stdout, result.stderr)
                    if len(breakdown) >= 2:  # 条件が1つだけなら基準式そのものと同じ情報なので出さない
                        # 案R6: 各条件に「実際の出力はどうだったか」を添える
                        evid = {t: mask(criteria.term_evidence(
                            t, result.rc, result.stdout, result.stderr)) for t, _ in breakdown}
                        rec.criteria_breakdown = [
                            {"expr": t, "ok": ok, "evidence": evid[t]} for t, ok in breakdown]
                        # 全角文字を含む条件式でも → の位置を揃えるため表示幅で計算する
                        width = max(cell_len(mask(t)) for t, _ in breakdown)
                        console.print("  ├ 判定内訳:")
                        art.log("判定内訳:")
                        for text, ok in breakdown:
                            mark = "[bold #5fd9a4]OK[/]" if ok else "[bold #ff6b60]NG[/]"
                            pad = " " * (width - cell_len(mask(text)))
                            note = f"{pad}  [dim]→ {escape(evid[text])}[/]" if evid[text] else ""
                            console.print(f"  │   \\[{mark}] {escape(mask(text))}{note}")
                            art.log(f"  [{'OK' if ok else 'NG'}] {text}"
                                    + (f"  → {evid[text]}" if evid[text] else ""))
                console.print(f"  └ 結果: [bold #ff6b60]✘ Failed[/] ({result_note})")
                console.print("[bold red]失敗したため、実行を中断します。[/]")
                show_onfail_guidance(step, art)  # 提案B: 失敗時ガイダンス
                status = "aborted"
                exit_code = 1
                break
        else:
            aborted_at = None  # break せず全ステップ走破した(中断位置なし)
    except KeyboardInterrupt:
        art.log("中断されました(SIGINT)")
        console.print("\n[red]中断されました[/red]")
        status = "aborted"
        exit_code = 130
    except SignalInterrupt as e:
        art.log(f"中断されました(シグナル {signal.Signals(e.signum).name})")
        console.print("\n[red]中断されました[/red]")
        status = "aborted"
        exit_code = 128 + e.signum

    # 集約マトリックス(host_matrix 有効なステップが2つ以上あるとき)
    matrix_records = [r for r in art.records if r.host_matrix and r.host_results]
    if len(matrix_records) >= 2:
        console.print()
        console.print("・ 最終ホスト別結果マトリックス")
        print_host_matrix(
            [(f"{r.number}: {r.title}", r.host_results) for r in matrix_records],
            label_header="ステップ",
            indent="  "
        )
        console.print(f"  └ 記号解説: {_MATRIX_LEGEND}")

    log_dir = art.finalize(status)
    console.print()
    n_skipped = sum(1 for r in art.records if r.status == "skipped")
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
    # 案R1: 中断時は「どのステップで落ちたか」を1行目で示す(遡って探させない)
    failed = next((r for r in art.records if r.status in ("ng", "error")), None)
    if failed is not None:
        lbl += f" — ステップ {failed.number}「{failed.title}」で{'失敗' if failed.status == 'ng' else 'エラー'}"
    console.print(f"・ 実行結果: [{style}]{escape(lbl)}[/]")
    # 案R1: ステップ別リザルト一覧(未実行・対象外も明示する)
    console.print(result_table(steps, art.records, selected, aborted_at))
    console.print(f"  └ ログ保存先: {log_dir}", markup=False)
    return exit_code


def cmd_list(args: argparse.Namespace) -> int:
    proc = parser.parse_file(args.file, parse_vars(args.var))
    mask = make_mask(proc)
    console.print(step_table(f"{proc.title} ({proc.path})", proc.steps, mask))
    # 一覧表はコマンドを持たないので、全文を見たいときは詳細ブロックを出す
    # (check --preview の第2部と同じ表示部品を使う)
    if args.detail:
        for s in proc.steps:
            show_step_header(s, len(proc.steps), mask, preview=True)
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


def _check_paths(steps) -> list[str]:
    """ステップが参照するパス(インベントリ / playbook / cwd)の存在を確認し、
    見つからないものを警告文のリストで返す。

    実行時と check 時でカレントディレクトリが違う場合は誤検知になり得るため、
    エラーではなく警告とする(check は実行するディレクトリで行うこと)。
    """
    warns = []
    for s in steps:
        ctx = f"ステップ{s.number}「{s.title}」"
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


def collect_check_diagnostics(proc) -> tuple[list[dict], list[dict]]:
    """検証結果を (エラー, 警告) の構造化リストで返す。

    各要素は {"line": 手順書内の行番号(1始まり。不明なら 0),
              "step": ステップ番号(なければ None), "message": 本文}。
    テキスト表示(cmd_check)と --json 出力の両方がこれを使う。
    """
    errors: list[dict] = []
    for s in proc.steps:
        if s.runner == "manual":
            continue  # 手動ステップに基準式はない
        try:
            criteria.validate(s.criteria)
        except criteria.CriteriaError as e:
            errors.append({"line": s.line, "step": s.number,
                           "message": f"ステップ{s.number}「{s.title}」(L{s.line}): {e}"})
    if errors:
        return errors, []

    warnings_: list[dict] = []

    def warn(message: str, step=None) -> None:
        warnings_.append({"line": step.line if step else 0,
                          "step": step.number if step else None,
                          "message": message})

    for s in proc.steps:
        if s.heading_number is not None and s.heading_number != s.number:
            warn(f"ステップ{s.number}「{s.title}」: "
                 f"見出しの番号 {s.heading_number} が実際の順序 {s.number} と不一致です"
                 f"(runbook renumber で振り直せます)", s)
    # 共通設定(```runbook フェンス)の未知キー。互換のため解析は通すが、
    # 書いた本人は効いていると思い込むので警告する。
    for key in proc.unknown_config_keys:
        note = ("ステップ単位の RB-LOCALDEF に書いてください"
                "(共通設定では効かず、既定はタイムアウトなし=無制限に待ちます)"
                if key == "timeout" else "無視されます")
        warn(f"共通設定(```runbook)のキー「{key}」は解釈されません。{note}")

    # 案R9: 見出しはあるが本文が空の自由記述セクション。特に RB-ONFAIL は
    # 失敗して中断した瞬間にしか表示されないため、空だと気付く機会が事実上ない。
    for s in proc.steps:
        for name in s.empty_sections:
            warn(f"ステップ{s.number}「{s.title}」: {name} の内容が空です"
                 f"(コードフェンス ``` の中に書かれている可能性があります。"
                 f"{name} はフェンスなしで記述してください)", s)

    by_number = {s.number: s for s in proc.steps}
    for text in _check_paths(proc.steps):
        m = re.match(r"ステップ(\d+)", text)
        warn(text, by_number.get(int(m.group(1))) if m else None)
    return errors, warnings_


def cmd_check_json(args: argparse.Namespace) -> int:
    """機械可読出力(VSCode 拡張などのエディタ統合用)。stdout に JSON 1 件のみ。"""
    def emit(payload: dict, code: int) -> int:
        print(json.dumps(payload, ensure_ascii=False))
        return code

    path = str(Path(args.file))
    try:
        proc = parser.parse_file(args.file, parse_vars(args.var))
    except (parser.ParseError, ValueError, OSError) as e:
        return emit({"ok": False, "path": path, "steps": 0,
                     "diagnostics": [{"severity": "error", "line": 0, "step": None,
                                      "message": str(e)}]}, 1)
    errors, warnings_ = collect_check_diagnostics(proc)
    diagnostics = ([dict(d, severity="error") for d in errors]
                   + [dict(d, severity="warning") for d in warnings_])
    return emit({"ok": not errors, "path": path, "steps": len(proc.steps),
                 "diagnostics": diagnostics}, 1 if errors else 0)


def cmd_check(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        return cmd_check_json(args)
    errors: list[str] = []
    try:
        proc = parser.parse_file(args.file, parse_vars(args.var))
    except parser.ParseError as e:
        console.print(f"[bold red]NG[/bold red] {e}")
        return 1
    errors_, warnings_ = collect_check_diagnostics(proc)
    errors = [d["message"] for d in errors_]
    if errors:
        for e in errors:
            console.print(f"[bold red]NG[/bold red] {e}")
        return 1
    for w in warnings_:
        console.print(f"[bold yellow]警告[/bold yellow] {escape(w['message'])}")
    summary = f"{len(proc.steps)} ステップ"
    note = f"(警告 {len(warnings_)} 件)" if warnings_ else ""
    console.print(f"[bold green]OK[/bold green] {proc.path}: {summary}、書式・基準式に問題ありません{note}")

    if args.preview:
        mask = make_mask(proc)
        console.print()
        console.print(step_table(f"{proc.title} ({proc.path})", proc.steps, mask))
        for s in proc.steps:
            show_step_header(s, len(proc.steps), mask, preview=True)
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
    # D7.3: 手順書ファイルと同じディレクトリ内の一時ファイルへ書いてからアトミックに rename
    atomic_write_text(path, "\n".join(out) + "\n")
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
                       help="ステップ N から最後まで再開実行する。直近実行の環境変数"
                            "(env_overlay.sh)を復元する(見つからなければエラー)")
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
    p_list.add_argument("--detail", action="store_true",
                        help="一覧に加えて、変数展開後の実行コマンドを全文表示する")
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser(
        "check",
        help="手順書の書式・基準式・参照パス(インベントリ/playbook/cwd)を検証する(実行しない)")
    add_common(p_check)
    p_check.add_argument("--json", action="store_true",
                         help="検証結果を行番号付きの JSON で出力する(エディタ統合用)")
    p_check.add_argument("--preview", action="store_true",
                         help="変数展開・ansibleコマンド組み立て後の実行コマンドを全文表示する")
    p_check.set_defaults(func=cmd_check)

    p_renum = sub.add_parser("renumber",
                             help="## 見出しに実行順の連番(1. 2. ...)を付与/振り直す")
    add_common(p_renum)
    p_renum.set_defaults(func=cmd_renumber)
    return ap


def main(argv: list[str] | None = None) -> int:
    # D4: SIGTERM/SIGHUP は例外化して中断処理(証跡の確定)に回す。
    # SIGINT は Python 既定のハンドラのまま(KeyboardInterrupt として届く)。
    signal.signal(signal.SIGTERM, _raise_signal_interrupt)
    signal.signal(signal.SIGHUP, _raise_signal_interrupt)
    args = build_argparser().parse_args(argv)
    try:
        return args.func(args)
    except (parser.ParseError, ValueError) as e:
        console.print(f"[bold red]エラー:[/bold red] {e}")
        return 2
    except KeyboardInterrupt:
        console.print("\n[red]中断されました[/red]")
        return 130
    except SignalInterrupt as e:
        console.print("\n[red]中断されました[/red]")
        return 128 + e.signum


if __name__ == "__main__":
    sys.exit(main())
