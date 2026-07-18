"""コマンド実行部。bash -c で実行し、出力をリアルタイム表示しつつ全量捕捉する。"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field


@dataclass
class ExecResult:
    rc: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False


@dataclass
class StepRecord:
    """1ステップの実行記録(ログ出力用)"""
    number: int
    title: str
    command: str
    criteria: str
    status: str = "pending"  # ok / ng / skipped / error / pending
    rc: int | None = None
    duration: float | None = None
    started_at: str | None = None
    finished_at: str | None = None
    detail: str = ""
    stdout: str = ""
    stderr: str = ""
    host_results: dict = field(default_factory=dict)  # ansibleステップ: ホスト名 → ok/failed/unreachable
    host_matrix: bool = False  # マトリックス表示が有効なステップか
    criteria_breakdown: list = field(default_factory=list)  # NG時の判定内訳: [{"expr": 条件式, "ok": bool}]

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        # 生の出力は別ファイルに保存するので JSON からは除く
        d.pop("stdout")
        d.pop("stderr")
        return d


# ansible ad-hoc のホスト別結果行: 例 "web01 | CHANGED | rc=0 >>" / "bad | UNREACHABLE! => {"
_HOST_RESULT_RE = re.compile(r"^(\S+) \| (CHANGED|SUCCESS|FAILED|UNREACHABLE)", re.MULTILINE)
_HOST_STATUS_MAP = {"CHANGED": "ok", "SUCCESS": "ok", "FAILED": "failed", "UNREACHABLE": "unreachable"}

# ansible-playbook の PLAY RECAP 行:
# 例 "web01    : ok=2    changed=1    unreachable=0    failed=0    skipped=0 ..."
_RECAP_RE = re.compile(
    r"^(\S+)\s+:\s+ok=\d+\s+changed=\d+\s+unreachable=(\d+)\s+failed=(\d+)", re.MULTILINE
)


def parse_ansible_host_results(output: str) -> dict[str, str]:
    """ansible ad-hoc / ansible-playbook 出力からホストごとの結果を抽出する。

    ad-hoc はホスト別結果行、playbook は PLAY RECAP を解析する。
    戻り値: {ホスト名: "ok" | "failed" | "unreachable"}
    """
    results: dict[str, str] = {}
    for host, status in _HOST_RESULT_RE.findall(output):
        results[host] = _HOST_STATUS_MAP[status]
    for host, unreachable, failed in _RECAP_RE.findall(output):
        if int(failed) > 0:
            results[host] = "failed"
        elif int(unreachable) > 0:
            results[host] = "unreachable"
        else:
            results[host] = "ok"
    return results


def _wrap_share_env(command: str, env_file: str) -> str:
    """ステップ実行の前後で環境変数を env_file に保存・復元するラッパー。

    export した変数が次のステップに引き継がれる。コマンドの終了コードは
    そのままステップの終了コードになる。コマンド内で exit すると
    その時点で終わるため、環境変数の保存は行われない点に注意。
    """
    q = shlex.quote(env_file)
    return (
        f"if [ -f {q} ]; then source {q}; fi\n"
        f"{command}\n"
        f"__runbook_rc=$?\n"
        f"export -p > {q}\n"
        f"exit $__runbook_rc"
    )


def run_command(
    command: str,
    timeout: float | None = None,
    cwd: str | None = None,
    on_line=None,
    env_file: str | None = None,
) -> ExecResult:
    """command を bash -c で実行する。

    on_line(line, is_stderr) を渡すと出力行ごとに呼ばれる(リアルタイム表示用)。
    env_file を渡すと実行前に source、実行後に export -p で保存し、
    ステップ間で環境変数を引き継げる(share_env: true 用)。
    stdin は閉じる(対話プロンプトで無限待ちにならないように)。
    タイムアウト時はプロセスグループごと kill する。
    """
    if env_file:
        command = _wrap_share_env(command, env_file)
    start = time.monotonic()
    proc = subprocess.Popen(
        ["/bin/bash", "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
        cwd=cwd,
        start_new_session=True,
    )

    buffers: dict[bool, list[str]] = {False: [], True: []}

    def reader(stream, is_stderr: bool) -> None:
        for line in stream:
            buffers[is_stderr].append(line)
            if on_line:
                on_line(line.rstrip("\n"), is_stderr)
        stream.close()

    threads = [
        threading.Thread(target=reader, args=(proc.stdout, False), daemon=True),
        threading.Thread(target=reader, args=(proc.stderr, True), daemon=True),
    ]
    for t in threads:
        t.start()

    timed_out = False
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        rc = proc.wait()

    for t in threads:
        t.join(timeout=5)

    return ExecResult(
        rc=rc,
        stdout="".join(buffers[False]),
        stderr="".join(buffers[True]),
        duration=time.monotonic() - start,
        timed_out=timed_out,
    )
