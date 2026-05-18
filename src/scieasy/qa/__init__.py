"""SciEasy QA infrastructure namespace (ADR-042/043/044 cascade).

This package owns the quality-assurance infrastructure introduced by the
ADR-042/043/044 cascade. It is built up incrementally during Phase 1 of
the cascade; sub-packages land as their tracking branches merge.

Already shipped on this tracking branch base (1A schemas, merged via
#1128/#1131/#1133):

- ``scieasy.qa.schemas`` — pydantic models for frontmatter (ADR-042 §5),
  MAINTAINERS (§6), audit reports (§7), facts registry (§7.5), identity
  (§25.3), tracker (ADR-043 §2.2), governance (§3), test_quality (§4.2),
  classification (§6), and doc schemas (ADR-044 §5).
- ``scieasy.qa.workflow`` — Workflow v2 gate primitives (§19.5).

This PR (Phase 1D sub-PR 1, TC-1D.9) adds:

- ``scieasy.qa.translation`` — translator client + providers + settings
  (per ADR-042 §22).

Future contents (other Phase 1 sub-phases):

- ``scieasy.qa.audit`` — audit tools (doc_drift, frontmatter_lint,
  fact_drift, closure, trailer_lint, full_audit, ...).
- ``scieasy.qa.docs.directives`` + ``scieasy.qa.docs.generators`` — Sphinx
  custom directives and reference doc generators.
- ``scieasy.qa.test_quality`` — AST anti-pattern lint, mutation runner.
- ``scieasy.qa.codemods`` — libCST codemod base + ADR-specific codemods.

See ``docs/adr/ADR-042.md``, ``ADR-043.md``, ``ADR-044.md`` for the full
design.
"""
