"""ADR-045 multi-session race regression coverage."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.helpers import build_linear_workflow


def test_multi_session_workflow_write_broadcasts_same_version_to_all_tabs(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="multi-session-race")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    base_version = created.json()["state_version"]

    with client.websocket_connect("/ws") as tab_a, client.websocket_connect("/ws") as tab_b:
        payload["description"] = "tab A saved version N+1"
        response = client.put(
            "/api/workflows/multi-session-race",
            json={**payload, "source_id": "browser-tab-a"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        event_a = tab_a.receive_json()["data"]
        event_b = tab_b.receive_json()["data"]

    assert body["state_version"] == base_version + 1
    assert event_a["version"] == body["state_version"]
    assert event_b["version"] == body["state_version"]
    assert event_a["source"] == "canvas"
    assert event_b["source"] == "canvas"
    assert event_a["source_id"] == "browser-tab-a"
    assert event_b["source_id"] == "browser-tab-a"
    assert event_a["entity_id"] == "multi-session-race"
    assert event_b["entity_id"] == "multi-session-race"

    fetched = client.get("/api/workflows/multi-session-race")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["state_version"] == body["state_version"]
