"""LineageStore — unified 4-table SQLite store for run lineage (ADR-038 §3.1).

Tables:

* ``runs``             — one row per workflow execution
* ``block_executions`` — one row per block per run
* ``data_objects``     — DataObject identity catalog
* ``block_io``         — port-to-DataObject edges per execution

All writes happen in the engine process. Worker subprocesses do NOT connect
to this database. The store is best-effort: write failures are logged and
swallowed by the recorder so a lineage outage never breaks the workflow.

Connection lifecycle (D38-3.2 / Codex P1-1)
-------------------------------------------

For file-backed stores the connection is opened **per public method call**
and closed on exit. This keeps the file handle un-pinned on Windows so that
external `shutil.rmtree(project_path)` (e.g. the user deletes the project
directory outside SciEasy) succeeds without `PermissionError [WinError 32]`.
The cost is a fresh SQLite connection per operation — a few hundred
microseconds locally — which is acceptable because lineage is best-effort
and writes happen at terminal-event cadence (block-rate, not tight-loop).

In-memory stores (``":memory:"``, used by tests) keep a single persistent
connection because each new connection to ``":memory:"`` is a brand-new DB.
The constructor still runs the schema bootstrap on this persistent
connection so the four tables exist before the first write.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
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


def _apply_pragmas_and_schema(conn: sqlite3.Connection) -> None:
    """Apply ``WAL`` + ``foreign_keys`` PRAGMAs and create tables if absent.

    Called on every connection open so the file is always schema-current
    (idempotent CREATE IF NOT EXISTS).
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for stmt in _SCHEMA_STATEMENTS:
        conn.execute(stmt)
    conn.commit()


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
        # In-memory stores can't reconnect (each new ":memory:" connection
        # is an empty DB), so we keep one persistent connection for them.
        # File-backed stores open + close per call so the Windows file
        # handle is released and external `shutil.rmtree` works.
        self._is_memory = self._db_path == ":memory:"
        self._persistent_conn: sqlite3.Connection | None = None
        self._closed = False
        if self._is_memory:
            # ``check_same_thread=False`` because the engine emits events
            # from asyncio tasks across the default loop's executor;
            # SQLite is serialised internally and the recorder calls are
            # single-flight.
            self._persistent_conn = sqlite3.connect(self._db_path, check_same_thread=False)
            _apply_pragmas_and_schema(self._persistent_conn)
        else:
            # Bootstrap the file: open a transient connection just to run
            # the schema PRAGMAs + CREATE TABLEs. Without this, the very
            # first reader (.list_runs() on a brand-new project) would
            # race the writer on file creation.
            with self._connect() as conn:
                _apply_pragmas_and_schema(conn)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a usable SQLite connection.

        For in-memory stores returns the single persistent connection
        (do not close). For file-backed stores opens a fresh connection,
        applies PRAGMAs lazily, and closes on exit so the file handle is
        immediately released (Windows external-delete robustness — see
        module docstring).
        """
        if self._closed:
            # close() was called explicitly; refuse new connections so
            # late writes don't silently re-create the file (file-backed)
            # or operate on a dangling pointer (memory-backed).
            raise sqlite3.ProgrammingError("LineageStore is closed")
        if self._is_memory:
            assert self._persistent_conn is not None
            yield self._persistent_conn
            return
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        try:
            # PRAGMAs are per-connection; foreign_keys especially MUST be
            # set on every connection or the FK constraints are silently
            # skipped (a well-known SQLite footgun).
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    def close(self) -> None:
        """Close the underlying connection (in-memory) and mark closed.

        For file-backed stores there is no persistent connection — each
        public method opens + closes its own — so :meth:`close` just sets
        the closed flag so subsequent calls raise rather than silently
        recreating the database file.
        """
        self._closed = True
        if self._persistent_conn is not None:
            with contextlib.suppress(sqlite3.ProgrammingError, Exception):
                self._persistent_conn.close()
            self._persistent_conn = None

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def insert_run(self, run: RunRecord) -> None:
        """Insert a row into ``runs``."""
        with self._connect() as conn:
            conn.execute(
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
            conn.commit()

    def finalize_run(self, run_id: str, *, finished_at: str, status: str) -> None:
        """Update terminal columns on a ``runs`` row."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, status = ? WHERE run_id = ?",
                (finished_at, status, run_id),
            )
            conn.commit()

    def set_pending_git_commit(self, workflow_id: str, sha: str | None) -> None:
        """Stamp ``runs.workflow_git_commit`` on the most recent run for ``workflow_id``.

        D38-3.2 / Phase 3.5 hazard H-A1: ``D39-2.5`` calls this from
        ``ApiRuntime.start_workflow`` as a forward-compatible hook to
        propagate the pre-run auto-commit SHA into the lineage DB. The
        target row is the most recently inserted ``runs`` row matching
        ``workflow_id`` — i.e. the run that was just created by
        ``begin_run``. No-op when there is no matching row (e.g. lineage
        write failed; we silently skip rather than raise).

        Parameters
        ----------
        workflow_id:
            The workflow identifier from ``RunRecord.workflow_id``.
        sha:
            The git commit SHA to record. ``None`` is allowed and clears
            the column (used by ADR-039 §5.2 when commit creation fails).
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT run_id FROM runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT 1",
                (workflow_id,),
            )
            row = cur.fetchone()
            if row is None:
                return
            run_id = row[0]
            conn.execute(
                "UPDATE runs SET workflow_git_commit = ? WHERE run_id = ?",
                (sha, run_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a ``runs`` row as a dict, or ``None`` if absent."""
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row, strict=False))

    def list_runs(self, workflow_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Return runs in reverse-chronological order."""
        with self._connect() as conn:
            if workflow_id is None:
                cur = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
            else:
                cur = conn.execute(
                    "SELECT * FROM runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT ?",
                    (workflow_id, limit),
                )
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # block_executions
    # ------------------------------------------------------------------

    def insert_block_execution(self, be: BlockExecutionRecord) -> None:
        """Insert (or skip) a row into ``block_executions``.

        D38-3.2 / D38-3.1b P3-3: use ``INSERT OR IGNORE`` so a re-emit on
        the same ``(run_id, block_id)`` UNIQUE constraint does not raise
        ``IntegrityError``. The recorder already guards against
        double-write via its ``_exec_ids`` cache; this is belt-and-braces.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO block_executions (
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
            conn.commit()

    def list_block_executions(self, run_id: str) -> list[dict[str, Any]]:
        """List blocks for a run ordered by start time."""
        with self._connect() as conn:
            cur = conn.execute(
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
        with self._connect() as conn:
            conn.execute(
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
            conn.commit()

    def get_data_object(self, object_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM data_objects WHERE object_id = ?", (object_id,))
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
        with self._connect() as conn:
            conn.execute(
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
            conn.commit()

    def list_block_io(self, block_execution_id: str) -> list[dict[str, Any]]:
        """Return all I/O edges for a block_execution, ordered for display."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT * FROM block_io
                WHERE block_execution_id = ?
                ORDER BY direction, port_name, position
                """,
                (block_execution_id,),
            )
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    def list_block_io_with_objects(
        self, run_id: str
    ) -> list[dict[str, Any]]:
        """Return all I/O edges joined with their ``data_objects`` row for a run.

        Hotfix #996: ADR-038 §3.7 Q4b "Per-block I/O DataObjects?" SQL
        rendered as a single batched query so ``GET /api/runs/{run_id}``
        can inline inputs/outputs into each ``block_executions`` row
        without N round-trips. Pre-#996 the route deferred the JOIN and
        the frontend rendered "0 inputs / 0 outputs" on every block card
        (Phase 4a finding).

        Returned columns: ``block_execution_id``, ``direction``,
        ``port_name``, ``position``, ``object_id``, ``type_name``,
        ``backend``, ``storage_path``, ``wire_payload``,
        ``produced_by_execution``. Rows are ordered by
        ``(block_execution_id, direction, port_name, position)`` so
        callers can stream-bucket them.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT bio.block_execution_id,
                       bio.direction,
                       bio.port_name,
                       bio.position,
                       bio.object_id,
                       do.type_name,
                       do.backend,
                       do.storage_path,
                       do.wire_payload,
                       do.produced_by_execution
                FROM block_io bio
                JOIN block_executions be ON bio.block_execution_id = be.block_execution_id
                JOIN data_objects do ON bio.object_id = do.object_id
                WHERE be.run_id = ?
                ORDER BY bio.block_execution_id, bio.direction, bio.port_name, bio.position
                """,
                (run_id,),
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
        with self._connect() as conn:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")  # table name allow-listed above
            return int(cur.fetchone()[0])

    def execute_query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Execute a read-only SQL query and return all rows.

        Public helper added in D38-3.2 so the ``MetadataStore`` shim (and
        any future read-only consumer) doesn't have to reach into the
        private ``_conn`` attribute. The shim runs recursive-CTE
        ancestor / descendant queries that don't fit the high-level
        per-table accessors. Best-effort: SQLite errors propagate to the
        caller, which is expected to log + degrade.
        """
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return list(cur.fetchall())
