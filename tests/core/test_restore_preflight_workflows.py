"""Restore preflight across every workflow recorded at a commit (#2425).

A project commit snapshots every workflow file, so the preflight must check
the newest run of each workflow at that commit rather than only the newest run
overall, and must refuse a ``run_id`` recorded at a different commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.core.lineage.record import BlockExecutionRecord, BlockIORow, DataObjectRow, RunRecord
from scistudio.core.lineage.restore_preflight import RestoreRunMismatchError, evaluate_restore_target
from scistudio.core.lineage.store import LineageStore

COMMIT = "c0ffee" + "0" * 34
OTHER_COMMIT = "deadbeef" + "0" * 32


@pytest.fixture()
def store(tmp_path: Path) -> LineageStore:
    return LineageStore(str(tmp_path / "lineage.db"))


def _add_run(
    store: LineageStore,
    run_id: str,
    workflow_id: str,
    started_at: str,
    *,
    commit: str | None = COMMIT,
    input_path: Path | None = None,
    environment: dict | None = None,
) -> None:
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot="",
            started_at=started_at,
            status="completed",
            environment_snapshot=environment if environment is not None else {},
            workflow_git_commit=commit,
        )
    )
    if input_path is None:
        return
    be = f"be-{run_id}"
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id=be,
            run_id=run_id,
            block_id="loader",
            block_type="proc",
            block_version="1",
            block_config_resolved={},
            started_at=started_at,
            finished_at=started_at,
            duration_ms=0,
            termination="completed",
        )
    )
    object_id = f"in-{run_id}"
    store.upsert_data_object(
        DataObjectRow(
            object_id=object_id,
            type_name="DataFrame",
            wire_payload={},
            created_at=started_at,
            storage_path=str(input_path),
        )
    )
    store.insert_block_io(
        BlockIORow(block_execution_id=be, direction="input", port_name="in", object_id=object_id, position=0)
    )


def test_store_returns_newest_run_of_each_workflow(store: LineageStore) -> None:
    _add_run(store, "a-old", "wf_a", "2026-09-15T09:00:00")
    _add_run(store, "a-new", "wf_a", "2026-09-15T10:00:00")
    _add_run(store, "b-new", "wf_b", "2026-09-15T11:00:00")
    _add_run(store, "c-elsewhere", "wf_c", "2026-09-15T12:00:00", commit=OTHER_COMMIT)

    rows = store.latest_runs_per_workflow_for_git_commit(COMMIT)

    assert [r["run_id"] for r in rows] == ["b-new", "a-new"]
    assert all("_workflow_rank" not in r for r in rows)
    assert store.latest_runs_per_workflow_for_git_commit("") == []


def test_drift_in_an_older_workflow_is_reported(store: LineageStore, tmp_path: Path) -> None:
    """The audit repro: A's input changed, but B ran at the commit after A."""
    a_input = tmp_path / "a_input.csv"
    a_input.write_text("x\n1\n")
    b_input = tmp_path / "b_input.csv"
    b_input.write_text("y\n2\n")
    _add_run(store, "runA", "wf_a", "2026-09-15T10:00:00", input_path=a_input)
    _add_run(store, "runB", "wf_b", "2026-09-15T11:00:00", input_path=b_input)
    a_input.write_text("x\n1\n2\n3\n")

    result = evaluate_restore_target(store, COMMIT)

    assert result["run_id"] == "runB", "top-level run stays the newest run at the commit"
    assert len(result["input_warnings"]) == 1
    warning = result["input_warnings"][0]
    assert warning["path"] == str(a_input)
    assert "size changed" in warning["reason"]
    assert (warning["workflow_id"], warning["run_id"]) == ("wf_a", "runA")
    by_workflow = {entry["workflow_id"]: entry for entry in result["runs"]}
    assert set(by_workflow) == {"wf_a", "wf_b"}
    assert by_workflow["wf_b"]["input_warnings"] == []
    assert len(by_workflow["wf_a"]["input_warnings"]) == 1


def test_identical_environment_drift_is_listed_once(store: LineageStore) -> None:
    env = {"key_packages": {"scistudio": "0.0.0-recorded"}}
    _add_run(store, "runA", "wf_a", "2026-09-15T10:00:00", environment=env)
    _add_run(store, "runB", "wf_b", "2026-09-15T11:00:00", environment=env)

    result = evaluate_restore_target(store, COMMIT)

    drifts = [w for w in result["env_warnings"] if w["package"] == "scistudio"]
    assert len(drifts) == 1
    assert drifts[0]["workflow_ids"] == ["wf_b", "wf_a"]
    assert drifts[0]["run_ids"] == ["runB", "runA"]


def test_run_id_from_another_commit_is_rejected(store: LineageStore) -> None:
    _add_run(store, "runA", "wf_a", "2026-09-15T10:00:00")
    _add_run(store, "runOther", "wf_a", "2026-09-15T12:00:00", commit=OTHER_COMMIT)

    with pytest.raises(RestoreRunMismatchError) as excinfo:
        evaluate_restore_target(store, COMMIT, run_id="runOther")
    assert "runOther" in str(excinfo.value)
    assert COMMIT in str(excinfo.value)


def test_run_id_without_a_commit_is_rejected(store: LineageStore) -> None:
    _add_run(store, "runA", "wf_a", "2026-09-15T10:00:00")
    _add_run(store, "unanchored", "wf_a", "2026-09-15T12:00:00", commit=None)

    with pytest.raises(RestoreRunMismatchError):
        evaluate_restore_target(store, COMMIT, run_id="unanchored")


def test_selected_run_replaces_only_its_own_workflow(store: LineageStore) -> None:
    _add_run(store, "a-picked", "wf_a", "2026-09-15T09:00:00")
    _add_run(store, "a-later", "wf_a", "2026-09-15T10:00:00")
    _add_run(store, "b-new", "wf_b", "2026-09-15T11:00:00")

    result = evaluate_restore_target(store, COMMIT, run_id="a-picked")

    assert result["run_id"] == "a-picked"
    assert [entry["run_id"] for entry in result["runs"]] == ["a-picked", "b-new"]


def test_single_workflow_shape_is_unchanged(store: LineageStore, tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n")
    _add_run(store, "only", "wf_a", "2026-09-15T10:00:00", input_path=source)

    result = evaluate_restore_target(store, COMMIT)

    assert result["commit_sha"] == COMMIT
    assert result["run_id"] == "only"
    assert result["run_started_at"] == "2026-09-15T10:00:00"
    assert result["input_warnings"] == []
    assert [entry["run_id"] for entry in result["runs"]] == ["only"]


def test_no_run_at_commit_stays_unknown(store: LineageStore) -> None:
    _add_run(store, "elsewhere", "wf_a", "2026-09-15T10:00:00", commit=OTHER_COMMIT)

    result = evaluate_restore_target(store, COMMIT)

    assert result == {
        "commit_sha": COMMIT,
        "run_id": None,
        "run_started_at": None,
        "input_warnings": [],
        "env_warnings": [],
        "runs": [],
    }
