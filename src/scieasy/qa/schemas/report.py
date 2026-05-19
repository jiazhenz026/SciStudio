"""Finding models shared by ADR-042 audit tools."""

from __future__ import annotations

from enum import StrEnum

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
