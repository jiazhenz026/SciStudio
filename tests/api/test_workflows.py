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
# #718 part (a): workflow versioning + If-Match + workflow.changed
# ---------------------------------------------------------------------------


def test_get_workflow_includes_current_revision(client: TestClient, opened_project: Path) -> None:
    """``GET /api/workflows/{id}`` must surface the in-memory revision."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-get")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200
    # Create bumps revision once.
    assert created.json()["revision"] == 1

    fetched = client.get("/api/workflows/rev-get")
    assert fetched.status_code == 200
    assert fetched.json()["revision"] == 1


def test_put_with_current_if_match_bumps_revision(client: TestClient, opened_project: Path) -> None:
    """A PUT with the current If-Match must succeed and bump the revision."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-put")
    create = client.post("/api/workflows/", json=payload).json()
    rev = create["revision"]
    assert rev == 1

    payload["description"] = "first update"
    updated = client.put("/api/workflows/rev-put", json=payload, headers={"If-Match": str(rev)})
    assert updated.status_code == 200
    body = updated.json()
    assert body["revision"] == rev + 1
    assert body["description"] == "first update"


def test_put_with_stale_if_match_returns_412_and_latest_payload(client: TestClient, opened_project: Path) -> None:
    """A stale If-Match must produce 412 with the latest workflow JSON."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-stale")
    create = client.post("/api/workflows/", json=payload).json()
    rev_initial = create["revision"]

    # First writer advances the revision.
    payload["description"] = "first writer"
    first = client.put("/api/workflows/rev-stale", json=payload, headers={"If-Match": str(rev_initial)})
    assert first.status_code == 200
    current_revision = first.json()["revision"]
    assert current_revision == rev_initial + 1

    # Second writer is still on the original revision.
    stale_payload = build_linear_workflow(opened_project, workflow_id="rev-stale")
    stale_payload["description"] = "stale writer"
    stale = client.put("/api/workflows/rev-stale", json=stale_payload, headers={"If-Match": str(rev_initial)})
    assert stale.status_code == 412
    body = stale.json()
    assert body["current_revision"] == current_revision
    # The latest payload is attached so the client can rebase.
    assert body["workflow"]["id"] == "rev-stale"
    assert body["workflow"]["description"] == "first writer"
    assert body["workflow"]["revision"] == current_revision

    # The on-disk content is the first writer's, not the stale writer's.
    yaml_text = (opened_project / "workflows" / "rev-stale.yaml").read_text(encoding="utf-8")
    assert "first writer" in yaml_text
    assert "stale writer" not in yaml_text


def test_put_without_if_match_is_accepted_for_backwards_compat(client: TestClient, opened_project: Path) -> None:
    """Legacy clients that omit If-Match must continue to work (#718)."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-nomatch")
    client.post("/api/workflows/", json=payload)

    payload["description"] = "no header"
    updated = client.put("/api/workflows/rev-nomatch", json=payload)
    assert updated.status_code == 200
    assert updated.json()["description"] == "no header"
    # Revision still bumps so other clients see the change.
    assert updated.json()["revision"] >= 2


def test_put_with_malformed_if_match_returns_400(client: TestClient, opened_project: Path) -> None:
    """A non-integer If-Match must be rejected rather than silently accepted."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-malformed")
    client.post("/api/workflows/", json=payload)
    response = client.put("/api/workflows/rev-malformed", json=payload, headers={"If-Match": "not-an-int"})
    assert response.status_code == 400


def test_two_concurrent_writers_second_is_rejected(client: TestClient, opened_project: Path) -> None:
    """Two writers race; the one carrying the older revision is rejected."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-race")
    rev0 = client.post("/api/workflows/", json=payload).json()["revision"]

    # Both writers loaded the workflow at rev0 and now PUT with that header.
    payload_a = build_linear_workflow(opened_project, workflow_id="rev-race")
    payload_a["description"] = "writer A"
    payload_b = build_linear_workflow(opened_project, workflow_id="rev-race")
    payload_b["description"] = "writer B"

    first = client.put("/api/workflows/rev-race", json=payload_a, headers={"If-Match": str(rev0)})
    assert first.status_code == 200
    second = client.put("/api/workflows/rev-race", json=payload_b, headers={"If-Match": str(rev0)})
    assert second.status_code == 412
    assert second.json()["workflow"]["description"] == "writer A"


def test_websocket_receives_workflow_changed_event_after_write(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """A successful write must emit ``workflow.changed`` to connected clients."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-ws")
    # POST happens before the WS connects — that emission is not observed.
    create = client.post("/api/workflows/", json=payload).json()
    rev = create["revision"]

    with client.websocket_connect("/ws") as websocket:
        payload["description"] = "ws-triggered"
        response = client.put("/api/workflows/rev-ws", json=payload, headers={"If-Match": str(rev)})
        assert response.status_code == 200
        new_rev = response.json()["revision"]
        message = websocket.receive_json()

    assert message["type"] == WORKFLOW_CHANGED
    assert message["data"]["workflow_id"] == "rev-ws"
    assert message["data"]["revision"] == new_rev
    assert message["data"]["changed_by"] == "api"


def test_import_path_bumps_revision_and_emits_event(
    client: TestClient, runtime: ApiRuntime, opened_project: Path, tmp_path: Path
) -> None:
    """``POST /import-path`` must bump the revision so frontend caches invalidate."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-import")
    client.post("/api/workflows/", json=payload)
    rev_before = runtime.current_revision("rev-import")

    # Write a YAML to an external location and import it back.
    external = tmp_path / "external.yaml"
    from scieasy.workflow.serializer import load_yaml, save_yaml

    definition = load_yaml(opened_project / "workflows" / "rev-import.yaml")
    definition.description = "edited externally"
    save_yaml(definition, external)

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda ev: seen.append(ev))

    response = client.post("/api/workflows/import-path", json={"path": str(external)})
    assert response.status_code == 200
    new_rev = response.json()["revision"]
    assert new_rev == rev_before + 1
    wait_for_condition(lambda: len(seen) >= 1)
    assert seen[-1].data["workflow_id"] == "rev-import"
    assert seen[-1].data["revision"] == new_rev
    assert seen[-1].data["changed_by"] == "import-path"


def test_x_changed_by_header_propagates_to_workflow_changed_event(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    """``X-Changed-By`` lets the MCP tool / agent self-identify on writes."""
    payload = build_linear_workflow(opened_project, workflow_id="rev-tag")
    rev = client.post("/api/workflows/", json=payload).json()["revision"]

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda ev: seen.append(ev))

    payload["description"] = "agent edit"
    response = client.put(
        "/api/workflows/rev-tag",
        json=payload,
        headers={"If-Match": str(rev), "X-Changed-By": "embedded-agent"},
    )
    assert response.status_code == 200
    wait_for_condition(lambda: len(seen) >= 1)
    assert seen[-1].data["changed_by"] == "embedded-agent"
