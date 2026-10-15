"""表示部品のテスト(リザルト一覧・出力行のスタイル判定)"""

from runbook.executor import StepRecord
from runbook.parser import Step
from runbook.render import (
    ACCENT,
    LABEL_WIDTH,
    MUTED,
    NG,
    OK,
    STYLE_NG,
    STYLE_OK,
    WARN,
    console,
    print_host_matrix,
    tree_item,
    output_line_style,
    result_table,
    show_step_header,
    target_signature,
)


def render_to_text(renderable) -> str:
    with console.capture() as cap:
        console.print(renderable)
    return cap.get()


def make_steps(n: int) -> list[Step]:
    return [Step(number=i, title=f"S{i}") for i in range(1, n + 1)]


def test_result_table_marks_unreached_steps_as_not_run():
    """案R1: 中断で到達しなかったステップを「未実行」と明示する(引き算をさせない)"""
    steps = make_steps(4)
    records = [
        StepRecord(1, "S1", "", "", status="ok", rc=0, duration=0.1),
        StepRecord(2, "S2", "", "", status="ng", rc=0, duration=0.2),
    ]
    text = render_to_text(result_table(steps, records, {1, 2, 3, 4}, aborted_at=2))
    assert "✓ 完了" in text
    assert "✘ 失敗" in text
    assert text.count("未実行") == 2  # S3 / S4
    assert "← 中断" in text


def test_result_table_marks_unselected_steps_as_excluded():
    """--only で選ばれなかったステップは「対象外」(未実行と区別する)"""
    steps = make_steps(3)
    records = [StepRecord(1, "S1", "", "", status="ok", rc=0, duration=0.1)]
    text = render_to_text(result_table(steps, records, {1}))
    assert text.count("対象外") == 2
    assert "未実行" not in text


def test_result_table_shows_skipped_and_error():
    steps = make_steps(2)
    records = [
        StepRecord(1, "S1", "", "", status="skipped"),
        StepRecord(2, "S2", "", "", status="error", rc=1, duration=0.5),
    ]
    text = render_to_text(result_table(steps, records, {1, 2}))
    assert "スキップ" in text
    assert "エラー" in text


def test_result_table_has_no_blank_edge_lines():
    """show_edge=False で表の上下の空行が出ないこと(案R2 の行数削減)"""
    steps = make_steps(1)
    records = [StepRecord(1, "S1", "", "", status="ok", rc=0, duration=0.1)]
    lines = render_to_text(result_table(steps, records, {1})).splitlines()
    assert lines[0].strip() != ""
    assert lines[-1].strip() != ""


def test_output_line_style_flags_ansible_host_headers():
    """案R5: ホスト区切り行を成功/失敗で色分けする"""
    assert output_line_style("web01 | CHANGED | rc=0 >>") == STYLE_OK
    assert output_line_style("web01 | SUCCESS | rc=0 >>") == STYLE_OK
    assert output_line_style("bad | UNREACHABLE! => {") == STYLE_NG
    assert output_line_style("db01 | FAILED | rc=1 >>") == STYLE_NG


def test_output_line_style_flags_play_headings():
    assert output_line_style("PLAY [変数表示プレイ] ***") == f"bold {ACCENT}"
    assert output_line_style("TASK [値を表示] ***") == f"bold {ACCENT}"
    assert output_line_style("PLAY RECAP ***") == f"bold {ACCENT}"


def test_output_line_style_recap_only_flagged_when_nonzero_failures():
    ok_line = "web01 : ok=1 changed=0 unreachable=0 failed=0"
    ng_line = "web02 : ok=0 changed=0 unreachable=0 failed=1"
    assert output_line_style(ok_line) is None
    assert output_line_style(ng_line) == STYLE_NG


def test_output_line_style_plain_output_unstyled():
    assert output_line_style("機能テスト: host=web03") is None
    assert output_line_style("  ふつうの出力") is None


def capture_step_header(step, prev_signature=None) -> str:
    with console.capture() as cap:
        show_step_header(step, 3, prev_signature=prev_signature)
    return cap.get()


def ansible_step(number: int, target: str, inventory: str) -> Step:
    return Step(number=number, title=f"S{number}", description="説明本文",
                runner="ansible", remote_command="uptime",
                command=f"ansible {target} -i {inventory} -m shell -a uptime",
                criteria="rc == 0", targets=[target], inventories=[inventory])


def test_step_header_block_order():
    """表示順は 説明 → 対象 → コマンド → 実行コマンド → 正常性基準"""
    text = capture_step_header(ansible_step(1, "webservers", "inv.ini"))
    order = [text.index(label) for label in
             ("├ 説明", "├ 対象", "├ コマンド", "├ 実行コマンド", "└ 正常性基準")]
    assert order == sorted(order)


def test_step_header_target_line_marks_first_step():
    text = capture_step_header(ansible_step(1, "webservers", "inv.ini"))
    assert "webservers @ inv.ini  (最初の実行対象)" in text


def test_step_header_target_line_marks_change_from_previous_step():
    """インベントリ/ターゲットが前の ansible ステップから変わったら明示する"""
    prev = target_signature(ansible_step(1, "webservers", "inv.ini"))
    text = capture_step_header(ansible_step(2, "db01", "db_prod.ini"), prev_signature=prev)
    assert "⇄ 前ステップから変更" in text


def test_step_header_target_line_marks_same_as_previous_step():
    prev = target_signature(ansible_step(1, "webservers", "inv.ini"))
    text = capture_step_header(ansible_step(2, "webservers", "inv.ini"), prev_signature=prev)
    assert "= 前ステップと同じ" in text


def test_step_header_shell_step_has_no_target_line():
    """bash ステップは実行先を持たないので「対象」行を出さない"""
    step = Step(number=1, title="S1", runner="shell", command="uname -a", criteria="rc == 0")
    text = capture_step_header(step)
    assert "対象" not in text


def test_target_signature_is_none_for_non_ansible_steps():
    assert target_signature(Step(number=1, title="S1", runner="shell")) is None
    assert target_signature(Step(number=1, title="S1", runner="manual")) is None


def test_step_header_playbook_without_limit_says_hosts_come_from_playbook():
    step = Step(number=1, title="S1", runner="playbook",
                remote_command="site.yml", command="ansible-playbook -i inv.ini site.yml",
                criteria="rc == 0", inventories=["inv.ini"])
    assert "(プレイブックの hosts:)" in capture_step_header(step)


def capture(fn, *args, **kwargs) -> str:
    with console.capture() as cap:
        fn(*args, **kwargs)
    return cap.get()


def test_step_header_starts_with_rule_carrying_number_and_title():
    """ステップの区切りは番号とタイトルを埋め込んだ罫線(本文と形で区別する)"""
    first = capture_step_header(ansible_step(2, "webservers", "inv.ini")).strip().splitlines()[0]
    assert first.startswith("── ステップ 2/3  S2 ─")


def test_step_header_plan_block_is_closed():
    """計画ブロックは正常性基準(手動ステップは手動ステップ行)で └ で閉じる"""
    lines = capture_step_header(ansible_step(1, "webservers", "inv.ini")).strip().splitlines()
    assert lines[-1].startswith("  └ 正常性基準")
    manual = Step(number=1, title="M", runner="manual", description="確認する")
    lines = capture_step_header(manual).strip().splitlines()
    assert lines[-1].startswith("  └ 手動ステップ")


def test_tree_item_aligns_values_regardless_of_label_length():
    """ラベルの長さに関係なく値の開始桁が揃い、続き行も同じ桁から始まる"""
    from rich.cells import cell_len
    text = capture(tree_item, "説明", "一行目\n二行目") + capture(tree_item, "実行コマンド", "x", last=True)
    lines = text.splitlines()
    starts = {cell_len(ln[:ln.index(v)]) for ln, v in zip(lines, ("一行目", "二行目", "x"))}
    assert starts == {4 + LABEL_WIDTH + 1}
    assert lines[1].startswith("  │ ")
    assert lines[2].startswith("  └ 実行コマンド")


def test_tree_item_does_not_wrap_when_not_a_terminal():
    """パイプ・ファイル出力では長い値を折り返さない(1行のまま grep・tee できる)"""
    long = "a" * 300
    assert capture(tree_item, "実行コマンド", long).count("\n") == 1


def test_result_table_has_no_unlabeled_column():
    """中断位置の注記は「結果」列に入れ、見出しのない列を作らない"""
    steps = make_steps(2)
    records = [StepRecord(1, "S1", "", "", status="ng", rc=1, duration=0.1)]
    table = result_table(steps, records, {1, 2}, aborted_at=1)
    assert all(str(c.header).strip() for c in table.columns)
    assert "✘ 失敗 ← 中断" in render_to_text(table)


def test_host_matrix_keeps_host_names_and_does_not_wrap_labels():
    """ステップ名が長くてもホスト名は省略せず、ステップ名を折り返さない(空行を作らない)"""
    rows = [("4: " + "とても長いステップ名" * 8, {"db01": "ok", "web01": "failed"})]
    text = capture(print_host_matrix, rows, label_header="ステップ", indent="  ")
    lines = text.splitlines()
    assert "db01" in lines[0] and "web01" in lines[0]
    assert len(lines) == 3  # ヘッダ・罫線・データ1行


def test_palette_uses_only_named_colors():
    """配色は端末テーマに追従する名前付き色だけ(16進カラーは明るい背景で読めなくなる)"""
    import re
    from pathlib import Path
    for path in ("runbook/render.py", "runbook/cli.py"):
        src = Path(path).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{6}\b", src), path
    assert {OK, NG, WARN, ACCENT, MUTED} == {"green", "red", "yellow", "cyan", "dim"}
