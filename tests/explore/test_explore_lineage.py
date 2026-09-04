"""Explore-session lineage: cell runs, block calls, the boundary, retention.

ADR-054 FR-051 to FR-055 (#2240). The claim the spec makes is that a session
writes into the same tables a workflow run does, and the test that proves it is
the one about the boundary: an object produced in a session and consumed by a
workflow run has to resolve **in both directions**, from the object to the
session that made it and from the object to the run that used it, without either
side knowing the other exists.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scistudio.core.lineage.record import BlockExecutionRecord, BlockIORow, DataObjectRow, RunRecord
from scistudio.core.lineage.retention import apply_retention, plan_retention
from scistudio.core.lineage.store import DECLARED_OUTPUT_DIRECTION, LineageStore
from scistudio.explore.lineage import CELL_BLOCK_TYPE, ExploreLineage

NOTEBOOK_COMMIT = "a" * 40


@pytest.fixture
def store() -> Iterator[LineageStore]:
    """An in-memory lineage store."""
    lineage_store = LineageStore(":memory:")
    yield lineage_store
    lineage_store.close()


@pytest.fixture
def lineage(store: LineageStore) -> ExploreLineage:
    """An :class:`ExploreLineage` over the in-memory store."""
    return ExploreLineage(store)


def _object(object_id: str, *, path: str | None = None) -> DataObjectRow:
    """Build a data-object row, optionally backed by a path."""
    return DataObjectRow(
        object_id=object_id,
        type_name="Table",
        wire_payload={"backend": "zarr", "path": path} if path else {},
        created_at="2026-09-04T10:00:00+00:00",
        backend="zarr" if path else None,
        storage_path=path,
    )


def _seed_run(store: LineageStore, run_id: str = "run-1", *, workflow_id: str = "wf") -> None:
    """Insert a completed workflow run."""
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot="id: wf\n",
            started_at="2026-09-04T12:00:00+00:00",
            finished_at="2026-09-04T12:00:10+00:00",
            status="completed",
            environment_snapshot={},
        )
    )


def _run_block(
    store: LineageStore,
    *,
    run_id: str = "run-1",
    execution_id: str = "be-run-1",
    block_id: str = "consumer",
    block_version: str = "1.0.0",
) -> str:
    """Insert a run-anchored block execution and return its id."""
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id=execution_id,
            run_id=run_id,
            block_id=block_id,
            block_type="Consumer",
            block_version=block_version,
            block_config_resolved={},
            started_at="2026-09-04T12:00:01+00:00",
            termination="completed",
        )
    )
    return execution_id


# ---------------------------------------------------------------------------
# FR-052 — the session anchor
# ---------------------------------------------------------------------------


def test_open_session_writes_the_anchor(lineage: ExploreLineage, store: LineageStore) -> None:
    """Opening a session is one ``explore_sessions`` row, running."""
    record = lineage.open_session(
        session_id="sess-1",
        notebook_path="explore/a.ipynb",
        notebook_snapshot='{"cells": []}',
        environment_ref="env:abc",
    )

    assert record.status == "running"
    row = store.get_explore_session("sess-1")
    assert row is not None
    assert row["notebook_path"] == "explore/a.ipynb"
    assert row["environment_ref"] == "env:abc"
    assert row["opened_over"] == "file"
    assert store.sessions_in_progress() == ["sess-1"]


def test_close_session_ends_it_and_can_latch_degradation(lineage: ExploreLineage, store: LineageStore) -> None:
    """A closed session stops blocking retention and can say its lineage is partial."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    lineage.close_session("sess-1", provenance_degraded=True)

    row = store.get_explore_session("sess-1")
    assert row is not None
    assert row["status"] == "closed"
    assert row["finished_at"] is not None
    assert row["provenance_degraded"] == 1
    assert store.sessions_in_progress() == []


def test_set_notebook_commit_records_the_sessions_current_commit(lineage: ExploreLineage, store: LineageStore) -> None:
    """FR-035: the session names the commit its last cell run produced."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    lineage.set_notebook_commit("sess-1", NOTEBOOK_COMMIT)

    row = store.get_explore_session("sess-1")
    assert row is not None and row["notebook_git_commit"] == NOTEBOOK_COMMIT


# ---------------------------------------------------------------------------
# FR-053 — cell runs
# ---------------------------------------------------------------------------


def test_a_cell_run_carries_the_session_commit_cell_and_environment(
    lineage: ExploreLineage, store: LineageStore
) -> None:
    """FR-053 names four things; the record carries all four."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    execution_id = lineage.record_cell_run(
        session_id="sess-1",
        cell_id="cell-a",
        notebook_commit=NOTEBOOK_COMMIT,
        environment_ref="env:abc",
        duration_ms=42,
    )

    [row] = store.list_session_block_executions("sess-1")
    assert row["block_execution_id"] == execution_id
    assert row["session_id"] == "sess-1"
    assert row["block_version"] == NOTEBOOK_COMMIT
    assert row["block_id"] == "cell-a"
    assert row["environment_ref"] == "env:abc"
    assert row["block_type"] == CELL_BLOCK_TYPE
    assert row["run_id"] is None
    assert row["duration_ms"] == 42


def test_every_run_of_the_same_cell_is_its_own_record(lineage: ExploreLineage, store: LineageStore) -> None:
    """FR-053 says *every* cell run, and a person re-runs a cell constantly."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    first = lineage.record_cell_run(
        session_id="sess-1", cell_id="cell-a", notebook_commit=NOTEBOOK_COMMIT, started_at="2026-09-04T10:00:00"
    )
    second = lineage.record_cell_run(
        session_id="sess-1", cell_id="cell-a", notebook_commit="b" * 40, started_at="2026-09-04T10:00:05"
    )

    rows = store.list_session_block_executions("sess-1")
    assert [r["block_execution_id"] for r in rows] == [first, second]
    assert [r["block_version"] for r in rows] == [NOTEBOOK_COMMIT, "b" * 40]


def test_a_failed_cell_run_is_recorded_with_its_reason(lineage: ExploreLineage, store: LineageStore) -> None:
    """A cell that raised is a record, not a gap."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    lineage.record_cell_run(
        session_id="sess-1",
        cell_id="cell-a",
        notebook_commit=NOTEBOOK_COMMIT,
        termination="error",
        termination_detail="ZeroDivisionError",
    )

    [row] = store.list_session_block_executions("sess-1")
    assert row["termination"] == "error"
    assert row["termination_detail"] == "ZeroDivisionError"


# ---------------------------------------------------------------------------
# FR-051 — a block called from a cell
# ---------------------------------------------------------------------------


def test_a_block_call_records_its_edges_as_a_workflow_run_would(lineage: ExploreLineage, store: LineageStore) -> None:
    """FR-051: the anchor is the session; the io is ordinary ``block_io``."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    execution_id = lineage.record_block_call(
        session_id="sess-1",
        block_id="cell-a:0",
        block_type="Smooth",
        block_version="2.1.0",
        config={"window": 5},
        inputs={"table": _object("obj-in")},
        outputs={"result": _object("obj-out")},
    )

    [row] = store.list_session_block_executions("sess-1")
    assert row["block_execution_id"] == execution_id
    assert row["session_id"] == "sess-1"
    assert row["block_type"] == "Smooth"
    assert row["block_version"] == "2.1.0"
    assert row["block_config_resolved"] == '{"window": 5}'

    edges = store.list_block_io(execution_id)
    assert [(e["direction"], e["port_name"], e["object_id"]) for e in edges] == [
        ("input", "table", "obj-in"),
        ("output", "result", "obj-out"),
    ]
    produced = store.get_data_object("obj-out")
    assert produced is not None and produced["produced_by_execution"] == execution_id
    consumed = store.get_data_object("obj-in")
    assert consumed is not None and consumed["produced_by_execution"] is None


def test_a_collection_port_becomes_one_edge_per_item(lineage: ExploreLineage, store: LineageStore) -> None:
    """Positions are recorded the same way a run records a Collection port."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")

    execution_id = lineage.record_block_call(
        session_id="sess-1",
        block_id="cell-a:0",
        block_type="Merge",
        block_version="1.0.0",
        inputs={"tables": [_object("obj-1"), _object("obj-2")]},
        outputs={"merged": _object("obj-3")},
    )

    inputs = [e for e in store.list_block_io(execution_id) if e["direction"] == "input"]
    assert [(e["position"], e["object_id"]) for e in inputs] == [(0, "obj-1"), (1, "obj-2")]


def test_a_block_call_keeps_a_producer_the_caller_already_knows(lineage: ExploreLineage, store: LineageStore) -> None:
    """An output row that already names its producer is not restamped."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")
    first = lineage.record_block_call(
        session_id="sess-1", block_id="c0", block_type="T", block_version="1", outputs={"out": _object("obj-1")}
    )

    lineage.record_block_call(
        session_id="sess-1",
        block_id="c1",
        block_type="T",
        block_version="1",
        outputs={"out": DataObjectRow(**{**_object("obj-1").__dict__, "produced_by_execution": first})},
    )

    row = store.get_data_object("obj-1")
    assert row is not None and row["produced_by_execution"] == first


# ---------------------------------------------------------------------------
# The boundary — the test that matters
# ---------------------------------------------------------------------------


def test_an_object_made_in_a_session_and_used_by_a_run_resolves_both_ways(
    lineage: ExploreLineage, store: LineageStore
) -> None:
    """The claim of §4.1: one catalog, two anchors, reachable from either side."""
    lineage.open_session(
        session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}", environment_ref="env:abc"
    )
    session_execution = lineage.record_block_call(
        session_id="sess-1",
        block_id="cell-a:0",
        block_type="Featurise",
        block_version="3.0.0",
        outputs={"features": _object("obj-shared")},
    )
    _seed_run(store)
    run_execution = _run_block(store)
    store.insert_block_io(
        BlockIORow(
            block_execution_id=run_execution,
            direction="input",
            port_name="table",
            object_id="obj-shared",
        )
    )

    # Session → run: who used what the session made?
    uses = lineage.uses_of("obj-shared")
    assert [(u.kind, u.anchor_id, u.block_id, u.port_name) for u in uses] == [("run", "run-1", "consumer", "table")]

    # Run → session: where did the object this run consumed come from?
    origin = lineage.origin_of("obj-shared")
    assert origin is not None
    assert origin.kind == "session"
    assert origin.anchor_id == "sess-1"
    assert origin.block_execution_id == session_execution
    assert origin.block_id == "cell-a:0"
    assert origin.block_type == "Featurise"
    session_row = lineage.session_of("obj-shared")
    assert session_row is not None and session_row["notebook_path"] == "explore/a.ipynb"


def test_the_boundary_resolves_the_other_way_round_too(lineage: ExploreLineage, store: LineageStore) -> None:
    """An object a run produced and a session then consumed reads symmetrically."""
    _seed_run(store)
    run_execution = _run_block(store, block_id="producer")
    store.upsert_data_object(
        DataObjectRow(**{**_object("obj-from-run").__dict__, "produced_by_execution": run_execution})
    )
    store.insert_block_io(
        BlockIORow(block_execution_id=run_execution, direction="output", port_name="out", object_id="obj-from-run")
    )
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")
    session_execution = lineage.record_block_call(
        session_id="sess-1",
        block_id="cell-a:0",
        block_type="Smooth",
        block_version="1.0.0",
        inputs={"table": _object("obj-from-run")},
    )

    origin = lineage.origin_of("obj-from-run")
    assert origin is not None and (origin.kind, origin.anchor_id) == ("run", "run-1")
    assert lineage.session_of("obj-from-run") is None

    uses = lineage.uses_of("obj-from-run")
    assert [(u.kind, u.anchor_id, u.block_execution_id) for u in uses] == [("session", "sess-1", session_execution)]


def test_an_unknown_or_external_object_resolves_to_nothing(lineage: ExploreLineage) -> None:
    """No producer recorded is ``None``, not a guess."""
    assert lineage.origin_of("obj-nope") is None
    assert lineage.uses_of("obj-nope") == []
    assert lineage.session_of("obj-nope") is None


# ---------------------------------------------------------------------------
# FR-054 — a packaged block's run points back at the session
# ---------------------------------------------------------------------------


def test_a_packaged_blocks_step_resolves_back_to_its_session(lineage: ExploreLineage, store: LineageStore) -> None:
    """FR-054: the step's block version is the notebook commit, so the session is reachable."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")
    lineage.record_cell_run(session_id="sess-1", cell_id="cell-a", notebook_commit=NOTEBOOK_COMMIT)
    _seed_run(store)
    _run_block(store, block_id="packaged", block_version=NOTEBOOK_COMMIT)

    session_row = lineage.session_behind_step("run-1", "packaged")

    assert session_row is not None
    assert session_row["session_id"] == "sess-1"


def test_a_session_is_reachable_from_its_own_current_commit(lineage: ExploreLineage, store: LineageStore) -> None:
    """The fallback path: a session that recorded the commit but no cell run at it."""
    lineage.open_session(
        session_id="sess-1",
        notebook_path="explore/a.ipynb",
        notebook_snapshot="{}",
        notebook_git_commit=NOTEBOOK_COMMIT,
    )
    _seed_run(store)
    _run_block(store, block_id="packaged", block_version=NOTEBOOK_COMMIT)

    session_row = lineage.session_behind_step("run-1", "packaged")

    assert session_row is not None and session_row["session_id"] == "sess-1"


def test_an_ordinary_step_resolves_to_no_session(lineage: ExploreLineage, store: LineageStore) -> None:
    """A block version that is a version, not a commit, belongs to nobody."""
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")
    _seed_run(store)
    _run_block(store, block_id="loader", block_version="1.0.0")

    assert lineage.session_behind_step("run-1", "loader") is None
    assert lineage.session_behind_step("run-1", "absent") is None


# ---------------------------------------------------------------------------
# FR-055 — durability and retention
# ---------------------------------------------------------------------------


def _zarr(root: Path, workflow_id: str, block_id: str, name: str) -> Path:
    """Create a directory-backed artifact under ``data/zarr`` and return its path."""
    path = root / "data" / "zarr" / workflow_id / block_id / f"{name}.zarr"
    path.mkdir(parents=True)
    (path / "0.0").write_bytes(b"x" * 64)
    (path / ".zarray").write_text("{}", encoding="utf-8")
    return path


def _session_with_two_objects(lineage: ExploreLineage, tmp_path: Path) -> tuple[Path, Path, str]:
    """A closed session that produced one declared object and one scratch object."""
    declared_path = _zarr(tmp_path, "sess-1", "cell-a", "declared")
    scratch_path = _zarr(tmp_path, "sess-1", "cell-a", "scratch")
    lineage.open_session(session_id="sess-1", notebook_path="explore/a.ipynb", notebook_snapshot="{}")
    execution_id = lineage.record_block_call(
        session_id="sess-1",
        block_id="cell-a:0",
        block_type="Featurise",
        block_version="1.0.0",
        outputs={
            "declared": _object("obj-declared", path=str(declared_path)),
            "scratch": _object("obj-scratch", path=str(scratch_path)),
        },
    )
    lineage.declare_output(
        block_execution_id=execution_id, name="result", row=_object("obj-declared", path=str(declared_path))
    )
    lineage.close_session("sess-1")
    return declared_path, scratch_path, execution_id


def test_declare_output_marks_an_object_durable(lineage: ExploreLineage, store: LineageStore, tmp_path: Path) -> None:
    """FR-055: the declared object is durable, the other one is a candidate."""
    declared_path, scratch_path, execution_id = _session_with_two_objects(lineage, tmp_path)

    assert lineage.durable_paths() == {str(declared_path)}
    assert lineage.reclaimable_paths() == {str(scratch_path)}
    edge_directions = {e["direction"] for e in store.list_block_io(execution_id)}
    assert DECLARED_OUTPUT_DIRECTION in edge_directions
    assert lineage.durable_paths(["sess-other"]) == set()


def test_declaring_the_same_name_twice_is_a_no_op(lineage: ExploreLineage, tmp_path: Path) -> None:
    """Re-running the declaring cell must not duplicate the edge."""
    declared_path, _, execution_id = _session_with_two_objects(lineage, tmp_path)

    lineage.declare_output(
        block_execution_id=execution_id, name="result", row=_object("obj-declared", path=str(declared_path))
    )

    assert lineage.durable_paths() == {str(declared_path)}


def test_retention_keeps_the_declared_object_and_reclaims_the_rest(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """The existing planner sweeps a session's objects on FR-055's terms."""
    declared_path, scratch_path, _ = _session_with_two_objects(lineage, tmp_path)

    plan = plan_retention(store, tmp_path)

    assert not plan.is_blocked
    assert [c.path for c in plan.candidates] == [scratch_path]
    assert plan.durable_session_paths == {str(declared_path.resolve())}

    removed, freed = apply_retention(plan)

    assert removed == 1
    assert freed > 0
    assert declared_path.exists()
    assert not scratch_path.exists()


def test_retention_does_not_orphan_the_rows_it_sweeps(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """Reclaiming bytes leaves the provenance intact and still resolvable."""
    _, scratch_path, execution_id = _session_with_two_objects(lineage, tmp_path)

    apply_retention(plan_retention(store, tmp_path))

    assert store.get_data_object("obj-scratch") is not None
    origin = lineage.origin_of("obj-scratch")
    assert origin is not None and origin.block_execution_id == execution_id
    assert store.get_explore_session("sess-1") is not None
    assert store.check_object_integrity("obj-scratch") in {"dangling", "unknown"}
    assert not scratch_path.exists()


def test_retention_refuses_to_sweep_while_a_session_is_open(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """An open session can still produce objects, so nothing is reclaimable yet."""
    _session_with_two_objects(lineage, tmp_path)
    lineage.open_session(session_id="sess-2", notebook_path="explore/b.ipynb", notebook_snapshot="{}")

    plan = plan_retention(store, tmp_path)

    assert plan.is_blocked
    assert "explore session" in (plan.blocked_reason or "")
    assert plan.candidates == ()
    assert apply_retention(plan) == (0, 0)


def test_a_project_with_only_sessions_is_not_an_empty_lineage_database(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """The empty-database guard must not fire on a project that has only explored."""
    _, scratch_path, _ = _session_with_two_objects(lineage, tmp_path)

    plan = plan_retention(store, tmp_path)

    assert not plan.is_blocked
    assert [c.path for c in plan.candidates] == [scratch_path]


def test_an_object_a_retained_run_also_produced_is_never_reclaimed(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """The run rule and the session rule both protect; neither one overrides the other."""
    _session_with_two_objects(lineage, tmp_path)
    run_artifact = _zarr(tmp_path, "wf", "loader", "kept")
    _seed_run(store)
    run_execution = _run_block(store, block_id="loader")
    store.upsert_data_object(
        DataObjectRow(
            **{
                **_object("obj-run", path=str(run_artifact)).__dict__,
                "produced_by_execution": run_execution,
            }
        )
    )

    plan = plan_retention(store, tmp_path)

    assert run_artifact not in [c.path for c in plan.candidates]
    assert str(run_artifact.resolve()) in plan.live_paths


def test_a_workflows_artifacts_are_untouched_by_the_session_rule(
    lineage: ExploreLineage, store: LineageStore, tmp_path: Path
) -> None:
    """A session in the project must not make a workflow's floor invariant fire.

    The workflow here has one artifact and no successful run recording it, so
    the pre-existing guard protects its directory — a session sharing the
    project changes nothing about that.
    """
    _session_with_two_objects(lineage, tmp_path)
    orphan = _zarr(tmp_path, "wf", "loader", "orphan")

    plan = plan_retention(store, tmp_path)

    assert orphan.exists()
    assert orphan not in [c.path for c in plan.candidates]
    assert "wf" in plan.protected_workflows
