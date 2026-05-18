"""Implementation tracker schemas for ADR-043 section 2."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import ADRRef, FunctionOrClassPath, RepoRelativePath


class SectionStatus(StrEnum):
    """Lifecycle state for one tracked ADR section."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"


class RequiredArtifacts(BaseModel):
    """Files, symbols, and tests required by a tracker entry."""

    model_config = ConfigDict(extra="forbid")

    files: list[RepoRelativePath] = Field(default_factory=list)
    symbols: list[FunctionOrClassPath] = Field(default_factory=list)
    tests: list[RepoRelativePath] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    """One named verification required before a section can be marked verified."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class TrackerEntry(BaseModel):
    """Per-section implementation tracker row."""

    model_config = ConfigDict(extra="forbid")

    section: str = Field(min_length=1)
    requires_artifacts: RequiredArtifacts
    verification_checks: list[VerificationCheck] = Field(default_factory=list)
    status: SectionStatus
    implemented_in_pr: int | None = Field(default=None, ge=1)
    verified_at: datetime | None = None
    verifier_skill: str | None = None
    verifier_command: str = Field(min_length=1)

    @model_validator(mode="after")
    def _implemented_entries_cite_pr(self) -> TrackerEntry:
        """ADR-043 section 2.3 requires implemented entries to cite their PR."""
        if self.status in {SectionStatus.IMPLEMENTED, SectionStatus.VERIFIED} and self.implemented_in_pr is None:
            raise ValueError("implemented or verified tracker entries require implemented_in_pr")
        return self


class ImplementationTracker(BaseModel):
    """Top-level implementation tracker file model."""

    model_config = ConfigDict(extra="forbid")

    adr: ADRRef
    schema_version: int = 1
    sections: list[TrackerEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _section_names_unique(self) -> ImplementationTracker:
        """Avoid ambiguous duplicate section rows."""
        sections = [entry.section for entry in self.sections]
        if len(sections) != len(set(sections)):
            raise ValueError("tracker section names must be unique")
        return self
