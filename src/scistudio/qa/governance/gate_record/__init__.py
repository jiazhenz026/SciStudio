"""ADR-042 Addendum 6 gate ledger package.

Single append-only ledger + one shared evaluator + workflow CLI. Hooks, the PR
wrapper, and CI all call the same ``evaluator.reconcile()``. The
``python -m scistudio.qa.governance.gate_record`` entry point is preserved; only
the internals and CLI surface changed.

Public surface (B2/B3/B4 build against these):

- ``GateLedger`` and its event models (``ledger``)
- ``reconcile`` / ``ReconcileResult`` / ``EvaluatorMode`` (``evaluator``)
- ``GuardInputs`` / ``Guard`` / ``GUARD_REGISTRY`` (``guards``)
- ``surfaces`` classifier predicates and ``labels`` vocabulary
- ``io`` append-only writers + deterministic discovery
- ``main`` (CLI entry point)
"""

from __future__ import annotations

from scistudio.qa.governance.gate_record.cli import main
from scistudio.qa.governance.gate_record.evaluator import (
    EvaluatorMode,
    ReconcileResult,
    classify_surfaces,
    derive_tier,
    reconcile,
)
from scistudio.qa.governance.gate_record.guards import GUARD_REGISTRY, Guard, GuardInputs
from scistudio.qa.governance.gate_record.labels import (
    ADMIN_LABELS,
    BYPASS_LABEL,
    CORE_CHANGE_LABEL,
    HUMAN_AUTHORED_LABEL,
    MERGE_LABEL,
    VALID_LABELS,
)
from scistudio.qa.governance.gate_record.ledger import (
    LEDGER_SCHEMA_VERSION,
    SUPPORTED_PERSONAS,
    SUPPORTED_TASK_KINDS,
    AdminLabel,
    CheckEvent,
    CommitEvidence,
    DeclaredScope,
    DirectiveEvent,
    DocsEvent,
    GateLedger,
    GuardEvent,
    IssueRef,
    ObservedDiff,
    Persona,
    PullRequestEvidence,
    ReconcileEvent,
    RequiredObligations,
    ScopeEvent,
    StrictnessTier,
    TaskKind,
    TestEvent,
)

__all__ = [
    "ADMIN_LABELS",
    "BYPASS_LABEL",
    "CORE_CHANGE_LABEL",
    "GUARD_REGISTRY",
    "HUMAN_AUTHORED_LABEL",
    "LEDGER_SCHEMA_VERSION",
    "MERGE_LABEL",
    "SUPPORTED_PERSONAS",
    "SUPPORTED_TASK_KINDS",
    "VALID_LABELS",
    "AdminLabel",
    "CheckEvent",
    "CommitEvidence",
    "DeclaredScope",
    "DirectiveEvent",
    "DocsEvent",
    "EvaluatorMode",
    "GateLedger",
    "Guard",
    "GuardEvent",
    "GuardInputs",
    "IssueRef",
    "ObservedDiff",
    "Persona",
    "PullRequestEvidence",
    "ReconcileEvent",
    "ReconcileResult",
    "RequiredObligations",
    "ScopeEvent",
    "StrictnessTier",
    "TaskKind",
    "TestEvent",
    "classify_surfaces",
    "derive_tier",
    "main",
    "reconcile",
]
