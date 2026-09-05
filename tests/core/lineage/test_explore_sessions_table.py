"""The ``explore_sessions`` anchor and the shared ``block_executions`` table.

ADR-054 FR-051 and FR-052 (#2240). ``explore_sessions`` parallels ``runs`` so
that block executions, data objects, and io edges are the same code with a
different foreign key. Two things therefore have to be true at once, and this
file asserts both:

* a session's rows behave like a run's wherever the shape is shared, and
* nothing a workflow run does changes — the table gained an anchor, not a
  meaning. ``src/scistudio/core/lineage`` is a protected core path and the
  change to it is promised to be additive, so the legacy-database test below
  opens a database written against the pre-#2240 schema and checks the rows,
  the constraints, and the indexes that survive the rebuild.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    ExploreSessionRecord,
    RunRecord,
)
from scistudio.core.lineage.store import (
    DECLARED_OUTPUT_DIRECTION,
    LINEAGE_SCHEMA_VERSION,
    LineageStore,
)

# The ``block_executions`` definition exactly as it shipped before #2240, used
# to build a legacy database the migration then has to carry forward. It is
# spelled out rather than imported because the point is to pin what the old
# format was, not to follow the current constant wherever it goes.
_LEGACY_BLOCK_EXECUTIONS_DDL = """
    CREATE TABLE block_executions (
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
"""

_LEGACY_RUNS_DDL = """
    CREATE TABLE runs (
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
        provenance_degraded     INTEGER NOT NULL DEFAULT 0
    )
"""

_LEGACY_DATA_OBJECTS_DDL = """
    CREATE TABLE data_objects (
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
        content_hash            TEXT
    )
"""

_LEGACY_BLOCK_IO_DDL = """
    CREATE TABLE block_io (
        block_execution_id      TEXT NOT NULL REFERENCES block_executions(block_execution_id),
        direction               TEXT NOT NULL,
        port_name               TEXT NOT NULL,
        object_id               TEXT NOT NULL REFERENCES data_objects(object_id),
        position                INTEGER NOT NULL,
        PRIMARY KEY (block_execution_id, direction, port_name, position)
    )
"""


def _session(session_id: str = "sess-1", **overrides: object) -> ExploreSessionRecord:
    """Build a session record with sensible defaults."""
    fields: dict[str, object] = {
        "session_id": session_id,
        "notebook_path": "explore/analysis.ipynb",
        "notebook_snapshot": '{"cells": []}',
        "started_at": "2026-09-04T10:00:00+00:00",
        "status": "running",
        "environment_ref": "env:abc123",
        "notebook_git_commit": "c" * 40,
        "opened_over": "file",
    }
    fields.update(overrides)
    return ExploreSessionRecord(**fields)  # type: ignore[arg-type]


def _run(run_id: str = "run-1", **overrides: object) -> RunRecord:
    """Build a run record with sensible defaults."""
    fields: dict[str, object] = {
        "run_id": run_id,
        "workflow_id": "wf",
        "workflow_yaml_snapshot": "id: wf\n",
        "started_at": "2026-09-04T09:00:00+00:00",
        "status": "completed",
        "environment_snapshot": {},
    }
    fields.update(overrides)
    return RunRecord(**fields)  # type: ignore[arg-type]


def _cell_run(execution_id: str, session_id: str = "sess-1", **overrides: object) -> BlockExecutionRecord:
    """Build a session-anchored block execution."""
    fields: dict[str, object] = {
        "block_execution_id": execution_id,
        "run_id": None,
        "block_id": "cell-a",
        "block_type": "explore_cell",
        "block_version": "c" * 40,
        "block_config_resolved": {},
        "started_at": "2026-09-04T10:00:01+00:00",
        "termination": "completed",
        "session_id": session_id,
        "environment_ref": "env:abc123",
    }
    fields.update(overrides)
    return BlockExecutionRecord(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FR-052 — the anchor
# ---------------------------------------------------------------------------


def test_fresh_database_has_the_session_anchor_and_the_current_version(tmp_path: Path) -> None:
    """A new lineage.db carries ``explore_sessions`` and is stamped current."""
    store = LineageStore(str(tmp_path / "lineage.db"))
    try:
        tables = {row[0] for row in store.execute_query("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "explore_sessions" in tables
        assert {"runs", "block_executions", "data_objects", "block_io"} <= tables
        assert store.execute_query("PRAGMA user_version")[0][0] == LINEAGE_SCHEMA_VERSION
    finally:
        store.close()


def test_session_round_trips_through_insert_get_and_list() -> None:
    """The anchor stores and returns every field FR-052 names."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session())

    row = store.get_explore_session("sess-1")

    assert row is not None
    assert row["session_id"] == "sess-1"
    assert row["notebook_path"] == "explore/analysis.ipynb"
    assert row["notebook_snapshot"] == '{"cells": []}'
    assert row["notebook_git_commit"] == "c" * 40
    assert row["environment_ref"] == "env:abc123"
    assert row["started_at"] == "2026-09-04T10:00:00+00:00"
    assert row["status"] == "running"
    assert row["finished_at"] is None
    assert row["provenance_degraded"] == 0
    assert [r["session_id"] for r in store.list_explore_sessions()] == ["sess-1"]
    assert store.list_explore_sessions(notebook_path="explore/other.ipynb") == []
    assert store.count("explore_sessions") == 1
    store.close()


def test_finalize_session_latches_provenance_degraded() -> None:
    """One failed write marks the session even when later ones succeed — as for runs."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session())

    store.finalize_explore_session(
        "sess-1", finished_at="2026-09-04T11:00:00+00:00", status="closed", provenance_degraded=True
    )
    store.finalize_explore_session("sess-1", finished_at="2026-09-04T11:00:01+00:00", status="closed")

    row = store.get_explore_session("sess-1")
    assert row is not None
    assert row["status"] == "closed"
    assert row["finished_at"] == "2026-09-04T11:00:01+00:00"
    assert row["provenance_degraded"] == 1
    store.close()


def test_sessions_in_progress_reports_only_open_sessions() -> None:
    """The session-side counterpart of ``runs_in_progress``."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session("sess-open"))
    store.insert_explore_session(_session("sess-shut", status="closed"))

    assert store.sessions_in_progress() == ["sess-open"]
    store.close()


def test_set_session_notebook_commit_stamps_the_current_commit() -> None:
    """FR-035: the session reports the commit its last cell run produced."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session(notebook_git_commit=None))

    store.set_session_notebook_commit("sess-1", "d" * 40)

    row = store.get_explore_session("sess-1")
    assert row is not None and row["notebook_git_commit"] == "d" * 40
    store.close()


def test_session_bound_to_a_run_references_it() -> None:
    """A session opened over a paused run keeps the foreign key to it (FR-046)."""
    store = LineageStore(":memory:")
    store.insert_run(_run())
    store.insert_explore_session(_session(opened_over="paused_run", bound_run_id="run-1"))

    row = store.get_explore_session("sess-1")
    assert row is not None and row["bound_run_id"] == "run-1"

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_explore_session(_session("sess-2", opened_over="paused_run", bound_run_id="run-nope"))
    store.close()


# ---------------------------------------------------------------------------
# FR-051 — the shared block_executions table
# ---------------------------------------------------------------------------


def test_block_execution_anchors_to_a_session() -> None:
    """A session's execution is a ``block_executions`` row with a NULL run_id."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session())

    store.insert_block_execution(_cell_run("be-cell-1"))

    rows = store.list_session_block_executions("sess-1")
    assert [r["block_execution_id"] for r in rows] == ["be-cell-1"]
    assert rows[0]["run_id"] is None
    assert rows[0]["session_id"] == "sess-1"
    assert rows[0]["block_version"] == "c" * 40
    assert rows[0]["environment_ref"] == "env:abc123"
    store.close()


def test_a_session_execution_is_invisible_to_every_run_scoped_read() -> None:
    """The reuse must not leak: run queries key on ``run_id`` and see nothing new."""
    store = LineageStore(":memory:")
    store.insert_run(_run())
    store.insert_explore_session(_session())
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id="be-run-1",
            run_id="run-1",
            block_id="loader",
            block_type="Loader",
            block_version="1.0.0",
            block_config_resolved={},
            started_at="2026-09-04T09:00:01+00:00",
            termination="completed",
        )
    )
    store.insert_block_execution(_cell_run("be-cell-1"))

    assert [r["block_execution_id"] for r in store.list_block_executions("run-1")] == ["be-run-1"]
    # The shim's workflow join is an inner join through ``runs``; a session row
    # has no run to join to, so it drops out.
    joined = store.execute_query(
        """
        SELECT be.block_execution_id FROM block_executions be
        JOIN runs r ON r.run_id = be.run_id
        """
    )
    assert [row[0] for row in joined] == ["be-run-1"]
    # ``count`` is deliberately the table's count, both anchors included.
    assert store.count("block_executions") == 2
    store.close()


def test_a_session_may_run_the_same_cell_repeatedly() -> None:
    """``UNIQUE (run_id, block_id)`` is inert for a session: NULLs are distinct."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session())

    store.insert_block_execution(_cell_run("be-1"))
    store.insert_block_execution(_cell_run("be-2", started_at="2026-09-04T10:00:02+00:00"))

    rows = store.list_session_block_executions("sess-1")
    assert [r["block_execution_id"] for r in rows] == ["be-1", "be-2"]
    store.close()


def test_a_run_still_gets_one_row_per_block() -> None:
    """The run-side de-duplication the UNIQUE constraint provides is unchanged."""
    store = LineageStore(":memory:")
    store.insert_run(_run())
    record = BlockExecutionRecord(
        block_execution_id="be-run-1",
        run_id="run-1",
        block_id="loader",
        block_type="Loader",
        block_version="1.0.0",
        block_config_resolved={},
        started_at="2026-09-04T09:00:01+00:00",
        termination="completed",
    )
    store.insert_block_execution(record)
    store.insert_block_execution(BlockExecutionRecord(**{**record.__dict__, "block_execution_id": "be-run-1-again"}))

    assert [r["block_execution_id"] for r in store.list_block_executions("run-1")] == ["be-run-1"]
    store.close()


@pytest.mark.parametrize(
    ("run_id", "session_id"),
    [("run-1", "sess-1"), (None, None)],
    ids=["both-anchors", "no-anchor"],
)
def test_an_execution_must_have_exactly_one_anchor(run_id: str | None, session_id: str | None) -> None:
    """Ambiguity is refused at the API, before SQLite's CHECK has to catch it."""
    store = LineageStore(":memory:")
    store.insert_run(_run())
    store.insert_explore_session(_session())

    with pytest.raises(ValueError, match="exactly one"):
        store.insert_block_execution(_cell_run("be-x", run_id=run_id, session_id=session_id))
    store.close()


def test_the_database_refuses_a_two_anchor_row_even_bypassing_the_store() -> None:
    """The CHECK constraint is the backstop, not just the Python guard."""
    store = LineageStore(":memory:")
    store.insert_run(_run())
    store.insert_explore_session(_session())

    # Reaches past the API on purpose: the subject is the schema's own guard.
    with pytest.raises(sqlite3.IntegrityError), store._connect() as conn:
        conn.execute(
            """
                INSERT INTO block_executions (
                    block_execution_id, run_id, block_id, block_type, block_version,
                    block_config_resolved, started_at, termination, session_id
                ) VALUES ('be-x', 'run-1', 'c', 't', 'v', '{}', 'now', 'completed', 'sess-1')
                """
        )
    store.close()


def test_an_execution_cannot_point_at_a_session_that_does_not_exist() -> None:
    """The session anchor is a real foreign key, enforced like the run one."""
    store = LineageStore(":memory:")

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_block_execution(_cell_run("be-1", session_id="sess-missing"))
    store.close()


# ---------------------------------------------------------------------------
# The migration — the additive promise on a protected path
# ---------------------------------------------------------------------------


def _write_legacy_database(path: Path) -> None:
    """Create a lineage.db in the pre-#2240 (schema version 1) format."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA user_version = 1")
        for ddl in (
            _LEGACY_RUNS_DDL,
            _LEGACY_BLOCK_EXECUTIONS_DDL,
            _LEGACY_DATA_OBJECTS_DDL,
            _LEGACY_BLOCK_IO_DDL,
        ):
            conn.execute(ddl)
        conn.execute("CREATE INDEX idx_runs_workflow ON runs(workflow_id, started_at DESC)")
        conn.execute("CREATE INDEX idx_be_run ON block_executions(run_id)")
        conn.execute("CREATE INDEX idx_be_block ON block_executions(block_id)")
        conn.execute("CREATE INDEX idx_do_producer ON data_objects(produced_by_execution)")
        conn.execute("CREATE INDEX idx_io_object ON block_io(object_id)")
        conn.execute(
            "INSERT INTO runs (run_id, workflow_id, workflow_yaml_snapshot, workflow_dirty, "
            "started_at, status, environment_snapshot, triggered_by) "
            "VALUES ('run-old', 'wf', 'id: wf', 0, '2026-01-01T00:00:00', 'completed', '{}', 'user')"
        )
        conn.execute(
            "INSERT INTO block_executions (block_execution_id, run_id, block_id, block_type, "
            "block_version, block_config_resolved, started_at, finished_at, duration_ms, "
            "termination, termination_detail) "
            "VALUES ('be-old', 'run-old', 'loader', 'Loader', '1.0.0', '{\"k\": 1}', "
            "'2026-01-01T00:00:01', '2026-01-01T00:00:02', 1234, 'completed', 'fine')"
        )
        conn.execute(
            "INSERT INTO data_objects (object_id, type_name, created_at, wire_payload, "
            "produced_by_execution) VALUES ('obj-old', 'Table', '2026-01-01T00:00:02', '{}', 'be-old')"
        )
        conn.execute(
            "INSERT INTO block_io (block_execution_id, direction, port_name, object_id, position) "
            "VALUES ('be-old', 'output', 'out', 'obj-old', 0)"
        )
        conn.commit()
    finally:
        conn.close()


def test_a_legacy_database_keeps_every_row_and_gains_the_anchor(tmp_path: Path) -> None:
    """Opening a v1 database migrates it without touching what it already held."""
    db = tmp_path / "lineage.db"
    _write_legacy_database(db)

    store = LineageStore(str(db))
    try:
        [row] = store.list_block_executions("run-old")
        assert row["block_execution_id"] == "be-old"
        assert row["run_id"] == "run-old"
        assert row["block_id"] == "loader"
        assert row["block_type"] == "Loader"
        assert row["block_version"] == "1.0.0"
        assert row["block_config_resolved"] == '{"k": 1}'
        assert row["started_at"] == "2026-01-01T00:00:01"
        assert row["finished_at"] == "2026-01-01T00:00:02"
        assert row["duration_ms"] == 1234
        assert row["termination"] == "completed"
        assert row["termination_detail"] == "fine"
        # The two new columns arrive empty rather than invented.
        assert row["session_id"] is None
        assert row["environment_ref"] is None

        # The rows that pointed at the rebuilt table still point at it.
        assert store.get_data_object("obj-old") is not None
        assert [e["object_id"] for e in store.list_block_io("be-old")] == ["obj-old"]
        assert store.execute_query("PRAGMA foreign_key_check") == []
        assert store.execute_query("PRAGMA user_version")[0][0] == LINEAGE_SCHEMA_VERSION

        # The indexes the rebuild dropped with the old table are back, plus the
        # session one. ``index_list`` rows are ``(seq, name, unique, origin, partial)``.
        indexes = {row[1] for row in store.execute_query("PRAGMA index_list(block_executions)")}
        assert {"idx_be_run", "idx_be_block", "idx_be_session"} <= indexes
        assert store.execute_query(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='block_executions_migrating'"
        ) == [(0,)]
    finally:
        store.close()


def test_a_migrated_database_accepts_both_anchors_afterwards(tmp_path: Path) -> None:
    """The migration is what makes the legacy file usable for sessions too."""
    db = tmp_path / "lineage.db"
    _write_legacy_database(db)

    store = LineageStore(str(db))
    try:
        store.insert_explore_session(_session())
        store.insert_block_execution(_cell_run("be-cell-1"))

        assert [r["block_execution_id"] for r in store.list_session_block_executions("sess-1")] == ["be-cell-1"]
        assert [r["block_execution_id"] for r in store.list_block_executions("run-old")] == ["be-old"]

        # ``UNIQUE (run_id, block_id)`` came through the rebuild: a re-emit of
        # the legacy run's block is still ignored.
        store.insert_block_execution(
            BlockExecutionRecord(
                block_execution_id="be-old-again",
                run_id="run-old",
                block_id="loader",
                block_type="Loader",
                block_version="1.0.0",
                block_config_resolved={},
                started_at="2026-01-01T00:00:03",
                termination="completed",
            )
        )
        assert [r["block_execution_id"] for r in store.list_block_executions("run-old")] == ["be-old"]
    finally:
        store.close()


def test_reopening_a_migrated_database_is_a_no_op(tmp_path: Path) -> None:
    """The rebuild guard means the second open costs a PRAGMA and nothing else."""
    db = tmp_path / "lineage.db"
    _write_legacy_database(db)
    LineageStore(str(db)).close()

    store = LineageStore(str(db))
    try:
        [row] = store.list_block_executions("run-old")
        assert row["session_id"] is None
        assert store.execute_query("PRAGMA foreign_key_check") == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# FR-055 — the paths retention reads
# ---------------------------------------------------------------------------


def _object(object_id: str, path: str, execution_id: str) -> DataObjectRow:
    """Build a data-object row produced by *execution_id* at *path*."""
    return DataObjectRow(
        object_id=object_id,
        type_name="Table",
        wire_payload={},
        created_at="2026-09-04T10:00:02+00:00",
        backend="zarr",
        storage_path=path,
        produced_by_execution=execution_id,
    )


def test_declared_and_produced_paths_are_reported_separately(tmp_path: Path) -> None:
    """A declared output is durable; everything else the session made is not."""
    store = LineageStore(":memory:")
    store.insert_explore_session(_session())
    store.insert_block_execution(_cell_run("be-cell-1"))
    kept = str(tmp_path / "kept.zarr")
    scratch = str(tmp_path / "scratch.zarr")
    store.upsert_data_object(_object("obj-kept", kept, "be-cell-1"))
    store.upsert_data_object(_object("obj-scratch", scratch, "be-cell-1"))
    store.insert_block_io(
        BlockIORow(
            block_execution_id="be-cell-1",
            direction=DECLARED_OUTPUT_DIRECTION,
            port_name="result",
            object_id="obj-kept",
        )
    )

    assert store.session_declared_output_paths() == {kept}
    assert store.artifact_paths_produced_by_sessions() == {kept, scratch}
    assert store.session_declared_output_paths(["sess-other"]) == set()
    assert store.artifact_paths_produced_by_sessions([]) == set()
    store.close()


def test_a_declaration_is_invisible_to_the_run_scoped_io_reads(tmp_path: Path) -> None:
    """A session's declaration never reaches a workflow surface.

    A declaration is written on a session-anchored execution, and the run-scoped
    io read reaches its edges through ``run_id``, so the run sees its own
    ``'output'`` edge on the shared object and nothing else.
    """
    store = LineageStore(":memory:")
    store.insert_run(_run())
    store.insert_explore_session(_session())
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id="be-run-1",
            run_id="run-1",
            block_id="loader",
            block_type="Loader",
            block_version="1.0.0",
            block_config_resolved={},
            started_at="2026-09-04T09:00:01+00:00",
            termination="completed",
        )
    )
    store.insert_block_execution(_cell_run("be-cell-1"))
    store.upsert_data_object(_object("obj-1", str(tmp_path / "a.zarr"), "be-cell-1"))
    store.insert_block_io(
        BlockIORow(block_execution_id="be-run-1", direction="output", port_name="out", object_id="obj-1")
    )
    store.insert_block_io(
        BlockIORow(
            block_execution_id="be-cell-1",
            direction=DECLARED_OUTPUT_DIRECTION,
            port_name="named",
            object_id="obj-1",
        )
    )

    edges = store.list_block_io_with_objects("run-1")
    assert [(e["block_execution_id"], e["direction"]) for e in edges] == [("be-run-1", "output")]
    assert {e["direction"] for e in store.list_block_io("be-cell-1")} == {DECLARED_OUTPUT_DIRECTION}
    store.close()


def test_count_rejects_a_table_it_does_not_know() -> None:
    """The allow-list gained a table; it did not become a free-form query."""
    store = LineageStore(":memory:")
    with pytest.raises(ValueError, match="unknown lineage table"):
        store.count("sqlite_master")
    store.close()
