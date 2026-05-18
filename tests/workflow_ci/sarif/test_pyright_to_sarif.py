"""Tests for ``ci.sarif.pyright_to_sarif``."""

from __future__ import annotations

import json

from ci.sarif.pyright_to_sarif import convert_json


def _diag(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "file": "src/scieasy/foo.py",
        "severity": "error",
        "message": 'Argument missing for parameter "x"',
        "rule": "reportGeneralTypeIssues",
        "range": {
            "start": {"line": 11, "character": 4},
            "end": {"line": 11, "character": 20},
        },
    }
    base.update(kw)
    return base


def test_convert_single_finding() -> None:
    payload = {"generalDiagnostics": [_diag()], "version": "1.1.350"}
    log = convert_json(payload)
    r = log["runs"][0]["results"][0]
    assert r["ruleId"] == "reportGeneralTypeIssues"
    assert r["level"] == "error"
    # pyright is 0-indexed; SARIF is 1-indexed -> startLine=12 startColumn=5
    region = r["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 12, "startColumn": 5}


def test_convert_uses_payload_version_when_not_overridden() -> None:
    payload = {"generalDiagnostics": [_diag()], "version": "1.1.350"}
    log = convert_json(payload)
    assert log["runs"][0]["tool"]["driver"]["version"] == "1.1.350"


def test_convert_explicit_version_overrides_payload() -> None:
    payload = {"generalDiagnostics": [_diag()], "version": "1.1.350"}
    log = convert_json(payload, tool_version="2.0.0")
    assert log["runs"][0]["tool"]["driver"]["version"] == "2.0.0"


def test_convert_severity_mapping() -> None:
    payload = {
        "generalDiagnostics": [
            _diag(rule="r1", severity="error"),
            _diag(rule="r2", severity="warning"),
            _diag(rule="r3", severity="information"),
            _diag(rule="r4", severity="hint"),
            _diag(rule="r5", severity="weirdo"),
        ],
    }
    log = convert_json(payload)
    levels = {r["ruleId"]: r["level"] for r in log["runs"][0]["results"]}
    assert levels == {
        "r1": "error",
        "r2": "warning",
        "r3": "note",
        "r4": "note",
        "r5": "warning",
    }


def test_convert_accepts_json_string() -> None:
    payload = json.dumps({"generalDiagnostics": [_diag()]})
    log = convert_json(payload)
    assert len(log["runs"][0]["results"]) == 1


def test_convert_missing_diagnostics() -> None:
    log = convert_json({})
    assert log["runs"][0]["results"] == []


def test_convert_missing_range() -> None:
    payload = {"generalDiagnostics": [_diag(range=None)]}
    log = convert_json(payload)
    physical = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
    assert "region" not in physical


def test_convert_missing_rule_falls_back() -> None:
    diag = _diag()
    diag.pop("rule")
    payload = {"generalDiagnostics": [diag]}
    log = convert_json(payload)
    assert log["runs"][0]["results"][0]["ruleId"] == "pyright"
