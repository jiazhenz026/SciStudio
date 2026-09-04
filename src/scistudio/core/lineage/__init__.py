"""Unified run-lineage package — the four-table provenance store.

Records what every workflow run did: which blocks executed, which data objects
they consumed and produced, and the environment they ran in. Everything is
written by the engine into a single SQLite database, so block authors never
have to touch the lineage layer directly.

Exports:

* :class:`LineageStore` — the SQLite-backed store holding the four tables.
* :class:`LineageRecorder` — the engine-side writer that listens for block
  events and fills the store as a run proceeds.
* :class:`RunRecord`, :class:`ExploreSessionRecord`,
  :class:`BlockExecutionRecord`, :class:`DataObjectRow`, :class:`BlockIORow` —
  dataclasses mirroring the tables. ``runs`` and ``explore_sessions`` are the
  two anchors (ADR-054 FR-052); the three below them are shared.
* :class:`EnvironmentSnapshot` — a capture of the Python and package versions a
  run used.
* :class:`RunContext` (with :func:`get_run_context`, :func:`set_run_context`,
  :func:`reset_run_context`) — a thread/task-local handle to the active run.

There is no in-memory provenance graph; query the store with SQL instead.
"""

from __future__ import annotations

from scistudio.core.lineage.environment import EnvironmentSnapshot
from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    ExploreSessionRecord,
    RunRecord,
)
from scistudio.core.lineage.recorder import LineageRecorder
from scistudio.core.lineage.run_context import (
    RunContext,
    get_run_context,
    reset_run_context,
    set_run_context,
)
from scistudio.core.lineage.store import LineageStore

__all__ = [
    "BlockExecutionRecord",
    "BlockIORow",
    "DataObjectRow",
    "EnvironmentSnapshot",
    "ExploreSessionRecord",
    "LineageRecorder",
    "LineageStore",
    "RunContext",
    "RunRecord",
    "get_run_context",
    "reset_run_context",
    "set_run_context",
]
