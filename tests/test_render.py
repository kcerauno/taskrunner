"""表示部品のテスト(リザルト一覧・出力行のスタイル判定)"""

from runbook.executor import StepRecord
from runbook.parser import Step
from runbook.render import (
    console,
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
             ("説明:", "対象:", "コマンド (ansible", "実行コマンド:", "正常性基準:")]
    assert order == sorted(order)


def test_step_header_target_line_marks_first_step():
    text = capture_step_header(ansible_step(1, "webservers", "inv.ini"))
    assert "対象: webservers @ inv.ini (最初の実行対象)" in text


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
    assert "対象:" not in text


def test_target_signature_is_none_for_non_ansible_steps():
    assert target_signature(Step(number=1, title="S1", runner="shell")) is None
    assert target_signature(Step(number=1, title="S1", runner="manual")) is None


def test_step_header_playbook_without_limit_says_hosts_come_from_playbook():
    step = Step(number=1, title="S1", runner="playbook",
                remote_command="site.yml", command="ansible-playbook -i inv.ini site.yml",
                criteria="rc == 0", inventories=["inv.ini"])
    assert "(プレイブックの hosts:)" in capture_step_header(step)
