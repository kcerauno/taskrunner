"""実行ログ(エビデンス)の保存。

実行 1 回ごとに logs/<手順書名>_<日時>/ を作り、以下を書く:
    run.log             人間が読む実行ログ(全ステップの経過と判定)
    result.json         機械可読な実行結果サマリ
    stepNN_stdout.txt   各ステップの標準出力(生データ)
    stepNN_stderr.txt   各ステップの標準エラー(生データ)

mask(シークレットマスキング関数)を渡すと、run.log・result.json・
stepNN_*.txt に書かれるすべてのテキストにマスクが適用される
(secrets: [VAR] で宣言された変数の値を残さないため)。
"""

from __future__ import annotations

import json
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


class RunLogger:
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

    def add_record(self, rec: StepRecord) -> None:
        self.records.append(rec)
        n = f"{rec.number:02d}"
        (self.dir / f"step{n}_stdout.txt").write_text(self.mask(rec.stdout), encoding="utf-8")
        (self.dir / f"step{n}_stderr.txt").write_text(self.mask(rec.stderr), encoding="utf-8")

    def finalize(self, status: str) -> Path:
        result = {
            "procedure": self.meta,
            "status": status,  # completed / aborted / error
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [r.as_dict() for r in self.records],
        }
        result = _mask_deep(result, self.mask)
        (self.dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.log(f"実行終了: {status}")
        self._log.close()
        return self.dir
