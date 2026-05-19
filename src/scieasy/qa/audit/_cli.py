"""Shared CLI helpers for ADR-042 audit tools."""

from __future__ import annotations

from scieasy.qa.schemas.report import AuditReport


def print_report(report: AuditReport, *, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json())
        return
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.path}:{finding.line or 0} {finding.id} {finding.message}")


def exit_code(report: AuditReport) -> int:
    return 1 if report.status in {"failed", "error"} and report.error_findings() else 0
