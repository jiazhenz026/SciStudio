"""Tests for ``ci.sarif.mypy_to_sarif``."""

from __future__ import annotations

from ci.sarif.mypy_to_sarif import convert_text


def test_convert_error_line() -> None:
    text = "src/scieasy/foo.py:12:5: error: Incompatible types in assignment  [assignment]"
    log = convert_text(text)
    results = log["runs"][0]["results"]
    assert len(results) == 1
    r = results[0]
    assert r["ruleId"] == "assignment"
    assert r["level"] == "error"
    assert "Incompatible types" in r["message"]["text"]
    region = r["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 12, "startColumn": 5}


def test_convert_error_without_rule_falls_back_to_mypy() -> None:
    text = "src/scieasy/foo.py:12: error: Bad thing"
    log = convert_text(text)
    r = log["runs"][0]["results"][0]
    assert r["ruleId"] == "mypy"
    assert r["level"] == "error"


def test_convert_warning_line() -> None:
    text = "src/scieasy/foo.py:7: warning: unused thing  [unused-ignore]"
    log = convert_text(text)
    r = log["runs"][0]["results"][0]
    assert r["level"] == "warning"
    assert r["ruleId"] == "unused-ignore"


def test_convert_skips_note_lines() -> None:
    text = "\n".join(
        [
            "src/scieasy/foo.py:12: error: bad  [assignment]",
            "src/scieasy/foo.py:13: note: Revealed type is ...",
        ],
    )
    log = convert_text(text)
    results = log["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["level"] == "error"


def test_convert_skips_summary_line() -> None:
    text = "\n".join(
        [
            "src/scieasy/foo.py:12: error: bad  [assignment]",
            "Found 1 error in 1 file (checked 1 source file)",
        ],
    )
    log = convert_text(text)
    assert len(log["runs"][0]["results"]) == 1


def test_convert_empty() -> None:
    log = convert_text("")
    assert log["runs"][0]["results"] == []


def test_convert_multiple_errors_collect_unique_rules() -> None:
    text = "\n".join(
        [
            "a.py:1: error: x  [assignment]",
            "b.py:2: error: y  [assignment]",
            "c.py:3: error: z  [arg-type]",
        ],
    )
    log = convert_text(text)
    rules = {r["id"] for r in log["runs"][0]["tool"]["driver"]["rules"]}
    assert rules == {"assignment", "arg-type"}


def test_convert_with_version_string() -> None:
    log = convert_text("a.py:1: error: x  [assignment]", tool_version="1.11.0")
    assert log["runs"][0]["tool"]["driver"]["version"] == "1.11.0"
