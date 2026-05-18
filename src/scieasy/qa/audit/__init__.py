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

Additional orchestrators / specialised lint tools land in later sub-PRs
of the Phase 1B cascade.
"""

from __future__ import annotations

__all__ = [
    "auto_generated_lint",
    "closure",
    "codemod_lint",
    "doc_drift",
    "doc_length_lint",
    "fact_drift",
    "frontmatter_lint",
    "skill_pointer_sync",
    "workflow_sync",
]
