"""ADR-045 ``workflow.changed`` payload schema compatibility tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.engine.events import WORKFLOW_CHANGED
from tests.api.helpers import build_linear_workflow


def test_workflow_changed_websocket_payload_carries_adr045_fields(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="schema-ws")
    client.post("/api/workflows/", json=payload)

    with client.websocket_connect("/ws") as websocket:
        payload["description"] = "schema check"
        response = client.put(
            "/api/workflows/schema-ws",
            json=payload,
            headers={"X-Source-Id": "ws-source-id"},
        )
        assert response.status_code == 200, response.text
        message = websocket.receive_json()

    data = message["data"]
    assert message["type"] == WORKFLOW_CHANGED
    assert data["entity_class"] == "workflow"
    assert data["entity_id"] == "schema-ws"
    assert isinstance(data["version"], int)
    assert data["source"] == "canvas"
    assert data["source_id"] == "ws-source-id"
    assert data["kind"] == "modified"
    assert datetime.fromisoformat(data["timestamp"])

    # Backward-compatible keys stay present for clients not yet migrated to
    # ADR-045 reconciliation.
    assert data["workflow_id"] == "schema-ws"
    assert data["changed_by"] == "api"
    assert "revision" not in data
