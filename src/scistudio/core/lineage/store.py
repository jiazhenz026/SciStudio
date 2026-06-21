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
directory outside SciStudio) succeeds without `PermissionError [WinError 32]`.
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

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Artifact content hashing (#1529 / DSN-5)
# ---------------------------------------------------------------------------

# Streamed in 1 MiB chunks so hashing a multi-GB artifact does not load the
# whole file into memory.
_HASH_CHUNK_BYTES = 1024 * 1024


def hash_artifact_file(storage_path: str | None) -> str | None:
    """Return an xxhash digest of the file at *storage_path*, or ``None``.

    #1529 (DSN-5): records a content digest alongside the mutable
    ``storage_path`` so a later run that overwrites the same path (ADR-038
    §3.5 "no per-run isolation") can be detected as a dangling artifact.

    Returns ``None`` (rather than raising) when *storage_path* is falsy, is
    not a regular file (e.g. a directory-backed zarr store, or a path that
    does not exist), or cannot be read — lineage hashing is best-effort and
    must never break a workflow. Directory-backed backends are intentionally
    not walked here; their integrity check is deferred (see TODO below).

    TODO(#1517): hash directory-backed artifacts (zarr / parquet datasets)
      by digesting their constituent files. Out of scope for #1529, which
      targets single-file intermediates.
      Followup: https://github.com/zjzcpj/SciStudio/issues/1517.
    """
    if not storage_path:
        return None
    path = Path(storage_path)
    try:
        if not path.is_file():
            return None
        import xxhash

        hasher = xxhash.xxh3_64()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        logger.debug("lineage: content hash failed for %s", storage_path, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Read-only query enforcement (#1546 / BUG-11)
# ---------------------------------------------------------------------------

# Leading keywords that begin a read-only statement. ``WITH`` covers
# recursive-CTE ancestor/descendant queries (the documented use case);
# ``EXPLAIN`` and the read form of ``PRAGMA`` are harmless introspection.
_READONLY_PREFIXES = ("select", "with", "explain", "pragma", "values")


def _reject_non_readonly_sql(sql: str) -> None:
    """Raise ``ValueError`` unless *sql* is a single read-only statement.

    #1546 (BUG-11): ``execute_query`` advertised "read-only" but executed any
    SQL, so a future caller passing a mutating statement could silently
    corrupt the lineage DB. We reject anything that is not a single
    SELECT/WITH/EXPLAIN/PRAGMA/VALUES statement. The check is intentionally
    conservative: it strips leading SQL comments, forbids statement
    batching (a trailing ``;`` plus more SQL), and matches on the first
    keyword case-insensitively.
    """
    stripped = _strip_sql_leading_comments(sql).strip()
    if not stripped:
        raise ValueError("execute_query: empty SQL is not allowed")

    # Forbid statement batching: split on ';' and ensure at most one
    # non-empty statement remains.
    statements = [s for s in (part.strip() for part in stripped.split(";")) if s]
    if len(statements) > 1:
        raise ValueError("execute_query: multiple statements are not allowed (read-only)")

    first_word = statements[0].split(None, 1)[0].lower() if statements else ""
    if first_word not in _READONLY_PREFIXES:
        raise ValueError(f"execute_query is read-only; statement starting with {first_word!r} is rejected")


def _strip_sql_leading_comments(sql: str) -> str:
    """Strip leading ``--`` line comments and ``/* */`` block comments."""
    text = sql.lstrip()
    while True:
        if text.startswith("--"):
            newline = text.find("\n")
            text = "" if newline == -1 else text[newline + 1 :].lstrip()
            continue
        if text.startswith("/*"):
            end = text.find("*/")
            text = "" if end == -1 else text[end + 2 :].lstrip()
            continue
        return text


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
        user_notes              TEXT,
        -- #1527 (BUG-6): set to 1 when one or more provenance writes for
        -- this run failed, so a run whose lineage is incomplete cannot
        -- be reported as a clean "completed" with only a log line as
        -- evidence. Surfaced on the run row / API response.
        provenance_degraded     INTEGER NOT NULL DEFAULT 0
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
        produced_by_execution   TEXT REFERENCES block_executions(block_execution_id),
        -- #1529 (DSN-5): content digest (xxhash) of the bytes at
        -- ``storage_path`` captured at record time, plus the size/mtime
        -- snapshot. ADR-038 §3.5 says on-disk intermediates may be
        -- overwritten by a later run with no per-run isolation, so a bare
        -- ``storage_path`` can silently dangle (point at bytes that no
        -- longer match what the producing run wrote). Recording the digest
        -- lets ``detect_dangling_objects`` flag artifacts whose current
        -- bytes differ from (or are missing relative to) the recorded ones.
        content_hash            TEXT
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


# #1530: persisted-format version stamp for lineage.db (SQLite PRAGMA
# user_version). Bump on a non-backward-compatible schema change and pair the
# bump with a migration step; stamping is the cheap half done now.
LINEAGE_SCHEMA_VERSION = 1


def _apply_pragmas_and_schema(conn: sqlite3.Connection) -> None:
    """Apply ``WAL`` + ``foreign_keys`` PRAGMAs and create tables if absent.

    Called on every connection open so the file is always schema-current
    (idempotent CREATE IF NOT EXISTS).
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # #1530: stamp the schema version on fresh/legacy DBs (user_version == 0) so
    # a future format change has a version to branch on. No migration logic is
    # performed here — only the stamp.
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        conn.execute(f"PRAGMA user_version = {LINEAGE_SCHEMA_VERSION}")
    for stmt in _SCHEMA_STATEMENTS:
        conn.execute(stmt)
    _migrate_runs_provenance_degraded(conn)
    _migrate_data_objects_content_hash(conn)
    conn.commit()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for *table* (allow-listed by caller)."""
    cur = conn.execute(f"PRAGMA table_info({table})")  # table name is an internal literal
    return {row[1] for row in cur.fetchall()}


def _migrate_runs_provenance_degraded(conn: sqlite3.Connection) -> None:
    """Add ``runs.provenance_degraded`` to pre-#1527 databases.

    ``CREATE TABLE IF NOT EXISTS`` does not add new columns to an existing
    table, so a lineage.db created before #1527 (BUG-6) lacks the
    ``provenance_degraded`` column. Detect its absence and ``ALTER TABLE``
    it in with the same ``DEFAULT 0`` so existing rows read as "clean".
    """
    if "provenance_degraded" not in _column_names(conn, "runs"):
        conn.execute("ALTER TABLE runs ADD COLUMN provenance_degraded INTEGER NOT NULL DEFAULT 0")


def _migrate_data_objects_content_hash(conn: sqlite3.Connection) -> None:
    """Add ``data_objects.content_hash`` to pre-#1529 databases.

    Same ``CREATE TABLE IF NOT EXISTS`` limitation as the provenance-degraded
    migration: a lineage.db created before #1529 (DSN-5) lacks the
    ``content_hash`` column. New column is nullable so existing rows read as
    "no recorded digest" (treated as not-checkable rather than dangling).
    """
    if "content_hash" not in _column_names(conn, "data_objects"):
        conn.execute("ALTER TABLE data_objects ADD COLUMN content_hash TEXT")


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
            default_dir = Path(".scistudio")
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

    def finalize_run(
        self,
        run_id: str,
        *,
        finished_at: str,
        status: str,
        provenance_degraded: bool = False,
    ) -> None:
        """Update terminal columns on a ``runs`` row.

        #1527 (BUG-6): ``provenance_degraded`` records whether any lineage
        write for this run failed. It is OR-ed into the existing column so a
        single failed write latches the flag even if later writes succeed.
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?,
                    status = ?,
                    provenance_degraded = MAX(provenance_degraded, ?)
                WHERE run_id = ?
                """,
                (finished_at, status, 1 if provenance_degraded else 0, run_id),
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

    def workflow_git_commits_in(self, sha_list: list[str]) -> set[str]:
        """Return the subset of *sha_list* that any ``runs`` row references.

        ADR-039 Addendum 1 §11.4 row #1356: the branch-delete safety net
        needs to know which orphan-candidate SHAs are referenced by
        lineage rows so it can pin them under ``refs/scistudio/lineage/*``
        before the delete. This is the read-side query that powers that
        check.

        Empty input returns an empty set without touching the database
        (SQLite ``IN ()`` is a syntax error in some bindings; cheaper to
        short-circuit).

        SHAs absent from ``runs.workflow_git_commit`` (including NULL
        rows) are filtered out — the returned set is always a subset of
        ``sha_list``.

        Parameters
        ----------
        sha_list:
            Candidate SHAs to check. Order is irrelevant; duplicates are
            tolerated (the DB query collapses them).

        Returns
        -------
        set[str]
            The subset of input SHAs that appear in
            ``runs.workflow_git_commit``.
        """
        if not sha_list:
            return set()
        # De-duplicate to keep the SQL parameter count tight.
        unique = list({s for s in sha_list if s})
        if not unique:
            return set()
        placeholders = ",".join("?" * len(unique))
        with self._connect() as conn:
            cur = conn.execute(
                f"SELECT DISTINCT workflow_git_commit FROM runs WHERE workflow_git_commit IN ({placeholders})",
                unique,
            )
            return {row[0] for row in cur.fetchall() if row[0]}

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

        #1529 (DSN-5): when the row has a ``storage_path`` but no
        ``content_hash`` we compute the xxhash digest of the on-disk bytes
        here (first-writer-wins, matching the ``INSERT OR IGNORE`` upsert) so
        :meth:`detect_dangling_objects` can later tell whether the path still
        points at the bytes the producing run wrote. ``size_bytes`` /
        ``mtime_at_write`` are snapshotted from the same ``stat`` when not
        already supplied.
        """
        content_hash = row.content_hash
        size_bytes = row.size_bytes
        mtime_at_write = row.mtime_at_write
        if row.storage_path:
            path = Path(row.storage_path)
            try:
                if path.is_file():
                    if content_hash is None:
                        content_hash = hash_artifact_file(row.storage_path)
                    stat = path.stat()
                    if size_bytes is None:
                        size_bytes = stat.st_size
                    if mtime_at_write is None:
                        mtime_at_write = str(stat.st_mtime)
            except Exception:
                logger.debug(
                    "lineage: stat/hash failed for data_object %s at %s",
                    row.object_id,
                    row.storage_path,
                    exc_info=True,
                )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO data_objects (
                    object_id, type_name, backend, storage_path, size_bytes,
                    mtime_at_write, created_at, wire_payload, derived_from,
                    produced_by_execution, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.object_id,
                    row.type_name,
                    row.backend,
                    row.storage_path,
                    size_bytes,
                    mtime_at_write,
                    row.created_at,
                    json.dumps(row.wire_payload, default=str),
                    row.derived_from,
                    row.produced_by_execution,
                    content_hash,
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

    def check_object_integrity(self, object_id: str) -> str:
        """Return the integrity status of one ``data_objects`` row (#1529).

        Compares the recorded ``content_hash`` against a freshly computed
        digest of the bytes currently at ``storage_path``. Possible results:

        * ``"ok"``           — recorded hash matches the current file bytes.
        * ``"dangling"``     — a hash was recorded but the file is missing or
          its current bytes differ (overwritten by a later run, deleted,
          etc.). This is the silent-dangling case #1529 targets.
        * ``"unknown"``      — no row, no ``storage_path``, no recorded hash,
          or a path that is not a regular file (e.g. directory-backed
          backend). Not checkable, so neither confirmed ok nor dangling.
        """
        row = self.get_data_object(object_id)
        if row is None:
            return "unknown"
        recorded = row.get("content_hash")
        storage_path = row.get("storage_path")
        if not recorded or not storage_path:
            return "unknown"
        current = hash_artifact_file(storage_path)
        if current is None:
            # Recorded a hash but the file is now missing / unreadable.
            return "dangling"
        return "ok" if current == recorded else "dangling"

    def detect_dangling_objects(self, run_id: str | None = None) -> list[dict[str, Any]]:
        """Return ``data_objects`` whose on-disk bytes no longer match (#1529).

        Iterates rows that carry both a ``content_hash`` and a
        ``storage_path`` and recomputes the digest. Rows whose current bytes
        differ from (or are missing relative to) the recorded digest are
        returned, each augmented with an ``integrity`` key (always
        ``"dangling"`` for returned rows). Rows without a recorded hash /
        path are skipped (not checkable).

        Parameters
        ----------
        run_id:
            When provided, restrict the scan to objects produced by a block
            execution in that run (via the ``produced_by_execution`` →
            ``block_executions.run_id`` join). When ``None``, scan all rows.
        """
        with self._connect() as conn:
            if run_id is None:
                cur = conn.execute(
                    "SELECT * FROM data_objects WHERE content_hash IS NOT NULL AND storage_path IS NOT NULL"
                )
            else:
                cur = conn.execute(
                    """
                    SELECT do.* FROM data_objects do
                    JOIN block_executions be
                      ON do.produced_by_execution = be.block_execution_id
                    WHERE be.run_id = ?
                      AND do.content_hash IS NOT NULL
                      AND do.storage_path IS NOT NULL
                    """,
                    (run_id,),
                )
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

        dangling: list[dict[str, Any]] = []
        for row in rows:
            current = hash_artifact_file(row["storage_path"])
            if current is None or current != row["content_hash"]:
                row["integrity"] = "dangling"
                dangling.append(row)
        return dangling

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

    def list_block_io_with_objects(self, run_id: str) -> list[dict[str, Any]]:
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
        """Execute a **read-only** SQL query and return all rows.

        Public helper added in D38-3.2 so the ``MetadataStore`` shim (and
        any future read-only consumer) doesn't have to reach into the
        private ``_conn`` attribute. The shim runs recursive-CTE
        ancestor / descendant queries that don't fit the high-level
        per-table accessors. Best-effort: SQLite errors propagate to the
        caller, which is expected to log + degrade.

        #1546 (BUG-11): the "read-only" contract is now enforced rather than
        merely documented. Two layers of defence:

        1. **Statement check** — only a single ``SELECT`` / ``WITH`` /
           ``EXPLAIN`` / read-form ``PRAGMA`` statement is accepted; anything
           else (INSERT/UPDATE/DELETE/DROP/ATTACH/multiple statements/…)
           raises :class:`ValueError` before touching the DB.
        2. **Read-only connection** — for file-backed stores the query runs
           on a ``file:...?mode=ro`` connection so even a statement that
           slipped past the check cannot mutate the file. In-memory stores
           cannot reopen read-only (a new ``:memory:`` connection is an empty
           DB), so they rely on the statement check; SQLite query-only
           PRAGMA is also engaged as a backstop.
        """
        _reject_non_readonly_sql(sql)
        if self._is_memory:
            assert self._persistent_conn is not None
            conn = self._persistent_conn
            conn.execute("PRAGMA query_only=ON")
            try:
                cur = conn.execute(sql, params)
                return list(cur.fetchall())
            finally:
                conn.execute("PRAGMA query_only=OFF")
        if self._closed:
            raise sqlite3.ProgrammingError("LineageStore is closed")
        uri = f"file:{Path(self._db_path).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        try:
            cur = conn.execute(sql, params)
            return list(cur.fetchall())
        finally:
            with contextlib.suppress(Exception):
                conn.close()
