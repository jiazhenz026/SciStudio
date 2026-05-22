"""ADR-045 autosave race regression coverage."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.helpers import build_linear_workflow


def test_autosave_echoes_are_source_id_and_version_correlated(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="autosave-race")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    base_version = created.json()["state_version"]

    with client.websocket_connect("/ws") as websocket:
        payload["description"] = "autosave snapshot"
        first = client.put(
            "/api/workflows/autosave-race",
            json={**payload, "source_id": "autosave-write-1"},
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        first_event = websocket.receive_json()["data"]

        payload["description"] = "local edit after first autosave"
        second = client.put(
            "/api/workflows/autosave-race",
            json={**payload, "source_id": "autosave-write-2"},
        )
        assert second.status_code == 200, second.text
        second_body = second.json()
        second_event = websocket.receive_json()["data"]

    assert first_body["state_version"] == base_version + 1
    assert first_event["version"] == first_body["state_version"]
    assert first_event["source"] == "canvas"
    assert first_event["source_id"] == "autosave-write-1"

    assert second_body["state_version"] == first_body["state_version"] + 1
    assert second_event["version"] == second_body["state_version"]
    assert second_event["source"] == "canvas"
    assert second_event["source_id"] == "autosave-write-2"
    assert second_event["version"] > first_event["version"]
