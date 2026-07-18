"""Markdown手順書のパーサ。

手順書フォーマット:

    # 手順書タイトル

    ```runbook
    vars:
      TARGET: web01
    ```

    ## 事前確認         ← "## " 見出し 1つが 1ステップ

    ### RB-DESCRIPTION
    自由記述の説明文。

    ### RB-CMD
    ```bash
    df -h /
    ```

    ### RB-EXPECTED
    ```
    rc == 0 and out("/dev/") and not out("100%")
    ```

    ### RB-LOCALDEF     ← 省略可
    ```yaml
    timeout: 300
    cwd: /var/tmp
    ```

- 共通設定(title / vars / ansible / secrets)は最初の「## 」より前に置く
  ```runbook フェンス(YAML)で定義する。
- RB-CMD のないステップは「手動ステップ」(runner="manual")。目視確認や手作業を
  手順に組み込むためのもので、RB-DESCRIPTION が必須。実行時は説明を表示して
  作業者の完了確認を待つ。
- 「### RB-ONFAIL」(省略可)は、そのステップが失敗して中断した瞬間に表示する
  作業者向けガイダンス(自由記述)。
- 「# RB-ROLLBACK」見出し(切り戻し機能)は v0.5.0 で削除された。フェンス外で
  検出した場合はパースエラーとし、切り戻し手順は別ファイルの手順書として
  作成するよう案内する。
- frontmatter(ファイル先頭の --- 〜 ---)は一般的な Markdown メタデータとして
  読み飛ばすだけで、runbook は解釈しない。ただし runbook の設定キー
  (vars / ansible / secrets)が入っている場合は、意図しない無視を防ぐため
  エラーにする。
- 「### RB-CMD」のコードフェンスが複数ある場合は連結して 1 コマンド列とする。
- 「### RB-EXPECTED」省略時は `rc == 0`。
- コマンド・正常性基準内の `{{VAR}}` は共通設定の vars と
  CLI の --var で与えた値で置換される。
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CRITERIA = "rc == 0"

# 認識するサブセクション名(小文字化して照合するため小文字で定義)。
# 一般的な日本語(説明/コマンド等)は言語要素として認識しづらいため、
# RB- プレフィックス付きの専用キーワードとする。
_SECTION_ALIASES = {
    "rb-description": "description",
    "rb-cmd": "command",
    "rb-expected": "criteria",
    "rb-localdef": "options",
    "rb-onfail": "onfail",
}
_SECTION_NAMES = "RB-DESCRIPTION/RB-CMD/RB-EXPECTED/RB-LOCALDEF/RB-ONFAIL"

# v0.5.0 で削除された切り戻し機能の見出し。フェンス外で検出したら即エラーにする
# (黙って通常ステップ・通常見出しとして扱わない。fail-loud 原則)。
_ROLLBACK_PATTERN = re.compile(r"^#\s+RB-ROLLBACK\s*$", re.IGNORECASE)

_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# ステップ見出しの先頭番号: "1. タイトル" "2．タイトル" "3: タイトル" など
_HEADING_NUM_PATTERN = re.compile(r"^(\d+)\s*[.．:：]\s*(.*)$")


def split_heading_number(title: str) -> tuple[int | None, str]:
    """見出しテキストから先頭の連番を分離する。番号がなければ (None, 原文)。"""
    m = _HEADING_NUM_PATTERN.match(title)
    if m and m.group(2).strip():
        return int(m.group(1)), m.group(2).strip()
    return None, title


class ParseError(Exception):
    """手順書の書式エラー"""


@dataclass
class Step:
    number: int  # 1始まりの通し番号
    title: str
    description: str = ""
    command: str = ""
    criteria: str = DEFAULT_CRITERIA
    timeout: float | None = None
    cwd: str | None = None
    line: int = 0  # 手順書内の行番号(エラー表示用)
    heading_number: int | None = None  # 見出しに書かれていた連番(表示用。実行は記載順)
    runner: str = "shell"  # shell / ansible / playbook / manual(RB-CMD なし=手動ステップ)
    ansible: dict = field(default_factory=dict)  # RB-LOCALDEF での ansible 上書き
    remote_command: str = ""  # ansible: リモートコマンド原文 / playbook: プレイブックパス一覧
    host_matrix: bool = False  # ansible: host_matrix: true でホスト別結果マトリックスを表示
    onfail: str = ""  # RB-ONFAIL: 失敗で中断した瞬間に表示する作業者向けガイダンス
    inventories: list[str] = field(default_factory=list)  # ansible系: 使用インベントリ(実行前サマリー表示用)


@dataclass
class Procedure:
    path: Path
    title: str
    vars: dict[str, str] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)  # 共通設定 secrets: [VAR] で値を表示・ログからマスクする変数名


def _split_frontmatter(text: str) -> tuple[dict, str, int]:
    """YAML frontmatter を切り出す。戻り値: (meta, 本文, 本文開始行)"""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                meta = yaml.safe_load("\n".join(lines[1:i])) or {}
                if not isinstance(meta, dict):
                    raise ParseError("frontmatter は YAML の辞書で書いてください")
                return meta, "\n".join(lines[i + 1:]), i + 1
        raise ParseError("frontmatter の閉じ '---' がありません")
    return {}, text, 0


def _extract_code_blocks(body_lines: list[str]) -> list[tuple[str, str]]:
    """フェンスコードブロックを (言語, 中身) で列挙する"""
    blocks: list[tuple[str, str]] = []
    in_fence = False
    lang = ""
    buf: list[str] = []
    for line in body_lines:
        m = re.match(r"^\s*```\s*(\S*)", line)
        if m:
            if in_fence:
                blocks.append((lang, "\n".join(buf)))
                buf = []
            else:
                lang = m.group(1).lower()
            in_fence = not in_fence
            continue
        if in_fence:
            buf.append(line)
    if in_fence:
        raise ParseError("コードフェンス ``` が閉じられていません")
    return blocks


def _plain_text(body_lines: list[str]) -> str:
    """フェンス外のテキストを取り出す(説明・基準のフェンスなし記述用)"""
    out: list[str] = []
    in_fence = False
    for line in body_lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out).strip()


def _parse_step(number: int, title: str, body_lines: list[str], line_no: int) -> Step:
    step = Step(number=number, title=title, line=line_no)

    # ```runbook(手順書設定)フェンスはステップ内のどこにあってもエラーにする
    # (前書き専用。黙って無視すると「書いたのに効かない」事故になる)
    try:
        all_blocks = _extract_code_blocks(body_lines)
    except ParseError as e:
        raise ParseError(f"ステップ{number}「{title}」: {e}") from e
    if any(lang == "runbook" for lang, _ in all_blocks):
        raise ParseError(
            f"ステップ{number}「{title}」: ```runbook(手順書設定)フェンスは"
            f"最初のステップより前(前書き)に置いてください")

    # 「### 見出し」でサブセクションに分割(フェンス内の ### は見出し扱いしない)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_fence = False
    for line in body_lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
        m = None if in_fence else re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            key = _SECTION_ALIASES.get(m.group(1).strip().lower())
            if key is None:
                raise ParseError(
                    f"ステップ{number}「{title}」: 不明なセクション「{m.group(1)}」"
                    f"(使用可能: {_SECTION_NAMES})"
                )
            current = key
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)

    if "description" in sections:
        step.description = _plain_text(sections["description"])

    if "onfail" in sections:
        step.onfail = _plain_text(sections["onfail"])

    # RB-CMD がないステップは「手動ステップ」(目視確認・手作業・関係者連絡など)。
    # 実行時は RB-DESCRIPTION を表示して作業者の完了確認を待つ。
    # 書き忘れとの区別のため RB-DESCRIPTION を必須とし、コマンドがないのに
    # 判定式や実行設定があるものはエラーにする。
    if "command" not in sections:
        if "criteria" in sections:
            raise ParseError(
                f"ステップ{number}「{title}」: RB-CMD のない手動ステップに"
                f" RB-EXPECTED は書けません(判定対象のコマンドがありません)")
        if "options" in sections:
            raise ParseError(
                f"ステップ{number}「{title}」: RB-CMD のない手動ステップに"
                f" RB-LOCALDEF は書けません")
        if not step.description:
            raise ParseError(
                f"ステップ{number}「{title}」: コマンドがありません。"
                f"手動ステップ(目視確認・手作業など)とする場合は"
                f" RB-DESCRIPTION に作業内容を書いてください")
        step.runner = "manual"
        step.criteria = ""
        return step

    if "command" in sections:
        blocks = _extract_code_blocks(sections["command"])
        if blocks:
            runner_langs = {"ansible": "ansible", "playbook": "playbook", "ansible-playbook": "playbook"}
            langs = {lang for lang, _ in blocks}
            runners = {runner_langs[lang] for lang in langs if lang in runner_langs}
            if runners:
                if len(runners) > 1 or not langs <= set(runner_langs):
                    raise ParseError(
                        f"ステップ{number}「{title}」: ansible/playbook フェンスと"
                        f"他の言語のフェンスは混在できません"
                    )
                step.runner = runners.pop()
            step.command = "\n".join(text for _, text in blocks).strip()
        else:
            step.command = _plain_text(sections["command"])
    if not step.command:
        raise ParseError(f"ステップ{number}「{title}」: コマンドがありません")

    if "criteria" in sections:
        blocks = _extract_code_blocks(sections["criteria"])
        text = blocks[0][1].strip() if blocks else _plain_text(sections["criteria"])
        if text:
            step.criteria = text

    if "options" in sections:
        blocks = _extract_code_blocks(sections["options"])
        text = blocks[0][1] if blocks else _plain_text(sections["options"])
        opts = yaml.safe_load(text) or {}
        if not isinstance(opts, dict):
            raise ParseError(f"ステップ{number}「{title}」: RB-LOCALDEF は YAML の辞書で書いてください")
        if "timeout" in opts:
            step.timeout = float(opts["timeout"])
        if "cwd" in opts:
            step.cwd = str(opts["cwd"])
        if "ansible" in opts:
            if not isinstance(opts["ansible"], dict):
                raise ParseError(f"ステップ{number}「{title}」: RB-LOCALDEF の ansible は辞書で書いてください")
            step.ansible = opts["ansible"]
        unknown = set(opts) - {"timeout", "cwd", "ansible"}
        if unknown:
            raise ParseError(f"ステップ{number}「{title}」: RB-LOCALDEF に不明なキー {sorted(unknown)}"
                             f"(使用可能: timeout, cwd, ansible)")

    return step


def _merge_ansible_cfg(step: Step, defaults: dict, variables: dict[str, str],
                       ctx: str) -> tuple[str | None, str | None, str]:
    """共通設定(```runbook フェンス)の ansible: とステップ設定をマージし、
    (inventory, target, extra_args) を返す。

    inventory は共通設定では指定できない(parse_file で拒否)ため、
    ステップ設定にある場合のみ値が入る。host_matrix の反映もここで行う。
    必須チェックは呼び出し側の責務。
    """
    cfg = {**defaults, **step.ansible}
    unknown = set(cfg) - {"inventory", "target", "extra_args", "host_matrix"}
    if unknown:
        raise ParseError(f"{ctx}: 不明な ansible 設定 {sorted(unknown)} "
                         f"(使用可能: inventory, target, extra_args, host_matrix)")
    host_matrix = cfg.get("host_matrix", False)
    if not isinstance(host_matrix, bool):
        raise ParseError(f"{ctx}: ansible の host_matrix は true/false で指定してください")
    step.host_matrix = host_matrix

    inventory = cfg.get("inventory")
    target = cfg.get("target")
    inventory = substitute_vars(str(inventory), variables, ctx) if inventory else None
    target = substitute_vars(str(target), variables, ctx) if target else None
    extra_args = substitute_vars(str(cfg.get("extra_args", "")), variables, ctx).strip()
    return inventory, target, extra_args


def _resolve_ansible_command(step: Step, defaults: dict, variables: dict[str, str]) -> None:
    """```ansible フェンスのステップを ansible ad-hoc(shellモジュール)コマンドに組み立てる。

    target は共通設定の ansible: を既定にできるが、inventory は
    意図しない環境での実行を防ぐため共通既定を持たず、ステップの
    RB-LOCALDEF(ansible: {...})か行内指定で毎回指定する。

    フェンスの中身(リモートコマンド)には runbook のテキスト置換を行わない。
    手順書の変数は extra-vars(-e JSON)として渡し、ansible の jinja2 に
    {{VAR}} をそのまま解決させる。これにより {{ inventory_hostname }} などの
    jinja2 記法とバッティングしない。

    行内指定: フェンスの1行目が `ansible ` で始まる場合、その行を起動指定
    (ターゲット・-i・オプション)としてそのまま使い、設定側の target /
    inventory は使わない。2行目以降がリモートコマンドになる:

        ```ansible
        ansible dbservers -i inventories/db.ini
        df -h /
        ```

    起動指定行はコントローラ側の値なので {{VAR}} のテキスト置換が効く。
    行内に書いた -e は自動付与の -e JSON より後ろに並ぶため優先される。
    """
    ctx = f"ステップ{step.number}「{step.title}」"
    inventory, target, extra_args = _merge_ansible_cfg(step, defaults, variables, ctx)

    lines = step.command.splitlines()
    inline_args = None
    if lines and re.match(r"^ansible(\s|$)", lines[0].strip()):
        inline_args = substitute_vars(lines[0].strip()[len("ansible"):].strip(), variables, ctx)
        if not inline_args:
            raise ParseError(f"{ctx}: 1行目の ansible の後にターゲットや -i を書いてください")
        step.remote_command = "\n".join(lines[1:]).strip()
        if not step.remote_command:
            raise ParseError(f"{ctx}: 起動指定行(ansible ...)の後にリモートコマンドがありません")
    else:
        step.remote_command = step.command

    if inline_args is not None:
        # 自動付与の -e JSON を先に置き、行内の -e が後ろ=優先になるようにする
        parts = ["ansible"]
        if variables:
            parts += ["-e", shlex.quote(json.dumps(variables, ensure_ascii=False))]
        parts.append(inline_args)
        step.inventories = _extract_inventory_values(inline_args)
    else:
        if not inventory:
            raise ParseError(f"{ctx}: ansible の inventory が未指定です"
                             f"(ステップの RB-LOCALDEF の ansible: inventory か、フェンス1行目の ansible 行で毎回指定)")
        if not target:
            raise ParseError(f"{ctx}: ansible の target(ホストグループ/ホスト名)が未指定です"
                             f"(共通設定/RB-LOCALDEF の ansible: か、フェンス1行目の ansible 行で指定)")
        parts = ["ansible", shlex.quote(target), "-i", shlex.quote(inventory)]
        if variables:
            parts += ["-e", shlex.quote(json.dumps(variables, ensure_ascii=False))]
        step.inventories = [inventory]
    if extra_args:
        parts.append(extra_args)
    parts += ["-m", "shell", "-a", shlex.quote(step.remote_command)]
    step.command = " ".join(parts)


_PLAYBOOK_INLINE_PATTERN = re.compile(r"^ansible-playbook(\s|$)")


def _resolve_playbook_command(step: Step, defaults: dict, variables: dict[str, str]) -> None:
    """```playbook フェンスのステップを ansible-playbook コマンドに組み立てる。

    フェンスの各行は、行が `ansible-playbook` で始まるかどうかで 2 つのスタイルに
    分かれる(行単位判定・1 フェンス内で混在可。ansible ad-hoc の行内指定 §7.3 と
    対称: 「行が実行コマンド名で始まれば行内指定、始まらなければ設定指定」)。

    設定指定スタイル: 行そのものを「プレイブックのパスに続けて書くオプション列」
    として扱う:

        ```playbook
        deploy.yml -e HOGE=PIYO --check
        ```

    行内指定スタイル: 行の `ansible-playbook` に続く残り部分を起動指定として
    そのまま使い、設定側の inventory / target は付与しない(inventory 必須
    チェックもしない):

        ```playbook
        ansible-playbook -i inventories/web.ini deploy.yml -e HOGE=PIYO --check
        ```

    いずれのスタイルも行の内容はコントローラ側の値なので {{VAR}} のテキスト置換が
    効く(置換は parse_file 側で実施済み)。手順書の変数は ad-hoc と同様 -e JSON
    でも渡すので、プレイブック内の jinja2 からそのまま参照できる。行に書いた -e は
    自動付与の -e より後ろに並ぶため、同名変数は行に書いた値が優先される。
    設定指定スタイルで target を指定した場合は -l(limit)として対象ホストを
    絞り込む。複数行は && で連結し、1つでも失敗したら以降は実行されない。
    """
    ctx = f"ステップ{step.number}「{step.title}」"
    inventory, target, extra_args = _merge_ansible_cfg(step, defaults, variables, ctx)

    lines = [line.strip() for line in step.command.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    if not lines:
        raise ParseError(f"{ctx}: playbook フェンスにプレイブックのファイルパス"
                         f"(と必要ならオプション)を書いてください")

    step.remote_command = "\n".join(lines)
    cmds = []
    used_inventories: list[str] = []
    for line in lines:
        if _PLAYBOOK_INLINE_PATTERN.match(line):
            # 行内指定: 起動指定をそのまま使い、設定側の inventory / target は
            # 付与しない(ansible ad-hoc の行内指定 §7.3 と同じ扱い)。
            rest = line[len("ansible-playbook"):].strip()
            if not rest:
                raise ParseError(f"{ctx}: 行内指定(ansible-playbook ...)の後に引数がありません: {line!r}")
            base = ["ansible-playbook"]
            if variables:
                base += ["-e", shlex.quote(json.dumps(variables, ensure_ascii=False))]
            base.append(rest)
            if extra_args:
                base.append(extra_args)
            used_inventories += _extract_inventory_values(rest)
            cmds.append(" ".join(base))
            continue

        base = ["ansible-playbook"]
        # 行内に -i があればそちらを使う(設定側インベントリは付与しない)。
        # ansible は複数の -i を「結合」してしまうため、二重付与は事故のもと。
        if _has_inventory_option(line):
            used_inventories += _extract_inventory_values(line)
        elif inventory:
            base += ["-i", shlex.quote(inventory)]
            used_inventories.append(inventory)
        else:
            raise ParseError(
                f"{ctx}: インベントリが未指定です。ステップの RB-LOCALDEF の ansible: inventory を"
                f"指定するか、行内に -i <インベントリ> を書いてください: {line!r}")
        if target:
            base += ["-l", shlex.quote(target)]
        if variables:
            base += ["-e", shlex.quote(json.dumps(variables, ensure_ascii=False))]
        if extra_args:
            base.append(extra_args)
        cmds.append(" ".join(base + [line]))
    step.command = " && ".join(cmds)
    seen: set[str] = set()
    step.inventories = [inv for inv in used_inventories if not (inv in seen or seen.add(inv))]


def _tokenize(line: str) -> list[str]:
    try:
        return shlex.split(line)
    except ValueError:  # クォート不整合時は素朴に分割して判定
        return line.split()


def _has_inventory_option(line: str) -> bool:
    """行内に -i / --inventory 指定が含まれるか"""
    return any(
        tok.startswith("--inventory") or (tok.startswith("-i") and not tok.startswith("--"))
        for tok in _tokenize(line)
    )


def _extract_inventory_values(line: str) -> list[str]:
    """行内の -i / --inventory 指定からインベントリ値を取り出す(実行前サマリー表示用)"""
    tokens = _tokenize(line)
    values: list[str] = []
    for i, tok in enumerate(tokens):
        if tok in ("-i", "--inventory"):
            if i + 1 < len(tokens):
                values.append(tokens[i + 1])
        elif tok.startswith("--inventory="):
            values.append(tok.split("=", 1)[1])
        elif tok.startswith("-i") and not tok.startswith("--") and len(tok) > 2:
            values.append(tok[2:])
    return values


def substitute_vars(text: str, variables: dict[str, str], context: str) -> str:
    """{{VAR}} を置換する。未定義変数はエラー。"""

    def repl(m: re.Match) -> str:
        name = m.group(1)
        if name not in variables:
            raise ParseError(f"{context}: 変数 {{{{{name}}}}} が未定義です(共通設定の vars か --var で指定)")
        return str(variables[name])

    return _VAR_PATTERN.sub(repl, text)


# runbook が解釈する共通設定キー。frontmatter にこれらが書かれていた場合は
# 「書いたのに効いていない」事故を防ぐためエラーにする(それ以外の frontmatter は
# 一般的な Markdown メタデータとして単に読み飛ばす)。
_CONFIG_KEYS = {"vars", "ansible", "secrets"}


def _reject_config_in_frontmatter(frontmatter: dict) -> None:
    bad = sorted(_CONFIG_KEYS & set(frontmatter))
    if bad:
        raise ParseError(
            f"frontmatter に runbook の設定キー {bad} は書けません。"
            f"共通設定は最初のステップより前の ```runbook フェンスに書いてください"
            f"(frontmatter は一般的な Markdown メタデータ用で、runbook は解釈しません)")


def _extract_preamble_config(preamble_lines: list[str]) -> dict:
    """前書き(最初の ## より前)の ```runbook フェンスから共通設定を取り出す。

    ```runbook フェンスの中身は YAML(title / vars / ansible / secrets)。
    未知のキー(share_env など)は他の未知キーと同様に黙って無視する。
    コードフェンスは CommonMark 標準要素なので、どの Markdown プレビューでも
    確実に表示される。
    """
    blocks = [text for lang, text in _extract_code_blocks(preamble_lines) if lang == "runbook"]
    if not blocks:
        return {}
    if len(blocks) > 1:
        raise ParseError("```runbook(共通設定)フェンスが複数あります。1つにまとめてください")
    config = yaml.safe_load(blocks[0]) or {}
    if not isinstance(config, dict):
        raise ParseError("```runbook フェンスの中身は YAML の辞書で書いてください")
    return config


def parse_file(path: str | Path, extra_vars: dict[str, str] | None = None) -> Procedure:
    path = Path(path)
    # frontmatter は一般的な Markdown メタデータとして読み飛ばすだけ
    # (設定キーが紛れ込んでいる場合のみエラー)。共通設定は ```runbook フェンス。
    frontmatter, body, offset = _split_frontmatter(path.read_text(encoding="utf-8"))
    _reject_config_in_frontmatter(frontmatter)

    lines = body.splitlines()
    title_heading = ""

    # ステップ分割("## " 見出し単位)。"# " はタイトル扱い。
    # 最初の "## " より前の行は前書き(preamble)として保持し、
    # ```runbook フェンス(手順書設定)の抽出に使う。
    # "# RB-ROLLBACK" 見出し(v0.5.0 で削除された切り戻し機能)がフェンス外に
    # 現れたら、黙って通常見出しとして扱わず即エラーにする(fail-loud 原則)。
    steps_raw: list[tuple[str, list[str], int]] = []
    preamble: list[str] = []
    current_title: str | None = None
    current_lines: list[str] = []
    current_start = 0
    in_fence = False

    def flush() -> None:
        nonlocal current_title, current_lines
        if current_title is not None:
            steps_raw.append((current_title, current_lines, current_start))
        current_title = None
        current_lines = []

    for i, line in enumerate(lines):
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
        if not in_fence:
            if _ROLLBACK_PATTERN.match(line):
                raise ParseError(
                    f"{path}: 切り戻し機能(# RB-ROLLBACK)は v0.5.0 で削除されました。"
                    f"切り戻し手順は別ファイルの手順書として作成してください")
            m2 = re.match(r"^##\s+(.+?)\s*$", line)
            if m2:
                flush()
                current_title = m2.group(1)
                current_start = offset + i + 1
                continue
            if current_title is None:
                m1 = re.match(r"^#\s+(.+?)\s*$", line)
                if m1 and not title_heading:
                    title_heading = m1.group(1)
                    continue
        if current_title is not None:
            current_lines.append(line)
        else:
            preamble.append(line)
    flush()

    if not steps_raw:
        raise ParseError(f"{path}: ステップ(## 見出し)が 1 つもありません")

    meta = _extract_preamble_config(preamble)
    title = str(meta.get("title", "")) or title_heading

    variables = {str(k): str(v) for k, v in (meta.get("vars") or {}).items()}
    variables.update(extra_vars or {})

    steps: list[Step] = []
    for raw_title, raw_lines, start in steps_raw:
        heading_number, clean_title = split_heading_number(raw_title)
        step = _parse_step(len(steps) + 1, clean_title, raw_lines, start)
        step.heading_number = heading_number
        steps.append(step)

    # 変数置換(コマンドと正常性基準に適用)。
    # ansible フェンスの中身は jinja2 の世界なのでテキスト置換しない。
    # 代わりに _resolve_ansible_command で全変数を -e として渡し、
    # ansible 側で同じ {{VAR}} 記法のまま解決させる。
    for step in steps:
        ctx = f"ステップ{step.number}「{step.title}」"
        if step.runner != "ansible":
            step.command = substitute_vars(step.command, variables, ctx)
        step.criteria = substitute_vars(step.criteria, variables, ctx)

    # ansible ステップの実行コマンド組み立て
    ansible_defaults = meta.get("ansible") or {}
    if not isinstance(ansible_defaults, dict):
        raise ParseError("共通設定の ansible は辞書(target/extra_args/host_matrix)で書いてください")
    if "inventory" in ansible_defaults:
        # インベントリの共通デフォルトは許可しない。デフォルトがあると、ステップでの
        # 指定漏れがエラーにならず「意図しない環境」で実行される事故につながるため、
        # ansible 系ステップごとの明示指定(設定 or 行内)を必須とする。
        raise ParseError(
            "共通設定(```runbook フェンス)の ansible に inventory は指定できません。"
            "インベントリは各ステップの RB-LOCALDEF(ansible: inventory)か"
            "行内(-i / 1行目の ansible 行)で毎回指定してください")
    for step in steps:
        if step.runner == "ansible":
            _resolve_ansible_command(step, ansible_defaults, variables)
        elif step.runner == "playbook":
            _resolve_playbook_command(step, ansible_defaults, variables)

    # secrets: 値を表示・ログからマスクする変数名の明示宣言。
    # プレフィックス等の暗黙の命名規則ではなく明示宣言方式(fail-loud):
    # 宣言した変数が未定義なら「書いたのに効かない」事故防止のためエラー。
    secrets = meta.get("secrets") or []
    if not isinstance(secrets, list) or not all(isinstance(s, str) for s in secrets):
        raise ParseError("共通設定の secrets は変数名のリストで書いてください(例: secrets: [DB_PASS])")
    for name in secrets:
        if name not in variables:
            raise ParseError(f"secrets に宣言された変数 {name} が定義されていません"
                             f"(共通設定の vars か --var で定義してください)")

    return Procedure(path=path, title=title or path.stem, vars=variables, steps=steps,
                     secrets=secrets)
