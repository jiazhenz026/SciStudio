"""Append-only gate ledger Pydantic models for ADR-042 Addendum 6 (§7.2).

The ledger is one append-only JSON object: top-level identity fields plus event
arrays. Events accumulate and are never overwritten or deleted; corrections are
new events. ``schema_version`` is ``2`` (bumped from the legacy flat document).

This module is import-clean: it depends only on pydantic, stdlib, and
``surfaces`` for path normalization. It owns no CLI, no I/O, no subprocess.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scistudio.qa.governance.gate_record.surfaces import normalize_path

LEDGER_SCHEMA_VERSION: Literal[2] = 2

TaskKind = Literal[
    "hotfix",
    "bugfix",
    "feature",
    "refactor",
    "docs",
    "maintenance",
    "manager",
    "guided",
]
SUPPORTED_TASK_KINDS: tuple[TaskKind, ...] = (
    "hotfix",
    "bugfix",
    "feature",
    "refactor",
    "docs",
    "maintenance",
    "manager",
    "guided",
)

Persona = Literal[
    "manager",
    "implementer",
    "adr_author",
    "audit_reviewer",
    "test_engineer",
    "live_implementer",
]
SUPPORTED_PERSONAS: tuple[Persona, ...] = (
    "manager",
    "implementer",
    "adr_author",
    "audit_reviewer",
    "test_engineer",
    "live_implementer",
)

StrictnessTier = Literal[1, 2, 3]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IssueRef(BaseModel):
    """A GitHub issue linked to the ledger (carried forward from schema v1)."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(gt=0)
    url: str | None = None
    close_in_pr: bool = True
    followup_rationale: str | None = None

    @model_validator(mode="after")
    def _require_followup_rationale(self) -> IssueRef:
        if not self.close_in_pr and not self.followup_rationale:
            raise ValueError("non-closing issue references require followup_rationale")
        return self


class DeclaredScope(BaseModel):
    """Declared include/exclude path scope (carried forward as a sub-object)."""

    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include", "exclude")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return [normalize_path(item) for item in value]


class DirectiveEvent(BaseModel):
    """A later owner instruction that redirects or expands work."""

    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    owner_directive: str
    reason: str | None = None


class ScopeEvent(BaseModel):
    """An append-only scope add/supersede event."""

    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    action: Literal["add-include", "add-exclude", "remove-include", "remove-exclude"]
    pattern: str
    reason: str | None = None

    @field_validator("pattern")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_path(value)


class ObservedDiff(BaseModel):
    """Git-observed objective change facts (§7.2). The evidence, not a claim."""

    model_config = ConfigDict(extra="forbid")

    base: str
    head: str
    base_sha: str | None = None
    head_sha: str | None = None
    diff_fingerprint: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    surfaces: Mapping[str, int] = Field(default_factory=dict)

    @field_validator("changed_files")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return [normalize_path(item) for item in value]


class CheckEvent(BaseModel):
    """An append-only, incremental check event (§7.2).

    Validity is scoped to ``covered_surface`` + ``input_fingerprint``: a later
    edit to that surface invalidates only this event's evidence.
    """

    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    name: str
    command: str
    tool_versions: Mapping[str, str] = Field(default_factory=dict)
    covered_surface: str
    input_fingerprint: str | None = None
    exit_code: int | None = None
    status: Literal["pass", "fail", "skipped", "unknown"] = "unknown"
    summary: str = ""
    raw_log_ref: str | None = None
    pr_only: bool = False
    # When True the nonzero exit is an ENVIRONMENT-PARITY cause (collection
    # ImportError/ModuleNotFoundError, missing interpreter/tool, missing dep),
    # NOT a genuine code/assertion failure (§7.10). The evaluator reports these
    # as parity gaps (fail closed for PR readiness) rather than misleading code
    # failures, and ``parity_detail`` names what is missing.
    parity_gap: bool = False
    parity_detail: str | None = None

    @model_validator(mode="after")
    def _validate_exit(self) -> CheckEvent:
        if self.status == "pass" and self.exit_code not in (None, 0):
            raise ValueError("passing checks cannot record a non-zero exit_code")
        return self


class DocsEvent(BaseModel):
    """A docs landing path or N/A rationale event."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    at: datetime = Field(default_factory=_utcnow)
    kind: Literal["path", "na"]
    path: str | None = None
    doc_class: str | None = Field(default=None, alias="class")
    rationale: str | None = None
    verified_in_diff: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> DocsEvent:
        if self.kind == "path" and not self.path:
            raise ValueError("docs path events require a path")
        if self.kind == "na" and not self.rationale:
            raise ValueError("docs N/A events require a rationale")
        return self


class TestEvent(BaseModel):
    """A test path / runtime-evidence path or N/A rationale event."""

    # Opt out of pytest collection (the class name starts with ``Test``).
    __test__ = False

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    at: datetime = Field(default_factory=_utcnow)
    kind: Literal["path", "na"]
    path: str | None = None
    test_class: str | None = Field(default=None, alias="class")
    rationale: str | None = None
    verified_in_diff: bool | None = None

    @model_validator(mode="after")
    def _validate(self) -> TestEvent:
        if self.kind == "path" and not self.path:
            raise ValueError("test path events require a path")
        if self.kind == "na" and not self.rationale:
            raise ValueError("test N/A events require a rationale")
        return self


class GuardEvent(BaseModel):
    """A guard calculator result recorded as an append-only event."""

    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    guard: str
    status: Literal["pass", "fail", "skipped"]
    findings: list[Mapping[str, Any]] = Field(default_factory=list)


class ReconcileEvent(BaseModel):
    """A local/CI reconciliation result for a specific candidate."""

    model_config = ConfigDict(extra="forbid")

    at: datetime = Field(default_factory=_utcnow)
    mode: str
    tier: StrictnessTier
    diff_fingerprint: str | None = None
    result: Literal["pass", "fail"]
    unsatisfied: list[str] = Field(default_factory=list)


class RequiredObligations(BaseModel):
    """Evaluator-inferred obligations recorded for transparency."""

    model_config = ConfigDict(extra="forbid")

    checks: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    guards: list[str] = Field(default_factory=list)
    admin_labels: list[str] = Field(default_factory=list)


class CheckNa(BaseModel):
    """An accepted N/A rationale for a named check."""

    model_config = ConfigDict(extra="forbid")

    name: str
    rationale: str


class CommitEvidence(BaseModel):
    """Commit provenance (carried forward from schema v1)."""

    model_config = ConfigDict(extra="forbid")

    sha: str | None = None
    shas: list[str] = Field(default_factory=list)
    trailers: list[str] = Field(default_factory=list)


class PullRequestEvidence(BaseModel):
    """PR provenance with pre-PR/post-PR distinction (§7.2)."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None
    number: int | None = Field(default=None, gt=0)
    closes: list[int] = Field(default_factory=list)
    body_closes_issues: list[int] = Field(default_factory=list)


class AdminLabel(BaseModel):
    """A requested or observed admin label.

    ``requested_admin_labels`` carry no provenance (local, non-authoritative).
    ``observed_admin_labels`` carry actor/permission provenance (CI-only).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    applied_by: str | None = None
    actor_permission: str | None = None
    applied_at: datetime | None = None


class GateLedger(BaseModel):
    """Append-only ADR-042 Addendum 6 gate ledger (schema v2)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    record_id: str
    session_id: str | None = None
    runtime: str
    task_kind: TaskKind
    strictness_tier: StrictnessTier | None = None
    persona: Persona
    branch: str
    owner_directive: str
    governance_touch: bool = False
    declared_scope: DeclaredScope = Field(default_factory=DeclaredScope)
    required_obligations: RequiredObligations = Field(default_factory=RequiredObligations)
    issues: list[IssueRef] = Field(default_factory=list)
    directive_events: list[DirectiveEvent] = Field(default_factory=list)
    scope_events: list[ScopeEvent] = Field(default_factory=list)
    observed_diff: ObservedDiff | None = None
    check_events: list[CheckEvent] = Field(default_factory=list)
    check_na: list[CheckNa] = Field(default_factory=list)
    docs_events: list[DocsEvent] = Field(default_factory=list)
    test_events: list[TestEvent] = Field(default_factory=list)
    guard_events: list[GuardEvent] = Field(default_factory=list)
    reconcile_events: list[ReconcileEvent] = Field(default_factory=list)
    commit: CommitEvidence | None = None
    pull_request: PullRequestEvidence | None = None
    requested_admin_labels: list[AdminLabel] = Field(default_factory=list)
    observed_admin_labels: list[AdminLabel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_schema_version(self) -> GateLedger:
        if self.schema_version != 2:
            raise ValueError(f"unsupported gate ledger schema_version: {self.schema_version}")
        return self

    # -- Effective-state helpers (latest-wins over append-only events) -------

    def effective_include(self) -> list[str]:
        """Return the effective include set: declared + add events - removes."""

        include = list(self.declared_scope.include)
        for event in self.scope_events:
            if event.action == "add-include" and event.pattern not in include:
                include.append(event.pattern)
            elif event.action == "remove-include" and event.pattern in include:
                include.remove(event.pattern)
        return include

    def effective_exclude(self) -> list[str]:
        """Return the effective exclude set: declared + add events - removes."""

        exclude = list(self.declared_scope.exclude)
        for event in self.scope_events:
            if event.action == "add-exclude" and event.pattern not in exclude:
                exclude.append(event.pattern)
            elif event.action == "remove-exclude" and event.pattern in exclude:
                exclude.remove(event.pattern)
        return exclude

    def declared_docs_paths(self) -> list[str]:
        """Return declared docs landing paths (path-kind docs events)."""

        return [event.path for event in self.docs_events if event.kind == "path" and event.path]

    def declared_test_paths(self) -> list[str]:
        """Return declared test paths (path-kind test events)."""

        return [event.path for event in self.test_events if event.kind == "path" and event.path]

    def requested_label_names(self) -> set[str]:
        """Return the set of requested admin-label names."""

        return {label.name for label in self.requested_admin_labels}

    def observed_label_names(self) -> set[str]:
        """Return the set of observed admin-label names."""

        return {label.name for label in self.observed_admin_labels}
