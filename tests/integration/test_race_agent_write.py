"""ADR-045 agent-write race regression coverage."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp import tools_workflow
from tests.api.helpers import build_linear_workflow


def test_agent_workflow_write_is_remote_source_tagged_for_conflict_detection(
    client: TestClient,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="agent-write-race")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    base_version = created.json()["state_version"]

    with client.websocket_connect("/ws") as websocket:
        payload["description"] = "agent wrote while browser was dirty"
        response = client.put(
            "/api/workflows/agent-write-race",
            json=payload,
            headers={
                "X-Changed-By": "claude-agent",
                "X-Source-Id": "agent-run-456",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        event = websocket.receive_json()["data"]

    assert body["version"] == "1.0.0"
    assert body["state_version"] == base_version + 1
    assert body["source"] == "agent"
    assert body["source_id"] == "agent-run-456"
    assert event["version"] == body["state_version"]
    assert event["source"] == "agent"
    assert event["source_id"] == "agent-run-456"
    assert event["changed_by"] == "claude-agent"

    fetched = client.get("/api/workflows/agent-write-race")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["state_version"] == body["state_version"]


def test_mcp_write_workflow_pushes_agent_workflow_changed_before_watcher_echo(
    client: TestClient,
    opened_project: Path,
) -> None:
    workflow_id = "mcp-agent-write-race"
    workflow_yaml = yaml.safe_dump(
        {
            "workflow": {
                "id": workflow_id,
                "version": "1.0.0",
                "description": "MCP agent write",
                "nodes": [],
                "edges": [],
            }
        },
        sort_keys=False,
    )

    with client.websocket_connect("/ws") as websocket:
        result = asyncio.run(tools_workflow.write_workflow(f"workflows/{workflow_id}.yaml", workflow_yaml))
        event = websocket.receive_json()

    assert result.bytes_written > 0
    assert event["type"] == "workflow.changed"
    assert event["workflow_id"] == workflow_id
    data = event["data"]
    assert data["entity_id"] == workflow_id
    assert data["workflow_id"] == workflow_id
    assert data["source"] == "agent"
    assert data["source_id"] is None
    assert data["changed_by"] == "mcp.write_workflow"
    assert data["kind"] == "created"

    fetched = client.get(f"/api/workflows/{workflow_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["state_version"] == data["version"]
