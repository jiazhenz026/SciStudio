"""Tests for workflow CRUD and execution endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scieasy.api.runtime import ApiRuntime
from scieasy.blocks.base.state import BlockState
from scieasy.engine.events import WORKFLOW_CHANGED, EngineEvent
from tests.api.helpers import (
    build_linear_workflow,
    wait_for_block_state,
    wait_for_condition,
    wait_for_workflow_completion,
)


def test_workflow_crud_round_trips_yaml_layout(client: TestClient, opened_project: Path) -> None:
    """Workflow CRUD should persist YAML and round-trip layout metadata."""
    payload = build_linear_workflow(opened_project, workflow_id="crud-flow")

    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200
    assert created.json()["nodes"][0]["layout"] == {"x": 20.0, "y": 40.0}

    workflow_file = opened_project / "workflows" / "crud-flow.yaml"
    assert workflow_file.exists()
    assert "layout:" in workflow_file.read_text(encoding="utf-8")

    fetched = client.get("/api/workflows/crud-flow")
    assert fetched.status_code == 200
    assert fetched.json()["metadata"]["kind"] == "linear"

    payload["description"] = "updated description"
    payload["nodes"][1]["config"]["params"]["label"] = "updated"
    updated = client.put("/api/workflows/crud-flow", json=payload)
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated description"

    deleted = client.delete("/api/workflows/crud-flow")
    assert deleted.status_code == 204
    assert not workflow_file.exists()


def test_workflow_execute_and_execute_from_reuses_cached_outputs(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Workflow execution should produce checkpoints that enable execute-from."""
    payload = build_linear_workflow(opened_project, workflow_id="execute-flow")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    started = client.post("/api/workflows/execute-flow/execute")
    assert started.status_code == 200
    run = wait_for_workflow_completion(runtime, "execute-flow")
    assert run.scheduler.block_states() == {
        "load": BlockState.DONE,
        "transform": BlockState.DONE,
        "final": BlockState.DONE,
    }

    checkpoint = run.checkpoint_manager.load("execute-flow")
    assert checkpoint is not None
    assert checkpoint.intermediate_refs

    rerun = client.post("/api/workflows/execute-flow/execute-from", json={"block_id": "final"})
    assert rerun.status_code == 200
    assert rerun.json()["reused_blocks"] == ["load", "transform"]
    assert rerun.json()["reset_blocks"] == ["final"]
    rerun_handle = wait_for_workflow_completion(runtime, "execute-flow")
    assert rerun_handle.scheduler.block_states()["final"] == BlockState.DONE

    # Hotfix #992: the new run's `runs.parent_run_id` must point at the
    # most-recent completed run of the same workflow per ADR-038 §3.6a.
    # Pre-#992 the field was always NULL because the execute-from route
    # didn't forward `parent_run_id` into `start_workflow`.
    if runtime.lineage_store is not None:
        rows = runtime.lineage_store.list_runs(workflow_id="execute-flow", limit=5)
        # Most-recent first
        assert len(rows) >= 2, rows
        partial = rows[0]
        parent = rows[1]
        assert partial["execute_from_block_id"] == "final"
        assert partial["parent_run_id"] == parent["run_id"], (
            "parent_run_id should link the partial re-run back to the prior full run"
        )


def test_workflow_pause_and_resume_keeps_downstream_block_ready(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Pause should prevent dispatch of newly ready nodes until resume is called."""
    payload = build_linear_workflow(
        opened_project,
        workflow_id="pause-flow",
        middle_sleep_seconds=0.2,
    )
    assert client.post("/api/workflows/", json=payload).status_code == 200

    assert client.post("/api/workflows/pause-flow/execute").status_code == 200
    wait_for_block_state(runtime, "pause-flow", "transform", "running")

    paused = client.post("/api/workflows/pause-flow/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    states = wait_for_block_state(runtime, "pause-flow", "final", "ready", timeout=5.0)
    assert states["transform"] == BlockState.DONE

    resumed = client.post("/api/workflows/pause-flow/resume")
    assert resumed.status_code == 200
    run = wait_for_workflow_completion(runtime, "pause-flow")
    assert run.scheduler.block_states()["final"] == BlockState.DONE


def test_cancel_block_and_cancel_workflow_propagate_terminal_states(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Cancel controls should cancel active work and skip blocked descendants."""
    cancel_block_payload = build_linear_workflow(
        opened_project,
        workflow_id="cancel-block-flow",
        middle_sleep_seconds=0.3,
    )
    assert client.post("/api/workflows/", json=cancel_block_payload).status_code == 200
    assert client.post("/api/workflows/cancel-block-flow/execute").status_code == 200
    wait_for_block_state(runtime, "cancel-block-flow", "transform", "running")

    block_cancel = client.post("/api/workflows/cancel-block-flow/blocks/transform/cancel")
    assert block_cancel.status_code == 200
    wait_for_workflow_completion(runtime, "cancel-block-flow")
    block_states = runtime.workflow_runs["cancel-block-flow"].scheduler.block_states()
    assert block_states["transform"] == BlockState.CANCELLED
    assert block_states["final"] == BlockState.SKIPPED

    cancel_workflow_payload = build_linear_workflow(
        opened_project,
        workflow_id="cancel-workflow-flow",
        middle_sleep_seconds=0.3,
    )
    assert client.post("/api/workflows/", json=cancel_workflow_payload).status_code == 200
    assert client.post("/api/workflows/cancel-workflow-flow/execute").status_code == 200
    wait_for_block_state(runtime, "cancel-workflow-flow", "transform", "running")

    workflow_cancel = client.post("/api/workflows/cancel-workflow-flow/cancel")
    assert workflow_cancel.status_code == 200
    wait_for_workflow_completion(runtime, "cancel-workflow-flow")
    workflow_states = runtime.workflow_runs["cancel-workflow-flow"].scheduler.block_states()
    assert workflow_states["transform"] == BlockState.CANCELLED
    assert workflow_states["final"] == BlockState.SKIPPED


# ---------------------------------------------------------------------------
# workflow.changed event flow (#718 part a, post ADR-039 §5.2)
#
# The legacy ``If-Match``/``revision`` optimistic-concurrency layer was removed
# in D39-2.1; git commit SHA + working-tree dirty state replace it. The
# ``workflow.changed`` event itself still fires after every successful write
# so other browser tabs / the embedded agent's WS subscriber can invalidate
# cached views. Last-write-wins on the file save is the same model as
# VS Code and most editors.
# ---------------------------------------------------------------------------


def test_put_no_longer_requires_if_match_header(client: TestClient, opened_project: Path) -> None:
    """ADR-039 §5.2: PUT must succeed without any ``If-Match`` header."""
    payload = build_linear_workflow(opened_project, workflow_id="no-ifmatch-put")
    create = client.post("/api/workflows/", json=payload)
    assert create.status_code == 200

    payload["description"] = "updated"
    updated = client.put("/api/workflows/no-ifmatch-put", json=payload)
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated"


def test_put_ignores_if_match_header_for_legacy_clients(client: TestClient, opened_project: Path) -> None:
    """ADR-039 §5.2: a stale ``If-Match`` is no longer rejected with 412.

    Legacy frontends still wired to send the header must not be broken;
    the server simply ignores it now that git is the durable concurrency
    mechanism. Last-write-wins on the file save.
    """
    payload = build_linear_workflow(opened_project, workflow_id="ignored-ifmatch")
    client.post("/api/workflows/", json=payload)

    payload["description"] = "first"
    first = client.put("/api/workflows/ignored-ifmatch", json=payload, headers={"If-Match": "1"})
    assert first.status_code == 200
    # Second writer carries a "stale" header — must NOT receive 412.
    payload["description"] = "second"
    second = client.put("/api/workflows/ignored-ifmatch", json=payload, headers={"If-Match": "1"})
    assert second.status_code == 200
    assert second.json()["description"] == "second"


def test_response_no_longer_carries_revision_field(client: TestClient, opened_project: Path) -> None:
    """ADR-039 §5.2: WorkflowResponse must no longer expose ``revision``."""
    payload = build_linear_workflow(opened_project, workflow_id="no-revision")
    response = client.post("/api/workflows/", json=payload)
    assert response.status_code == 200
    assert "revision" not in response.json()
    fetched = client.get("/api/workflows/no-revision")
    assert "revision" not in fetched.json()


def test_websocket_receives_workflow_changed_event_after_write(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """A successful write must still emit ``workflow.changed`` to connected clients.

    The payload no longer carries ``revision`` post ADR-039 §5.2; ``workflow_id``
    and ``changed_by`` are the surviving fields the frontend keys off.
    """
    payload = build_linear_workflow(opened_project, workflow_id="changed-ws")
    # POST happens before the WS connects — that emission is not observed.
    client.post("/api/workflows/", json=payload)

    with client.websocket_connect("/ws") as websocket:
        payload["description"] = "ws-triggered"
        response = client.put("/api/workflows/changed-ws", json=payload)
        assert response.status_code == 200
        message = websocket.receive_json()

    assert message["type"] == WORKFLOW_CHANGED
    assert message["data"]["workflow_id"] == "changed-ws"
    assert message["data"]["changed_by"] == "api"
    # Field is gone, not silently zero.
    assert "revision" not in message["data"]


def test_import_path_emits_workflow_changed_event(
    client: TestClient, runtime: ApiRuntime, opened_project: Path, tmp_path: Path
) -> None:
    """``POST /import-path`` must emit ``workflow.changed`` so caches invalidate."""
    payload = build_linear_workflow(opened_project, workflow_id="changed-import")
    client.post("/api/workflows/", json=payload)

    # Write a YAML to an external location and import it back.
    external = tmp_path / "external.yaml"
    from scieasy.workflow.serializer import load_yaml, save_yaml

    definition = load_yaml(opened_project / "workflows" / "changed-import.yaml")
    definition.description = "edited externally"
    save_yaml(definition, external)

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda ev: seen.append(ev))

    response = client.post("/api/workflows/import-path", json={"path": str(external)})
    assert response.status_code == 200
    wait_for_condition(lambda: len(seen) >= 1)
    assert seen[-1].data["workflow_id"] == "changed-import"
    assert seen[-1].data["changed_by"] == "import-path"


def test_x_changed_by_header_propagates_to_workflow_changed_event(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """``X-Changed-By`` still lets the MCP tool / agent self-identify on writes."""
    payload = build_linear_workflow(opened_project, workflow_id="changed-tag")
    client.post("/api/workflows/", json=payload)

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda ev: seen.append(ev))

    payload["description"] = "agent edit"
    response = client.put(
        "/api/workflows/changed-tag",
        json=payload,
        headers={"X-Changed-By": "embedded-agent"},
    )
    assert response.status_code == 200
    wait_for_condition(lambda: len(seen) >= 1)
    assert seen[-1].data["changed_by"] == "embedded-agent"
