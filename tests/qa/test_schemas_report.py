from __future__ import annotations

from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


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
