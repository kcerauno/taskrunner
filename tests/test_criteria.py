import pytest

from runbook.criteria import CriteriaError, evaluate, validate


def test_rc_only():
    assert evaluate("rc == 0", 0, "", "")
    assert not evaluate("rc == 0", 1, "", "")
    assert evaluate("exit_code == 2", 2, "", "")


def test_regex_out_err_match():
    assert evaluate('out("act.ve")', 0, "service is active", "")
    assert not evaluate('out("ERROR")', 0, "all good", "")
    assert evaluate('err("WARN")', 0, "", "WARN: disk")
    assert evaluate('match("WARN")', 0, "", "WARN: disk")


def test_logical_operators():
    expr = 'rc == 0 and out("OK") and not out("ERROR|FATAL")'
    assert evaluate(expr, 0, "OK done", "")
    assert not evaluate(expr, 0, "OK but ERROR", "")
    assert evaluate('(rc == 0 or rc == 2) and out("done")', 2, "done", "")


def test_in_operator():
    assert evaluate('"failed=0" in stdout', 0, "ok=3 failed=0", "")
    assert evaluate('"fatal" not in stderr', 0, "", "clean")


def test_multiline_expression():
    expr = 'rc == 0 and\nout("A") and\nout("B")'
    assert evaluate(expr, 0, "A B", "")


def test_unsafe_constructs_rejected():
    for expr in [
        "__import__('os').system('true')",
        "open('/etc/passwd')",
        "stdout.upper()",
        "[x for x in stdout]",
        "unknown_name",
    ]:
        with pytest.raises(CriteriaError):
            evaluate(expr, 0, "", "")


def test_regex_backslash_escape_no_warning():
    # 正規表現の \| \d を文字列内にそのまま書いても SyntaxWarning を出さず評価できる
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert evaluate('out("web01 \\| CHANGED") and out("rc=\\d+")',
                        0, "web01 | CHANGED | rc=0 >>", "")


def test_validate():
    validate('rc == 0 and out("OK")')
    with pytest.raises(CriteriaError):
        validate('out("[unclosed")')  # 不正な正規表現
    with pytest.raises(CriteriaError):
        validate("rc ==")  # 構文エラー


def test_diagnose_and_chain():
    from runbook.criteria import diagnose
    expr = 'rc == 0 and out("OK") and not out("ERROR")'
    result = diagnose(expr, 0, "OK but ERROR", "")
    assert result == [
        ("rc == 0", True),
        ('out("OK")', True),
        ('not out("ERROR")', False),
    ]


def test_diagnose_or_group_kept_whole():
    """or のまとまりは作成者の1つの判断単位として分解しない"""
    from runbook.criteria import diagnose
    expr = '(rc == 0 or rc == 2) and "failed=0" in stdout'
    result = diagnose(expr, 2, "failed=1", "")
    assert result == [
        ("rc == 0 or rc == 2", True),
        ('"failed=0" in stdout', False),
    ]


def test_diagnose_multiline_expr_flattened():
    from runbook.criteria import diagnose
    expr = 'rc == 0 and\nout("A") and\nout("B")'
    result = diagnose(expr, 0, "A only", "")
    assert result == [
        ("rc == 0", True),
        ('out("A")', True),
        ('out("B")', False),
    ]


def test_diagnose_single_condition():
    from runbook.criteria import diagnose
    assert diagnose("rc == 0", 1, "", "") == [("rc == 0", False)]


def test_diagnose_invalid_expr_returns_empty():
    from runbook.criteria import diagnose
    assert diagnose("rc ==", 0, "", "") == []


def test_diagnose_consistent_with_evaluate():
    """診断の各条件の and 合成は evaluate の全体結果と一致する"""
    from runbook.criteria import diagnose
    expr = 'rc == 0 and out("active") and not err("fatal")'
    for rc, out_s, err_s in [(0, "active", ""), (1, "active", ""), (0, "dead", "fatal")]:
        whole = evaluate(expr, rc, out_s, err_s)
        parts = diagnose(expr, rc, out_s, err_s)
        assert all(ok for _, ok in parts) == whole
