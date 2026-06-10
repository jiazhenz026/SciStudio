"""ADR-042 Addendum 6 governance runtime.

Single append-only gate ledger plus one shared evaluator. The historical
top-level guard modules and the flat ``GateRecord`` schema are gone
(delete-and-replace, ADR-042 Addendum 6 §3); guards are now evaluator-owned
calculators under ``gate_record.guards`` and the ledger lives in
``gate_record.ledger``.

The public surface delegates to the ``gate_record`` package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.qa.governance.gate_record import (
        GateLedger,
        GuardInputs,
        ReconcileResult,
    )

__all__ = [
    "GateLedger",
    "GuardInputs",
    "ReconcileResult",
    "main",
    "reconcile",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from scistudio.qa.governance import gate_record

        return getattr(gate_record, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
