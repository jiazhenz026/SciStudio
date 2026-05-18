"""Shared audit-report envelope for ADR-042/043 QA tools."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DriftClass(StrEnum):
    """ADR-042 drift classes."""

    A = "a"
    B = "b"
    C1 = "c1"
    C2 = "c2"
    C3 = "c3"
    D = "d"


class Severity(StrEnum):
    """Severity levels shared by audit findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """One audit finding emitted by a QA tool."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: Severity
    drift_class: DriftClass | None = None
    file: str
    line: int | None = None
    symbol: str | None = None
    message: str
    suggested_fix: str | None = None
    git_evidence: str | None = None
    related_findings: list[str] = Field(default_factory=list)


class ToolRun(BaseModel):
    """One audit-tool invocation inside an :class:`AuditReport`."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    version: str
    config_hash: str
    started_at: datetime
    completed_at: datetime
    exit_status: Literal["ok", "warnings", "errors", "crash"]
    findings: list[Finding] = Field(default_factory=list)


class AuditReport(BaseModel):
    """Top-level report envelope from ADR-042 section 7."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    repo_sha: str
    repo_branch: str
    pr_number: int | None = None
    generated_at: datetime
    runs: list[ToolRun]

    total_findings: int
    by_severity: dict[Severity, int]
    by_drift_class: dict[DriftClass, int]

    bidirectional_closure_ok: bool = False
    translation_ok: bool = False

    @model_validator(mode="after")
    def _denormalized_counts_match_runs(self) -> AuditReport:
        """Keep denormalized finding counts consistent with embedded runs."""
        findings = [finding for run in self.runs for finding in run.findings]
        if self.total_findings != len(findings):
            raise ValueError("total_findings must equal the number of embedded findings")

        severity_counts = Counter(finding.severity for finding in findings)
        declared_severities = {severity: count for severity, count in self.by_severity.items() if count}
        observed_severities = {severity: count for severity, count in severity_counts.items() if count}
        if declared_severities != observed_severities:
            raise ValueError("by_severity must match embedded findings")

        class_counts = Counter(finding.drift_class for finding in findings if finding.drift_class is not None)
        declared_classes = {drift_class: count for drift_class, count in self.by_drift_class.items() if count}
        observed_classes = {drift_class: count for drift_class, count in class_counts.items() if count}
        if declared_classes != observed_classes:
            raise ValueError("by_drift_class must match embedded findings")

        return self
