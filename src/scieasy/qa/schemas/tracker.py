"""ADR-implementation tracker schemas (ADR-043 §2.2).

This module owns the pydantic shapes that back
``docs/adr/_implementation-tracker.yaml`` (or the per-ADR tracker file
referenced by ``scripts/audit/adr_implementation_check.py``). The tracker
records, for every ADR section, what artifacts the implementation is
required to ship and whether the section is currently
``not_started`` / ``in_progress`` / ``implemented`` / ``verified``.

State transition rules (monotonic forward only, except via addendum) are
documented in ADR-043 §2.3 and enforced at the tool layer
(``scripts/audit/adr_implementation_check.py``); the schema here is
purely structural per the SUMMARY (TC-1A.6 manager default).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ._common import ADRRef, FunctionOrClassPath, RepoRelativePath


class SectionStatus(StrEnum):
    """Lifecycle state of one ADR section's implementation.

    Defined verbatim in ADR-043 §2.2. Monotonic advancement
    (``not_started → in_progress → implemented → verified``) is enforced
    by ``scripts/audit/adr_implementation_check.py`` per §2.3, not here.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"


class RequiredArtifacts(BaseModel):
    """Files / symbols / tests that an ADR section must materialise."""

    model_config = ConfigDict(extra="forbid")

    files: list[RepoRelativePath] = Field(default_factory=list)
    symbols: list[FunctionOrClassPath] = Field(default_factory=list)
    tests: list[RepoRelativePath] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    """One named verification a section must pass to reach ``verified``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str


class TrackerEntry(BaseModel):
    """Per-section tracker row."""

    model_config = ConfigDict(extra="forbid")

    section: str
    requires_artifacts: RequiredArtifacts
    verification_checks: list[VerificationCheck]
    status: SectionStatus
    implemented_in_pr: int | None = None
    verified_at: datetime | None = None
    verifier_skill: str | None = None
    verifier_command: str


class ImplementationTracker(BaseModel):
    """Top-level tracker file model.

    One instance per ADR (e.g. ``docs/adr/_implementation-tracker-042.yaml``).
    """

    model_config = ConfigDict(extra="forbid")

    adr: ADRRef
    schema_version: int = 1
    sections: list[TrackerEntry]
