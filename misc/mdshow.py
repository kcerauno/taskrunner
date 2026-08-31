#!/usr/bin/env python3
"""python3 -m rich.markdown の代替: 見出し左寄せ + 余計な空行なし"""
import sys
from rich.console import Console
from rich.markdown import Markdown, Heading, CodeBlock, Paragraph, ListItem
from rich.syntax import Syntax


class LeftHeading(Heading):
    LEVEL_ALIGN = dict.fromkeys(Heading.LEVEL_ALIGN, "left")


class TightCodeBlock(CodeBlock):
    def __rich_console__(self, console, options):
        yield Syntax(str(self.text).rstrip(), self.lexer_name,
                     theme=self.theme, word_wrap=True, padding=0)


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
    md = TightMarkdown(src, justify=None)
    with console.capture() as cap:
        console.print(md)
    sys.stdout.write("\n".join(l.rstrip() for l in cap.get().split("\n")).strip("\n") + "\n")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--tight"]
    main(args[0], "--tight" in sys.argv)
