"""QA (Quality Assurance) package.

This package contains the QA infrastructure introduced by ADR-042/043/044
(QA Infrastructure Overhaul cascade). It is built up incrementally during
Phase 1 of the cascade; sub-packages land as their tracking branches merge.

Current contents (Phase 1D, sub-PR 1 — TC-1D.9):

- ``scieasy.qa.translation`` — translator client + providers + settings
  (per ADR-042 §22).

Future contents (Phase 1A/1B/etc., not yet landed in this PR):

- ``scieasy.qa.schemas`` — pydantic models for frontmatter, audit reports,
  governance, identity, etc.
- ``scieasy.qa.audit`` — audit tools (doc_drift, frontmatter_lint,
  fact_drift, closure, trailer_lint, full_audit, ...).
- ``scieasy.qa.docs`` — Sphinx directive/generator package.
- ``scieasy.qa.workflow`` — gate.py v2 + per-stage validators.

See ``docs/adr/ADR-042.md``, ``ADR-043.md``, ``ADR-044.md`` for the
full design.
"""
