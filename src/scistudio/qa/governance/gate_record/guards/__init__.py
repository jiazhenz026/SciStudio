"""Evaluator-owned guard calculators for ADR-042 Addendum 6 (spec §4).

Each guard is a pure function ``check(inputs: GuardInputs) -> AuditReport``
that takes evaluator-built inputs (ledger facts + observed diff + classified
surfaces + repo state + PR context) and returns findings via the shared
``qa.schemas.report`` types. No guard reads the ledger itself, runs its own git
diff, or keeps its own task-kind rules, required-check sets, bypass vocabulary,
or protected-path lists — the evaluator owns those and supplies them.

This module defines the :class:`GuardInputs` bundle, the ``Guard`` callable
type, and the ``GUARD_REGISTRY`` the evaluator iterates. Calculators here are
STUBS returning empty reports; B2 (#1509) replaces them with real logic. The
interface signature is frozen so B2/B3/B4 build against it without churn.
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


from scistudio.qa.governance.gate_record.guards import (  # noqa: E402  (avoid cycle at import top)
    core_change_guard,
    docs_landing,
    human_bypass_guard,
    issue_link,
    mod_guard,
    persona_policy,
    pr_merge_guard,
    sentrux_gate,
    test_engineer_scope_guard,
    weakened_ci_check,
)

# The registry the evaluator iterates. Each guard runs exactly once. B2 (#1509)
# replaces these stubs with real calculators; the keys and signatures are
# stable contract for B2/B3/B4.
GUARD_REGISTRY: dict[str, Guard] = {
    "core_change_guard": core_change_guard.check,
    "human_bypass_guard": human_bypass_guard.check,
    "pr_merge_guard": pr_merge_guard.check,
    "mod_guard": mod_guard.check,
    "weakened_ci_check": weakened_ci_check.check,
    "sentrux_gate": sentrux_gate.check,
    "test_engineer_scope_guard": test_engineer_scope_guard.check,
    "docs_landing": docs_landing.check,
    "issue_link": issue_link.check,
    "persona_policy": persona_policy.check,
}

__all__ = ["GUARD_REGISTRY", "Guard", "GuardInputs"]
