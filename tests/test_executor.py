import os
import signal
import threading
import time

from runbook.executor import parse_ansible_host_results, run_command


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
