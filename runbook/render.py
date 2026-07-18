"""表示部品(console 出力の共通コンポーネント。D2)。

cli.py の run / list / check --preview から共通で使う表示ロジックをここに集約する。
list の一覧表(step_table)と run のステップ詳細(show_step_header)は、
check --preview の 2 部構成表示でもそのまま再利用する。
"""

from __future__ import annotations

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


def step_table(title: str, steps, mask=lambda t: t) -> Table:
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
