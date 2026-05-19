"""Finding models shared by ADR-042 audit tools."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DriftClass(StrEnum):
    """ADR-042 drift classes for documentation/code consistency checks."""

    MATCH = "match"
    BEHAVIOR_DRIFT = "behavior-drift"
    PHANTOM_REFERENCE = "phantom-reference"
    MISSING_DOCUMENTATION = "missing-documentation"
    SIGNATURE_DRIFT = "signature-drift"


class Severity(StrEnum):
    """Finding severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AuditStatus(StrEnum):
    """Overall status for an ADR-042 audit report."""

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class Finding(BaseModel):
    """A single machine-readable governance finding."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: Severity
    file: str
    message: str
    line: int | None = None
    symbol: str | None = None
    drift_class: DriftClass | None = None
    suggested_fix: str | None = None
    git_evidence: str | None = None
    related_findings: list[str] = Field(default_factory=list)


class AuditReport(BaseModel):
    """Shared report envelope for ADR-042 audit tools."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    status: AuditStatus
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_sha: str
    findings: list[Finding] = Field(default_factory=list)
    summary: Mapping[str, Any] = Field(default_factory=dict)
    child_reports: list[AuditReport] = Field(default_factory=list)

    @property
    def blocks_merge(self) -> bool:
        """Return true when this report should fail a blocking check."""

        if self.status == AuditStatus.FAIL:
            return True
        if any(finding.severity == Severity.ERROR for finding in self.findings):
            return True
        return any(child.blocks_merge for child in self.child_reports)

    def error_findings(self) -> list[Finding]:
        """Return all error-severity findings, including child reports."""

        errors = [finding for finding in self.findings if finding.severity == Severity.ERROR]
        for child in self.child_reports:
            errors.extend(child.error_findings())
        return errors
