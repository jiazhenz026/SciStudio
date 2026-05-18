"""Tests for ``ci.sarif._common``."""

from __future__ import annotations

from ci.sarif._common import (
    SARIF_SCHEMA,
    SARIF_VERSION,
    collect_rules,
    compute_partial_fingerprint,
    make_log,
    make_result,
    make_run,
    normalize_message,
)


def test_normalize_collapses_whitespace() -> None:
    assert normalize_message("foo  bar\tbaz\n  qux") == "foo bar baz qux"


def test_normalize_strips_ends() -> None:
    assert normalize_message("   foo   ") == "foo"


def test_normalize_empty() -> None:
    assert normalize_message("") == ""
    assert normalize_message("   \n\t  ") == ""


def test_fingerprint_is_32_hex_chars() -> None:
    fp = compute_partial_fingerprint(
        rule_id="F401",
        file_path="src/a.py",
        normalized_message="unused import",
        line=12,
    )
    assert len(fp) == 32
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_stable_across_calls() -> None:
    args = dict(rule_id="F401", file_path="src/a.py", normalized_message="msg", line=12)
    assert compute_partial_fingerprint(**args) == compute_partial_fingerprint(**args)


def test_fingerprint_differs_on_rule() -> None:
    a = compute_partial_fingerprint(rule_id="F401", file_path="src/a.py", normalized_message="m", line=1)
    b = compute_partial_fingerprint(rule_id="F402", file_path="src/a.py", normalized_message="m", line=1)
    assert a != b


def test_fingerprint_differs_on_file() -> None:
    a = compute_partial_fingerprint(rule_id="F401", file_path="src/a.py", normalized_message="m", line=1)
    b = compute_partial_fingerprint(rule_id="F401", file_path="src/b.py", normalized_message="m", line=1)
    assert a != b


def test_fingerprint_differs_on_line() -> None:
    a = compute_partial_fingerprint(rule_id="F401", file_path="src/a.py", normalized_message="m", line=1)
    b = compute_partial_fingerprint(rule_id="F401", file_path="src/a.py", normalized_message="m", line=2)
    assert a != b


def test_fingerprint_handles_none_line() -> None:
    fp = compute_partial_fingerprint(
        rule_id="F401",
        file_path="src/a.py",
        normalized_message="m",
        line=None,
    )
    assert len(fp) == 32


def test_make_result_basic_shape() -> None:
    r = make_result(
        rule_id="F401",
        level="warning",
        message="unused import",
        file_path="src/a.py",
        line=12,
    )
    assert r["ruleId"] == "F401"
    assert r["level"] == "warning"
    assert r["message"]["text"] == "unused import"
    locations = r["locations"]
    assert locations[0]["physicalLocation"]["artifactLocation"]["uri"] == "src/a.py"
    assert locations[0]["physicalLocation"]["region"]["startLine"] == 12
    assert "primaryLocationLineHash" in r["partialFingerprints"]


def test_make_result_normalizes_message() -> None:
    r = make_result(
        rule_id="F401",
        level="warning",
        message="foo   bar\n  baz",
        file_path="src/a.py",
        line=1,
    )
    assert r["message"]["text"] == "foo bar baz"


def test_make_result_with_column() -> None:
    r = make_result(
        rule_id="X",
        level="error",
        message="m",
        file_path="f.py",
        line=1,
        column=5,
    )
    assert r["locations"][0]["physicalLocation"]["region"]["startColumn"] == 5


def test_make_result_no_line_omits_region() -> None:
    r = make_result(
        rule_id="X",
        level="error",
        message="m",
        file_path="f.py",
        line=None,
    )
    physical = r["locations"][0]["physicalLocation"]
    assert "region" not in physical
    assert physical["artifactLocation"]["uri"] == "f.py"


def test_make_run_shape() -> None:
    results = [
        make_result(rule_id="F401", level="warning", message="m", file_path="f.py", line=1),
    ]
    rules = collect_rules(results)
    run = make_run(tool_name="ruff", tool_version="0.7.0", rules=rules, results=results)
    assert run["tool"]["driver"]["name"] == "ruff"
    assert run["tool"]["driver"]["version"] == "0.7.0"
    assert run["tool"]["driver"]["rules"][0]["id"] == "F401"
    assert run["results"] == results


def test_make_run_without_version() -> None:
    run = make_run(tool_name="ruff", tool_version=None, rules=[], results=[])
    assert "version" not in run["tool"]["driver"]


def test_make_log_shape() -> None:
    log = make_log([make_run(tool_name="ruff", tool_version=None, rules=[], results=[])])
    assert log["version"] == SARIF_VERSION
    assert log["$schema"] == SARIF_SCHEMA
    assert isinstance(log["runs"], list) and len(log["runs"]) == 1


def test_collect_rules_dedupes() -> None:
    results = [
        make_result(rule_id="X", level="error", message="a", file_path="a.py", line=1),
        make_result(rule_id="X", level="error", message="b", file_path="b.py", line=1),
        make_result(rule_id="Y", level="warning", message="c", file_path="c.py", line=1),
    ]
    rules = collect_rules(results)
    rule_ids = {r["id"] for r in rules}
    assert rule_ids == {"X", "Y"}
    assert len(rules) == 2


def test_collect_rules_skips_results_without_rule_id() -> None:
    results = [{"level": "error", "message": {"text": "no rule"}}]
    rules = collect_rules(results)
    assert rules == []
