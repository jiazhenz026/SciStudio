"""Leaf-level types shared by guard calculators (ADR-042 Addendum 6 spec §4).

``GuardInputs`` and the ``Guard`` callable type live here (not in
``guards/__init__.py``) so individual guard modules can import them without
creating an import cycle through the package ``__init__``.

``guards/__init__.py`` re-exports both names for callers that import from the
package (the evaluator imports ``GuardInputs`` and ``GUARD_REGISTRY`` from
there). Guard submodules MUST import from this module directly:

    from scistudio.qa.governance.gate_record.guards._base import GuardInputs

Never import ``from scistudio.qa.governance.gate_record.guards import GuardInputs``
inside a guard submodule — that path goes through ``__init__`` which imports
the submodule back, creating a cycle.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record.ledger import (
    AdminLabel,
    IssueRef,
    Persona,
    StrictnessTier,
    TaskKind,
)
from scistudio.qa.schemas.report import AuditReport


@dataclass(frozen=True)
class GuardInputs:
    """The evaluator-built input bundle every guard calculator receives (§4).

    Guards must read ONLY from this bundle. They must not load the ledger, run
    git, or maintain independent rule sets.
    """

    repo_root: Path
    mode: str
    task_kind: TaskKind
    persona: Persona
    runtime: str
    tier: StrictnessTier
    governance_touch: bool
    # Observed (git-derived) facts.
    changed_files: Sequence[str]
    diff_fingerprint: str | None
    # Classified surfaces: surface-class name -> changed paths in that class.
    surfaces: Mapping[str, Sequence[str]]
    # Effective declared scope.
    effective_include: Sequence[str]
    effective_exclude: Sequence[str]
    # Declared vs observed docs/tests (already reconciled by the evaluator).
    declared_docs_paths: Sequence[str]
    declared_test_paths: Sequence[str]
    verified_docs_paths: Sequence[str]
    verified_test_paths: Sequence[str]
    # Issues and PR facts.
    issues: Sequence[IssueRef]
    pr_body: str | None
    pr_context: Mapping[str, Any] | None
    # Admin labels.
    requested_admin_labels: Sequence[AdminLabel]
    observed_admin_labels: Sequence[AdminLabel]
    # Free-form extras the evaluator may attach (e.g. sentrux evidence).
    extras: Mapping[str, Any] = field(default_factory=dict)


# A guard calculator: pure function from inputs to an AuditReport.
Guard = Callable[[GuardInputs], AuditReport]
