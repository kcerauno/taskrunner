#!/usr/bin/env python3
"""python3 -m rich.markdown の代替: 見出し左寄せ + 余計な空行なし

runbook 手順書向けに、レンダラが落としてしまう情報を補って表示する(§preprocess)。
"""
import re
import sys
from rich.console import Console
from rich.markdown import Markdown, Heading, CodeBlock, Paragraph, ListItem
from rich.syntax import Syntax


class LeftHeading(Heading):
    LEVEL_ALIGN = dict.fromkeys(Heading.LEVEL_ALIGN, "left")


# runbook 独自のフェンス言語名は Pygments が知らず無着色になるため、近い lexer に読み替える
# (VSCode 拡張の syntaxes/runbook-injection.json と同じ対応付け)
FENCE_LEXERS = {
    "runbook": "yaml",            # 共通設定フェンス(YAML)
    "ansible": "bash",            # ad-hoc: 中身はリモートで実行される shell コマンド
    "playbook": "bash",           # 各行が ansible-playbook の引数列
    "ansible-playbook": "bash",
}


class TightCodeBlock(CodeBlock):
    def __rich_console__(self, console, options):
        lexer = FENCE_LEXERS.get((self.lexer_name or "").lower(), self.lexer_name)
        yield Syntax(str(self.text).rstrip(), lexer,
                     theme=self.theme, word_wrap=True, padding=0)


# ランナーを示すフェンス言語名は、レンダリングすると消えて中身だけが残る。
# 中身は「手元で打つコマンド」ではない(ad-hoc は対象ホスト側で実行され、playbook は
# そもそもコマンドですらなく引数列)ため、どのランナーのフェンスかを見出しとして補う。
RUNNER_LABELS = {
    "ansible": "▶ ansible ad-hoc",
    "playbook": "▶ ansible-playbook",
    "ansible-playbook": "▶ ansible-playbook",
}

# RB-EXPECTED の判定式は言語名なしフェンスで書くため無着色になる。
# 式の文法は Python 風(and / not / == / 文字列)なので python lexer を当てる。
CRITERIA_LEXER = "python"

_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(\S*)\s*$")


def preprocess(src: str) -> str:
    """runbook 手順書のフェンスに、表示に必要な情報を補う。

    - ansible / playbook フェンスの直前にランナー名の行を挿入する
    - RB-EXPECTED 直下の言語名なしフェンスに python lexer を割り当てる

    どちらもフェンスの開始行だけを見て判断し、フェンスの中身には手を触れない。
    """
    out, opener, section = [], None, None
    for line in src.split("\n"):
        m = _FENCE_RE.match(line)
        if opener is not None:
            # CommonMark と同じ規則: 開始フェンスと同じ文字・同じ長さ以上で、
            # 言語名のない行だけが閉じフェンス(````markdown の中の ``` は中身のまま)
            if m and m.group(2)[0] == opener[0] and len(m.group(2)) >= len(opener) and not m.group(3):
                opener = None
            out.append(line)
            continue
        if m:
            opener = m.group(2)
            lang = m.group(3).lower()
            label = RUNNER_LABELS.get(lang)
            if label:
                if out and out[-1].strip():
                    out.append("")
                out.append(f"{m.group(1)}**{label}**")   # リスト内のフェンスでは字下げを保つ
                out.append("")
            elif not lang and section == "rb-expected":
                line = f"{m.group(1)}{m.group(2)}{CRITERIA_LEXER}"
            out.append(line)
            continue
        h = re.match(r"^###\s+(.+?)\s*$", line)
        if h:
            section = h.group(1).strip().lower()
        out.append(line)
    return "\n".join(out)


class TightMarkdown(Markdown):
    elements = {
        **Markdown.elements,
        "heading_open": LeftHeading,
        "fence": TightCodeBlock,
        "code_block": TightCodeBlock,
    }


def main(path, tight=False):
    src = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    if tight:
        for cls in (Paragraph, LeftHeading, ListItem):
            cls.new_line = False
    console = Console(soft_wrap=False)
    md = TightMarkdown(preprocess(src), justify=None)
    with console.capture() as cap:
        console.print(md)
    sys.stdout.write("\n".join(l.rstrip() for l in cap.get().split("\n")).strip("\n") + "\n")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--tight"]
    main(args[0], "--tight" in sys.argv)
