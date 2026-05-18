"""Pydantic models for ADR / spec YAML frontmatter.

ADR-042 §5 defines the machine-parseable header carried by every ADR and
spec document in the repository. This module is the authoritative
Python shape — ``frontmatter_lint`` (Phase 1B.2) and ``doc_drift``
(Phase 1B.1) consume it; the ``governs`` declarations within feed the
bidirectional-closure check (§11).

Both ``ADRFrontmatter`` and ``SpecFrontmatter`` use ``extra="forbid"``,
so unknown fields are rejected rather than silently dropped. Cross-field
invariants (status/date consistency, ``is_code_implementation`` →
non-empty ``governs``/``tests``, agent_editable/allowlist pairing,
self-supersede prevention) are enforced by ``model_validator(mode="after")``
hooks.

References
----------
ADR-042 §5.1 — design rationale.
ADR-042 §5.2 — pydantic models (authoritative source for this file).
ADR-042 §5.4.1 — ``agent_editable`` enum semantics.
ADR-042 §5.5 — status lifecycle.
ADR-042 §5.7 — spec frontmatter subset.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import (
    ADRRef,
    AssistedByLine,
    FunctionOrClassPath,
    GitHandle,
    IssueRef,
    LocaleCode,
    PathGlob,
    RepoRelativePath,
)
from ._common import (
    DottedModulePath as DottedModulePath,  # re-export for downstream callers
)
from .maintainers import AgentRuntime


class Status(StrEnum):
    """ADR lifecycle status. See ADR-042 §5.5 for the transition graph."""

    DRAFT = "Draft"
    PROPOSED = "Proposed"
    ACCEPTED = "Accepted"
    SUPERSEDED = "Superseded"
    WITHDRAWN = "Withdrawn"
    DEPRECATED = "Deprecated"


class AgentEditable(StrEnum):
    """Tri-state agent-editability flag per ADR-042 §5.4.1.

    * ``false`` — humans only.
    * ``true`` — any agent runtime may edit (subject to trailer/RBP).
    * ``allowlist`` — only runtimes listed in ``agent_editable_allowlist``.
    """

    TRUE = "true"
    FALSE = "false"
    ALLOWLIST = "allowlist"


class Phase(StrEnum):
    """Phase enum.

    Values are the canonical machine form; §26 prose uses 'Phase 0',
    'Phase 1.5', etc. for readability. ADR-043 phase_gate CLI uses
    enum-form (e.g., ``--check phase-1->phase-1-5``).
    """

    PLANNING = "planning"
    PHASE_0 = "phase-0"
    PHASE_1 = "phase-1"
    PHASE_1_5 = "phase-1-5"  # §26.3 Baseline review gate
    PHASE_2 = "phase-2"
    PHASE_3 = "phase-3"
    PHASE_4 = "phase-4"
    PHASE_5 = "phase-5"
    COMPLETE = "complete"


class Governs(BaseModel):
    """Governance scope declaration carried in ``governs:`` of frontmatter.

    ``modules`` are coarse-grained dotted module paths; ``contracts`` are
    function/class-level dotted symbol paths (ADR-042 §5.4). ``files``
    covers non-Python artefacts (workflows, configs, schemas).
    ``excludes`` carves negation out of any of the inclusive lists.
    """

    model_config = ConfigDict(extra="forbid")

    modules: list[DottedModulePath] = Field(default_factory=list)
    contracts: list[FunctionOrClassPath] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    files: list[RepoRelativePath] = Field(default_factory=list)
    # excludes: list[PathGlob] — both primitives imported from
    # `scieasy.qa.schemas._common` (audit fix C1: no circular import).
    excludes: list[PathGlob] = Field(default_factory=list)


class Translation(BaseModel):
    """Translation-link descriptor for ``translations:`` of frontmatter."""

    model_config = ConfigDict(extra="forbid")

    locale: LocaleCode
    path: RepoRelativePath
    auto_generated: bool = True
    source_sha: str | None = None


class AmendmentKind(StrEnum):
    """How an addendum amendment relates to its target section (§27.5)."""

    EXTEND = "extend"  # adds to the target (target prose still applies)
    REPLACE = "replace"  # supersedes target prose entirely
    CONSTRAIN = "constrain"  # tightens target (target still applies + restriction)
    CLARIFY = "clarify"  # editorial; no semantic change


class Amendment(BaseModel):
    """Single addendum amendment record. Used in ``ADRFrontmatter.amends``."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=4)  # e.g. "ADR-042 §17 Required Skills"
    kind: AmendmentKind
    summary: str = Field(min_length=4, max_length=240)


class ADRFrontmatter(BaseModel):
    """Full ADR frontmatter schema. See ADR-042 §5.2."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Identity
    adr: ADRRef
    title: str = Field(min_length=4, max_length=120)
    status: Status
    date_created: date
    date_accepted: date | None = None
    date_superseded: date | None = None

    # Lifecycle
    supersedes: list[ADRRef] = Field(default_factory=list)
    superseded_by: ADRRef | None = None
    related: list[ADRRef] = Field(default_factory=list)
    closes_issues: list[IssueRef] = Field(default_factory=list)
    tracking_issue: IssueRef | None = None

    # Addendum amendment records (§27.5; required for any ADR that amends another)
    amends: list[Amendment] = Field(default_factory=list)

    # Governance
    is_code_implementation: bool
    governs: Governs

    # Validation
    tests: list[RepoRelativePath] = Field(default_factory=list)

    # AI governance
    agent_editable: AgentEditable = AgentEditable.FALSE
    # AgentRuntime imported from `scieasy.qa.schemas.maintainers` (defined
    # in §6.2). Forward-import handled by `from __future__ import annotations`
    # at module top — pydantic resolves at validation time, not import time.
    # (iter-7 ITER-FRESH-012: import dependency made explicit.)
    agent_editable_allowlist: list[AgentRuntime] = Field(default_factory=list)
    # required non-empty iff agent_editable == ALLOWLIST (audit fix F4)
    assisted_by: list[AssistedByLine] = Field(default_factory=list)

    # Meta
    phase: Phase = Phase.PLANNING
    tags: list[str] = Field(default_factory=list)
    owner: GitHandle
    co_authors: list[GitHandle] = Field(default_factory=list)
    language_source: Literal["en"] = "en"
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _agent_editable_allowlist_paired(self) -> ADRFrontmatter:
        """Enforce ``allowlist`` ↔ non-empty ``agent_editable_allowlist`` pairing."""
        if self.agent_editable == AgentEditable.ALLOWLIST and not self.agent_editable_allowlist:
            raise ValueError("agent_editable=allowlist requires non-empty agent_editable_allowlist")
        if self.agent_editable != AgentEditable.ALLOWLIST and self.agent_editable_allowlist:
            raise ValueError("agent_editable_allowlist is only valid when agent_editable=allowlist")
        return self

    @model_validator(mode="after")
    def _status_dates_consistent(self) -> ADRFrontmatter:
        """Require date fields consistent with the declared status."""
        if self.status == Status.ACCEPTED and self.date_accepted is None:
            raise ValueError("status=Accepted requires date_accepted")
        if self.status == Status.SUPERSEDED:
            if self.date_superseded is None:
                raise ValueError("status=Superseded requires date_superseded")
            if self.superseded_by is None:
                raise ValueError("status=Superseded requires superseded_by")
        return self

    @model_validator(mode="after")
    def _code_impl_requires_governs_and_tests(self) -> ADRFrontmatter:
        """``is_code_implementation=true`` forces non-empty governs + tests."""
        if self.is_code_implementation:
            if not (self.governs.modules or self.governs.contracts):
                raise ValueError("is_code_implementation=true requires non-empty governs.modules or governs.contracts")
            if not self.tests:
                raise ValueError("is_code_implementation=true requires non-empty tests")
        return self

    @model_validator(mode="after")
    def _no_self_supersede(self) -> ADRFrontmatter:
        """Forbid an ADR superseding itself in either direction."""
        if self.adr in self.supersedes:
            raise ValueError("ADR cannot supersede itself")
        if self.superseded_by == self.adr:
            raise ValueError("ADR cannot be superseded by itself")
        return self


class SpecFrontmatter(BaseModel):
    """Subset of ADRFrontmatter for specs (no supersession lifecycle)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    spec_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$")
    title: str = Field(min_length=4, max_length=120)
    status: Literal["Draft", "Active", "Deprecated"]
    date_created: date

    related_adrs: list[ADRRef] = Field(default_factory=list)
    closes_issues: list[IssueRef] = Field(default_factory=list)

    is_code_implementation: bool
    governs: Governs  # already-implemented (subject to closure)
    planned_governs: Governs = Field(default_factory=Governs)
    # to-be-created in named phases
    tests: list[RepoRelativePath] = Field(default_factory=list)

    agent_editable: AgentEditable = AgentEditable.FALSE
    assisted_by: list[AssistedByLine] = Field(default_factory=list)

    tags: list[str] = Field(default_factory=list)
    owner: GitHandle
    co_authors: list[GitHandle] = Field(default_factory=list)
    language_source: Literal["en"] = "en"
    translations: list[Translation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _code_impl_requires_governs_and_tests(self) -> SpecFrontmatter:
        """``is_code_implementation=true`` requires governs OR planned_governs + tests."""
        if self.is_code_implementation:
            if not (
                self.governs.modules
                or self.governs.contracts
                or self.planned_governs.modules
                or self.planned_governs.contracts
            ):
                raise ValueError("is_code_implementation=true requires non-empty governs OR planned_governs")
            if not self.tests:
                raise ValueError("is_code_implementation=true requires non-empty tests")
        return self
