"""コマンド実行部。bash -c で実行し、出力をリアルタイム表示しつつ全量捕捉する。

D3(環境注入+スナップショット捕捉)と D4(シグナル転送)をここで担う:
- env= で子プロセスの環境変数一式を注入する(cli 側で baseline+オーバーレイを渡す)。
- capture_env=True でコマンド終了直後の export 済み変数一式(env_snapshot)を捕捉し、
  ステップ間の環境変数引き継ぎ(envstate.py)の材料にする。
- 親プロセスが中断シグナル(SIGINT/SIGTERM/SIGHUP)を受信したら、新しいセッションで
  起動した子プロセスグループへ転送する(端末シグナルは自動では届かないため)。
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from . import criteria


@dataclass
class ExecResult:
    rc: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False
    env_snapshot: dict[str, str] | None = None  # capture_env=True 時のステップ終了直後の export 済み変数一式
    interrupted: int | None = None  # 受信した中断シグナル番号(なければ None)


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
    host_rc: dict = field(default_factory=dict)  # ansibleステップ: ホスト名 → リモートコマンドの終了コード(不明は None)
    host_matrix: bool = False  # マトリックス表示が有効なステップか
    criteria_breakdown: list = field(default_factory=list)  # NG時の判定内訳: [{"expr": 条件式, "ok": bool, "host": ホスト名}]

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


# ansible ad-hoc ステップでリモートコマンドの終了コードを受け取るための目印。
# parser がリモートコマンドの末尾に ANSIBLE_RC_SUFFIX を付け足し、リモートの rc を
# 出力に書き出したうえで exit 0 する(ansible 自身には失敗と判定させない)。
# shell モジュールは stdout 末尾の改行を落とし stderr を直結して表示するため、
# 目印は前後を __ で挟み、行頭・行末に依存せず検出できるようにしている。
ANSIBLE_RC_MARKER_RE = re.compile(r"__RUNBOOK_RC=(-?\d+)__")
ANSIBLE_RC_SUFFIX = '\n__runbook_rc=$?; echo "__RUNBOOK_RC=${__runbook_rc}__"; exit 0'

# ホスト別ブロックの見出し行: "web01 | CHANGED | rc=0 >>" / "db01 | FAILED! => {" など
_HOST_HEADER_RE = re.compile(
    r"^(\S+) \| (CHANGED|SUCCESS|FAILED|UNREACHABLE|SKIPPED)!?(?: \| rc=(-?\d+))?(.*)$",
    re.MULTILINE,
)


@dataclass
class HostJudge:
    """ansible ad-hoc ステップの1ホスト分の判定結果"""
    host: str
    status: str  # ok / failed / unreachable / skipped
    rc: int | None  # リモートコマンドの終了コード(不明は None)
    output: str  # そのホストの出力(見出し行と rc の目印を除いたもの)
    reason: str = ""  # failed / unreachable の理由(基準NG 以外のとき)


def split_ansible_host_blocks(stdout: str) -> list[tuple[str, str, int | None, str]]:
    """ansible ad-hoc の出力をホストごとのブロックに分ける。

    戻り値: [(ホスト名, 状態(CHANGED/FAILED/...), 見出しの rc, ブロック本文), ...]
    ブロック本文は見出し行の残り(`=> {` 以降など)と次の見出しまでの行。
    """
    matches = list(_HOST_HEADER_RE.finditer(stdout))
    blocks = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(stdout)
        rest = m.group(4)
        rest = rest[3:] if rest.startswith(" >>") else rest.lstrip(" =>")
        body = stdout[m.end():end].lstrip("\n")
        if rest.strip():
            body = rest.strip() + ("\n" + body if body else "")
        header_rc = int(m.group(3)) if m.group(3) is not None else None
        blocks.append((m.group(1), m.group(2), header_rc, body.rstrip("\n")))
    return blocks


def judge_ansible_hosts(expr: str, stdout: str, stderr: str) -> list[HostJudge]:
    """ansible ad-hoc ステップの正常性基準をホストごとに評価する。

    rc / stdout / out() はそのホストのリモート rc と出力を指す。stderr / err() は
    ansible プロセスの標準エラー(警告など、ホスト共通)、all_stdout / all_out() は
    全ホスト分の出力(rc の目印は除く)を指す。
    到達不能なホストと、rc が分からない失敗(モジュールエラー等)は基準を評価せず失敗とする。
    ホスト別ブロックが1つも無い場合(インベントリ不正など)は空リストを返すので、
    呼び出し側は従来どおり ansible プロセスの終了コードで評価する。
    基準式の誤りは criteria.CriteriaError のまま送出する。
    """
    judges: list[HostJudge] = []
    all_output = ANSIBLE_RC_MARKER_RE.sub("", stdout)
    for host, raw, header_rc, body in split_ansible_host_blocks(stdout):
        markers = ANSIBLE_RC_MARKER_RE.findall(body)
        output = ANSIBLE_RC_MARKER_RE.sub("", body).rstrip("\n")
        rc = int(markers[-1]) if markers else header_rc
        if raw == "UNREACHABLE":
            judges.append(HostJudge(host, "unreachable", None, output, "到達不能"))
            continue
        if raw == "SKIPPED":
            judges.append(HostJudge(host, "skipped", None, output))
            continue
        if rc is None:
            if raw == "FAILED":
                judges.append(HostJudge(host, "failed", None, output, "ansible がエラーを返しました"))
                continue
            rc = 0
        ok = criteria.evaluate(expr, rc, output, stderr, all_stdout=all_output)
        judges.append(HostJudge(host, "ok" if ok else "failed", rc, output))
    return judges


def _parse_env_snapshot(data: bytes) -> dict[str, str] | None:
    """`env -0` の出力(NUL区切り)を dict にパースする。

    出力が空、または末尾が NUL で終わっていない(強制終了等による切断)場合は
    不完全とみなし None を返す。`=` を含まない要素は捨てる。
    """
    if not data or not data.endswith(b"\0"):
        return None
    text = data.decode(errors="replace")
    result: dict[str, str] = {}
    for item in text.split("\0"):
        if not item or "=" not in item:
            continue
        key, _, value = item.partition("=")
        result[key] = value
    return result


def run_command(
    command: str,
    timeout: float | None = None,
    cwd: str | None = None,
    on_line=None,
    env: dict[str, str] | None = None,
    capture_env: bool = False,
    grace: float = 10.0,
) -> ExecResult:
    """command を bash -c で実行する。

    on_line(line, is_stderr) を渡すと出力行ごとに呼ばれる(リアルタイム表示用)。
    行は改行付きの生の行がそのまま渡される(末尾が改行で終わらない最終行は
    改行なしのまま)。呼び出し側で内容を改変してはならない(仕様 05 章 §7.1)。

    env は子プロセスの環境変数一式としてそのまま Popen へ渡す(None なら親環境を継承)。

    capture_env=True のとき、コマンド終了直後に `env -0` で export 済み変数一式を
    捕捉し ExecResult.env_snapshot に入れる。コマンド内で exit する等でラッパー末尾に
    到達しなかった場合(タイムアウト・中断シグナル受信を含む)は env_snapshot=None
    になる(呼び出し側は None なら直前のオーバーレイを維持する)。

    stdin は閉じる(対話プロンプトで無限待ちにならないように)。
    プロセスは新しいセッション(プロセスグループ)で起動する。
    タイムアウト時はプロセスグループごと即 SIGKILL する。
    親プロセスが SIGINT/SIGTERM/SIGHUP を受信した場合は、受信したものと同じ
    シグナルを子プロセスグループへ転送し、grace 秒以内に終了しなければ SIGKILL する。
    """
    env_r = env_w = None
    if capture_env:
        env_r, env_w = os.pipe()
        command = (
            f"{command}\n"
            f"__runbook_rc=$?\n"
            f"env -0 >&{env_w} 2>/dev/null\n"
            f"exit $__runbook_rc"
        )

    start = time.monotonic()
    proc = subprocess.Popen(
        ["/bin/bash", "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
        cwd=cwd,
        env=env,
        start_new_session=True,
        pass_fds=(env_w,) if capture_env else (),
    )
    if capture_env:
        # 親側の書き込み端を閉じないと、子プロセス終了後も読み取り側が EOF を
        # 検知できない(親が w を握ったままだとパイプが「開いたまま」になるため)。
        os.close(env_w)

    buffers: dict[bool, list[str]] = {False: [], True: []}

    def reader(stream, is_stderr: bool) -> None:
        for line in stream:
            buffers[is_stderr].append(line)
            if on_line:
                on_line(line, is_stderr)
        stream.close()

    threads = [
        threading.Thread(target=reader, args=(proc.stdout, False), daemon=True),
        threading.Thread(target=reader, args=(proc.stderr, True), daemon=True),
    ]

    env_chunks: list[bytes] = []
    if capture_env:
        def env_reader() -> None:
            # パイプバッファ詰まり防止のため専用スレッドで EOF まで読み切る
            while True:
                chunk = os.read(env_r, 65536)
                if not chunk:
                    break
                env_chunks.append(chunk)
            os.close(env_r)

        threads.append(threading.Thread(target=env_reader, daemon=True))

    for t in threads:
        t.start()

    # D4: 中断シグナルの転送。子プロセスは新しいセッションで起動しているため
    # 端末や親へのシグナルは自動では届かない。親が明示的に転送する。
    received: list[int] = []
    grace_timer: threading.Timer | None = None

    def _killpg(sig: int) -> None:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass

    def _handler(signum, frame) -> None:
        nonlocal grace_timer
        if received:
            return  # 初回のみ転送する
        received.append(signum)
        _killpg(signum)
        grace_timer = threading.Timer(grace, _killpg, args=(signal.SIGKILL,))
        grace_timer.daemon = True
        grace_timer.start()

    old_handlers = {
        sig: signal.signal(sig, _handler)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    }

    timed_out = False
    try:
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _killpg(signal.SIGKILL)
            rc = proc.wait()
    finally:
        for sig, old in old_handlers.items():
            signal.signal(sig, old)
        if grace_timer is not None:
            grace_timer.cancel()

    for t in threads:
        t.join(timeout=5)

    env_snapshot = _parse_env_snapshot(b"".join(env_chunks)) if capture_env else None
    if timed_out or received:
        # 途中終了の可能性があるスナップショットは信用しない(前回オーバーレイ維持)
        env_snapshot = None

    return ExecResult(
        rc=rc,
        stdout="".join(buffers[False]),
        stderr="".join(buffers[True]),
        duration=time.monotonic() - start,
        timed_out=timed_out,
        env_snapshot=env_snapshot,
        interrupted=received[0] if received else None,
    )
