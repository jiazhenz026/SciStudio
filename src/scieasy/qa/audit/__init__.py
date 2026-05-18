"""Audit tools for the ADR-042/043/044 QA regime.

The four core tools in this sub-package are:

* :mod:`~scieasy.qa.audit.doc_drift` — a/b/c1/c2/c3/d drift classification
  (ADR-042 §9).
* :mod:`~scieasy.qa.audit.frontmatter_lint` — per-file YAML frontmatter
  validation dispatch (ADR-042 §5, ADR-044 §5.6).
* :mod:`~scieasy.qa.audit.fact_drift` — hardcoded-fact detection in prose
  (ADR-042 §10).
* :mod:`~scieasy.qa.audit.closure` — bidirectional MAINTAINERS↔governs
  closure (ADR-042 §11).

Additional orchestrators / specialised lint tools land in later sub-PRs of
the Phase 1B cascade (sub-PRs 2 + 3).
"""

from __future__ import annotations

__all__ = [
    "closure",
    "doc_drift",
    "fact_drift",
    "frontmatter_lint",
]
