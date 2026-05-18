"""Governance-layer audit tools (ADR-043 §3 + §6.4).

Phase 1E deliverables — consumers of the schemas already shipped in
:mod:`scieasy.qa.schemas.governance`.

Modules:

- :mod:`scieasy.qa.governance.mod_guard` — LOCAL pre-commit governance-
  modification check (ADR-043 §3.3 Tool 1).
- :mod:`scieasy.qa.governance.mod_pr_check` — CI authoritative
  governance-modification verifier (ADR-043 §3.3 Tool 2).
- :mod:`scieasy.qa.governance.monotonic_check` — 14-axis monotonic-
  strengthening check (ADR-043 §3.4).
- :mod:`scieasy.qa.governance.honeypot` — Honeypot canary integrity
  check (ADR-043 §3.6.3).

Each module exposes the top-level entry-point function signatures listed
in ADR-043 §4.7 (audit fix F14) plus a ``main(argv)`` CLI used by the
``scripts/audit/<tool>.py`` pre-commit / CI shims.
"""
