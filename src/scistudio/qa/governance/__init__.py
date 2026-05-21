"""ADR-042 governance guard tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.qa.governance.gate_record import (
        CheckEvidence,
        FullAuditEvidence,
        GateRecord,
        GateStage,
        SentruxEvidence,
    )

__all__ = [
    "CheckEvidence",
    "FullAuditEvidence",
    "GateRecord",
    "GateStage",
    "SentruxEvidence",
    "amend_record",
    "check_commit_msg",
    "check_pr",
    "check_pr_ready",
    "check_pre_commit",
    "check_pre_push",
    "check_record",
    "docs_record",
    "finalize_record",
    "plan_record",
    "sentrux_record",
    "start_record",
    "validate_gate_record",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from scistudio.qa.governance import gate_record

        return getattr(gate_record, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
