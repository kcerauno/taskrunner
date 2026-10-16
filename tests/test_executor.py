import os
import signal
import threading
import time

import pytest

from runbook import criteria
from runbook.executor import (
    judge_ansible_hosts,
    parse_ansible_host_results,
    run_command,
    split_ansible_host_blocks,
)


def test_parse_ansible_host_results():
    output = """\
web01 | CHANGED | rc=0 >>
uptime output here
web02 | SUCCESS => {
    "changed": false
}
db01 | FAILED | rc=1 >>
The command exited with a non-zero return code.
badhost | UNREACHABLE! => {
    "changed": false
}
"""
    assert parse_ansible_host_results(output) == {
        "web01": "ok",
        "web02": "ok",
        "db01": "failed",
        "badhost": "unreachable",
    }


def test_parse_ansible_host_results_ignores_plain_output():
    assert parse_ansible_host_results("hello\nweb01 | rc=0\n") == {}


def test_parse_playbook_recap():
    output = """\
PLAY RECAP *********************************************************************
web01                      : ok=2    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
web02                      : ok=1    changed=0    unreachable=0    failed=1    skipped=0    rescued=0    ignored=0
badhost                    : ok=0    changed=0    unreachable=1    failed=0    skipped=0    rescued=0    ignored=0
"""
    assert parse_ansible_host_results(output) == {
        "web01": "ok",
        "web02": "failed",
        "badhost": "unreachable",
    }


def test_run_basic():
    r = run_command("echo hello; echo oops >&2; exit 3")
    assert r.rc == 3
    assert r.stdout == "hello\n"
    assert r.stderr == "oops\n"
    assert not r.timed_out


def test_timeout_kills():
    r = run_command("sleep 10", timeout=0.3)
    assert r.timed_out
    assert r.duration < 5


def test_on_line_receives_raw_lines_with_trailing_newline():
    """on_line 契約: rstrip されない生の行(末尾改行付き)が渡される"""
    received: list[tuple[str, bool]] = []
    run_command("echo hello; echo oops >&2",
               on_line=lambda line, is_stderr: received.append((line, is_stderr)))
    assert ("hello\n", False) in received
    assert ("oops\n", True) in received


def test_on_line_final_line_without_trailing_newline_is_unchanged():
    """改行で終わらない最終出力はそのまま(改行を足さない)"""
    received: list[str] = []
    run_command("printf 'no-newline'",
               on_line=lambda line, is_stderr: received.append(line))
    assert received == ["no-newline"]


def test_env_injection_visible_to_command():
    r = run_command("printenv KEY", env={"KEY": "injected-value", "PATH": os.environ["PATH"]})
    assert r.rc == 0
    assert "injected-value" in r.stdout


def test_capture_env_snapshot_on_normal_exit():
    r = run_command("export FOO=bar", capture_env=True)
    assert r.rc == 0
    assert r.env_snapshot is not None
    assert r.env_snapshot["FOO"] == "bar"


def test_capture_env_snapshot_none_on_mid_command_exit():
    """コマンド内で exit するとラッパー末尾(env -0)に到達しないため snapshot なし。
    rc はコマンド自身の終了コードが保たれる。"""
    r = run_command("export FOO=bar; exit 3", capture_env=True)
    assert r.rc == 3
    assert r.env_snapshot is None


def test_signal_interrupt_forwarded_to_child(tmp_path):
    """親プロセスが SIGTERM を受信すると子プロセスグループへ転送される"""
    original = signal.getsignal(signal.SIGTERM)
    timer = threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.daemon = True
    start = time.monotonic()
    timer.start()
    try:
        r = run_command("sleep 5")
    finally:
        timer.cancel()
    duration = time.monotonic() - start
    assert r.interrupted == signal.SIGTERM
    assert duration < 3
    assert signal.getsignal(signal.SIGTERM) is original


# ---- ansible ad-hoc のホストごとの判定 ----

# リモートコマンドの末尾に付けた目印(__RUNBOOK_RC=N__)を含む ad-hoc 出力。
# shell モジュールは stdout 末尾の改行を落とし、stderr を直結して表示する。
ADHOC_OUTPUT = """\
web01 | CHANGED | rc=0 >>
same
__RUNBOOK_RC=0__
web02 | CHANGED | rc=0 >>
1c1
< a
---
> b
__RUNBOOK_RC=1__
db01 | CHANGED | rc=0 >>
__RUNBOOK_RC=2__diff: /nonexist: No such file or directory
"""


def _by_host(judges):
    return {j.host: j for j in judges}


def test_judge_uses_remote_rc_per_host():
    j = _by_host(judge_ansible_hosts("rc == 0 or rc == 1", ADHOC_OUTPUT, ""))
    assert (j["web01"].status, j["web01"].rc) == ("ok", 0)
    assert (j["web02"].status, j["web02"].rc) == ("ok", 1)
    assert (j["db01"].status, j["db01"].rc) == ("failed", 2)


def test_judge_default_criteria_fails_on_nonzero_remote_rc():
    j = _by_host(judge_ansible_hosts("rc == 0", ADHOC_OUTPUT, ""))
    assert [h for h, v in j.items() if v.status == "ok"] == ["web01"]


def test_judge_host_output_excludes_header_and_marker():
    j = _by_host(judge_ansible_hosts("rc == 0", ADHOC_OUTPUT, ""))
    assert j["web01"].output == "same"
    # stderr が目印の直後に連結されても、目印だけを取り除く
    assert j["db01"].output == "diff: /nonexist: No such file or directory"


def test_judge_out_is_per_host_and_all_out_is_whole_output():
    expr = 'out("1c1")'
    j = _by_host(judge_ansible_hosts(expr, ADHOC_OUTPUT, ""))
    assert {h: v.status for h, v in j.items()} == {"web01": "failed", "web02": "ok", "db01": "failed"}
    j = _by_host(judge_ansible_hosts('all_out("1c1") and not all_out("__RUNBOOK_RC")', ADHOC_OUTPUT, ""))
    assert all(v.status == "ok" for v in j.values())


def test_judge_marker_glued_to_stdout_without_newline():
    out = "web01 | CHANGED | rc=0 >>\nno-newline__RUNBOOK_RC=3__\n"
    [j] = judge_ansible_hosts("rc == 3", out, "")
    assert (j.status, j.rc, j.output) == ("ok", 3, "no-newline")


def test_judge_falls_back_to_header_rc_without_marker():
    # set -e や exit で目印の前に抜けた場合は ansible の見出しの rc を使う
    out = "web01 | FAILED | rc=4 >>\nboom\nnon-zero return code\n"
    [j] = judge_ansible_hosts("rc == 0", out, "")
    assert (j.status, j.rc) == ("failed", 4)


def test_judge_unreachable_and_module_error_fail_without_evaluating():
    out = """\
bad | UNREACHABLE! => {
    "changed": false,
    "unreachable": true
}
db01 | FAILED! => {
    "msg": "module failure"
}
"""
    # 基準式が常に真でも失敗扱い(コマンドが実行されていないため)
    j = _by_host(judge_ansible_hosts("True", out, ""))
    assert (j["bad"].status, j["bad"].reason) == ("unreachable", "到達不能")
    assert j["db01"].status == "failed" and j["db01"].rc is None
    assert '"msg": "module failure"' in j["db01"].output


def test_judge_returns_empty_without_host_blocks():
    assert judge_ansible_hosts("rc == 0", "[WARNING]: No hosts matched\n", "") == []


def test_judge_propagates_criteria_error():
    with pytest.raises(criteria.CriteriaError):
        judge_ansible_hosts("unknown_name == 0", ADHOC_OUTPUT, "")


def test_split_blocks_oneline_mode():
    # -o(1行表示)でも見出しと目印を拾える
    out = 'web01 | CHANGED | rc=0 | (stdout) x\\n__RUNBOOK_RC=1__\n'
    [(host, raw, header_rc, body)] = split_ansible_host_blocks(out)
    assert (host, raw, header_rc) == ("web01", "CHANGED", 0)
    [j] = judge_ansible_hosts("rc == 1", out, "")
    assert j.status == "ok"
