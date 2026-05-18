"""Tests for ``scieasy.qa.schemas.report`` (ADR-042 §7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.report import (
    AuditReport,
    DriftClass,
    Finding,
    Severity,
    ToolRun,
)

# --------------------------------------------------------------------------- #
# Enums                                                                       #
# --------------------------------------------------------------------------- #


def test_drift_class_values() -> None:
    assert {c.value for c in DriftClass} == {"a", "b", "c1", "c2", "c3", "d"}


def test_severity_values() -> None:
    assert {s.value for s in Severity} == {"error", "warning", "info"}


# --------------------------------------------------------------------------- #
# Finding                                                                     #
# --------------------------------------------------------------------------- #


def test_finding_minimal() -> None:
    f = Finding(
        rule_id="QA001",
        severity=Severity.ERROR,
        file="src/scieasy/qa/foo.py",
        message="missing module docstring",
    )
    assert f.line is None and f.symbol is None and f.drift_class is None


def test_finding_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(
            {
                "rule_id": "QA001",
                "severity": "error",
                "file": "x.py",
                "message": "x",
                "unknown_field": "no",
            }
        )


def test_finding_with_drift_class() -> None:
    f = Finding(
        rule_id="DD-001",
        severity=Severity.WARNING,
        drift_class=DriftClass.C2,
        file="docs/adr/ADR-007.md",
        message="cites symbol that never existed",
    )
    assert f.drift_class is DriftClass.C2


# --------------------------------------------------------------------------- #
# ToolRun                                                                     #
# --------------------------------------------------------------------------- #


def _ts() -> datetime:
    return datetime(2026, 5, 18, 4, 0, 0, tzinfo=UTC)


def test_tool_run_minimal() -> None:
    r = ToolRun(
        tool="doc_drift",
        version="1.0.0",
        config_hash="abc",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="ok",
    )
    assert r.exit_status == "ok"
    assert r.findings == []


def test_tool_run_exit_status_literal() -> None:
    with pytest.raises(ValidationError):
        ToolRun.model_validate(
            {
                "tool": "x",
                "version": "1",
                "config_hash": "h",
                "started_at": _ts().isoformat(),
                "completed_at": _ts().isoformat(),
                "exit_status": "unknown",
            }
        )


def test_tool_run_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        ToolRun.model_validate(
            {
                "tool": "doc_drift",
                "version": "1.0.0",
                "config_hash": "abc",
                "started_at": _ts().isoformat(),
                "completed_at": _ts().isoformat(),
                "exit_status": "ok",
                "unknown": "x",
            }
        )


# --------------------------------------------------------------------------- #
# AuditReport                                                                 #
# --------------------------------------------------------------------------- #


def _empty_report() -> AuditReport:
    return AuditReport(
        run_id="r1",
        repo_sha="abcdef",
        repo_branch="track/adr-042/1a-schemas",
        generated_at=_ts(),
        runs=[],
        total_findings=0,
        by_severity={},
        by_drift_class={},
        bidirectional_closure_ok=True,
        translation_ok=True,
    )


def test_audit_report_empty_happy_path() -> None:
    r = _empty_report()
    assert r.schema_version == 1
    assert r.total_findings == 0


def test_audit_report_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        AuditReport.model_validate(
            {
                "run_id": "r1",
                "repo_sha": "abcdef",
                "repo_branch": "main",
                "generated_at": _ts().isoformat(),
                "runs": [],
                "total_findings": 0,
                "by_severity": {},
                "by_drift_class": {},
                "bidirectional_closure_ok": True,
                "translation_ok": True,
                "unknown": "x",
            }
        )


def test_audit_report_totals_consistent_happy_path() -> None:
    """Totals validator passes when counts match the flat findings."""
    f1 = Finding(
        rule_id="DD-001",
        severity=Severity.WARNING,
        drift_class=DriftClass.C2,
        file="docs/adr/ADR-X.md",
        message="m",
    )
    f2 = Finding(
        rule_id="QA001",
        severity=Severity.ERROR,
        file="src/x.py",
        message="m",
    )
    run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash="h",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="warnings",
        findings=[f1, f2],
    )
    r = AuditReport(
        run_id="r1",
        repo_sha="abc",
        repo_branch="main",
        generated_at=_ts(),
        runs=[run],
        total_findings=2,
        by_severity={Severity.ERROR: 1, Severity.WARNING: 1},
        by_drift_class={DriftClass.C2: 1},
        bidirectional_closure_ok=True,
        translation_ok=True,
    )
    assert r.total_findings == 2


def test_audit_report_totals_mismatch_rejected() -> None:
    """Validator catches arithmetic drift in ``total_findings``."""
    run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash="h",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="warnings",
        findings=[
            Finding(rule_id="X", severity=Severity.WARNING, file="x", message="m"),
        ],
    )
    with pytest.raises(ValidationError, match="disagrees"):
        AuditReport(
            run_id="r1",
            repo_sha="abc",
            repo_branch="main",
            generated_at=_ts(),
            runs=[run],
            total_findings=5,  # wrong
            by_severity={Severity.WARNING: 1},
            by_drift_class={},
            bidirectional_closure_ok=True,
            translation_ok=True,
        )


def test_audit_report_by_severity_mismatch_rejected() -> None:
    run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash="h",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="warnings",
        findings=[
            Finding(rule_id="X", severity=Severity.WARNING, file="x", message="m"),
        ],
    )
    with pytest.raises(ValidationError, match="by_severity"):
        AuditReport(
            run_id="r1",
            repo_sha="abc",
            repo_branch="main",
            generated_at=_ts(),
            runs=[run],
            total_findings=1,
            by_severity={Severity.ERROR: 1},  # wrong severity counted
            by_drift_class={},
            bidirectional_closure_ok=True,
            translation_ok=True,
        )


def test_audit_report_by_drift_class_mismatch_rejected() -> None:
    run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash="h",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="warnings",
        findings=[
            Finding(
                rule_id="DD",
                severity=Severity.WARNING,
                drift_class=DriftClass.B,
                file="x",
                message="m",
            ),
        ],
    )
    with pytest.raises(ValidationError, match="by_drift_class"):
        AuditReport(
            run_id="r1",
            repo_sha="abc",
            repo_branch="main",
            generated_at=_ts(),
            runs=[run],
            total_findings=1,
            by_severity={Severity.WARNING: 1},
            by_drift_class={DriftClass.A: 1},  # wrong class
            bidirectional_closure_ok=True,
            translation_ok=True,
        )


def test_audit_report_round_trip() -> None:
    """Round-trip preserves enum-keyed dicts (``Severity`` / ``DriftClass``)."""
    run = ToolRun(
        tool="doc_drift",
        version="1",
        config_hash="h",
        started_at=_ts(),
        completed_at=_ts(),
        exit_status="warnings",
        findings=[
            Finding(
                rule_id="DD",
                severity=Severity.WARNING,
                drift_class=DriftClass.B,
                file="x",
                message="m",
            ),
        ],
    )
    r = AuditReport(
        run_id="r1",
        repo_sha="abc",
        repo_branch="main",
        generated_at=_ts(),
        runs=[run],
        total_findings=1,
        by_severity={Severity.WARNING: 1},
        by_drift_class={DriftClass.B: 1},
        bidirectional_closure_ok=True,
        translation_ok=True,
    )
    dumped = r.model_dump_json()
    reloaded = AuditReport.model_validate_json(dumped)
    assert reloaded == r


def test_audit_report_schema_version_literal() -> None:
    with pytest.raises(ValidationError):
        AuditReport.model_validate(
            {
                "schema_version": 2,
                "run_id": "r1",
                "repo_sha": "abc",
                "repo_branch": "main",
                "generated_at": _ts().isoformat(),
                "runs": [],
                "total_findings": 0,
                "by_severity": {},
                "by_drift_class": {},
                "bidirectional_closure_ok": True,
                "translation_ok": True,
            }
        )


def test_audit_report_json_schema_export() -> None:
    for model in (Finding, ToolRun, AuditReport):
        schema = model.model_json_schema()
        assert isinstance(schema, dict)
        if "$schema" in schema:
            assert "2020-12" in schema["$schema"]
