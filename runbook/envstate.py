"""ステップ間の環境変数引き継ぎ(baseline + 差分オーバーレイ)の純ロジック。

このモジュールは文字列の生成・解析のみを行い、ファイル I/O は一切行わない
(読み書きは artifacts.py / cli.py の責務)。

- baseline: runbook 親プロセスが実行開始時に持っていた環境変数一式(実行中不変)。
- overlay(EnvOverlay): baseline との差分。各ステップの初期環境は
  「baseline に overlay を適用したもの」になる。
- overlay はステップ終了ごとに丸ごと再生成する(追記ではない)。ステップ実行後の
  export 済み変数一式(スナップショット)と baseline を比較して diff_env で作る。

詳細は仕様書 05 章 §4 を参照。
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass


# 差分計算から除外する変数(bash / OS が毎回書き換えるノイズ。
# これらをオーバーレイに載せると cwd 指定等と矛盾するため除外する)
EXCLUDED_VARS = {"SHLVL", "PWD", "OLDPWD", "_"}


@dataclass
class EnvOverlay:
    """baseline との差分。sets は export する変数、unsets は unset する変数(tombstone)。"""

    sets: dict[str, str]
    unsets: set[str]

    def to_script(self) -> str:
        """env_overlay.sh の内容を生成する(sets/unsets が空でもコメント行のみ返す)。"""
        lines = ["# runbook env overlay (auto-generated)"]
        for key in sorted(self.sets):
            lines.append(f"export {key}={shlex.quote(self.sets[key])}")
        for key in sorted(self.unsets):
            lines.append(f"unset {key}")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_script(cls, text: str) -> "EnvOverlay":
        """to_script が生成した自前フォーマットを逆パースする。

        shlex.split(text, comments=True) で全体をトークン化する(値の改行・
        シングルクォート等は shlex のクォート処理により正しく往復する)。
        `export KEY=VALUE` / `unset KEY` 以外のトークン列は不正とみなす。
        """
        tokens = shlex.split(text, comments=True)
        sets: dict[str, str] = {}
        unsets: set[str] = set()
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "export":
                if i + 1 >= len(tokens):
                    raise ValueError(
                        "env_overlay.sh の形式が不正です: "
                        "'export' の後にトークンがありません"
                    )
                kv = tokens[i + 1]
                if "=" not in kv:
                    raise ValueError(f"env_overlay.sh の形式が不正です: {kv!r}")
                key, _, value = kv.partition("=")
                sets[key] = value
                i += 2
            elif tok == "unset":
                if i + 1 >= len(tokens):
                    raise ValueError(
                        "env_overlay.sh の形式が不正です: "
                        "'unset' の後にトークンがありません"
                    )
                unsets.add(tokens[i + 1])
                i += 2
            else:
                raise ValueError(f"env_overlay.sh の形式が不正です: 想定外のトークン {tok!r}")
        return cls(sets=sets, unsets=unsets)

    def apply(self, base: dict[str, str]) -> dict[str, str]:
        """base のコピーに sets を上書きし、unsets のキーを取り除いて返す。"""
        result = dict(base)
        result.update(self.sets)
        for key in self.unsets:
            result.pop(key, None)
        return result


def diff_env(baseline: dict[str, str], snapshot: dict[str, str]) -> EnvOverlay:
    """baseline と snapshot(あるステップ実行後の export 済み変数一式)から差分を作る。"""
    sets = {
        key: value
        for key, value in snapshot.items()
        if key not in EXCLUDED_VARS and baseline.get(key) != value
    }
    unsets = {
        key
        for key in baseline
        if key not in snapshot and key not in EXCLUDED_VARS
    }
    return EnvOverlay(sets=sets, unsets=unsets)


class EnvManager:
    """baseline(実行開始時の親環境)+ 現在のオーバーレイを保持する。"""

    def __init__(self, baseline: dict[str, str] | None = None):
        self.baseline = dict(os.environ) if baseline is None else dict(baseline)
        self.overlay = EnvOverlay(sets={}, unsets=set())

    def child_env(self) -> dict[str, str]:
        """次のステップに渡す環境変数一式(baseline に現在のオーバーレイを適用)。"""
        return self.overlay.apply(self.baseline)

    def update_from_snapshot(self, snapshot: dict[str, str]) -> None:
        """ステップ実行後のスナップショットからオーバーレイを再生成する。"""
        self.overlay = diff_env(self.baseline, snapshot)

    def load_overlay_script(self, text: str) -> None:
        """env_overlay.sh の内容(--start-from での復元)からオーバーレイを読み込む。"""
        self.overlay = EnvOverlay.from_script(text)

    def overlay_script(self) -> str:
        """現在のオーバーレイを env_overlay.sh の内容として書き出す。"""
        return self.overlay.to_script()
