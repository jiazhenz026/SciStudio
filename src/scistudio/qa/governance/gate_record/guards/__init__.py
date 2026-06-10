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

# GuardInputs and Guard live in _base to avoid import cycles: guard submodules
# import from _base directly; __init__ re-exports them for external callers.
import scistudio.qa.governance.gate_record.guards.core_change_guard as core_change_guard
import scistudio.qa.governance.gate_record.guards.docs_landing as docs_landing
import scistudio.qa.governance.gate_record.guards.human_bypass_guard as human_bypass_guard
import scistudio.qa.governance.gate_record.guards.issue_link as issue_link
import scistudio.qa.governance.gate_record.guards.mod_guard as mod_guard
import scistudio.qa.governance.gate_record.guards.persona_policy as persona_policy
import scistudio.qa.governance.gate_record.guards.pr_merge_guard as pr_merge_guard
import scistudio.qa.governance.gate_record.guards.sentrux_gate as sentrux_gate
import scistudio.qa.governance.gate_record.guards.test_engineer_scope_guard as test_engineer_scope_guard
import scistudio.qa.governance.gate_record.guards.weakened_ci_check as weakened_ci_check

# GuardInputs and Guard live in _base to avoid import cycles: guard submodules
# import from _base directly; __init__ re-exports them for external callers.
from scistudio.qa.governance.gate_record.guards._base import Guard, GuardInputs

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
