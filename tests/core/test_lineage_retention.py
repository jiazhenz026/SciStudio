"""Tests for artifact retention (#1983).

Covers:

* ``artifact_size_bytes`` measuring directory-backed stores (zarr) recursively,
  which ``Path.stat().st_size`` cannot do.
* ``_extract_storage_fields`` reading ``backend`` / ``path`` from both wire
  shapes; the nested (ApiRuntime data-catalog) shape is the one that reaches
  the recorder, and reading only the top level left ``storage_path`` NULL for
  every artifact ever recorded.
* ``backfill_storage_fields`` recovering those NULL columns from
  ``wire_payload``.
* ``plan_retention`` keeping the most recent successful run's artifacts,
  reclaiming the rest, and refusing to sweep under each safety guard.
* ``apply_retention`` removing exactly the planned artifacts.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)
from scistudio.core.lineage.recorder import _extract_storage_fields
from scistudio.core.lineage.retention import (
    RECENT_WRITE_GRACE_SECONDS,
    apply_retention,
    plan_retention,
)
from scistudio.core.lineage.store import LineageStore, artifact_size_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zarr_store(root: Path, workflow: str, block: str, name: str, payload: bytes) -> Path:
    """Create a directory-backed artifact shaped like a real zarr store."""
    store_dir = root / "data" / "zarr" / workflow / block / f"{name}.zarr"
    (store_dir / "c" / "0").mkdir(parents=True, exist_ok=True)
    (store_dir / "zarr.json").write_bytes(b'{"zarr_format":3}')
    (store_dir / "c" / "0" / "0").write_bytes(payload)
    return store_dir


def _age(path: Path, seconds: float) -> None:
    """Backdate *path* by *seconds* so it is outside the recent-write grace.

    Retention keeps anything written within
    :data:`~scistudio.core.lineage.retention.RECENT_WRITE_GRACE_SECONDS`, so a
    test artifact created moments ago is protected unless it is aged first.
    """
    if not path.exists():
        return
    timestamp = time.time() - seconds
    for entry in sorted(path.rglob("*"), reverse=True):
        os.utime(entry, (timestamp, timestamp))
    os.utime(path, (timestamp, timestamp))


def _age_all(*paths: Path) -> None:
    """Age every path well past the recent-write grace."""
    for path in paths:
        _age(path, RECENT_WRITE_GRACE_SECONDS * 2)


def _seed_run(
    store: LineageStore,
    *,
    run_id: str,
    workflow_id: str,
    status: str,
    started_at: str,
    artifacts: dict[str, Path],
) -> None:
    """Insert a run plus one block execution that produced *artifacts*."""
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot="",
            started_at=started_at,
            status=status,
            environment_snapshot={},
        )
    )
    be_id = f"be-{run_id}"
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id=be_id,
            run_id=run_id,
            block_id="load",
            block_type="T",
            block_version="1",
            block_config_resolved={},
            started_at=started_at,
            termination="completed",
        )
    )
    for position, (object_id, path) in enumerate(artifacts.items()):
        store.upsert_data_object(
            DataObjectRow(
                object_id=object_id,
                type_name="Image",
                wire_payload={"metadata": {"backend": "zarr", "path": str(path)}},
                created_at=started_at,
                backend="zarr",
                storage_path=str(path),
                produced_by_execution=be_id,
            )
        )
        store.insert_block_io(
            BlockIORow(
                block_execution_id=be_id,
                direction="output",
                port_name="out",
                object_id=object_id,
                position=position,
            )
        )


# ---------------------------------------------------------------------------
# artifact_size_bytes
# ---------------------------------------------------------------------------


def test_artifact_size_bytes_sums_directory_backed_store(tmp_path: Path) -> None:
    store_dir = _make_zarr_store(tmp_path, "wf", "load", "a", b"x" * 4096)

    assert artifact_size_bytes(str(store_dir)) == 4096 + len(b'{"zarr_format":3}')
    # The inode size a naive stat() would have reported is much smaller.
    assert store_dir.stat().st_size < 4096


def test_artifact_size_bytes_handles_files_and_missing_paths(tmp_path: Path) -> None:
    regular = tmp_path / "a.parquet"
    regular.write_bytes(b"1234")

    assert artifact_size_bytes(str(regular)) == 4
    assert artifact_size_bytes(str(tmp_path / "absent.zarr")) is None
    assert artifact_size_bytes(None) is None
    assert artifact_size_bytes("") is None


# ---------------------------------------------------------------------------
# _extract_storage_fields — the NULL storage_path root cause
# ---------------------------------------------------------------------------


def test_extract_storage_fields_reads_nested_catalog_shape() -> None:
    """The shape that actually reaches the recorder nests backend/path."""
    wire = {
        "data_ref": "data-1",
        "type_name": "Image",
        "metadata": {"backend": "zarr", "path": "/p/a.zarr"},
    }

    assert _extract_storage_fields(wire) == ("zarr", "/p/a.zarr")


def test_extract_storage_fields_reads_raw_worker_shape() -> None:
    wire = {"backend": "zarr", "path": "/p/a.zarr", "metadata": {}}

    assert _extract_storage_fields(wire) == ("zarr", "/p/a.zarr")


def test_extract_storage_fields_prefers_top_level_and_tolerates_absence() -> None:
    wire = {"backend": "arrow", "path": "/top.parquet", "metadata": {"backend": "zarr", "path": "/nested.zarr"}}
    assert _extract_storage_fields(wire) == ("arrow", "/top.parquet")

    assert _extract_storage_fields({"metadata": None}) == (None, None)
    assert _extract_storage_fields({}) == (None, None)


# ---------------------------------------------------------------------------
# backfill_storage_fields
# ---------------------------------------------------------------------------


def test_backfill_recovers_null_storage_path_from_wire_payload(tmp_path: Path) -> None:
    artifact = _make_zarr_store(tmp_path, "wf", "load", "a", b"y" * 128)
    store = LineageStore(str(tmp_path / "lineage.db"))
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-1",
            type_name="Image",
            wire_payload={"metadata": {"backend": "zarr", "path": str(artifact)}},
            created_at="2026-06-10T00:00:00",
        )
    )
    assert store.get_data_object("obj-1")["storage_path"] is None

    assert store.backfill_storage_fields() == 1

    row = store.get_data_object("obj-1")
    assert row["storage_path"] == str(artifact)
    assert row["backend"] == "zarr"
    assert row["size_bytes"] == artifact_size_bytes(str(artifact))
    # Idempotent: a second pass finds nothing left to repair.
    assert store.backfill_storage_fields() == 0
    store.close()


# ---------------------------------------------------------------------------
# plan_retention
# ---------------------------------------------------------------------------


def test_plan_keeps_latest_successful_run_and_reclaims_the_rest(tmp_path: Path) -> None:
    old = _make_zarr_store(tmp_path, "wf", "load", "old", b"o" * 2048)
    newer = _make_zarr_store(tmp_path, "wf", "load", "new", b"n" * 1024)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-old",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-old": old},
    )
    _seed_run(
        store,
        run_id="run-new",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-new": newer},
    )
    _age_all(old, newer)

    plan = plan_retention(store, tmp_path)

    assert plan.retained_runs == {"wf": "run-new"}
    assert [c.path for c in plan.candidates] == [old]
    assert plan.total_bytes == artifact_size_bytes(str(old))
    store.close()


def test_plan_ignores_a_later_failed_run(tmp_path: Path) -> None:
    """A failed run must not make the last good run's artifacts reclaimable."""
    good = _make_zarr_store(tmp_path, "wf", "load", "good", b"g" * 512)
    broken = _make_zarr_store(tmp_path, "wf", "load", "broken", b"b" * 512)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-good",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-good": good},
    )
    _seed_run(
        store,
        run_id="run-broken",
        workflow_id="wf",
        status="failed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-broken": broken},
    )
    _age_all(good, broken)

    plan = plan_retention(store, tmp_path)

    assert plan.retained_runs == {"wf": "run-good"}
    assert [c.path for c in plan.candidates] == [broken]
    store.close()


def test_plan_reclaims_upstream_artifacts_a_partial_rerun_inherited(tmp_path: Path) -> None:
    """Liveness is "produced by", not "referenced by" (owner directive).

    A partial re-run produces only its downstream nodes, so the upstream
    artifacts it consumed are reclaimed and the workflow needs a full re-run.
    """
    upstream = _make_zarr_store(tmp_path, "wf", "load", "upstream", b"u" * 256)
    downstream = _make_zarr_store(tmp_path, "wf", "proj", "downstream", b"d" * 256)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-full",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-upstream": upstream},
    )
    _seed_run(
        store,
        run_id="run-partial",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-downstream": downstream},
    )
    # The partial run consumed the upstream artifact as an input.
    store.insert_block_io(
        BlockIORow(
            block_execution_id="be-run-partial",
            direction="input",
            port_name="in",
            object_id="obj-upstream",
            position=0,
        )
    )
    _age_all(upstream, downstream)

    plan = plan_retention(store, tmp_path)

    assert [c.path for c in plan.candidates] == [upstream]
    store.close()


def test_plan_keeps_an_unrecorded_artifact_written_during_the_retained_run(tmp_path: Path) -> None:
    """A sweep racing lineage recording must cost disk space, not data.

    Artifacts are recorded from an asynchronous event handler, so a sweep fired
    right after a run can observe a partially-recorded output set. Anything
    written since the retained run began is kept regardless.
    """
    old = _make_zarr_store(tmp_path, "wf", "load", "old", b"o" * 512)
    recorded = _make_zarr_store(tmp_path, "wf", "load", "recorded", b"r" * 512)
    unrecorded = _make_zarr_store(tmp_path, "wf", "proj", "unrecorded", b"u" * 512)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-old",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-old": old},
    )
    _seed_run(
        store,
        run_id="run-new",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-recorded": recorded},
    )
    _age_all(old, recorded)
    # `unrecorded` keeps its just-written mtime: produced by the retained run
    # but not yet flushed to data_objects when the sweep fires.

    plan = plan_retention(store, tmp_path)

    assert [c.path for c in plan.candidates] == [old]
    assert unrecorded.exists()
    store.close()


def test_plan_protects_a_workflow_whose_recorded_paths_are_all_absent(tmp_path: Path) -> None:
    """A copied/moved project records paths that no longer resolve."""
    present = _make_zarr_store(tmp_path, "wf", "load", "present", b"p" * 512)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-1",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-elsewhere": tmp_path / "old-location" / "data" / "zarr" / "wf" / "load" / "gone.zarr"},
    )
    _age_all(present)

    plan = plan_retention(store, tmp_path)

    assert "wf" in plan.protected_workflows
    assert plan.candidates == ()
    assert present.exists()
    store.close()


def test_plan_blocks_while_a_run_is_executing(tmp_path: Path) -> None:
    _make_zarr_store(tmp_path, "wf", "load", "a", b"a" * 64)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-1",
        workflow_id="wf",
        status="running",
        started_at="2026-06-10T00:00:00",
        artifacts={},
    )

    plan = plan_retention(store, tmp_path)

    assert plan.is_blocked
    assert plan.candidates == ()
    store.close()


def test_plan_blocks_on_an_empty_lineage_database(tmp_path: Path) -> None:
    _make_zarr_store(tmp_path, "wf", "load", "a", b"a" * 64)
    store = LineageStore(str(tmp_path / "lineage.db"))

    plan = plan_retention(store, tmp_path)

    assert plan.is_blocked
    assert plan.candidates == ()
    store.close()


def test_plan_protects_a_workflow_whose_retained_run_recorded_no_paths(tmp_path: Path) -> None:
    """Incomplete lineage must not be read as "everything is reclaimable"."""
    orphan = _make_zarr_store(tmp_path, "wf", "load", "orphan", b"o" * 64)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-1",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={},
    )
    _age_all(orphan)

    plan = plan_retention(store, tmp_path)

    assert "wf" in plan.protected_workflows
    assert plan.candidates == ()
    assert orphan.exists()
    store.close()


def test_plan_protects_a_workflow_with_no_successful_run(tmp_path: Path) -> None:
    kept = _make_zarr_store(tmp_path, "other", "load", "kept", b"k" * 64)
    reclaimable = _make_zarr_store(tmp_path, "wf", "load", "old", b"o" * 64)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-wf-old",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-old": reclaimable},
    )
    _seed_run(
        store,
        run_id="run-wf-new",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-new": _make_zarr_store(tmp_path, "wf", "load", "new", b"n" * 64)},
    )
    _seed_run(
        store,
        run_id="run-other",
        workflow_id="other",
        status="failed",
        started_at="2026-06-11T00:00:00",
        artifacts={},
    )
    _age_all(kept, reclaimable, *(tmp_path / "data" / "zarr" / "wf" / "load").iterdir())

    plan = plan_retention(store, tmp_path)

    assert "other" in plan.protected_workflows
    assert [c.path for c in plan.candidates] == [reclaimable]
    assert kept.exists()
    store.close()


# ---------------------------------------------------------------------------
# apply_retention
# ---------------------------------------------------------------------------


def test_apply_removes_exactly_the_planned_artifacts(tmp_path: Path) -> None:
    old = _make_zarr_store(tmp_path, "wf", "load", "old", b"o" * 2048)
    newer = _make_zarr_store(tmp_path, "wf", "load", "new", b"n" * 1024)
    store = LineageStore(str(tmp_path / "lineage.db"))
    _seed_run(
        store,
        run_id="run-old",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-10T00:00:00",
        artifacts={"obj-old": old},
    )
    _seed_run(
        store,
        run_id="run-new",
        workflow_id="wf",
        status="completed",
        started_at="2026-06-11T00:00:00",
        artifacts={"obj-new": newer},
    )
    _age_all(old, newer)
    old_size = artifact_size_bytes(str(old))
    plan = plan_retention(store, tmp_path)

    removed, freed = apply_retention(plan)

    assert removed == 1
    assert freed == old_size
    assert not old.exists()
    assert newer.exists()
    store.close()


def test_apply_on_a_blocked_plan_removes_nothing(tmp_path: Path) -> None:
    artifact = _make_zarr_store(tmp_path, "wf", "load", "a", b"a" * 64)
    store = LineageStore(str(tmp_path / "lineage.db"))

    removed, freed = apply_retention(plan_retention(store, tmp_path))

    assert (removed, freed) == (0, 0)
    assert artifact.exists()
    store.close()
