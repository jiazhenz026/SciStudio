"""Stage / validator shapes for Workflow v2 (ADR-042 §19.5).

This module is the public surface that Workflow v2's gate machinery
(loaded from ``.workflow/schema-v2.yaml`` in TC-1H.1) and the per-stage
validator implementations (TC-1H.2 under
``scieasy.qa.workflow.validators``) compose against.

Design summary (ADR-042 §19.5):

- ``StageContext`` is the read-only runtime context every Validator
  receives. ``declared_data: dict[str, object]`` carries the
  caller-provided ``--data`` payload from ``gate.py advance``; each
  Validator parses the slice it owns (the union shape is intentionally
  not modelled here — adding a discriminated union per stage would
  couple this base module to every stage's data shape).
- ``ValidationResult`` is the per-Validator outcome. ``status`` is a
  ``Literal["pass", "fail", "skip"]`` because the gate runner needs to
  distinguish "validator chose not to run" (skip) from "validator ran
  and is happy" (pass).
- ``Validator`` is a ``@runtime_checkable`` Protocol — Phase 1
  investigation SUMMARY X2 manager default. The runtime-checkable bit
  lets ``gate.py``'s stage loader confirm that a class registered in
  ``schema-v2.yaml`` actually matches the contract before invoking it.
- ``StageDefinition`` is a plain dataclass (not a pydantic model)
  because its ``validations: list[Validator]`` field holds executable
  objects, not data — pydantic v2 chokes on Protocol-typed lists
  containing instances unless we go through ``arbitrary_types_allowed``,
  and we get no value from validating an in-process list of callables.

References
----------
ADR-042 §19 — Workflow v2 design.
ADR-042 §19.5 (lines 2317-2366) — authoritative model definitions
(verbatim source for this file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class StageContext(BaseModel):
    """Per-stage runtime context passed to each Validator.

    ``declared_data`` carries arbitrary caller-supplied payload from
    ``gate.py advance --data '{...}'``; per-Validator parsing is the
    Validator's responsibility (each stage owns its own slice shape).
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    stage_name: str
    repo_root: str
    pr_number: int | None
    branch: str
    declared_data: dict[str, object]


class ValidationResult(BaseModel):
    """Outcome of a single Validator invocation."""

    model_config = ConfigDict(extra="forbid")

    validator_id: str
    status: Literal["pass", "fail", "skip"]
    message: str
    blocking: bool = True


@runtime_checkable
class Validator(Protocol):
    """Callable contract for stage-level check functions.

    A Validator inspects a ``StageContext`` and returns a
    ``ValidationResult``. Used by Workflow v2 (§19) to compose stage
    definition-of-done from machine-checkable building blocks.

    Marked ``@runtime_checkable`` per Phase 1 investigation SUMMARY X2
    so the stage loader can ``isinstance``-check registered objects
    against the protocol at startup.
    """

    validator_id: str
    blocking: bool

    def __call__(self, ctx: StageContext) -> ValidationResult: ...


@dataclass
class StageDefinition:
    """A single stage in the Workflow v2 graph.

    Authored declaratively in ``.workflow/schema-v2.yaml`` (TC-1H.1).
    """

    name: str
    requires: list[str]
    validations: list[Validator]
    guidance_template: str
    auto_advance: bool
    sub_checklist: list[str] = field(default_factory=list)
