"""A workflow run is identified by its file, never by the YAML ``id:`` (#2394).

Regression tests for the stem-vs-declared-id split: copied or id-less files
lost their block lineage and "Run from here", two files declaring one id
cross-wired their runs, an expanded subworkflow tab saved over the top-level
workflow sharing its declared id, and a moved workflow kept a stale id.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import WORKFLOW_CHANGED
from tests.api.helpers import (
    build_linear_workflow,
    wait_for_block_state,
    wait_for_condition,
    wait_for_workflow_completion,
)


def _declared_id(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["workflow"].get("id")


def _finished_run(runtime: ApiRuntime, workflow_id: str) -> dict[str, Any]:
    store = runtime.lineage_store
    assert store is not None

    def _done() -> dict[str, Any] | None:
        rows = store.list_runs(workflow_id=workflow_id, limit=1)
        return rows[0] if rows and rows[0]["status"] != "running" else None

    return wait_for_condition(_done, timeout=30)


def _zarr_dirs(project: Path) -> list[str]:
    return sorted(p.relative_to(project).as_posix() for p in (project / "data" / "zarr").glob("*/*"))


def _labels(runtime: ApiRuntime, run_id: str) -> dict[str, Any]:
    store = runtime.lineage_store
    assert store is not None
    return {
        row["block_id"]: json.loads(row["block_config_resolved"]).get("params", {}).get("label")
        for row in store.list_block_executions(run_id)
    }


def _run_and_rerun_from_final(client: TestClient, runtime: ApiRuntime, workflow_id: str) -> dict[str, Any]:
    assert client.post(f"/api/workflows/{workflow_id}/execute").status_code == 200
    wait_for_workflow_completion(runtime, workflow_id, timeout=30)
    run = _finished_run(runtime, workflow_id)
    assert run["status"] == "completed"

    rerun = client.post(f"/api/workflows/{workflow_id}/execute-from", json={"block_id": "final"})
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["reused_blocks"] == ["load", "transform"]
    handle = wait_for_workflow_completion(runtime, workflow_id, timeout=30)
    assert handle.scheduler.block_states()["final"] == BlockState.DONE
    return run


def test_correctly_named_workflow_keeps_its_identity(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """Backward compatibility: ``workflows/<id>.yaml`` declaring ``<id>`` runs exactly as before."""
    assert client.post("/api/workflows/", json=build_linear_workflow(opened_project, workflow_id="main")).status_code
    run = _run_and_rerun_from_final(client, runtime, "main")

    assert run["workflow_id"] == "main"
    assert len(runtime.lineage_store.list_block_executions(run["run_id"])) == 3
    assert _zarr_dirs(opened_project) == ["data/zarr/main/final", "data/zarr/main/load", "data/zarr/main/transform"]
    assert (opened_project / ".scistudio" / "pause" / "main" / "checkpoint_main.json").is_file()
    assert client.get("/api/workflows/main").json()["id"] == "main"


def test_copied_workflow_runs_under_its_file_name(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """A Finder-style copy keeps the original's ``id:`` but runs, records and resumes as the copy."""
    assert client.post("/api/workflows/", json=build_linear_workflow(opened_project, workflow_id="orig")).status_code
    copy_path = opened_project / "workflows" / "orig_copy.yaml"
    shutil.copy(opened_project / "workflows" / "orig.yaml", copy_path)

    run = _run_and_rerun_from_final(client, runtime, "orig_copy")

    assert run["workflow_id"] == "orig_copy"
    assert len(runtime.lineage_store.list_block_executions(run["run_id"])) == 3
    assert all(path.startswith("data/zarr/orig_copy/") for path in _zarr_dirs(opened_project))
    # Running never rewrites the file on disk.
    assert _declared_id(copy_path) == "orig"
    # The editor is handed the file identity, so its autosave targets the copy.
    assert client.get("/api/workflows/orig_copy").json()["id"] == "orig_copy"


def test_workflow_without_an_id_runs_under_its_file_name(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """An id-less file records lineage and writes outputs under its stem, not ``adhoc``."""
    assert client.post("/api/workflows/", json=build_linear_workflow(opened_project, workflow_id="noid")).status_code
    path = opened_project / "workflows" / "noid.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["workflow"].pop("id")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    run = _run_and_rerun_from_final(client, runtime, "noid")

    assert len(runtime.lineage_store.list_block_executions(run["run_id"])) == 3
    assert all(p.startswith("data/zarr/noid/") for p in _zarr_dirs(opened_project))
    assert not (opened_project / "data" / "zarr" / "adhoc").exists()


def test_two_files_declaring_one_id_run_concurrently_without_cross_talk(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """Each run keeps its own block states, process handles and lineage, and cancels alone."""
    payload = build_linear_workflow(opened_project, workflow_id="orig", middle_sleep_seconds=2.0)
    assert client.post("/api/workflows/", json=payload).status_code == 200
    text = (opened_project / "workflows" / "orig.yaml").read_text(encoding="utf-8")
    copy_text = text.replace("label: middle", "label: COPY-middle").replace("label: final", "label: COPY-final")
    assert copy_text != text
    (opened_project / "workflows" / "orig_copy.yaml").write_text(copy_text, encoding="utf-8")

    assert client.post("/api/workflows/orig/execute").status_code == 200
    assert client.post("/api/workflows/orig_copy/execute").status_code == 200
    wait_for_block_state(runtime, "orig", "transform", "running", timeout=15)
    wait_for_block_state(runtime, "orig_copy", "transform", "running", timeout=15)
    assert set(runtime.workflow_runs) >= {"orig", "orig_copy"}
    wait_for_condition(
        lambda: (
            runtime.process_registry.get_handle("orig", "transform") is not None
            and runtime.process_registry.get_handle("orig_copy", "transform") is not None
        ),
        timeout=15,
    )

    cancelled = client.post("/api/workflows/orig_copy/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert "transform" in cancelled.json()["cancelled_blocks"]
    copy_run = wait_for_workflow_completion(runtime, "orig_copy", timeout=30)
    assert copy_run.scheduler.block_states()["final"] == BlockState.SKIPPED

    orig_run = wait_for_workflow_completion(runtime, "orig", timeout=30)
    assert orig_run.scheduler.block_states() == {
        "load": BlockState.DONE,
        "transform": BlockState.DONE,
        "final": BlockState.DONE,
    }

    orig_row = _finished_run(runtime, "orig")
    copy_row = _finished_run(runtime, "orig_copy")
    assert orig_row["status"] == "completed"
    assert copy_row["status"] == "cancelled"
    assert _labels(runtime, orig_row["run_id"]) == {"load": None, "transform": "middle", "final": "final"}
    copy_labels = _labels(runtime, copy_row["run_id"])
    assert "middle" not in copy_labels.values()
    assert copy_labels.get("transform") == "COPY-middle"


def _write_subworkflow_declaring_main(project: Path) -> Path:
    path = project / "subworkflows" / "imported.yaml"
    path.parent.mkdir(exist_ok=True)
    payload = build_linear_workflow(project, workflow_id="main")
    body = {"workflow": {**payload, "description": "SUB copy"}}
    path.write_text("# imported subworkflow\n" + yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return path


def test_expanded_subworkflow_tab_saves_and_runs_its_own_file(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """A subworkflow declaring ``id: main`` is saved and run by path, never as ``workflows/main.yaml``."""
    parent = build_linear_workflow(opened_project, workflow_id="main")
    parent["description"] = "PARENT"
    assert client.post("/api/workflows/", json=parent).status_code == 200
    sub_path = _write_subworkflow_declaring_main(opened_project)
    top_before = (opened_project / "workflows" / "main.yaml").read_text(encoding="utf-8")

    opened = client.get("/api/workflows/by-path", params={"path": "subworkflows/imported.yaml"})
    assert opened.status_code == 200, opened.text
    identity = opened.json()["id"]
    assert identity == "@subworkflows@imported.yaml"

    edited = {key: opened.json()[key] for key in ("id", "version", "nodes", "edges", "metadata")}
    edited["description"] = "SUB edited in expanded tab"
    saved = client.put(f"/api/workflows/{identity}", json=edited)
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == identity

    assert (opened_project / "workflows" / "main.yaml").read_text(encoding="utf-8") == top_before
    sub_document = yaml.safe_load(sub_path.read_text(encoding="utf-8"))["workflow"]
    assert sub_document["description"] == "SUB edited in expanded tab"
    # The subworkflow keeps the id it declares; its file name is what identifies it.
    assert sub_document["id"] == "main"

    assert client.post(f"/api/workflows/{identity}/execute").json()["workflow_id"] == identity
    wait_for_workflow_completion(runtime, identity, timeout=30)
    run = _finished_run(runtime, identity)
    assert run["status"] == "completed"
    assert len(runtime.lineage_store.list_block_executions(run["run_id"])) == 3
    assert runtime.lineage_store.list_runs(workflow_id="main") == []
    assert all(p.startswith(f"data/zarr/{identity}/") for p in _zarr_dirs(opened_project))


def test_path_identity_cannot_escape_the_project_or_create_files(client: TestClient, opened_project: Path) -> None:
    """The path form only addresses existing workflow files inside the project."""
    missing = client.put(
        "/api/workflows/@subworkflows@missing.yaml",
        json={"id": "@subworkflows@missing.yaml", "nodes": [], "edges": []},
    )
    assert missing.status_code == 404, missing.text
    assert not (opened_project / "subworkflows" / "missing.yaml").exists()
    assert client.post("/api/workflows/@subworkflows@missing.yaml/execute").status_code == 404


def test_moving_a_workflow_rewrites_its_declared_id(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """Rename or move of a workflow file sets ``workflow.id`` to the new name, keeping comments."""
    assert client.post("/api/workflows/", json=build_linear_workflow(opened_project, workflow_id="draft")).status_code
    source = opened_project / "workflows" / "draft.yaml"
    source.write_text("# my analysis\n" + source.read_text(encoding="utf-8"), encoding="utf-8")

    events: list[dict[str, Any]] = []

    async def _capture(event: Any) -> None:
        events.append(dict(event.data))

    runtime.event_bus.subscribe(WORKFLOW_CHANGED, _capture)
    try:
        result = asyncio.run(runtime.project_files.move(source, opened_project / "workflows" / "final_analysis.yaml"))
        assert result["status"] == "ok", result
        moved_sub = asyncio.run(
            runtime.project_files.move(
                opened_project / "workflows" / "final_analysis.yaml",
                opened_project / "subworkflows" / "qc.swf.yaml",
                create_parents=True,
            )
        )
        assert moved_sub["status"] == "ok", moved_sub
    finally:
        runtime.event_bus.unsubscribe(WORKFLOW_CHANGED, _capture)

    target = opened_project / "subworkflows" / "qc.swf.yaml"
    assert _declared_id(target) == "qc"
    assert target.read_text(encoding="utf-8").startswith("# my analysis\n")
    changes = [(event["workflow_id"], event["kind"]) for event in events]
    assert ("draft", "deleted") in changes
    assert ("final_analysis", "created") in changes
    assert ("final_analysis", "deleted") in changes
    assert ("@subworkflows@qc.swf.yaml", "created") in changes


def test_moved_workflow_is_renamed_on_disk_before_it_runs(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """After a rename the file declares its new name, so a save of the new tab never collides."""
    assert client.post("/api/workflows/", json=build_linear_workflow(opened_project, workflow_id="old")).status_code
    result = asyncio.run(
        runtime.project_files.move(
            opened_project / "workflows" / "old.yaml", opened_project / "workflows" / "renamed.yaml"
        )
    )
    assert result["status"] == "ok", result
    assert _declared_id(opened_project / "workflows" / "renamed.yaml") == "renamed"
    fetched = client.get("/api/workflows/renamed").json()
    assert client.put("/api/workflows/renamed", json=fetched).status_code == 200
    assert not (opened_project / "workflows" / "old.yaml").exists()
