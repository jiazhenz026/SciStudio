"""Tests for ``ci.sarif.ruff_to_sarif``."""

from __future__ import annotations

import json

from ci.sarif.ruff_to_sarif import convert_lines, convert_text


def _ruff_line(**kw: object) -> str:
    base = {
        "code": "F401",
        "message": "`os` imported but unused",
        "filename": "src/scieasy/foo.py",
        "location": {"row": 12, "column": 1},
    }
    base.update(kw)
    return json.dumps(base)


def test_convert_single_finding() -> None:
    log = convert_text(_ruff_line(), tool_version="0.7.0")
    assert log["version"] == "2.1.0"
    runs = log["runs"]
    assert len(runs) == 1
    run = runs[0]
    assert run["tool"]["driver"]["name"] == "ruff"
    assert run["tool"]["driver"]["version"] == "0.7.0"
    results = run["results"]
    assert len(results) == 1
    r = results[0]
    assert r["ruleId"] == "F401"
    assert r["level"] == "warning"
    assert r["message"]["text"] == "`os` imported but unused"
    region = r["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 12, "startColumn": 1}


def test_convert_multiple_lines() -> None:
    text = "\n".join(
        [
            _ruff_line(code="F401"),
            _ruff_line(code="E501", message="line too long", location={"row": 3, "column": 1}),
        ],
    )
    log = convert_text(text)
    results = log["runs"][0]["results"]
    assert {r["ruleId"] for r in results} == {"F401", "E501"}


def test_convert_skips_blank_lines() -> None:
    text = "\n".join(["", _ruff_line(), "", "   ", _ruff_line(code="E501")])
    log = convert_text(text)
    assert len(log["runs"][0]["results"]) == 2


def test_convert_collects_rules() -> None:
    text = "\n".join(
        [_ruff_line(code="F401"), _ruff_line(code="F401"), _ruff_line(code="E501")],
    )
    log = convert_text(text)
    rule_ids = {r["id"] for r in log["runs"][0]["tool"]["driver"]["rules"]}
    assert rule_ids == {"F401", "E501"}


def test_convert_empty_input() -> None:
    log = convert_lines([])
    assert log["runs"][0]["results"] == []
    assert log["runs"][0]["tool"]["driver"]["rules"] == []


def test_convert_missing_code_falls_back() -> None:
    line = json.dumps({"filename": "f.py", "message": "m", "location": {"row": 1, "column": 1}})
    log = convert_text(line)
    assert log["runs"][0]["results"][0]["ruleId"] == "ruff"


def test_convert_missing_location_omits_region() -> None:
    line = json.dumps({"code": "X", "filename": "f.py", "message": "m"})
    log = convert_text(line)
    physical = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert "region" not in physical


def test_partial_fingerprint_stable() -> None:
    line = _ruff_line()
    a = convert_text(line)["runs"][0]["results"][0]["partialFingerprints"]
    b = convert_text(line)["runs"][0]["results"][0]["partialFingerprints"]
    assert a == b
