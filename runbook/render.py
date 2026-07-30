"""表示部品(console 出力の共通コンポーネント。D2)。

cli.py の run / list / check --preview から共通で使う表示ロジックをここに集約する。
list の一覧表(step_table)と run のステップ詳細(show_step_header)は、
check --preview の 2 部構成表示でもそのまま再利用する。
"""

from __future__ import annotations

import re

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

# soft_wrap: 長い行に強制改行を入れない(tee 等でテキスト保存しても行が崩れない)
console = Console(highlight=False, soft_wrap=True)

MASK = "*****"


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


def show_step_header(step, total: int, mask=lambda t: t, preview: bool = False) -> None:
    """ステップヘッダ・コマンド・正常性基準の表示。

    run の実行時ステップ表示と check --preview の第2部(D2)で共用する。
    preview=True の手動ステップは、まだ実行していないことを明示するため
    「上記の作業を実施してください」ではなく「作業者の完了確認のみ」と表示する。
    """
    console.print()
    console.print(f"・ ステップ {step.number}/{total}: [bold #cfd3ea]{escape(step.title)}[/]")
    if step.description:
        print_tree_item("説明", step.description)
    if step.runner == "manual":
        if preview:
            console.print("  └ [bold #f2b94d]手動ステップ[/](作業者の完了確認のみ)")
        else:
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
        # show_edge=False: 表の上下に入る空行を落とす(1表あたり2行の削減)
        pad_edge=False,
        show_edge=False,
    )
    table.add_column(label_header, style="bold", overflow="fold")
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


# 案R5: コマンド出力のうち「構造を示す行」を判別して強調するためのパターン。
# ansible の出力は長くなりやすく、どこでホストが切り替わったかが埋もれるため。
_OUT_HOST_OK_RE = re.compile(r"^\S+ \| (CHANGED|SUCCESS|OK) \|")
_OUT_HOST_NG_RE = re.compile(r"^\S+ \| (FAILED|UNREACHABLE)")
_OUT_PLAY_HEAD_RE = re.compile(r"^(PLAY|TASK|PLAY RECAP)\b")
_OUT_RECAP_NG_RE = re.compile(r"\b(failed|unreachable)=[1-9]")


def output_line_style(text: str) -> str | None:
    """コマンド出力1行の表示スタイルを返す(案R5)。None は既定のまま。

    文字は一切変えず、構造(ホストの切り替わり・プレイの区切り・失敗行)だけを
    色で浮かび上がらせる。判定に使う値そのものではないので、
    パターンが外れても表示が地味になるだけで害はない。
    """
    if _OUT_HOST_NG_RE.match(text) or _OUT_RECAP_NG_RE.search(text):
        return "bold #ff6b60"
    if _OUT_HOST_OK_RE.match(text):
        return "bold #5fd9a4"
    if _OUT_PLAY_HEAD_RE.match(text):
        return "bold #8ea7ff"
    return None


def host_results_logline(results: dict) -> str:
    return " ".join(f"{h}={_LOG_MARKS.get(s, '-')}" for h, s in sorted(results.items()))


# 最終リザルト一覧の状態表示: StepRecord.status → (表示ラベル, スタイル)
_RESULT_LABELS = {
    "ok": ("✓ 完了", "bold #5fd9a4"),
    "ng": ("✘ 失敗", "bold #ff6b60"),
    "error": ("✘ エラー", "bold #ff6b60"),
    "skipped": ("→ スキップ", "bold #f2b94d"),
}
# 記録が残っていない場合の状態(選択されていたが中断で到達しなかった / 実行対象外)
_RESULT_NOT_RUN = ("- 未実行", "dim")
_RESULT_EXCLUDED = ("- 対象外", "dim")


def result_table(steps, records, selected: set[int], aborted_at: int | None = None) -> Table:
    """実行後のステップ別リザルト一覧(案R1)。

    「どのステップで落ちたか」「どのステップが実行されなかったか」を
    最終サマリーだけで読めるようにする。records に無いステップは、
    選択されていれば「未実行」(中断で到達しなかった)、
    選択されていなければ「対象外」として明示する(読み手に引き算をさせない)。
    """
    by_number = {r.number: r for r in records}
    # show_edge=False: box.SIMPLE が表の上下に入れる空行を落として詰める
    table = Table(box=box.SIMPLE, border_style="#4a4f78", header_style="bold #cfd3ea",
                  pad_edge=False, show_edge=False)
    table.add_column("No.", justify="right")
    table.add_column("ステップ", overflow="fold")
    table.add_column("結果")
    table.add_column("rc", justify="right")
    table.add_column("所要", justify="right")
    table.add_column("")  # 中断位置の注記
    for s in steps:
        rec = by_number.get(s.number)
        if rec is None:
            label, style = _RESULT_NOT_RUN if s.number in selected else _RESULT_EXCLUDED
            rc_text = duration_text = "-"
        else:
            label, style = _RESULT_LABELS.get(rec.status, (rec.status, ""))
            rc_text = "-" if rec.rc is None else str(rec.rc)
            duration_text = "-" if rec.duration is None else f"{rec.duration}s"
        note = "← 中断" if aborted_at is not None and s.number == aborted_at else ""
        table.add_row(
            str(s.number),
            Text(s.title),
            Text(label, style=style),
            rc_text,
            duration_text,
            Text(note, style="bold #ff6b60"),
        )
    return table


# 一覧表の「種別」列: Step.runner → 表示名
_RUNNER_LABELS = {"shell": "bash", "ansible": "ansible", "playbook": "playbook", "manual": "手動"}


def step_table(title: str, steps, mask=lambda t: t) -> Table:
    """ステップ一覧表(俯瞰用)。

    コマンドは列に入れない。表の幅では必ず切り捨てが必要になり、折り返しても
    パスが単語途中で分断されて読めないため(実測で確認)、全文の表示は
    詳細ブロック(show_step_header)側に任せる。ここは「何番・何をする・種別・
    合否条件」の俯瞰に徹し、どの列も切り捨てない。
    """
    table = Table(title=title)
    table.add_column("No.", justify="right")
    table.add_column("ステップ", overflow="fold")
    table.add_column("種別")
    table.add_column("正常性基準", overflow="fold")
    for s in steps:
        label = _RUNNER_LABELS.get(s.runner, s.runner)
        if s.runner == "manual":
            table.add_row(str(s.number), s.title, label, "作業者の完了確認")
            continue
        table.add_row(str(s.number), s.title, label, mask(s.criteria))
    return table
