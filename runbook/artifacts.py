"""実行ログ(エビデンス)の保存。

実行 1 回ごとに logs/<手順書名>_<日時>/ を作り、以下を書く:
    run.log             人間が読む実行ログ(全ステップの経過と判定)
    result.json         機械可読な実行結果サマリ(ステップ終了ごとにアトミック更新)
    env_overlay.sh       ステップ間で引き継ぐ環境変数の差分オーバーレイ(常に作成)
    stepNN_stdout.txt   各ステップの標準出力(生データ。行単位で逐次書き込み)
    stepNN_stderr.txt   各ステップの標準エラー(生データ。行単位で逐次書き込み)

mask(シークレットマスキング関数)を渡すと、run.log・result.json・
stepNN_*.txt に書かれるすべてのテキストにマスクが適用される
(secrets: [VAR] で宣言された変数の値を残さないため)。env_overlay.sh は
環境変数の引き継ぎに実データが必要なためマスクしない(仕様 05 章 §4・§5)。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .executor import StepRecord


def _mask_deep(obj, mask: Callable[[str], str]):
    """dict / list を再帰的にたどり、すべての文字列にマスクを適用する"""
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: _mask_deep(v, mask) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_deep(v, mask) for v in obj]
    return obj


def atomic_write_text(path: Path, text: str) -> None:
    """path と同一ディレクトリに一時ファイルを書き、アトミックに rename する。

    rename の原子性は同一ファイルシステム内でのみ保証されるため(D7.2)、
    一時ファイルは path と同じディレクトリに作る。renumber(cli.py)からも
    共通ヘルパーとして利用する。
    """
    path = Path(path)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(text)
        tmp.flush()
        tmp.close()
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


class StepFiles:
    """1 ステップ分の stepNN_stdout.txt / stepNN_stderr.txt への逐次書き込み。

    open 時に両ファイルを作成する。write() のたびに即 flush するため、
    実行中でも `tail -f` で内容を追跡できる(仕様 05 章 §7.1)。
    """

    def __init__(self, directory: Path, number: int):
        n = f"{number:02d}"
        self._out = (Path(directory) / f"step{n}_stdout.txt").open("w", encoding="utf-8")
        self._err = (Path(directory) / f"step{n}_stderr.txt").open("w", encoding="utf-8")

    def write(self, line: str, is_stderr: bool = False) -> None:
        """mask 適用済みの行(改行付き)を書いて即 flush する。"""
        f = self._err if is_stderr else self._out
        f.write(line)
        f.flush()

    def close(self) -> None:
        self._out.close()
        self._err.close()


class RunArtifacts:
    def __init__(self, procedure_name: str, base_dir: str | Path = "logs",
                 mask: Callable[[str], str] | None = None):
        self.started_at = datetime.now()
        stamp = self.started_at.strftime("%Y%m%d_%H%M%S")
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        # 同一秒内の連続実行で名前が衝突しても、証跡が混ざらないよう
        # _2, _3... を付けて必ず新規ディレクトリを作る
        name = f"{procedure_name}_{stamp}"
        self.dir = base / name
        n = 1
        while True:
            try:
                self.dir.mkdir()
                break
            except FileExistsError:
                n += 1
                self.dir = base / f"{name}_{n}"
        self._log = (self.dir / "run.log").open("w", encoding="utf-8")
        self.records: list[StepRecord] = []
        self.meta: dict = {}
        self.mask = mask or (lambda t: t)

    def log(self, text: str = "") -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for line in self.mask(text).splitlines() or [""]:
            self._log.write(f"[{now}] {line}\n")
        self._log.flush()

    def open_step_files(self, number: int) -> StepFiles:
        return StepFiles(self.dir, number)

    def add_record(self, rec: StepRecord) -> None:
        """records に追加し、result.json をステップ終了時点の内容でアトミック更新する。

        stepNN_*.txt への書き込みは open_step_files() が呼び出し側で逐次
        行っている前提のため、ここでは行わない。
        """
        self.records.append(rec)
        self.save_result("running")

    def save_result(self, status: str) -> None:
        """result.json を status(running / completed / aborted)で全文更新する。"""
        result = {
            "procedure": self.meta,
            "status": status,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [r.as_dict() for r in self.records],
        }
        result = _mask_deep(result, self.mask)
        atomic_write_text(
            self.dir / "result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )

    def write_env_overlay(self, script: str) -> None:
        """env_overlay.sh をアトミックに書く。マスクは適用しない(仕様 05 章 §5)。"""
        atomic_write_text(self.dir / "env_overlay.sh", script)

    def finalize(self, status: str) -> Path:
        self.save_result(status)
        self.log(f"実行終了: {status}")
        self._log.close()
        return self.dir
