"""表示部品のテスト(リザルト一覧・出力行のスタイル判定)"""

from runbook.executor import StepRecord
from runbook.parser import Step
from runbook.render import console, output_line_style, result_table


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
    assert output_line_style("web01 | CHANGED | rc=0 >>") == "bold #5fd9a4"
    assert output_line_style("web01 | SUCCESS | rc=0 >>") == "bold #5fd9a4"
    assert output_line_style("bad | UNREACHABLE! => {") == "bold #ff6b60"
    assert output_line_style("db01 | FAILED | rc=1 >>") == "bold #ff6b60"


def test_output_line_style_flags_play_headings():
    assert output_line_style("PLAY [変数表示プレイ] ***") == "bold #8ea7ff"
    assert output_line_style("TASK [値を表示] ***") == "bold #8ea7ff"
    assert output_line_style("PLAY RECAP ***") == "bold #8ea7ff"


def test_output_line_style_recap_only_flagged_when_nonzero_failures():
    ok_line = "web01 : ok=1 changed=0 unreachable=0 failed=0"
    ng_line = "web02 : ok=0 changed=0 unreachable=0 failed=1"
    assert output_line_style(ok_line) is None
    assert output_line_style(ng_line) == "bold #ff6b60"


def test_output_line_style_plain_output_unstyled():
    assert output_line_style("機能テスト: host=web03") is None
    assert output_line_style("  ふつうの出力") is None
