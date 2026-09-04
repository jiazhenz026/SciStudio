"""LineageStore — the unified SQLite store for run and session lineage.

Tables:

* ``runs``             — one row per workflow execution
* ``explore_sessions`` — one row per Explore session (ADR-054 FR-052)
* ``block_executions`` — one row per block per run **or per session**
* ``data_objects``     — the catalog of every ``DataObject`` ever seen
* ``block_io``         — port-to-DataObject edges per execution

``runs`` and ``explore_sessions`` are the two anchors and the three tables
below them are shared: a block execution carries exactly one of ``run_id`` or
``session_id``, and everything downstream is the same code with a different
foreign key (ADR-054 §4.1, "Lineage adds a table and reuses three"). That is
what lets an object produced in a session and consumed by a workflow run be a
single ``data_objects`` row reachable from both sides.

Every pre-existing query keys on ``run_id``, so a session's rows are invisible
to the workflow surfaces without those queries changing.

All writes happen in the engine process; worker subprocesses never connect to
this database. The store is best-effort: write failures are logged and
swallowed by the recorder so a lineage outage never breaks a workflow.

Connection lifecycle
--------------------

For a file-backed store the connection is opened **per public-method call** and
closed on exit. This keeps the file handle unpinned on Windows so that deleting
the project directory from outside SciStudio succeeds. The cost — a fresh
SQLite connection per operation, a few hundred microseconds locally — is
acceptable because lineage is best-effort and writes happen at block-event
cadence, not in a tight loop.

An in-memory store (``":memory:"``, used by tests) keeps a single persistent
connection, because each new connection to ``":memory:"`` would be a brand-new
empty database. The constructor still bootstraps the schema on that connection
so the four tables exist before the first write.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    ExploreSessionRecord,
    RunRecord,
)
from scistudio.stability import provisional

logger = logging.getLogger(__name__)

#: ``block_io.direction`` for an object a cell named through ``scistudio.output``
#: (ADR-054 FR-055). Such an object is durable; every other object a session
#: produces is a reclaim candidate for the retention planner. The value is
#: deliberately neither ``'input'`` nor ``'output'`` so that a declaration is not
#: mistaken for a port, and it is only ever written on a session-anchored
#: execution, which every run-scoped read reaches past by keying on ``run_id``.
DECLARED_OUTPUT_DIRECTION = "declared_output"


# ---------------------------------------------------------------------------
# Artifact content hashing (#1529 / DSN-5)
# ---------------------------------------------------------------------------

# Streamed in 1 MiB chunks so hashing a multi-GB artifact does not load the
# whole file into memory.
_HASH_CHUNK_BYTES = 1024 * 1024


def hash_artifact_file(storage_path: str | None) -> str | None:
    """Return an xxhash digest of the file at *storage_path*, or ``None``.

    #1529 (DSN-5): records a content digest alongside the mutable
    ``storage_path`` so a subsequent run that overwrites the same path (ADR-038
    §3.5 "no per-run isolation") can be detected as a dangling artifact.

    Returns ``None`` (rather than raising) when *storage_path* is falsy, is
    not a regular file (e.g. a directory-backed zarr store, or a path that
    does not exist), or cannot be read — lineage hashing is best-effort and
    must never break a workflow. Directory-backed backends are intentionally
    not walked here; their integrity check is deferred (see TODO below).
    :func:`artifact_size_bytes` *does* handle directories, so #1983's retention
    accounting works for zarr stores even while their digest stays ``None``.

    TODO(#1984): hash directory-backed artifacts (zarr / parquet datasets)
      by digesting their constituent files. Out of scope for #1529 (which
      targeted single-file intermediates) and for #1983 (which needs sizes,
      not digests).
      Followup: https://github.com/jiazhenz026/SciStudio/issues/1984.
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


def artifact_size_bytes(storage_path: str | None) -> int | None:
    """Return the on-disk size of the artifact at *storage_path*, or ``None``.

    #1983: the dominant artifact backend (zarr) stores each array as a
    *directory* of chunk files, so a bare ``Path.stat().st_size`` reports the
    directory inode size (typically 64 to 128 bytes) rather than the payload.
    Retention accounting and any "how much disk is this project using" surface
    need the recursive total, so directories are walked and their file sizes
    summed.

    Returns ``None`` (rather than raising) when *storage_path* is falsy, does
    not exist, or cannot be read — lineage accounting is best-effort and must
    never break a workflow.

    Args:
        storage_path: Path to a file-backed or directory-backed artifact.

    Returns:
        Total bytes, or ``None`` when the size cannot be determined.
    """
    if not storage_path:
        return None
    path = Path(storage_path)
    try:
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return None
        total = 0
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                # A chunk file vanishing mid-walk (concurrent GC, or a store
                # still being written) must not fail the whole measurement.
                continue
        return total
    except Exception:
        logger.debug("lineage: size measurement failed for %s", storage_path, exc_info=True)
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

# ADR-054 FR-052: the session anchor. Every column is the ``runs`` column of the
# same role under a notebook name; see :class:`ExploreSessionRecord` for the
# mapping. ``environment_ref`` is the one that is not a rename — FR-034 stores a
# snapshot once per distinct environment and references it from records.
_EXPLORE_SESSIONS_DDL = """
    CREATE TABLE IF NOT EXISTS explore_sessions (
        session_id              TEXT PRIMARY KEY,
        notebook_path           TEXT NOT NULL,
        notebook_snapshot       TEXT NOT NULL,
        notebook_git_commit     TEXT,
        started_at              TEXT NOT NULL,
        finished_at             TEXT,
        status                  TEXT NOT NULL,
        environment_ref         TEXT,
        opened_over             TEXT NOT NULL,
        bound_run_id            TEXT REFERENCES runs(run_id),
        provenance_degraded     INTEGER NOT NULL DEFAULT 0
    )
"""

# ``block_executions`` is written with a ``{table}`` substitution slot because
# ``_migrate_block_executions_session_anchor`` rebuilds the table under a
# scratch name and must use exactly this definition to do it (SQLite cannot
# relax a NOT NULL constraint in place).
#
# The anchor is polymorphic: ``run_id`` for a workflow run, ``session_id`` for
# an Explore session, never both and never neither. Pre-#2240 rows all carry a
# ``run_id``, so the CHECK holds for every row that already exists.
#
# ``UNIQUE (run_id, block_id)`` is unchanged and stays inert for a session's
# rows: SQLite treats NULLs as distinct in a UNIQUE index, which is what lets a
# session re-run the same cell as often as a person presses the button while
# a run still gets one row per block.
_BLOCK_EXECUTIONS_DDL = """
    CREATE TABLE IF NOT EXISTS {table} (
        block_execution_id      TEXT PRIMARY KEY,
        run_id                  TEXT REFERENCES runs(run_id),
        block_id                TEXT NOT NULL,
        block_type              TEXT NOT NULL,
        block_version           TEXT NOT NULL,
        block_config_resolved   TEXT NOT NULL,
        started_at              TEXT NOT NULL,
        finished_at             TEXT,
        duration_ms             INTEGER,
        termination             TEXT NOT NULL,
        termination_detail      TEXT,
        session_id              TEXT REFERENCES explore_sessions(session_id),
        environment_ref         TEXT,
        UNIQUE (run_id, block_id),
        CHECK ((run_id IS NULL) <> (session_id IS NULL))
    )
"""

#: Index statements for ``block_executions``, kept beside the DDL because a
#: table rebuild drops the old table's indexes with it.
_BLOCK_EXECUTIONS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_be_run ON {table}(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_be_block ON {table}(block_id)",
    "CREATE INDEX IF NOT EXISTS idx_be_session ON {table}(session_id)",
)

#: Columns carried over verbatim when the table is rebuilt. The two new columns
#: are absent from the legacy table, so they are not listed and default to NULL.
_BLOCK_EXECUTIONS_LEGACY_COLUMNS = (
    "block_execution_id",
    "run_id",
    "block_id",
    "block_type",
    "block_version",
    "block_config_resolved",
    "started_at",
    "finished_at",
    "duration_ms",
    "termination",
    "termination_detail",
)


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
    # Table 1b: explore_sessions — the second anchor (ADR-054 FR-052).
    _EXPLORE_SESSIONS_DDL,
    "CREATE INDEX IF NOT EXISTS idx_es_notebook ON explore_sessions(notebook_path, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_es_commit ON explore_sessions(notebook_git_commit)",
    # Table 2: block_executions. Its indexes are *not* listed here: one of them
    # is on ``session_id``, which a pre-#2240 database does not have until
    # ``_migrate_block_executions_session_anchor`` has run, so all three are
    # created after the migrations instead.
    _BLOCK_EXECUTIONS_DDL.format(table="block_executions"),
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
        -- overwritten by a subsequent run with no per-run isolation, so a bare
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
#
# Version 2 (#2240, ADR-054 FR-051/FR-052): adds ``explore_sessions`` and gives
# ``block_executions`` a session anchor. The bump is paired with
# ``_migrate_block_executions_session_anchor``.
LINEAGE_SCHEMA_VERSION = 2


def _apply_pragmas_and_schema(conn: sqlite3.Connection) -> None:
    """Apply ``WAL`` + ``foreign_keys`` PRAGMAs and create tables if absent.

    Called on every connection open so the file is always schema-current
    (idempotent CREATE IF NOT EXISTS).
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for stmt in _SCHEMA_STATEMENTS:
        conn.execute(stmt)
    _migrate_runs_provenance_degraded(conn)
    _migrate_data_objects_content_hash(conn)
    _migrate_block_executions_session_anchor(conn)
    for stmt in _BLOCK_EXECUTIONS_INDEXES:
        conn.execute(stmt.format(table="block_executions"))
    # #1530: stamp the schema version so a future format change has a version to
    # branch on. Stamped *after* the migrations so a database that failed to
    # migrate is not advertised as current. A fresh database reads 0 here and is
    # stamped exactly as it was before #2240; a database stamped at an older
    # version is caught up once its migrations have run.
    if conn.execute("PRAGMA user_version").fetchone()[0] < LINEAGE_SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {LINEAGE_SCHEMA_VERSION}")
    conn.commit()


def _all(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    """Return every row of *cur* as a column-keyed dict."""
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]


def _one(cur: sqlite3.Cursor) -> dict[str, Any] | None:
    """Return the first row of *cur* as a column-keyed dict, or ``None``."""
    row = cur.fetchone()
    if row is None:
        return None
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, row, strict=False))


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


def _migrate_block_executions_session_anchor(conn: sqlite3.Connection) -> None:
    """Give a pre-#2240 ``block_executions`` table its Explore-session anchor.

    ADR-054 FR-051/FR-052 make the anchor polymorphic: a row belongs to a run or
    to a session. ``run_id`` was ``NOT NULL``, and SQLite has no
    ``ALTER COLUMN``, so this is the documented table rebuild rather than the
    ``ALTER TABLE ADD COLUMN`` the two migrations above could use.

    The rebuild is additive in the sense that matters: every legacy row is
    copied verbatim and keeps its ``run_id``, the two new columns default to
    NULL, the indexes and the ``UNIQUE (run_id, block_id)`` constraint are
    recreated as they were, and the only constraint that changes is one that
    every existing row already satisfies (``run_id`` non-NULL, ``session_id``
    NULL). ``PRAGMA foreign_key_check`` is run afterwards and a violation aborts
    the transaction rather than leaving a half-migrated file.

    No-op once ``session_id`` exists, so it costs one ``PRAGMA table_info`` per
    store construction thereafter.
    """
    if "session_id" in _column_names(conn, "block_executions"):
        return

    # Foreign keys must be off for the swap: ``data_objects.produced_by_execution``
    # and ``block_io.block_execution_id`` reference the table being dropped. The
    # PRAGMA is a no-op inside a transaction, so commit whatever the CREATEs
    # above left open first.
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        columns = ", ".join(_BLOCK_EXECUTIONS_LEGACY_COLUMNS)
        conn.execute("BEGIN")
        conn.execute(_BLOCK_EXECUTIONS_DDL.format(table="block_executions_migrating"))
        conn.execute(
            # The column list is a module constant, not caller input.
            f"INSERT INTO block_executions_migrating ({columns}) SELECT {columns} FROM block_executions"
        )
        conn.execute("DROP TABLE block_executions")
        conn.execute("ALTER TABLE block_executions_migrating RENAME TO block_executions")
        for stmt in _BLOCK_EXECUTIONS_INDEXES:
            conn.execute(stmt.format(table="block_executions"))
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(
                f"lineage: block_executions rebuild left {len(violations)} foreign-key violation(s)"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


class LineageStore:
    """SQLite-backed store holding the four lineage tables.

    Construct one per project. Read methods return plain column-keyed dicts;
    write methods take the row dataclasses from
    :mod:`scistudio.core.lineage.record`.

    Args:
        db_path: Path to the SQLite database file. Pass ``":memory:"`` for an
            ephemeral in-process store (used by tests). Defaults to
            ``.scistudio/lineage.db``.
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
        """Insert a row into the ``runs`` table.

        Args:
            run: The run record to insert.
        """
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
        """Update the terminal columns on a ``runs`` row.

        Args:
            run_id: Id of the run to finalise.
            finished_at: ISO-8601 timestamp of completion.
            status: Terminal status (e.g. ``"completed"``, ``"failed"``).
            provenance_degraded: Whether any lineage write for this run failed.
                It is OR-ed into the stored column, so a single failed write
                latches the flag even if subsequent writes succeed.
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
        """Stamp ``workflow_git_commit`` on the most recent run for a workflow.

        Records the workflow's git commit SHA on the most recently started run
        matching ``workflow_id`` (the run that was just created for it). A no-op
        when no matching run exists.

        Args:
            workflow_id: The workflow whose latest run should be stamped.
            sha: The git commit SHA to record. ``None`` clears the column.
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
        """Return a ``runs`` row as a dict, or ``None`` when absent.

        Args:
            run_id: Id of the run to fetch.

        Returns:
            The run row as a column-keyed dict, or ``None`` if not found.
        """
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row, strict=False))

    def list_runs(self, workflow_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """List runs in reverse-chronological order.

        Args:
            workflow_id: When given, return only runs of that workflow.
            limit: Maximum number of runs to return.

        Returns:
            A list of run rows (newest first), each a column-keyed dict.
        """
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

        Lets a caller find out which candidate commit SHAs are referenced by
        lineage rows (for example to pin them safely before deleting a branch).
        An empty input returns an empty set without touching the database.

        Args:
            sha_list: Candidate SHAs to check. Order is irrelevant and
                duplicates are tolerated.

        Returns:
            The subset of *sha_list* that appears in
            ``runs.workflow_git_commit`` (always a subset of the input; absent
            and NULL SHAs are filtered out).
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

    def latest_run_for_git_commit(self, commit_sha: str) -> dict[str, Any] | None:
        """Return the newest run recorded at *commit_sha*, or ``None``.

        ADR-038 Addendum 1 §11.3 (#2033): the restore preflight is driven by a
        git commit, not a run id, so it needs the reverse of the usual lookup.
        Several runs can share one commit (the pre-run auto-commit is skipped
        when the tree is already clean, so consecutive runs of an unedited
        workflow all anchor to the same SHA); the newest is the one whose
        recorded environment best describes "how it was when this worked".

        Args:
            commit_sha: Full SHA to look up. Falsy input returns ``None``
                without touching the database.

        Returns:
            The newest matching run row as a column-keyed dict, or ``None``
            when no run references this commit — which is the normal case for
            a manual commit or an ``auto: pre-restore`` commit, and which
            callers must report as "unknown" rather than as "no drift".
        """
        if not commit_sha:
            return None
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM runs WHERE workflow_git_commit = ? ORDER BY started_at DESC LIMIT 1",
                (commit_sha,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row, strict=False))

    def workflow_boundary_inputs(self, run_id: str) -> list[dict[str, Any]]:
        """Return the run's inputs that came from outside the run itself.

        ADR-038 §3.6 Check 1 operates on
        ``past_run.input_objects_at_workflow_boundary()``: the data objects a
        run consumed but did not produce. Intermediates flowing block-to-block
        inside the run are irrelevant to a drift check — they will be
        regenerated on the next execution. What matters is the files the
        workflow read from disk, because those can change underneath the user
        between the recorded run and now.

        The boundary test is ``produced_by_execution`` pointing outside this
        run (or being NULL, for objects whose producer was never recorded).

        Args:
            run_id: Id of the recorded run.

        Returns:
            One dict per distinct boundary input with ``object_id``,
            ``type_name``, ``storage_path``, ``size_bytes``, and
            ``mtime_at_write``. Objects with no ``storage_path`` (in-memory
            values) are excluded — there is nothing on disk to compare.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT do.object_id,
                       do.type_name,
                       do.storage_path,
                       do.size_bytes,
                       do.mtime_at_write
                FROM block_io bio
                JOIN block_executions be ON bio.block_execution_id = be.block_execution_id
                JOIN data_objects do ON bio.object_id = do.object_id
                WHERE be.run_id = ?
                  AND bio.direction = 'input'
                  AND do.storage_path IS NOT NULL
                  AND (
                        do.produced_by_execution IS NULL
                        OR do.produced_by_execution NOT IN (
                            SELECT block_execution_id FROM block_executions WHERE run_id = ?
                        )
                  )
                ORDER BY do.storage_path
                """,
                (run_id, run_id),
            )
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # explore_sessions (ADR-054 FR-052)
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def insert_explore_session(self, session: ExploreSessionRecord) -> None:
        """Insert a row into the ``explore_sessions`` table.

        The session-side counterpart of :meth:`insert_run`.

        Args:
            session: The session record to insert.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO explore_sessions (
                    session_id, notebook_path, notebook_snapshot, notebook_git_commit,
                    started_at, finished_at, status, environment_ref, opened_over,
                    bound_run_id, provenance_degraded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.notebook_path,
                    session.notebook_snapshot,
                    session.notebook_git_commit,
                    session.started_at,
                    session.finished_at,
                    session.status,
                    session.environment_ref,
                    session.opened_over,
                    session.bound_run_id,
                    int(bool(session.provenance_degraded)),
                ),
            )
            conn.commit()

    @provisional(since="0.3.4")
    def finalize_explore_session(
        self,
        session_id: str,
        *,
        finished_at: str,
        status: str,
        provenance_degraded: bool = False,
    ) -> None:
        """Update the terminal columns on an ``explore_sessions`` row.

        The session-side counterpart of :meth:`finalize_run`, including the
        latching of ``provenance_degraded``: one failed write marks the session
        even if the writes after it succeed.

        Args:
            session_id: Id of the session to close.
            finished_at: ISO-8601 timestamp of closure.
            status: Terminal status (e.g. ``"closed"``, ``"crashed"``).
            provenance_degraded: Whether any lineage write for this session failed.
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE explore_sessions
                SET finished_at = ?,
                    status = ?,
                    provenance_degraded = MAX(provenance_degraded, ?)
                WHERE session_id = ?
                """,
                (finished_at, status, 1 if provenance_degraded else 0, session_id),
            )
            conn.commit()

    @provisional(since="0.3.4")
    def set_session_notebook_commit(self, session_id: str, sha: str | None) -> None:
        """Stamp ``notebook_git_commit`` on a session row (FR-028, FR-035).

        Every cell run produces a commit on the session's ref, and the session
        reports the newest one so packaging and interaction memory can name it.

        Args:
            session_id: The session to stamp.
            sha: The commit SHA, or ``None`` to clear the column.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE explore_sessions SET notebook_git_commit = ? WHERE session_id = ?",
                (sha, session_id),
            )
            conn.commit()

    @provisional(since="0.3.4")
    def get_explore_session(self, session_id: str) -> dict[str, Any] | None:
        """Return an ``explore_sessions`` row as a dict, or ``None`` when absent.

        Args:
            session_id: Id of the session to fetch.

        Returns:
            The session row as a column-keyed dict, or ``None`` if not found.
        """
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM explore_sessions WHERE session_id = ?", (session_id,))
            return _one(cur)

    @provisional(since="0.3.4")
    def list_explore_sessions(self, notebook_path: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """List sessions in reverse-chronological order.

        Args:
            notebook_path: When given, return only sessions over that notebook.
            limit: Maximum number of sessions to return.

        Returns:
            A list of session rows (newest first), each a column-keyed dict.
        """
        with self._connect() as conn:
            if notebook_path is None:
                cur = conn.execute("SELECT * FROM explore_sessions ORDER BY started_at DESC LIMIT ?", (limit,))
            else:
                cur = conn.execute(
                    "SELECT * FROM explore_sessions WHERE notebook_path = ? ORDER BY started_at DESC LIMIT ?",
                    (notebook_path, limit),
                )
            return _all(cur)

    @provisional(since="0.3.4")
    def sessions_in_progress(self) -> list[str]:
        """Return the ids of sessions that have not been closed.

        The session-side counterpart of :meth:`runs_in_progress`, and used for
        the same reason: an open session's outputs are not all recorded yet, so
        retention must not read them as unreferenced.
        """
        with self._connect() as conn:
            cur = conn.execute("SELECT session_id FROM explore_sessions WHERE status = 'running'")
            return [row[0] for row in cur.fetchall()]

    @provisional(since="0.3.4")
    def list_session_block_executions(self, session_id: str) -> list[dict[str, Any]]:
        """List a session's block executions in start-time order.

        Covers both kinds of session-anchored row: a cell run (FR-053) and a
        block called from a cell (FR-051).

        Args:
            session_id: Id of the session.

        Returns:
            A list of block-execution rows, each a column-keyed dict.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM block_executions WHERE session_id = ? ORDER BY started_at",
                (session_id,),
            )
            return _all(cur)

    @provisional(since="0.3.4")
    def explore_session_for_notebook_commit(self, commit_sha: str) -> dict[str, Any] | None:
        """Return the session a notebook commit belongs to, or ``None``.

        ADR-054 FR-054: a packaged block's run is an ordinary workflow run whose
        block version is the notebook commit, so this is the lookup that walks
        from a run's step back to the session the step came from.

        Searches the cell-run records first, because each one stamps the commit
        it produced, and falls back to the session's own current commit.

        Args:
            commit_sha: The notebook commit to resolve. Falsy input returns
                ``None`` without touching the database.

        Returns:
            The session row as a column-keyed dict, or ``None`` when no session
            recorded that commit.
        """
        if not commit_sha:
            return None
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT es.* FROM explore_sessions es
                JOIN block_executions be ON be.session_id = es.session_id
                WHERE be.block_version = ?
                ORDER BY be.started_at DESC LIMIT 1
                """,
                (commit_sha,),
            )
            row = _one(cur)
            if row is not None:
                return row
            cur = conn.execute(
                "SELECT * FROM explore_sessions WHERE notebook_git_commit = ? ORDER BY started_at DESC LIMIT 1",
                (commit_sha,),
            )
            return _one(cur)

    # ------------------------------------------------------------------
    # Cross-anchor object resolution (ADR-054 FR-051, FR-054)
    # ------------------------------------------------------------------

    @provisional(since="0.3.4")
    def execution_producing_object(self, object_id: str) -> dict[str, Any] | None:
        """Return the block execution that produced *object_id*, or ``None``.

        The returned row carries both anchor columns, so the caller reads
        ``run_id`` or ``session_id`` to learn which side of the boundary the
        object came from.

        Args:
            object_id: Id of the data object.

        Returns:
            The block-execution row as a column-keyed dict, or ``None`` when the
            object is unknown or its producer was never recorded.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT be.* FROM data_objects do
                JOIN block_executions be ON be.block_execution_id = do.produced_by_execution
                WHERE do.object_id = ?
                """,
                (object_id,),
            )
            return _one(cur)

    @provisional(since="0.3.4")
    def executions_consuming_object(self, object_id: str) -> list[dict[str, Any]]:
        """Return every block execution that took *object_id* as an input.

        The other direction of :meth:`execution_producing_object`, and the half
        that crosses the boundary the other way: a workflow run consuming an
        object a session produced appears here.

        Args:
            object_id: Id of the data object.

        Returns:
            Block-execution rows in start-time order, each with an added
            ``port_name`` naming the port the object entered through.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT be.*, bio.port_name AS port_name
                FROM block_io bio
                JOIN block_executions be ON be.block_execution_id = bio.block_execution_id
                WHERE bio.object_id = ? AND bio.direction = 'input'
                ORDER BY be.started_at
                """,
                (object_id,),
            )
            return _all(cur)

    # ------------------------------------------------------------------
    # block_executions
    # ------------------------------------------------------------------

    def insert_block_execution(self, be: BlockExecutionRecord) -> None:
        """Insert a row into ``block_executions``, skipping a duplicate.

        Uses ``INSERT OR IGNORE`` so a re-emit on the same ``(run_id,
        block_id)`` does not raise; the first write for a block wins. That
        de-duplication is a run-only effect: a session's rows carry a NULL
        ``run_id``, and SQLite treats NULLs as distinct in a UNIQUE index, so
        re-running the same cell records every run of it.

        Args:
            be: The block-execution record to insert. Exactly one of
                ``run_id`` and ``session_id`` must be set.

        Raises:
            ValueError: When both anchors are set, or neither is.
        """
        if (be.run_id is None) == (be.session_id is None):
            raise ValueError(
                "block execution must be anchored to exactly one of run_id / session_id; "
                f"got run_id={be.run_id!r}, session_id={be.session_id!r}"
            )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO block_executions (
                    block_execution_id, run_id, block_id, block_type, block_version,
                    block_config_resolved, started_at, finished_at, duration_ms,
                    termination, termination_detail, session_id, environment_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    be.session_id,
                    be.environment_ref,
                ),
            )
            conn.commit()

    def list_block_executions(self, run_id: str) -> list[dict[str, Any]]:
        """List a run's block executions in start-time order.

        Session-anchored rows carry a NULL ``run_id`` and so are never returned
        here; :meth:`list_session_block_executions` is their read side.

        Args:
            run_id: Id of the run.

        Returns:
            A list of block-execution rows, each a column-keyed dict.
        """
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
        """Insert a ``data_objects`` row, skipping one that already exists.

        Duplicate writes of the same ``object_id`` are no-ops; the producing
        run's recorded ``storage_path`` is deliberately preserved rather than
        overwritten by a subsequent run.

        When the row has a ``storage_path`` but no ``content_hash``, the digest
        of the on-disk bytes is computed here (along with the size and
        modification time when not supplied), so :meth:`check_object_integrity`
        and :meth:`detect_dangling_objects` can subsequently tell whether the path
        still points at the bytes the producing run wrote.

        Args:
            row: The data-object row to insert.
        """
        content_hash = row.content_hash
        size_bytes = row.size_bytes
        mtime_at_write = row.mtime_at_write
        if row.storage_path:
            path = Path(row.storage_path)
            try:
                if path.is_file() and content_hash is None:
                    content_hash = hash_artifact_file(row.storage_path)
                # #1983: size/mtime are recorded for directory-backed stores
                # (zarr) as well, not only regular files. Hashing still skips
                # directories — see TODO(#1984) on ``hash_artifact_file``.
                if path.exists():
                    if size_bytes is None:
                        size_bytes = artifact_size_bytes(row.storage_path)
                    if mtime_at_write is None:
                        mtime_at_write = str(path.stat().st_mtime)
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
        """Return a ``data_objects`` row as a dict, or ``None`` when absent.

        Args:
            object_id: Id of the data object to fetch.

        Returns:
            The data-object row as a column-keyed dict, or ``None`` if not found.
        """
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM data_objects WHERE object_id = ?", (object_id,))
            row = cur.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cur.description]
            return dict(zip(columns, row, strict=False))

    def check_object_integrity(self, object_id: str) -> str:
        """Return the integrity status of one ``data_objects`` row.

        Compares the recorded ``content_hash`` against a freshly computed digest
        of the bytes currently at ``storage_path``.

        Args:
            object_id: Id of the data object to check.

        Returns:
            One of:

            * ``"ok"`` — the recorded hash matches the current file bytes.
            * ``"dangling"`` — a hash was recorded but the file is missing or
              its bytes differ (overwritten by a subsequent run, deleted, ...).
            * ``"unknown"`` — not checkable: no such row, no ``storage_path``,
              no recorded hash, or a path that is not a regular file (e.g. a
              directory-backed backend).
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
        """Return ``data_objects`` whose on-disk bytes no longer match.

        Recomputes the digest for every row that carries both a ``content_hash``
        and a ``storage_path``; rows whose current bytes differ from (or are
        missing relative to) the recorded digest are returned. Rows without a
        recorded hash or path are skipped (not checkable).

        Args:
            run_id: When given, restrict the scan to objects produced by a block
                execution in that run. When ``None``, scan all rows.

        Returns:
            The dangling rows, each a column-keyed dict with an added
            ``integrity`` key set to ``"dangling"``.
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
        """Insert a ``block_io`` edge, skipping a duplicate.

        Args:
            edge: The port-to-DataObject edge to insert.
        """
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
        """Return all I/O edges for one block execution, ordered for display.

        Args:
            block_execution_id: Id of the block execution.

        Returns:
            A list of edge rows ordered by direction, then port name, then
            position.
        """
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
        """Return a run's I/O edges joined with their ``data_objects`` rows.

        A single batched query so an API handler can inline each block's inputs
        and outputs without one round-trip per block.

        Args:
            run_id: Id of the run.

        Returns:
            One dict per edge with ``block_execution_id``, ``direction``,
            ``port_name``, ``position``, ``object_id``, ``type_name``,
            ``backend``, ``storage_path``, ``wire_payload``, and
            ``produced_by_execution``. Rows are ordered by
            ``(block_execution_id, direction, port_name, position)`` so callers
            can stream-bucket them.
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
    # Artifact retention support (#1983)
    # ------------------------------------------------------------------

    def backfill_storage_fields(self) -> int:
        """Recover NULL ``storage_path`` / ``backend`` / ``size_bytes`` columns.

        #1983: before the ``_extract_storage_fields`` fix, every row recorded
        ``storage_path=NULL`` because the recorder read the key from the wrong
        nesting level. The path was never actually lost — it is still in the
        row's ``wire_payload`` JSON — so existing projects can be repaired
        rather than losing their artifact mapping.

        Idempotent: rows that already carry a ``storage_path`` are untouched.
        Rows whose ``wire_payload`` has no path (in-memory objects, scalar
        pass-throughs) stay NULL.

        Returns:
            The number of rows updated.
        """
        updated = 0
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT object_id, wire_payload FROM data_objects
                WHERE storage_path IS NULL AND wire_payload <> '{}'
                """
            )
            pending: list[tuple[str, str, int | None, str]] = []
            for object_id, payload_json in cur.fetchall():
                try:
                    payload = json.loads(payload_json)
                except (TypeError, ValueError):
                    continue
                if not isinstance(payload, dict):
                    continue
                metadata = payload.get("metadata")
                nested = metadata if isinstance(metadata, dict) else {}
                path = next(
                    (v for v in (payload.get("path"), nested.get("path")) if isinstance(v, str) and v),
                    None,
                )
                if path is None:
                    continue
                backend = next(
                    (v for v in (payload.get("backend"), nested.get("backend")) if isinstance(v, str) and v),
                    None,
                )
                pending.append((path, backend or "", artifact_size_bytes(path), object_id))

            for path, backend, size_bytes, object_id in pending:
                conn.execute(
                    """
                    UPDATE data_objects
                    SET storage_path = ?,
                        backend = COALESCE(backend, NULLIF(?, '')),
                        size_bytes = COALESCE(size_bytes, ?)
                    WHERE object_id = ?
                    """,
                    (path, backend, size_bytes, object_id),
                )
                updated += 1
            conn.commit()
        return updated

    def runs_in_progress(self) -> list[str]:
        """Return the ids of runs that have not reached a terminal status.

        #1983: artifact retention refuses to sweep while any run is still
        executing, because an in-flight run's outputs are not yet recorded in
        ``data_objects`` and would look unreferenced.
        """
        with self._connect() as conn:
            cur = conn.execute("SELECT run_id FROM runs WHERE status = 'running'")
            return [row[0] for row in cur.fetchall()]

    def latest_successful_run_per_workflow(self) -> dict[str, tuple[str, str]]:
        """Map each ``workflow_id`` to its most recent clean ``completed`` run.

        #1983: this is the retention root set. A workflow whose runs all failed
        or were cancelled is absent from the mapping, which the caller treats
        as "no retained run" rather than as "retain nothing" — see
        :func:`scistudio.core.lineage.retention.plan_retention`.

        Runs with ``provenance_degraded=1`` are excluded. #1527 sets that flag
        when a block or data-object lineage write failed, so such a run's
        recorded output set is known to be incomplete. Trusting it as the
        retention root would produce a *partially* populated live set — enough
        to satisfy the "retained run recorded something" guard, while the
        previous clean run's artifacts were reclaimed as superseded. Falling
        back to the last clean run keeps a complete set on disk; the degraded
        run's own outputs are still protected because they were written after
        that older run started.

        Returns:
            ``workflow_id`` → ``(run_id, started_at)``. The start timestamp
            bounds which artifacts retention may reclaim: anything written
            since the retained run began belongs to that run however long it
            took, so the bound holds for a run of any duration.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT workflow_id, run_id, started_at FROM runs AS r
                WHERE status = 'completed'
                  AND COALESCE(provenance_degraded, 0) = 0
                  AND started_at = (
                      SELECT MAX(started_at) FROM runs
                      WHERE workflow_id = r.workflow_id
                        AND status = 'completed'
                        AND COALESCE(provenance_degraded, 0) = 0
                  )
                """
            )
            return {row[0]: (row[1], row[2]) for row in cur.fetchall()}

    def artifact_paths_produced_by(self, run_ids: Iterable[str]) -> set[str]:
        """Return the storage paths of artifacts produced by the given runs.

        #1983 (owner directive): liveness is "produced by the retained run",
        deliberately **not** "referenced by" it. A partial re-run
        (``runs.execute_from_block_id``) therefore does not extend protection
        to the upstream artifacts it consumed from an earlier run; those are
        reclaimed and the workflow must be re-run end to end. The owner chose
        this rule for its simplicity over inherited-input protection.

        Args:
            run_ids: The retained run ids.

        Returns:
            The set of non-NULL ``storage_path`` values those runs produced.
        """
        ids = [rid for rid in run_ids if rid]
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                SELECT DISTINCT do.storage_path
                FROM data_objects do
                JOIN block_executions be
                  ON do.produced_by_execution = be.block_execution_id
                WHERE be.run_id IN ({placeholders})
                  AND do.storage_path IS NOT NULL
                """,
                tuple(ids),
            )
            return {row[0] for row in cur.fetchall()}

    @provisional(since="0.3.4")
    def session_declared_output_paths(self, session_ids: Iterable[str] | None = None) -> set[str]:
        """Return the storage paths of objects a session named as an output.

        ADR-054 FR-055: an object named through ``scistudio.output`` is durable.
        Retention protects exactly these paths and treats everything else a
        session produced as a reclaim candidate.

        Args:
            session_ids: When given, restrict to those sessions. ``None`` covers
                every session. An empty iterable returns an empty set without
                touching the database.

        Returns:
            The set of non-NULL ``storage_path`` values declared as outputs.
        """
        # The interpolated direction is a module constant, not caller input.
        return self._session_paths(
            session_ids,
            f"""
            SELECT DISTINCT do.storage_path
            FROM block_io bio
            JOIN block_executions be ON be.block_execution_id = bio.block_execution_id
            JOIN data_objects do ON do.object_id = bio.object_id
            WHERE bio.direction = '{DECLARED_OUTPUT_DIRECTION}'
              AND be.session_id IS NOT NULL
              AND do.storage_path IS NOT NULL
            """,
        )

    @provisional(since="0.3.4")
    def artifact_paths_produced_by_sessions(self, session_ids: Iterable[str] | None = None) -> set[str]:
        """Return the storage paths of artifacts produced inside sessions.

        The session-side counterpart of :meth:`artifact_paths_produced_by`, and
        liveness is "produced by" on this side too.

        Args:
            session_ids: When given, restrict to those sessions. ``None`` covers
                every session. An empty iterable returns an empty set without
                touching the database.

        Returns:
            The set of non-NULL ``storage_path`` values those sessions produced.
        """
        return self._session_paths(
            session_ids,
            """
            SELECT DISTINCT do.storage_path
            FROM data_objects do
            JOIN block_executions be ON be.block_execution_id = do.produced_by_execution
            WHERE be.session_id IS NOT NULL
              AND do.storage_path IS NOT NULL
            """,
        )

    def _session_paths(self, session_ids: Iterable[str] | None, sql: str) -> set[str]:
        """Run *sql* (which selects one path column) over all or some sessions."""
        params: tuple[str, ...] = ()
        if session_ids is not None:
            ids = [sid for sid in session_ids if sid]
            if not ids:
                return set()
            sql = f"{sql} AND be.session_id IN ({','.join('?' * len(ids))})"
            params = tuple(ids)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return {row[0] for row in cur.fetchall() if row[0]}

    # ------------------------------------------------------------------
    # Test / introspection helpers
    # ------------------------------------------------------------------

    def count(self, table: str) -> int:
        """Return the row count of one of the lineage tables.

        ``block_executions`` holds both anchors' rows (ADR-054 FR-051), so its
        count spans workflow runs and Explore sessions alike.

        Args:
            table: One of ``"runs"``, ``"explore_sessions"``,
                ``"block_executions"``, ``"data_objects"``, or ``"block_io"``.

        Returns:
            The number of rows in the table.

        Raises:
            ValueError: When *table* is not a known lineage table.
        """
        if table not in {"runs", "explore_sessions", "block_executions", "data_objects", "block_io"}:
            raise ValueError(f"unknown lineage table: {table}")
        with self._connect() as conn:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")  # table name allow-listed above
            return int(cur.fetchone()[0])

    def execute_query(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Run a read-only SQL query and return all rows.

        Provided so a read-only consumer can run queries (e.g. recursive-CTE
        ancestor/descendant lookups) that do not fit the per-table accessors.
        Best-effort: SQLite errors propagate to the caller.

        The read-only contract is enforced with two layers of defence:

        1. **Statement check** — only a single ``SELECT`` / ``WITH`` /
           ``EXPLAIN`` / read-form ``PRAGMA`` / ``VALUES`` statement is
           accepted; anything that could mutate (or that batches multiple
           statements) raises :class:`ValueError` before the database is
           touched.
        2. **Read-only connection** — for a file-backed store the query runs on
           a ``mode=ro`` connection, so even a statement that slipped past the
           check cannot modify the file. An in-memory store cannot reopen
           read-only, so it additionally engages SQLite's query-only mode.

        Args:
            sql: A single read-only SQL statement.
            params: Positional parameters bound into the statement.

        Returns:
            All result rows as a list of tuples.

        Raises:
            ValueError: When *sql* is not a single read-only statement.
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
