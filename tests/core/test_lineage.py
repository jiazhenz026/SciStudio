"""Tests for the ADR-038 unified 4-table lineage subsystem.

Pre-ADR-038 this file exercised the single-table hash-keyed lineage store and
the ``ProvenanceGraph`` helper. ADR-038 §3.4 explicitly removes content
hashing; the graph helper is deleted and the store is rewritten with four
tables (``runs``, ``block_executions``, ``data_objects``, ``block_io``). The
tests below cover the new schema's read/write round-trip; the recorder side
of the contract is exercised in ``tests/engine/test_lineage_recorder.py``
and the end-to-end scheduler smoke test lives at
``tests/core/test_lineage_store_4table.py``.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.core.lineage.environment import EnvironmentSnapshot
from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)
from scistudio.core.lineage.store import LineageStore


def _make_run(run_id: str = "run-1", workflow_id: str = "wf") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_yaml_snapshot="id: wf\nnodes: []\n",
        started_at="2026-05-15T00:00:00",
        status="running",
        environment_snapshot={"python_version": "3.13.0"},
    )


def _make_block_execution(
    *,
    block_execution_id: str,
    run_id: str = "run-1",
    block_id: str = "A",
    block_type: str = "LoadData",
    block_version: str = "0.1.0-dev",
) -> BlockExecutionRecord:
    return BlockExecutionRecord(
        block_execution_id=block_execution_id,
        run_id=run_id,
        block_id=block_id,
        block_type=block_type,
        block_version=block_version,
        block_config_resolved={"path": "/tmp/x"},
        started_at="2026-05-15T00:00:01",
        finished_at="2026-05-15T00:00:02",
        duration_ms=1000,
        termination="completed",
    )


class TestEnvironmentSnapshot:
    """Verify EnvironmentSnapshot.capture()."""

    def test_capture_basic(self) -> None:
        snap = EnvironmentSnapshot.capture(full=False)
        assert "3." in snap.python_version
        assert snap.platform != ""
        assert isinstance(snap.key_packages, dict)

    def test_capture_custom_deps(self) -> None:
        snap = EnvironmentSnapshot.capture(key_dependencies=["pydantic"], full=False)
        # pydantic is a hard dep so it should resolve.
        assert "pydantic" in snap.key_packages

    def test_capture_missing_package_skipped(self) -> None:
        snap = EnvironmentSnapshot.capture(key_dependencies=["nonexistent_pkg_12345"], full=False)
        assert "nonexistent_pkg_12345" not in snap.key_packages

    def test_capture_full_attempts_freeze(self) -> None:
        """``full=True`` makes a best-effort pip-freeze; result may be None on weird envs."""
        snap = EnvironmentSnapshot.capture(full=True)
        # full_freeze can be None if neither uv nor pip is available; we only
        # assert the field exists in the right shape.
        assert snap.full_freeze is None or isinstance(snap.full_freeze, str)


class TestEnvironmentSnapshotSerialization:
    def test_to_dict_round_trip(self) -> None:
        snapshot = EnvironmentSnapshot.capture(full=False)
        data = snapshot.to_dict()
        restored = EnvironmentSnapshot.from_dict(data)
        assert restored == snapshot

    def test_to_dict_is_json_serializable(self) -> None:
        import json

        snapshot = EnvironmentSnapshot.capture(full=False)
        json.dumps(snapshot.to_dict())

    def test_from_dict_handles_missing_optional_fields(self) -> None:
        data = {"python_version": "3.11.0", "platform": "Linux"}
        snapshot = EnvironmentSnapshot.from_dict(data)
        assert snapshot.python_version == "3.11.0"
        assert snapshot.platform == "Linux"
        assert snapshot.key_packages == {}
        assert snapshot.full_freeze is None
        assert snapshot.conda_env is None


class TestLineageStoreRuns:
    def test_insert_and_get(self) -> None:
        store = LineageStore(":memory:")
        store.insert_run(_make_run())
        run = store.get_run("run-1")
        assert run is not None
        assert run["workflow_id"] == "wf"
        assert run["status"] == "running"
        store.close()

    def test_finalize_updates_status(self) -> None:
        store = LineageStore(":memory:")
        store.insert_run(_make_run())
        store.finalize_run("run-1", finished_at="2026-05-15T00:01:00", status="completed")
        run = store.get_run("run-1")
        assert run is not None
        assert run["status"] == "completed"
        assert run["finished_at"] == "2026-05-15T00:01:00"

    def test_list_runs_reverse_chrono(self) -> None:
        store = LineageStore(":memory:")
        for i, ts in enumerate(["2026-05-15T00:00:00", "2026-05-15T00:00:01", "2026-05-15T00:00:02"]):
            run = _make_run(run_id=f"run-{i}", workflow_id="wf")
            run.started_at = ts
            store.insert_run(run)
        rows = store.list_runs(workflow_id="wf")
        assert [r["run_id"] for r in rows] == ["run-2", "run-1", "run-0"]


class TestLineageStoreBlockExecutions:
    def test_insert_and_list(self) -> None:
        store = LineageStore(":memory:")
        store.insert_run(_make_run())
        store.insert_block_execution(_make_block_execution(block_execution_id="be-1"))
        store.insert_block_execution(_make_block_execution(block_execution_id="be-2", block_id="B"))
        rows = store.list_block_executions("run-1")
        assert len(rows) == 2
        assert {r["block_id"] for r in rows} == {"A", "B"}


class TestLineageStoreDataObjectsAndIO:
    def test_data_object_upsert_is_idempotent(self) -> None:
        store = LineageStore(":memory:")
        store.insert_run(_make_run())
        store.insert_block_execution(_make_block_execution(block_execution_id="be-1"))

        row = DataObjectRow(
            object_id="obj-1",
            type_name="DataFrame",
            wire_payload={"backend": "arrow", "path": "/tmp/x.parquet"},
            created_at="2026-05-15T00:00:01",
            produced_by_execution="be-1",
        )
        store.upsert_data_object(row)
        # Second upsert with the same object_id must be a no-op.
        store.upsert_data_object(row)
        assert store.count("data_objects") == 1

    def test_block_io_round_trip(self) -> None:
        store = LineageStore(":memory:")
        store.insert_run(_make_run())
        store.insert_block_execution(_make_block_execution(block_execution_id="be-1"))
        store.upsert_data_object(
            DataObjectRow(
                object_id="obj-1",
                type_name="DataFrame",
                wire_payload={},
                created_at="2026-05-15T00:00:01",
            )
        )
        store.insert_block_io(
            BlockIORow(
                block_execution_id="be-1",
                direction="output",
                port_name="result",
                object_id="obj-1",
                position=0,
            )
        )
        edges = store.list_block_io("be-1")
        assert len(edges) == 1
        assert edges[0]["object_id"] == "obj-1"


class TestLineageStorePersistence:
    def test_default_path_persists(self, tmp_path: Path, monkeypatch) -> None:
        """``LineageStore()`` with no path defaults to ``.scistudio/lineage.db`` under cwd."""
        monkeypatch.chdir(tmp_path)
        store = LineageStore()
        store.insert_run(_make_run())
        store.close()

        store2 = LineageStore()
        run = store2.get_run("run-1")
        assert run is not None
        assert run["workflow_id"] == "wf"
        store2.close()
        # File on disk lives under .scistudio/.
        assert (tmp_path / ".scistudio" / "lineage.db").exists()
