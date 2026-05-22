"""ADR-045 workflow state version-vector backend tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent
from tests.api.helpers import build_linear_workflow, wait_for_condition


def test_workflow_responses_return_monotonic_state_versions(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="versioned-flow")

    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    created_body = created.json()
    assert created_body["entity_class"] == "workflow"
    assert created_body["entity_id"] == "versioned-flow"
    assert created_body["version"] == "1.0.0"
    assert isinstance(created_body["state_version"], int)
    assert created_body["workflow_version"] == "1.0.0"
    assert created_body["source"] == "canvas"
    assert created_body["kind"] == "created"

    fetched = client.get("/api/workflows/versioned-flow")
    assert fetched.status_code == 200, fetched.text
    fetched_body = fetched.json()
    assert fetched_body["version"] == "1.0.0"
    assert fetched_body["state_version"] == created_body["state_version"]
    assert fetched_body["source"] is None
    assert fetched_body["kind"] == "current"

    payload["description"] = "updated once"
    updated = client.put("/api/workflows/versioned-flow", json=payload)
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["version"] == "1.0.0"
    assert updated_body["state_version"] == created_body["state_version"] + 1
    assert updated_body["kind"] == "modified"


def test_workflow_read_then_save_preserves_schema_version_string(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="read-save-flow")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["version"] == "1.0.0"
    assert isinstance(body["state_version"], int)

    body["description"] = "saved from response payload"
    saved = client.put("/api/workflows/read-save-flow", json=body)
    assert saved.status_code == 200, saved.text
    saved_body = saved.json()
    assert saved_body["version"] == "1.0.0"
    assert saved_body["state_version"] == body["state_version"] + 1


def test_workflow_versions_are_scoped_per_workflow(
    client: TestClient,
    opened_project: Path,
) -> None:
    left = build_linear_workflow(opened_project, workflow_id="left-flow")
    right = build_linear_workflow(opened_project, workflow_id="right-flow")

    left_version = client.post("/api/workflows/", json=left).json()["state_version"]
    right_version = client.post("/api/workflows/", json=right).json()["state_version"]

    left["description"] = "left changed"
    updated_left = client.put("/api/workflows/left-flow", json=left).json()
    fetched_right = client.get("/api/workflows/right-flow").json()

    assert updated_left["state_version"] == left_version + 1
    assert fetched_right["state_version"] == right_version


def test_source_and_source_id_propagate_to_response_and_event(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="agent-versioned")
    client.post("/api/workflows/", json=payload)

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda event: seen.append(event))

    payload["description"] = "agent write"
    response = client.put(
        "/api/workflows/agent-versioned",
        json=payload,
        headers={
            "X-Changed-By": "embedded-agent",
            "X-Source-Id": "source-id-123",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    wait_for_condition(lambda: len(seen) >= 1)
    event = seen[-1].data

    assert body["source"] == "agent"
    assert body["source_id"] == "source-id-123"
    assert event["source"] == "agent"
    assert event["source_id"] == "source-id-123"
    assert event["version"] == body["state_version"]
    assert event["changed_by"] == "embedded-agent"
