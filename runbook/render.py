"""表示部品(console 出力の共通コンポーネント。D2)。

cli.py の run / list / check --preview から共通で使う表示ロジックをここに集約する。
list の一覧表(step_table)と run のステップ詳細(show_step_header)は、
check --preview の 2 部構成表示でもそのまま再利用する。
"""

from __future__ import annotations

import re

from rich import box
from rich.cells import cell_len
from rich.console import Console
from rich.table import Table
from rich.text import Text

# soft_wrap: 長い行に強制改行を入れない(tee 等でテキスト保存しても行が崩れない)。
# 端末に出すときだけ tree_item() 側でツリーのインデントを保って折り返す。
# NO_COLOR 環境変数と --no-color で色を消せる(rich が NO_COLOR を解釈する)。
console = Console(highlight=False, soft_wrap=True)

MASK = "*****"

# 配色: 意味ごとに5種類だけ使う(1つの色に1つの意味)。
# 16進カラーは暗い背景前提になり、明るい背景の端末で読めなくなるため、
# 端末のテーマに追従する名前付き色と dim だけを使う。
# 太字は見出しと合否(結果・判定)にだけ付ける(多用すると強調が効かなくなる)。
OK = "green"        # 成功
NG = "red"          # 失敗・エラー・中断
WARN = "yellow"     # 注意: スキップ・手動ステップ・到達不能・警告・実行先の変更・失敗時ガイダンス
ACCENT = "cyan"     # 見出しの罫線・入力プロンプト・実行するコマンド・出力内の見出し
MUTED = "dim"       # 補足: ツリー記号・ラベル・監査用の控え・凡例

STYLE_OK = f"bold {OK}"
STYLE_NG = f"bold {NG}"
STYLE_WARN = f"bold {WARN}"
STYLE_PROMPT = f"bold {ACCENT}"

# ステップ表示の配色
STYLE_CMD = ACCENT              # RB-CMD の原文(何をするか)
STYLE_FULL_CMD = MUTED          # 組み立て後の実行コマンド全文(監査の控え)
STYLE_TARGET = "bold"           # どのインベントリ/ホストか(色ではなく太字で目立たせる)
STYLE_CHANGED = WARN            # 前ステップから実行先が変わった(失敗ではないので赤にしない)

# ツリーのラベル幅(表示幅)。ラベルの長さに関係なく値の開始桁を揃える。
LABEL_WIDTH = 12
# ツリーの値の開始桁: "  ├ " (4) + ラベル (LABEL_WIDTH) + 空白 (1)
VALUE_COLUMN = 4 + LABEL_WIDTH + 1
# コマンド出力の行頭。ツリーの縦線の内側に、出力専用の縦線(▏)を引いて
# 説明やコマンドの続き行と見分けられるようにする。
OUTPUT_PREFIX = "  │ ▏ "


def _as_text(value, style: str = "") -> Text:
    if isinstance(value, Text):
        return value
    return Text(str(value), style=style)


def _wrap(line: Text, width: int) -> list[Text]:
    """端末のときだけ、値を指定幅で折り返す(ツリーの縦線を突き破らせない)。

    パイプやファイルへの出力では折り返さない(1行のまま grep・tee できるように)。
    """
    if not console.is_terminal or width < 20 or cell_len(line.plain) <= width:
        return [line]
    return list(line.wrap(console, width, overflow="fold", no_wrap=False))


def tree_item(label: str, value, *, last: bool = False, first: bool = False,
              bare: bool = False, style: str = "") -> None:
    """ツリーの1項目を出す。ラベルは固定幅に揃え、複数行の値は値の開始桁で続ける。

    value は文字列(markup は解釈しない)か rich の Text。
    first=True は見出しを持たないブロックの先頭(┌)。実行ブロックの「開始」で使う。
    bare=True はツリー記号なし(ツリーに属さない単独の項目)。
    """
    text = _as_text(value, style)
    lines = text.split("\n", allow_blank=True) if text.plain else [Text("")]
    label_cells = max(LABEL_WIDTH, cell_len(label))
    if bare:
        lead = cont_lead = "  "
    else:
        lead = "  " + ("└" if last else "┌" if first else "├") + " "
        cont_lead = "    " if last else "  │ "
    head = Text.assemble((lead, MUTED), (label + " " * (label_cells - cell_len(label) + 1), MUTED))
    cont = Text.assemble((cont_lead, MUTED), " " * (label_cells + 1))
    width = console.width - (len(lead) + label_cells + 1)
    first = True
    for line in lines:
        for seg in _wrap(line, width):
            console.print(Text.assemble(head if first else cont, seg))
            first = False


def _rule(title: Text, char: str, width: int | None = None) -> None:
    """見出し付きの罫線。タイトルは切り捨てず、余った幅を罫線で埋める。"""
    width = width or console.width
    head = Text.assemble((char * 2 + " ", ACCENT), title, " ")
    fill = max(3, width - cell_len(head.plain))
    console.print(Text.assemble(head, (char * fill, ACCENT)))


def section_rule(title: str) -> None:
    """大きな区切り(実行前確認・実行開始・最終結果など)。太い罫線。"""
    console.print()
    _rule(Text(title, style="bold"), "━")


def step_rule(number: int, total: int, title: str) -> None:
    """ステップの区切り。ステップ番号とタイトルを罫線に埋め込む。"""
    console.print()
    _rule(Text.assemble((f"ステップ {number}/{total}", f"bold {ACCENT}"), "  ", (title, "bold")), "─")


def print_indented(renderable, indent: str = "  ") -> None:
    """表などを左に indent を付けて出す(ツリーと左端を揃える)。"""
    with console.capture() as cap:
        # インデント分を差し引いた幅で組む(右端からはみ出して折り返させない)
        console.print(renderable, width=max(20, console.width - cell_len(indent)))
    for line in cap.get().splitlines():
        console.print(Text.from_ansi(indent + line) if "\x1b" in line else Text(indent + line))


def prompt(message: str, style: str = STYLE_PROMPT) -> None:
    """入力プロンプト(改行しない)。ツリーと同じ左端から出す。"""
    console.print(Text.assemble("  ", ("▶ " + message, style), " > "), end="")


def notice(message: str, style: str = NG) -> None:
    """ツリーの外に出すメッセージ(中断・エラー)。値の開始桁に揃えて出す。"""
    console.print(Text.assemble(" " * VALUE_COLUMN, (message, style)))


def target_signature(step) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """ステップの実行先(ターゲット, インベントリ)。ansible 系以外は None。"""
    if step.runner not in ("ansible", "playbook"):
        return None
    return (tuple(step.targets), tuple(step.inventories))


def _target_text(step, mask, prev_signature) -> Text:
    """「対象」行: どのインベントリの、どのホストで実行されるか。

    ansible 系はステップごとにインベントリ/ターゲットが変わりうるため、
    実行コマンド全文を目で追わなくても実行先が読めるように独立した行にする。
    直前の ansible 系ステップとの一致/不一致も明示する(取り違えの検知)。
    """
    # playbook で -l 指定がない場合、対象はプレイブックの hosts: が決める
    no_target = "(プレイブックの hosts:)" if step.runner == "playbook" else "(指定なし)"
    targets = ", ".join(mask(t) for t in step.targets) or no_target
    inventories = ", ".join(mask(i) for i in step.inventories) or "(指定なし)"
    signature = target_signature(step)
    if prev_signature is None:
        mark = ("  (最初の実行対象)", MUTED)
    elif prev_signature == signature:
        mark = ("  = 前ステップと同じ", MUTED)
    else:
        mark = ("  ⇄ 前ステップから変更", STYLE_CHANGED)
    return Text.assemble((targets, STYLE_TARGET), (" @ ", MUTED), (inventories, STYLE_TARGET), mark)


def _command_text(lines: list[str], prefix: str, kind: str) -> Text:
    """コマンド行(複数行可)。1行目の後ろに種別を補足として添える。"""
    text = Text()
    for i, line in enumerate(lines):
        if i:
            text.append("\n")
        text.append(prefix + line, style=STYLE_CMD)
        if i == 0:
            text.append(f"  ({kind})", style=MUTED)
    return text


def show_step_header(step, total: int, mask=lambda t: t, preview: bool = False,
                     prev_signature=None) -> None:
    """ステップの区切り罫線と「計画」ブロック(説明・対象・コマンド・正常性基準)。

    表示順は 説明 → 対象 → コマンド → 実行コマンド → 正常性基準。
    run の実行時ステップ表示と check --preview の第2部(D2)で共用する。
    計画ブロックはここで └ で閉じる。実行結果は空行を挟んだ別ブロックに出す
    (「何をするか」と「何が起きたか」を形で分ける)。
    prev_signature は直前の ansible 系ステップの target_signature()。
    None を渡すと「最初の実行対象」として扱う(比較対象がない)。

    preview=True の手動ステップは、まだ実行していないことを明示するため
    「上記の作業を実施してください」ではなく「作業者の完了確認のみ」と表示する。
    """
    step_rule(step.number, total, step.title)
    if step.description:
        tree_item("説明", step.description)
    if step.runner == "manual":
        note = "作業者の完了確認のみ" if preview else "コマンドなし。上記の作業を実施してください"
        tree_item("手動ステップ", note, last=True, style=WARN)
        return
    if step.runner in ("ansible", "playbook"):
        tree_item("対象", _target_text(step, mask, prev_signature))
    if step.runner == "ansible":
        tree_item("コマンド", _command_text(mask(step.remote_command).splitlines(), "$ ",
                                            "ansible ad-hoc / shellモジュール"))
        tree_item("実行コマンド", mask(step.command), style=STYLE_FULL_CMD)
    elif step.runner == "playbook":
        tree_item("プレイブック", _command_text(mask(step.remote_command).splitlines(), "",
                                                "ansible-playbook"))
        tree_item("実行コマンド", mask(step.command), style=STYLE_FULL_CMD)
    else:
        tree_item("コマンド", _command_text(mask(step.command).splitlines(), "$ ", "bash"))
    tree_item("正常性基準", mask(step.criteria), last=True)


# ホスト別結果マトリックスのマーク: 状態 → (表示文字, スタイル)
_MATRIX_MARKS = {
    "ok": ("O", STYLE_OK),
    "failed": ("X", STYLE_NG),
    "unreachable": ("!", STYLE_WARN),
}
_MATRIX_LEGEND = (f"[{STYLE_OK}]O[/]=成功  [{STYLE_NG}]X[/]=失敗  "
                  f"[{STYLE_WARN}]![/]=到達不能  [{MUTED}]-[/]=対象外")
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
    # ホスト列(ホスト名 + 左右の余白 + 区切り)を確保した残りをステップ名の列に充てる
    label_width = max(8, console.width - cell_len(indent)
                      - sum(cell_len(h) + 3 for h in hosts) - 1)
    table = Table(
        box=box.SIMPLE,
        border_style=MUTED,
        header_style="bold",
        # show_edge=False: 表の上下に入る空行を落とす(1表あたり2行の削減)
        pad_edge=False,
        show_edge=False,
    )
    # 行ラベル(ステップ名)は折り返さない。折り返すとデータのない行ができて
    # 表が崩れるため。幅が足りないときは末尾を省略する(全文は実行結果の一覧にある)。
    table.add_column(label_header, no_wrap=True, overflow="ellipsis", max_width=label_width)
    for host in hosts:
        # ホスト名は省略させない(幅が足りないときはステップ名の側を省略する)
        table.add_column(Text(host), justify="center", no_wrap=True, min_width=cell_len(host))
    for label, results in rows:
        cells = [Text(label)]
        for host in hosts:
            mark, style = _MATRIX_MARKS.get(results.get(host, ""), ("-", ""))
            cells.append(Text(mark, style=style))
        table.add_row(*cells)

    print_indented(table, indent)


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
        return STYLE_NG
    if _OUT_HOST_OK_RE.match(text):
        return STYLE_OK
    if _OUT_PLAY_HEAD_RE.match(text):
        return f"bold {ACCENT}"
    return None


def host_results_logline(results: dict) -> str:
    return " ".join(f"{h}={_LOG_MARKS.get(s, '-')}" for h, s in sorted(results.items()))


# 最終リザルト一覧の状態表示: StepRecord.status → (表示ラベル, スタイル)
_RESULT_LABELS = {
    "ok": ("✓ 完了", STYLE_OK),
    "ng": ("✘ 失敗", STYLE_NG),
    "error": ("✘ エラー", STYLE_NG),
    "skipped": ("→ スキップ", STYLE_WARN),
}
# 記録が残っていない場合の状態(選択されていたが中断で到達しなかった / 実行対象外)
_RESULT_NOT_RUN = ("- 未実行", MUTED)
_RESULT_EXCLUDED = ("- 対象外", MUTED)


def result_label(status: str) -> tuple[str, str]:
    """StepRecord.status → (表示ラベル, スタイル)。ステップの結果行と一覧表で共用する。"""
    return _RESULT_LABELS.get(status, (status, ""))


def result_table(steps, records, selected: set[int], aborted_at: int | None = None) -> Table:
    """実行後のステップ別リザルト一覧(案R1)。

    「どのステップで落ちたか」「どのステップが実行されなかったか」を
    最終サマリーだけで読めるようにする。records に無いステップは、
    選択されていれば「未実行」(中断で到達しなかった)、
    選択されていなければ「対象外」として明示する(読み手に引き算をさせない)。
    """
    by_number = {r.number: r for r in records}
    # show_edge=False: box.SIMPLE が表の上下に入れる空行を落として詰める
    table = Table(box=box.SIMPLE, border_style=MUTED, header_style="bold",
                  pad_edge=False, show_edge=False)
    table.add_column("No.", justify="right")
    table.add_column("ステップ", overflow="fold")
    table.add_column("結果")
    table.add_column("rc", justify="right")
    table.add_column("所要", justify="right")
    for s in steps:
        rec = by_number.get(s.number)
        if rec is None:
            label, style = _RESULT_NOT_RUN if s.number in selected else _RESULT_EXCLUDED
            rc_text = duration_text = "-"
        else:
            label, style = result_label(rec.status)
            rc_text = "-" if rec.rc is None else str(rec.rc)
            duration_text = "-" if rec.duration is None else f"{rec.duration}s"
        result = Text(label, style=style)
        # 中断位置の注記は「結果」列に添える(見出しのない列を作らない)
        if aborted_at is not None and s.number == aborted_at:
            result.append(" ← 中断", style=STYLE_NG)
        table.add_row(str(s.number), Text(s.title), result, rc_text, duration_text)
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
