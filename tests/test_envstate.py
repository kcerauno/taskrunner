from runbook.envstate import EnvManager, EnvOverlay, diff_env


# ---- diff_env -----------------------------------------------------------

def test_diff_env_add_change_delete_unchanged():
    baseline = {"A": "1", "B": "2", "C": "3"}
    snapshot = {"A": "1a", "C": "3", "D": "new"}  # A変更, B削除, C不変, D追加
    overlay = diff_env(baseline, snapshot)
    assert overlay.sets == {"A": "1a", "D": "new"}
    assert overlay.unsets == {"B"}


def test_diff_env_no_changes_yields_empty_overlay():
    baseline = {"A": "1", "B": "2"}
    snapshot = {"A": "1", "B": "2"}
    overlay = diff_env(baseline, snapshot)
    assert overlay.sets == {}
    assert overlay.unsets == set()


def test_diff_env_excludes_noise_vars():
    baseline = {"SHLVL": "1", "PWD": "/a", "OLDPWD": "/b", "_": "c"}
    snapshot = {"SHLVL": "2", "PWD": "/z"}  # OLDPWD と _ は unset 相当、SHLVL/PWD は変更
    overlay = diff_env(baseline, snapshot)
    assert overlay.sets == {}
    assert overlay.unsets == set()


def test_diff_env_excluded_var_not_reported_even_if_newly_added():
    baseline: dict[str, str] = {}
    snapshot = {"SHLVL": "1", "REAL": "x"}
    overlay = diff_env(baseline, snapshot)
    assert overlay.sets == {"REAL": "x"}


# ---- to_script / from_script 往復 ----------------------------------------

def test_to_script_empty_overlay_is_comment_only():
    overlay = EnvOverlay(sets={}, unsets=set())
    assert overlay.to_script() == "# runbook env overlay (auto-generated)\n"


def test_to_script_sorted_keys_and_quoting():
    overlay = EnvOverlay(sets={"B": "2", "A": "1 x"}, unsets={"Z", "Y"})
    lines = overlay.to_script().splitlines()
    assert lines[0] == "# runbook env overlay (auto-generated)"
    assert lines[1] == "export A='1 x'"
    assert lines[2] == "export B=2"
    assert lines[3] == "unset Y"
    assert lines[4] == "unset Z"


def test_roundtrip_normal_values():
    overlay = EnvOverlay(sets={"FOO": "bar", "BAZ": "qux"}, unsets={"OLD"})
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == overlay.sets
    assert parsed.unsets == overlay.unsets


def test_roundtrip_empty_string_value():
    overlay = EnvOverlay(sets={"EMPTY": ""}, unsets=set())
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == {"EMPTY": ""}


def test_roundtrip_single_quote_in_value():
    overlay = EnvOverlay(sets={"MSG": "it's a test"}, unsets=set())
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == {"MSG": "it's a test"}


def test_roundtrip_newline_in_value():
    overlay = EnvOverlay(sets={"MULTI": "line1\nline2\nline3"}, unsets=set())
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == {"MULTI": "line1\nline2\nline3"}


def test_roundtrip_dollar_sign_in_value():
    overlay = EnvOverlay(sets={"PATHLIKE": "$HOME/bin:$PATH"}, unsets=set())
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == {"PATHLIKE": "$HOME/bin:$PATH"}


def test_roundtrip_japanese_value():
    overlay = EnvOverlay(sets={"MSG": "日本語の値です"}, unsets=set())
    parsed = EnvOverlay.from_script(overlay.to_script())
    assert parsed.sets == {"MSG": "日本語の値です"}


def test_roundtrip_mixed_all_special_cases_together():
    values = {
        "PLAIN": "hello",
        "EMPTY": "",
        "QUOTE": "it's a \"test\"",
        "NEWLINE": "line1\nline2",
        "DOLLAR": "$HOME/bin",
        "JP": "日本語の値、カンマや記号も$含む",
    }
    overlay = EnvOverlay(sets=values, unsets={"REMOVED_A", "REMOVED_B"})
    script = overlay.to_script()
    parsed = EnvOverlay.from_script(script)
    assert parsed.sets == values
    assert parsed.unsets == {"REMOVED_A", "REMOVED_B"}


def test_from_script_ignores_comment_header():
    text = "# runbook env overlay (auto-generated)\nexport A=1\n"
    parsed = EnvOverlay.from_script(text)
    assert parsed.sets == {"A": "1"}


def test_from_script_unrecognized_token_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        EnvOverlay.from_script("foo bar\n")


def test_from_script_export_without_token_raises():
    import pytest
    with pytest.raises(ValueError):
        EnvOverlay.from_script("export\n")


def test_from_script_export_without_equals_raises():
    import pytest
    with pytest.raises(ValueError):
        EnvOverlay.from_script("export FOO\n")


def test_from_script_unset_without_key_raises():
    import pytest
    with pytest.raises(ValueError):
        EnvOverlay.from_script("unset\n")


# ---- apply ----------------------------------------------------------------

def test_apply_sets_override_and_unsets_remove():
    base = {"A": "1", "B": "2", "C": "3"}
    overlay = EnvOverlay(sets={"A": "1a", "D": "4"}, unsets={"B"})
    result = overlay.apply(base)
    assert result == {"A": "1a", "C": "3", "D": "4"}
    # base 自体は変更されない
    assert base == {"A": "1", "B": "2", "C": "3"}


def test_apply_unset_of_baseline_var_is_tombstoned():
    base = {"X": "orig", "Y": "keep"}
    overlay = EnvOverlay(sets={}, unsets={"X"})
    assert overlay.apply(base) == {"Y": "keep"}


# ---- EnvManager -------------------------------------------------------------

def test_env_manager_child_env_is_baseline_when_no_overlay():
    mgr = EnvManager({"A": "1", "B": "2"})
    assert mgr.child_env() == {"A": "1", "B": "2"}


def test_env_manager_baseline_is_copied_not_referenced():
    baseline = {"A": "1"}
    mgr = EnvManager(baseline)
    baseline["A"] = "mutated"
    baseline["NEW"] = "x"
    assert mgr.child_env() == {"A": "1"}


def test_env_manager_none_baseline_uses_os_environ(monkeypatch):
    monkeypatch.setenv("RUNBOOK_ENVSTATE_TEST_VAR", "yes")
    mgr = EnvManager()
    assert mgr.baseline.get("RUNBOOK_ENVSTATE_TEST_VAR") == "yes"


def test_env_manager_update_from_snapshot_reflects_in_child_env():
    mgr = EnvManager({"A": "1", "B": "2"})
    mgr.update_from_snapshot({"A": "1a", "B": "2"})
    assert mgr.child_env() == {"A": "1a", "B": "2"}


def test_env_manager_update_from_snapshot_unset_var():
    mgr = EnvManager({"A": "1", "B": "2"})
    mgr.update_from_snapshot({"A": "1"})  # B が export -p から消えた(unset された)
    assert mgr.child_env() == {"A": "1"}


def test_env_manager_load_overlay_script_and_overlay_script_roundtrip():
    mgr = EnvManager({"A": "1"})
    mgr.overlay = EnvOverlay(sets={"NEW": "x"}, unsets={"OLD"})
    script = mgr.overlay_script()

    mgr2 = EnvManager({"A": "1"})
    mgr2.load_overlay_script(script)
    assert mgr2.overlay.sets == {"NEW": "x"}
    assert mgr2.overlay.unsets == {"OLD"}
    assert mgr2.child_env() == {"A": "1", "NEW": "x"}
