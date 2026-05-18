"""Tests for ``ci.sarif.bandit_to_sarif``."""

from __future__ import annotations

import json

from ci.sarif.bandit_to_sarif import convert_json


def _bandit_result(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "test_id": "B101",
        "test_name": "assert_used",
        "issue_text": "Use of assert detected.",
        "filename": "src/scieasy/foo.py",
        "line_number": 42,
        "col_offset": 3,
        "issue_severity": "MEDIUM",
        "issue_confidence": "HIGH",
    }
    base.update(kw)
    return base


def test_convert_single_finding() -> None:
    payload = {"results": [_bandit_result()]}
    log = convert_json(payload, tool_version="1.7.0")
    r = log["runs"][0]["results"][0]
    assert r["ruleId"] == "B101"
    assert r["level"] == "warning"  # MEDIUM -> warning
    assert "assert detected" in r["message"]["text"]
    region = r["locations"][0]["physicalLocation"]["region"]
    # col_offset=3 -> startColumn=4 (bandit is 0-indexed, SARIF is 1-indexed)
    assert region == {"startLine": 42, "startColumn": 4}


def test_convert_severity_mapping() -> None:
    payload = {
        "results": [
            _bandit_result(test_id="B1", issue_severity="HIGH"),
            _bandit_result(test_id="B2", issue_severity="MEDIUM"),
            _bandit_result(test_id="B3", issue_severity="LOW"),
            _bandit_result(test_id="B4", issue_severity="UNKNOWN"),
        ],
    }
    log = convert_json(payload)
    levels = {r["ruleId"]: r["level"] for r in log["runs"][0]["results"]}
    assert levels == {"B1": "error", "B2": "warning", "B3": "note", "B4": "warning"}


def test_convert_accepts_json_string() -> None:
    payload = json.dumps({"results": [_bandit_result()]})
    log = convert_json(payload)
    assert len(log["runs"][0]["results"]) == 1


def test_convert_empty_results() -> None:
    log = convert_json({"results": []})
    assert log["runs"][0]["results"] == []


def test_convert_missing_results_key() -> None:
    log = convert_json({})
    assert log["runs"][0]["results"] == []


def test_convert_missing_line() -> None:
    payload = {"results": [_bandit_result(line_number=None, col_offset=None)]}
    log = convert_json(payload)
    physical = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert "region" not in physical
