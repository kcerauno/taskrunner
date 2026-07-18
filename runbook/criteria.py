"""正常性基準の評価器。

基準は Python 風の論理式で書く。使える要素だけを AST で検査してから
評価するため、任意コード実行はできない。

使える名前・関数:
    rc / exit_code      : コマンドの終了コード (int)
    stdout / stderr     : 出力全文 (str)。 "OK" in stdout のように使える
    out("正規表現")     : 標準出力に正規表現がマッチすれば True
    err("正規表現")     : 標準エラーに正規表現がマッチすれば True
    match("正規表現")   : 標準出力+標準エラーを対象に検索

演算: and / or / not / == != < <= > >= / in / not in / ( )

例:
    rc == 0
    rc == 0 and out("active \\(running\\)") and not out("ERROR|WARN")
    (rc == 0 or rc == 2) and "failed=0" in stdout
"""

from __future__ import annotations

import ast
import operator
import re
import warnings

_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class CriteriaError(Exception):
    """基準式の構文・評価エラー"""


def validate(expr: str) -> None:
    """構文のみ検査する(check サブコマンド用)。エラー時は CriteriaError。"""
    evaluate(expr, rc=0, stdout="", stderr="", _validate_only=True)


def diagnose(expr: str, rc: int, stdout: str, stderr: str) -> list[tuple[str, bool]]:
    """判定の詳細診断: 基準式を and / or の結合単位に分解し、
    各条件の原文と真偽を [(条件式, True/False), ...] で返す。

    NG になったとき「どの条件で落ちたか」を即読めるようにするためのもの。
    分解するのは and の結合のみ。or のまとまり((rc == 0 or rc == 2) など)や
    not X は、作成者が書いた1つの判断単位としてそのまま評価する。
    and/or は短絡せず全値を評価する仕様(evaluate と同じ)なので、
    個別評価と全体の結果は一致する。
    診断は補助情報のため、失敗時は空リストを返す(例外にしない)。
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            src = f"({expr})"
            tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return []

    atoms: list[ast.AST] = []

    def collect(node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            collect(node.body)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            for v in node.values:
                collect(v)
        else:
            atoms.append(node)

    collect(tree)

    results: list[tuple[str, bool]] = []
    for node in atoms:
        text = ast.get_source_segment(src, node) or ast.unparse(node)
        text = " ".join(text.split())  # 複数行の条件は1行に整形
        try:
            ok = evaluate(text, rc, stdout, stderr)
        except CriteriaError:
            continue
        results.append((text, ok))
    return results


def evaluate(expr: str, rc: int, stdout: str, stderr: str, _validate_only: bool = False) -> bool:
    try:
        # 括弧で包むことで複数行の式も許容する。
        # 正規表現用の \| \d などを文字列内にそのまま書けるよう、
        # invalid escape sequence の SyntaxWarning は抑止する
        # (Python は未定義エスケープをバックスラッシュ付きのまま保持する)。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(f"({expr})", mode="eval")
    except SyntaxError as e:
        raise CriteriaError(f"基準式の構文エラー: {e.msg} (式: {expr!r})") from e

    names = {"rc": rc, "exit_code": rc, "stdout": stdout, "stderr": stderr}

    def regex(pattern: str, target: str) -> bool:
        try:
            return re.search(pattern, target) is not None
        except re.error as e:
            raise CriteriaError(f"正規表現エラー: {e} (パターン: {pattern!r})") from e

    funcs = {
        "out": lambda p: regex(p, stdout),
        "err": lambda p: regex(p, stderr),
        "match": lambda p: regex(p, stdout + "\n" + stderr),
    }

    def ev(node: ast.AST):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BoolOp):
            values = [ev(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            raise CriteriaError("使用できない単項演算子です")
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                elif type(op) in _COMPARE_OPS:
                    ok = _COMPARE_OPS[type(op)](left, right)
                else:
                    raise CriteriaError(f"使用できない比較演算子です: {ast.dump(op)}")
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in funcs:
                raise CriteriaError("使用できる関数は out() / err() / match() のみです")
            if len(node.args) != 1 or node.keywords:
                raise CriteriaError(f"{node.func.id}() の引数は正規表現文字列 1 つです")
            arg = node.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                raise CriteriaError(f"{node.func.id}() の引数は文字列リテラルで書いてください")
            if _validate_only:
                # パターンの正当性だけ確認
                try:
                    re.compile(arg.value)
                except re.error as e:
                    raise CriteriaError(f"正規表現エラー: {e} (パターン: {arg.value!r})") from e
                return True
            return funcs[node.func.id](arg.value)
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise CriteriaError(f"使用できない名前です: {node.id} (使用可能: rc, exit_code, stdout, stderr)")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, str, bool)) or node.value is None:
                return node.value
            raise CriteriaError(f"使用できないリテラルです: {node.value!r}")
        raise CriteriaError(f"使用できない構文です: {type(node).__name__}")

    return bool(ev(tree))
