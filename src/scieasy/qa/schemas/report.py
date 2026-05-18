"""Pydantic models for the shared audit-report envelope.

Every audit tool in the ADR-042/043/044 regime (``doc_drift``,
``frontmatter_lint``, ``fact_drift``, ``closure``, ``full_audit``, …)
emits its findings inside a versioned ``AuditReport``. This module is
the authoritative shape; consumers include CI annotations, the
``doc-drift-guard`` skill, the HTML weekly-report renderer, and the
Phase 4 revalidation gate.

The schema is intentionally extensible: ``ToolRun`` carries the
per-tool config hash so report consumers can detect re-runs vs
re-configurations; ``Finding.related_findings`` is a free-form
back-reference list for cross-rule grouping by downstream UIs.

References
----------
ADR-042 §7.1 — purpose.
ADR-042 §7.2 — schema (authoritative source for this file).
ADR-042 §7.3 — storage / immutability semantics.
ADR-042 §7.4 — consumers.

Manager-default validator note
------------------------------
Per the Phase 1 investigation SUMMARY TC-1A.3, ``AuditReport`` adds an
optional ``model_validator(mode="after")`` enforcing
``total_findings == sum(len(r.findings) for r in runs)`` and the
two ``by_*`` dicts agreeing with the flat ``findings`` list. This is a
denormalisation guard; report producers compute the totals themselves
and the validator catches arithmetic mistakes early.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DriftClass(StrEnum):
    """Drift classification per ADR-042 §9 (a/b/c1/c2/c3/d).

    * ``a`` — agree (doc cites symbol, code agrees).
    * ``b`` — disagree (signature/schema mismatch).
    * ``c1`` — doc cites symbol; code missing; symbol existed historically.
    * ``c2`` — doc cites symbol; code missing; symbol never existed.
    * ``c3`` — doc/code mismatch; cannot determine wrong side.
    * ``d`` — public code symbol with no ADR coverage.
    """

    A = "a"
    B = "b"
    C1 = "c1"
    C2 = "c2"
    C3 = "c3"
    D = "d"


class Severity(StrEnum):
    """Three-level severity scale for audit findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    """A single audit finding emitted by some tool.

    ``drift_class`` is ``None`` for tool runs whose findings are not drift-
    classified (e.g. frontmatter-lint validation errors). ``line`` /
    ``symbol`` may be ``None`` for repo-level findings. ``git_evidence``
    is an opaque tool-specific blob (e.g. a blame line, a trailer
    string) preserved for forensic queries.
    """

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
    """One audit-tool invocation packaged for inclusion in ``AuditReport``."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    version: str
    config_hash: str
    started_at: datetime
    completed_at: datetime
    exit_status: Literal["ok", "warnings", "errors", "crash"]
    findings: list[Finding] = Field(default_factory=list)


class CommitLogEntry(BaseModel):
    """One line of ``docs/audit/commit-log.jsonl`` (ADR-042 §16.5).

    Written by ``scripts/committer.py`` (TC-1H.8, not yet shipped) on every
    agent-authored commit. Consumed by
    :func:`scieasy.qa.audit.committer_enforce.check` to verify that every
    agent commit in ``git log`` is also present in the log file.

    Co-located here per Phase 1 investigation default Q1B.6.1 (the
    canonical schema lives next to the audit-report envelope so the
    committer-enforce tool has a single import path). The pydantic model
    enforces ``extra="forbid"`` so any field rename in
    ``scripts/committer.py`` surfaces as a validation error rather than
    silently dropped data.

    References
    ----------
    ADR-042 §16.5 — JSONL shape (authoritative).
    """

    model_config = ConfigDict(extra="forbid")

    sha: str = Field(min_length=7, max_length=64, pattern=r"^[0-9a-f]+$")
    timestamp: datetime
    author: str = Field(min_length=1)
    runtime: str = Field(min_length=1)
    model: str = Field(min_length=1)
    files: list[str] = Field(default_factory=list)
    message_first_line: str = Field(min_length=1)


class AuditReport(BaseModel):
    """Top-level audit report envelope. Versioned by ``schema_version``.

    The two ``by_*`` dicts plus ``total_findings`` are denormalisations
    of the embedded findings: consumers may use them for cheap summary
    queries without iterating ``runs``. The post-init validator enforces
    arithmetic consistency between the denormalisations and the raw
    findings list.
    """

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

    bidirectional_closure_ok: bool
    translation_ok: bool

    @model_validator(mode="after")
    def _denormalised_totals_consistent(self) -> AuditReport:
        """Enforce ``total_findings``/``by_severity``/``by_drift_class`` agree with ``runs``.

        Manager default per Phase 1 investigation SUMMARY TC-1A.3: the
        flat ``findings`` list is the source of truth; the denormalised
        counters are an optimisation that must not drift.
        """
        all_findings = [f for run in self.runs for f in run.findings]
        observed_total = len(all_findings)
        if self.total_findings != observed_total:
            raise ValueError(
                f"total_findings={self.total_findings} disagrees with len(flattened findings)={observed_total}"
            )

        observed_by_sev: Counter[Severity] = Counter(f.severity for f in all_findings)
        declared_by_sev = {sev: count for sev, count in self.by_severity.items() if count}
        if declared_by_sev != {sev: count for sev, count in observed_by_sev.items() if count}:
            raise ValueError(
                f"by_severity={dict(self.by_severity)} disagrees with observed counts {dict(observed_by_sev)}"
            )

        observed_by_class: Counter[DriftClass] = Counter(
            f.drift_class for f in all_findings if f.drift_class is not None
        )
        declared_by_class = {cls: count for cls, count in self.by_drift_class.items() if count}
        if declared_by_class != {cls: count for cls, count in observed_by_class.items() if count}:
            raise ValueError(
                f"by_drift_class={dict(self.by_drift_class)} disagrees with observed counts {dict(observed_by_class)}"
            )
        return self
