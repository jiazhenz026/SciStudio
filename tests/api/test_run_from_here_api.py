"""#2448: "Run from here" through the API.

A target with no upstream runs without an earlier run; otherwise every upstream
output the target and its descendants need must exist, still resolve to data,
and come from an unchanged definition, or the request is refused with one entry
per upstream block. Deleting or moving a workflow drops its pause checkpoint.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.blocks.base.state import BlockState
from tests.api.helpers import build_linear_workflow, wait_for_condition, wait_for_workflow_completion


def _finished_runs(runtime: ApiRuntime, workflow_id: str, count: int) -> list[dict[str, Any]]:
    store = runtime.lineage_store
    assert store is not None

    def _done() -> list[dict[str, Any]] | None:
        rows = store.list_runs(workflow_id=workflow_id, limit=10)
        if len(rows) >= count and all(row["status"] != "running" for row in rows):
            return rows
        return None

    return wait_for_condition(_done, timeout=30)


def _create_and_run(client: TestClient, runtime: ApiRuntime, project: Path, workflow_id: str) -> dict[str, Any]:
    payload = build_linear_workflow(project, workflow_id=workflow_id)
    assert client.post("/api/workflows/", json=payload).status_code == 200
    assert client.post(f"/api/workflows/{workflow_id}/execute").status_code == 200
    wait_for_workflow_completion(runtime, workflow_id, timeout=30)
    _finished_runs(runtime, workflow_id, 1)
    return payload


def _unmet(response: Any) -> dict[str, str]:
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "run_from_here_unmet"
    assert detail["message"].startswith("Cannot run from ")
    return {item["node_id"]: item["reason"] for item in detail["unmet"]}


def _stored_paths(value: Any) -> list[str]:
    if isinstance(value, dict):
        if "backend" in value and isinstance(value.get("path"), str):
            return [value["path"]]
        return [path for item in value.values() for path in _stored_paths(item)]
    if isinstance(value, list):
        return [path for item in value for path in _stored_paths(item)]
    return []


def _checkpoint_file(project: Path, workflow_id: str) -> Path:
    return project / ".scistudio" / "pause" / workflow_id / f"checkpoint_{workflow_id}.json"


def test_deleted_and_recreated_workflow_does_not_reuse_old_outputs(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """The 2026-09-15 audit repro: a new workflow under a deleted one's name."""
    _create_and_run(client, runtime, opened_project, "analysis")
    assert _checkpoint_file(opened_project, "analysis").exists()
    old_run_id = runtime.workflow_runs["analysis"].run_id

    assert client.delete("/api/workflows/analysis").status_code == 204
    assert not (opened_project / ".scistudio" / "pause" / "analysis").exists()

    fresh = build_linear_workflow(opened_project, workflow_id="analysis")
    new_csv = opened_project / "data" / "raw" / "brand_new.csv"
    new_csv.write_text("a,b\n100,200\n", encoding="utf-8")
    fresh["nodes"][0]["config"]["params"]["path"] = str(new_csv)
    assert client.post("/api/workflows/", json=fresh).status_code == 200

    response = client.post("/api/workflows/analysis/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "never_ran"}
    # Refused before anything recorded a run.
    assert runtime.workflow_runs["analysis"].run_id == old_run_id
    assert runtime.lineage_store is not None
    assert len(runtime.lineage_store.list_runs(workflow_id="analysis")) == 1


def test_recreated_workflow_with_a_surviving_checkpoint_is_refused_as_changed(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """Even if the old checkpoint survives (deleted outside the app), the new definition does not match."""
    _create_and_run(client, runtime, opened_project, "analysis")
    pause_dir = opened_project / ".scistudio" / "pause" / "analysis"
    kept = opened_project / "kept-pause"
    shutil.copytree(pause_dir, kept)

    assert client.delete("/api/workflows/analysis").status_code == 204
    shutil.copytree(kept, pause_dir)

    fresh = build_linear_workflow(opened_project, workflow_id="analysis")
    new_csv = opened_project / "data" / "raw" / "brand_new.csv"
    new_csv.write_text("a,b\n100,200\n", encoding="utf-8")
    fresh["nodes"][0]["config"]["params"]["path"] = str(new_csv)
    assert client.post("/api/workflows/", json=fresh).status_code == 200

    response = client.post("/api/workflows/analysis/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "definition_changed"}
    assert "load" in response.json()["detail"]["unmet"][0]["detail"]


def test_target_without_upstream_runs_before_any_full_run(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="fresh")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    response = client.post("/api/workflows/fresh/execute-from", json={"block_id": "load"})
    assert response.status_code == 200, response.text
    assert response.json()["reused_blocks"] == []
    handle = wait_for_workflow_completion(runtime, "fresh", timeout=30)
    assert handle.scheduler.block_states() == {
        "load": BlockState.DONE,
        "transform": BlockState.DONE,
        "final": BlockState.DONE,
    }
    run = _finished_runs(runtime, "fresh", 1)[0]
    assert run["parent_run_id"] is None


def test_target_with_upstream_is_refused_before_any_run(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="fresh")
    assert client.post("/api/workflows/", json=payload).status_code == 200
    response = client.post("/api/workflows/fresh/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "never_ran"}


def test_edited_upstream_block_is_refused_and_unedited_prefix_is_reused(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    payload = _create_and_run(client, runtime, opened_project, "edited")

    payload["nodes"][1]["config"]["params"]["label"] = "changed"
    assert client.put("/api/workflows/edited", json=payload).status_code == 200

    response = client.post("/api/workflows/edited/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "definition_changed"}

    # Running from the edited block itself only needs the unchanged loader.
    allowed = client.post("/api/workflows/edited/execute-from", json={"block_id": "transform"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["reused_blocks"] == ["load"]
    wait_for_workflow_completion(runtime, "edited", timeout=30)
    rows = _finished_runs(runtime, "edited", 2)
    assert rows[0]["parent_run_id"] == rows[1]["run_id"]

    # After that run the downstream block can be run from here again.
    again = client.post("/api/workflows/edited/execute-from", json={"block_id": "final"})
    assert again.status_code == 200, again.text
    wait_for_workflow_completion(runtime, "edited", timeout=30)


def test_missing_output_data_is_refused(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    _create_and_run(client, runtime, opened_project, "gone")
    checkpoint = json.loads(_checkpoint_file(opened_project, "gone").read_text(encoding="utf-8"))
    transform_paths = sorted({Path(path) for path in _stored_paths(checkpoint["intermediate_refs"]["transform"])})
    assert transform_paths
    for path in transform_paths:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    response = client.post("/api/workflows/gone/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "output_missing"}


def test_checkpoint_without_fingerprints_is_refused_as_unknown(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    _create_and_run(client, runtime, opened_project, "legacy")
    path = _checkpoint_file(opened_project, "legacy")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("node_fingerprints")
    raw["version"] = 1
    path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.post("/api/workflows/legacy/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "definition_unknown"}


def test_file_delete_and_move_drop_the_pause_checkpoint(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    _create_and_run(client, runtime, opened_project, "moved")
    _create_and_run(client, runtime, opened_project, "removed")
    assert (opened_project / ".scistudio" / "pause" / "moved").is_dir()
    assert (opened_project / ".scistudio" / "pause" / "removed").is_dir()

    moved = asyncio.run(
        runtime.project_files.move(
            opened_project / "workflows" / "moved.yaml", opened_project / "workflows" / "renamed.yaml"
        )
    )
    assert moved["status"] == "ok", moved
    assert not (opened_project / ".scistudio" / "pause" / "moved").exists()
    response = client.post("/api/workflows/renamed/execute-from", json={"block_id": "final"})
    assert _unmet(response) == {"transform": "never_ran"}

    removed = asyncio.run(runtime.project_files.delete(opened_project / "workflows" / "removed.yaml"))
    assert removed["status"] == "ok", removed
    assert not (opened_project / ".scistudio" / "pause" / "removed").exists()
