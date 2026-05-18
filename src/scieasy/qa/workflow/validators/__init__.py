"""Per-stage validators for Workflow v2 (ADR-042 §19).

Each module under this package exports one or more ``Validator`` protocol
implementations (see ``scieasy.qa.workflow.gate.Validator``). The
``_registry`` module wires them up by string ID so
``.workflow/schema-v2.yaml`` can reference them declaratively.

This package ships in **shadow mode** during Phase 1 of the
ADR-042/043/044 cascade: validators are exercised in parallel with the
existing v1 gate, but v1 remains authoritative. Phase 2 flips v2 to
authoritative; Phase 3 deprecates v1.

References
----------
ADR-042 §19 — Workflow v2 design.
ADR-042 §19.2 — the seven stages.
ADR-042 §19.5 — stage definitions in code (foundation shipped in TC-1A.11).
ADR-042 §19.6 — migration from 6-gate.
"""

from __future__ import annotations

from scieasy.qa.workflow.validators._registry import VALIDATORS, get_validator

__all__ = ["VALIDATORS", "get_validator"]
