"""Unified 4-table lineage package (ADR-038).

Exports:

* :class:`LineageStore` — SQLite-backed unified store
* :class:`LineageRecorder` — event-driven writer wired into the scheduler
* :class:`RunRecord`, :class:`BlockExecutionRecord`, :class:`DataObjectRow`,
  :class:`BlockIORow` — dataclasses mirroring the four tables
* :class:`EnvironmentSnapshot` — uv-pip-freeze capture used for ``runs.environment_snapshot``
* :class:`RunContext` — thread/task-local active-run accessor

The pre-ADR-038 ``ProvenanceGraph`` helper is removed (ADR-038 §3.4: no
content hashing → no hash-keyed graph). Use SQL queries against the unified
store instead — see ADR-038 §3.7 for the four canonical query patterns.

For backwards compatibility, the legacy ``LineageRecord`` name is re-exported
as a no-op shell (Phase D38-2.3 replaces it with a deprecation shim).
"""

from __future__ import annotations

from scieasy.core.lineage.environment import EnvironmentSnapshot
from scieasy.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    LineageRecord,
    RunRecord,
)
from scieasy.core.lineage.recorder import LineageRecorder
from scieasy.core.lineage.run_context import (
    RunContext,
    get_run_context,
    reset_run_context,
    set_run_context,
)
from scieasy.core.lineage.store import LineageStore

__all__ = [
    "BlockExecutionRecord",
    "BlockIORow",
    "DataObjectRow",
    "EnvironmentSnapshot",
    "LineageRecord",
    "LineageRecorder",
    "LineageStore",
    "RunContext",
    "RunRecord",
    "get_run_context",
    "reset_run_context",
    "set_run_context",
]
