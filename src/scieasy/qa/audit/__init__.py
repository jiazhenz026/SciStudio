"""Audit tools for the ADR-042/043/044 QA regime.

The four core tools landed in Phase 1B sub-PR 1:

* :mod:`~scieasy.qa.audit.doc_drift` — a/b/c1/c2/c3/d drift classification
  (ADR-042 §9).
* :mod:`~scieasy.qa.audit.frontmatter_lint` — per-file YAML frontmatter
  validation dispatch (ADR-042 §5, ADR-044 §5.6).
* :mod:`~scieasy.qa.audit.fact_drift` — hardcoded-fact detection in prose
  (ADR-042 §10).
* :mod:`~scieasy.qa.audit.closure` — bidirectional MAINTAINERS↔governs
  closure (ADR-042 §11).

Phase 1B sub-PR 2 adds trailer / committer enforcement and the
orchestrators:

* :mod:`~scieasy.qa.audit.trailer_lint` — git trailer validation
  (ADR-042 §13 + ADR-043 §3.3 / §3.4.2).
* :mod:`~scieasy.qa.audit.committer_enforce` — commit-log vs git-log
  cross-check (ADR-042 §16).
* :mod:`~scieasy.qa.audit.full_audit` — orchestrator for every audit
  tool (ADR-042 §9.6).
* :mod:`~scieasy.qa.audit.contradiction_audit` — internal-contradiction
  scan (ADR-042 §28.1).
* :mod:`~scieasy.qa.audit.complete_artifacts` — Workflow v2 stage-6
  composite (ADR-042 §19.2 stage 6).

Phase 1B sub-PR 3 adds the codemod-metadata lint plus four ADR-044
documentation lints:

* :mod:`~scieasy.qa.audit.codemod_lint` — libCST codemod metadata
  validation (ADR-042 §20.3).
* :mod:`~scieasy.qa.audit.auto_generated_lint` — hand-edit detection on
  ``generation: auto`` files (ADR-044 §11.5 + §10.3).
* :mod:`~scieasy.qa.audit.doc_length_lint` — 2-letter-page cap on
  procedural docs (ADR-044 §4.3).
* :mod:`~scieasy.qa.audit.skill_pointer_sync` — skill-as-pointer
  discipline (ADR-044 §11.4).
* :mod:`~scieasy.qa.audit.workflow_sync` — workflow ↔ skill bidirectional
  closure (ADR-044 §11.5 + §12.3).
"""

from __future__ import annotations

__all__ = [
    "auto_generated_lint",
    "closure",
    "codemod_lint",
    "committer_enforce",
    "complete_artifacts",
    "contradiction_audit",
    "doc_drift",
    "doc_length_lint",
    "fact_drift",
    "frontmatter_lint",
    "full_audit",
    "skill_pointer_sync",
    "trailer_lint",
    "workflow_sync",
]
