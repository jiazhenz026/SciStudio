"""Shared ADR-042 audit report envelope."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AuditSeverity = Literal["info", "warning", "error"]
AuditStatus = Literal["passed", "failed", "skipped", "error"]


class AuditFinding(BaseModel):
    id: str
    tool: str
    severity: AuditSeverity
    finding_class: str
    message: str
    path: str | None = None
    line: int | None = None
    subject: str | None = None
    expected: Any | None = None
    actual: Any | None = None
    remediation: str | None = None
    evidence: Mapping[str, Any] = Field(default_factory=dict)


class AuditReport(BaseModel):
    tool: str
    status: AuditStatus
    generated_at: datetime
    source_sha: str
    findings: list[AuditFinding] = Field(default_factory=list)
    summary: Mapping[str, Any] = Field(default_factory=dict)
    child_reports: list[AuditReport] = Field(default_factory=list)

    @property
    def blocks_merge(self) -> bool:
        return self.status in {"failed", "error"} and bool(self.error_findings())

    def error_findings(self) -> list[AuditFinding]:
        return [finding for finding in self.findings if finding.severity == "error"]
