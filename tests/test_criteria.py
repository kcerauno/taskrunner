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


def test_term_evidence_reports_match_count_and_first_line():
    """案R6: out() のマッチ行数と初出行を返す(NG時に出力を目で探さずに済む)"""
    from runbook.criteria import term_evidence
    stdout = "hello world\nnoise 1\nnoise 2\nnoise 3"
    ev = term_evidence('not out("noise")', 0, stdout, "")
    assert "3行がマッチ" in ev
    assert "初出 L2" in ev
    assert "noise 1" in ev


def test_term_evidence_reports_no_match():
    from runbook.criteria import term_evidence
    ev = term_evidence('out("ABSENT")', 0, "hello", "")
    assert "stdout にマッチなし" in ev


def test_term_evidence_includes_actual_rc():
    from runbook.criteria import term_evidence
    assert "実際 rc=3" in term_evidence("rc == 0", 3, "", "")


def test_term_evidence_targets_err_and_match_separately():
    from runbook.criteria import term_evidence
    assert "stderr の1行がマッチ" in term_evidence('err("boom")', 0, "", "boom")
    assert "stdout+stderr の1行がマッチ" in term_evidence('match("boom")', 0, "", "boom")


def test_term_evidence_multiline_pattern_falls_back_to_whole_text():
    """行をまたぐパターンは行単位検索で拾えないため全文で確認する"""
    from runbook.criteria import term_evidence
    ev = term_evidence(r'out("a\nb")', 0, "a\nb", "")
    assert "複数行にまたがる" in ev


def test_term_evidence_truncates_long_line():
    from runbook.criteria import term_evidence
    ev = term_evidence('out("x")', 0, "x" * 200, "", max_len=20)
    assert "…" in ev
    assert len(ev) < 100


def test_term_evidence_invalid_expr_returns_empty():
    from runbook.criteria import term_evidence
    assert term_evidence("rc ==", 0, "", "") == ""


def test_diagnose_return_shape_unchanged():
    """案R6 は diagnose の戻り値(2要素タプル)を変えない"""
    from runbook.criteria import diagnose
    result = diagnose('rc == 0 and out("A")', 0, "A", "")
    assert all(isinstance(r, tuple) and len(r) == 2 for r in result)
