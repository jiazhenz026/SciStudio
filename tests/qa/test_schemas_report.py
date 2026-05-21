from __future__ import annotations

from scistudio.qa.schemas.report import AuditFinding, AuditReport, AuditStatus, Finding, Severity


def test_audit_report_blocks_merge_on_error_finding() -> None:
    report = AuditReport(
        tool="example",
        status=AuditStatus.PASS,
        source_sha="abc123",
        findings=[
            Finding(
                rule_id="example.error",
                severity=Severity.ERROR,
                file="docs/example.md",
                message="example failure",
            )
        ],
    )

    assert report.blocks_merge
    assert [finding.rule_id for finding in report.error_findings()] == ["example.error"]
    assert isinstance(report.error_findings()[0], AuditFinding)


def test_audit_report_collects_child_error_findings() -> None:
    child = AuditReport(
        tool="child",
        status=AuditStatus.FAIL,
        source_sha="abc123",
        findings=[
            Finding(
                rule_id="child.error",
                severity=Severity.ERROR,
                file="docs/example.md",
                message="child failure",
            )
        ],
    )
    parent = AuditReport(tool="parent", status=AuditStatus.PASS, source_sha="abc123", child_reports=[child])

    assert parent.blocks_merge
    assert [finding.rule_id for finding in parent.error_findings()] == ["child.error"]


def test_audit_finding_accepts_adr042_compatibility_fields() -> None:
    finding = AuditFinding(
        id="finding-1",
        tool="example",
        rule_id="example.error",
        severity=Severity.ERROR,
        path="docs/example.md",
        subject="sample.Symbol",
        finding_class="signature-drift",
        message="example failure",
        expected={"a": 1},
        actual={"a": 2},
        remediation="fix it",
        evidence={"source": "fixture"},
    )

    assert finding.file == "docs/example.md"
    assert finding.path == "docs/example.md"
    assert finding.subject == "sample.Symbol"
    assert finding.id == "finding-1"
