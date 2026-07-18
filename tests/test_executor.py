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


def test_share_env_carries_exported_vars(tmp_path):
    env_file = str(tmp_path / "env.sh")
    r1 = run_command("export TOKEN=abc123", env_file=env_file)
    assert r1.rc == 0
    r2 = run_command('echo "token=$TOKEN"', env_file=env_file)
    assert "token=abc123" in r2.stdout


def test_share_env_preserves_exit_code(tmp_path):
    env_file = str(tmp_path / "env.sh")
    r = run_command("export X=1; exit 7", env_file=env_file)
    assert r.rc == 7
    # exit 7 は env 保存後ではなくコマンド本体の終了なので、この場合 X は保存されない
    r2 = run_command('echo "x=${X:-unset}"', env_file=env_file)
    assert "x=unset" in r2.stdout


def test_share_env_failure_rc_kept(tmp_path):
    env_file = str(tmp_path / "env.sh")
    r = run_command("export Y=2\nfalse", env_file=env_file)
    assert r.rc == 1  # 最後のコマンドの rc がステップの rc
    r2 = run_command('echo "y=$Y"', env_file=env_file)
    assert "y=2" in r2.stdout
