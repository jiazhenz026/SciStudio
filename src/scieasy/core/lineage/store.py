"""LineageStore — unified 4-table SQLite store for run lineage (ADR-038 §3.1).

Tables:

* ``runs``             — one row per workflow execution
* ``block_executions`` — one row per block per run
* ``data_objects``     — DataObject identity catalog
* ``block_io``         — port-to-DataObject edges per execution

All writes happen in the engine process. Worker subprocesses do NOT connect
to this database. The store is best-effort: write failures are logged and
swallowed by the recorder so a lineage outage never breaks the workflow.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from scieasy.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema (ADR-038 §3.1 verbatim)
# ---------------------------------------------------------------------------

_SCHEMA_STATEMENTS: list[str] = [
    # Table 1: runs
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id                  TEXT PRIMARY KEY,
        workflow_id             TEXT NOT NULL,
        workflow_git_commit     TEXT,
        workflow_yaml_snapshot  TEXT NOT NULL,
        workflow_dirty          INTEGER NOT NULL,
        started_at              TEXT NOT NULL,
        finished_at             TEXT,
        status                  TEXT NOT NULL,
        environment_snapshot    TEXT NOT NULL,
        triggered_by            TEXT NOT NULL,
        parent_run_id           TEXT REFERENCES runs(run_id),
        execute_from_block_id   TEXT,
        user_notes              TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_id, started_at DESC)",
    # Table 2: block_executions
    """
    CREATE TABLE IF NOT EXISTS block_executions (
        block_execution_id      TEXT PRIMARY KEY,
        run_id                  TEXT NOT NULL REFERENCES runs(run_id),
        block_id                TEXT NOT NULL,
        block_type              TEXT NOT NULL,
        block_version           TEXT NOT NULL,
        block_config_resolved   TEXT NOT NULL,
        started_at              TEXT NOT NULL,
        finished_at             TEXT,
        duration_ms             INTEGER,
        termination             TEXT NOT NULL,
        termination_detail      TEXT,
        UNIQUE (run_id, block_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_be_run ON block_executions(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_be_block ON block_executions(block_id)",
    # Table 3: data_objects
    """
    CREATE TABLE IF NOT EXISTS data_objects (
        object_id               TEXT PRIMARY KEY,
        type_name               TEXT NOT NULL,
        backend                 TEXT,
        storage_path            TEXT,
        size_bytes              INTEGER,
        mtime_at_write          TEXT,
        created_at              TEXT NOT NULL,
        wire_payload            TEXT NOT NULL,
        derived_from            TEXT REFERENCES data_objects(object_id),
        produced_by_execution   TEXT REFERENCES block_executions(block_execution_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_do_storage ON data_objects(storage_path)",
    "CREATE INDEX IF NOT EXISTS idx_do_derived ON data_objects(derived_from)",
    "CREATE INDEX IF NOT EXISTS idx_do_producer ON data_objects(produced_by_execution)",
    # Table 4: block_io
    """
    CREATE TABLE IF NOT EXISTS block_io (
        block_execution_id      TEXT NOT NULL REFERENCES block_executions(block_execution_id),
        direction               TEXT NOT NULL,
        port_name               TEXT NOT NULL,
        object_id               TEXT NOT NULL REFERENCES data_objects(object_id),
        position                INTEGER NOT NULL,
        PRIMARY KEY (block_execution_id, direction, port_name, position)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_io_object ON block_io(object_id)",
]


class LineageStore:
    """SQLite-backed unified lineage store (ADR-038 §3.1).

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file. Pass ``":memory:"`` for
        an in-process ephemeral store (used by tests).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            default_dir = Path(".scieasy")
            default_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(default_dir / "lineage.db")

        self._db_path = str(db_path)
        # ``check_same_thread=False`` because the engine emits events from
        # asyncio tasks across the default loop's executor; SQLite is
        # serialised internally and the recorder calls are single-flight.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        for stmt in _SCHEMA_STATEMENTS:
            self._conn.execute(stmt)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        import contextlib

        with contextlib.suppress(sqlite3.ProgrammingError):
            self._conn.close()

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def insert_run(self, run: RunRecord) -> None:
        """Insert a row into ``runs``."""
        self._conn.execute(
            """
            INSERT INTO runs (
                run_id, workflow_id, workflow_git_commit, workflow_yaml_snapshot,
                workflow_dirty, started_at, finished_at, status,
                environment_snapshot, triggered_by, parent_run_id,
                execute_from_block_id, user_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.workflow_id,
                run.workflow_git_commit,
                run.workflow_yaml_snapshot,
                int(bool(run.workflow_dirty)),
                run.started_at,
                run.finished_at,
                run.status,
                json.dumps(run.environment_snapshot),
                run.triggered_by,
                run.parent_run_id,
                run.execute_from_block_id,
                run.user_notes,
            ),
        )
        self._conn.commit()

    def finalize_run(self, run_id: str, *, finished_at: str, status: str) -> None:
        """Update terminal columns on a ``runs`` row."""
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, status = ? WHERE run_id = ?",
            (finished_at, status, run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a ``runs`` row as a dict, or ``None`` if absent."""
        cur = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row, strict=False))

    def list_runs(self, workflow_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Return runs in reverse-chronological order."""
        if workflow_id is None:
            cur = self._conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        else:
            cur = self._conn.execute(
                "SELECT * FROM runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
                (workflow_id, limit),
            )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # block_executions
    # ------------------------------------------------------------------

    def insert_block_execution(self, be: BlockExecutionRecord) -> None:
        """Insert a row into ``block_executions``."""
        self._conn.execute(
            """
            INSERT INTO block_executions (
                block_execution_id, run_id, block_id, block_type, block_version,
                block_config_resolved, started_at, finished_at, duration_ms,
                termination, termination_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                be.block_execution_id,
                be.run_id,
                be.block_id,
                be.block_type,
                be.block_version,
                json.dumps(be.block_config_resolved, default=str),
                be.started_at,
                be.finished_at,
                be.duration_ms,
                be.termination,
                be.termination_detail,
            ),
        )
        self._conn.commit()

    def list_block_executions(self, run_id: str) -> list[dict[str, Any]]:
        """List blocks for a run ordered by start time."""
        cur = self._conn.execute(
            "SELECT * FROM block_executions WHERE run_id = ? ORDER BY started_at",
            (run_id,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # data_objects
    # ------------------------------------------------------------------

    def upsert_data_object(self, row: DataObjectRow) -> None:
        """Insert a ``data_objects`` row, or skip when already present.

        ``object_id`` is a UUIDv4 produced by FrameworkMeta. Duplicate writes
        of the same object_id are no-ops; we deliberately do NOT update
        ``storage_path`` because subsequent runs may overwrite the path and
        the stored value should reflect the producing run's state.
        """
        self._conn.execute(
            """
            INSERT OR IGNORE INTO data_objects (
                object_id, type_name, backend, storage_path, size_bytes,
                mtime_at_write, created_at, wire_payload, derived_from,
                produced_by_execution
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.object_id,
                row.type_name,
                row.backend,
                row.storage_path,
                row.size_bytes,
                row.mtime_at_write,
                row.created_at,
                json.dumps(row.wire_payload, default=str),
                row.derived_from,
                row.produced_by_execution,
            ),
        )
        self._conn.commit()

    def get_data_object(self, object_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT * FROM data_objects WHERE object_id = ?", (object_id,))
        row = cur.fetchone()
        if row is None:
            return None
        columns = [d[0] for d in cur.description]
        return dict(zip(columns, row, strict=False))

    # ------------------------------------------------------------------
    # block_io
    # ------------------------------------------------------------------

    def insert_block_io(self, edge: BlockIORow) -> None:
        """Insert a ``block_io`` edge. Duplicate edges are silently skipped."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO block_io (
                block_execution_id, direction, port_name, object_id, position
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                edge.block_execution_id,
                edge.direction,
                edge.port_name,
                edge.object_id,
                edge.position,
            ),
        )
        self._conn.commit()

    def list_block_io(self, block_execution_id: str) -> list[dict[str, Any]]:
        """Return all I/O edges for a block_execution, ordered for display."""
        cur = self._conn.execute(
            """
            SELECT * FROM block_io
            WHERE block_execution_id = ?
            ORDER BY direction, port_name, position
            """,
            (block_execution_id,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Test / introspection helpers
    # ------------------------------------------------------------------

    def count(self, table: str) -> int:
        """Return ``SELECT COUNT(*)`` of a known table (used by tests)."""
        if table not in {"runs", "block_executions", "data_objects", "block_io"}:
            raise ValueError(f"unknown lineage table: {table}")
        cur = self._conn.execute(f"SELECT COUNT(*) FROM {table}")  # table name allow-listed above
        return int(cur.fetchone()[0])
