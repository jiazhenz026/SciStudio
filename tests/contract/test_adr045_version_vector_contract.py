"""Unified ADR-045 version-vector contract tests.

These tests intentionally sit under ``tests/contract`` as the compact
cross-surface proof for the ADR-045 wire contract. Narrower API, integration,
and frontend tests cover edge cases; this file keeps the contract entry point
discoverable.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.api.helpers import build_linear_workflow, wait_for_condition
from watchdog.events import FileModifiedEvent

from scistudio.api.app import create_app
from scistudio.api.routes.projects import FILE_CHANGED_EVENT_TYPE
from scistudio.api.routes.workflow_watcher import _ProjectFileHandler
from scistudio.api.runtime import FILE_ENTITY_CLASS, ApiRuntime
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent


@pytest.fixture()
def project_parent(tmp_path: Path) -> Path:
    parent = tmp_path / "projects"
    parent.mkdir()
    return parent


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def runtime(client: TestClient) -> ApiRuntime:
    return client.app.state.runtime


@pytest.fixture()
def opened_project(client: TestClient, project_parent: Path) -> Path:
    response = client.post(
        "/api/projects/",
        json={
            "name": "ADR-045 Contract Project",
            "description": "contract test workspace",
            "path": str(project_parent),
        },
    )
    assert response.status_code == 200, response.text
    return Path(response.json()["path"])


def test_adr045_http_and_event_contracts_are_consistent(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    workflow = build_linear_workflow(opened_project, workflow_id="contract-flow")
    created_workflow = client.post("/api/workflows/", json=workflow)
    assert created_workflow.status_code == 200, created_workflow.text
    created_workflow_body = created_workflow.json()

    assert created_workflow_body["version"] == "1.0.0"
    assert created_workflow_body["workflow_version"] == "1.0.0"
    assert "state_version" in created_workflow_body
    assert "revision" not in created_workflow_body

    workflow_events: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda event: workflow_events.append(event))

    workflow["description"] = "agent update"
    updated_workflow = client.put(
        "/api/workflows/contract-flow",
        json=workflow,
        headers={"X-Changed-By": "embedded-agent", "X-Source-Id": "workflow-source"},
    )
    assert updated_workflow.status_code == 200, updated_workflow.text
    updated_workflow_body = updated_workflow.json()
    wait_for_condition(lambda: len(workflow_events) >= 1)
    workflow_event = workflow_events[-1].data

    assert updated_workflow_body["state_version"] == created_workflow_body["state_version"] + 1
    assert updated_workflow_body["version"] == "1.0.0"
    assert workflow_event["entity_class"] == "workflow"
    assert workflow_event["entity_id"] == "contract-flow"
    assert workflow_event["version"] == updated_workflow_body["state_version"]
    assert workflow_event["source_id"] == "workflow-source"
    assert workflow_event["changed_by"] == "embedded-agent"

    file_events: list[EngineEvent] = []
    runtime.event_bus.subscribe(FILE_CHANGED_EVENT_TYPE, lambda event: file_events.append(event))

    project_file = opened_project / "notes.md"
    project_file.write_text("base\n", encoding="utf-8")
    read_file = client.get(f"/api/projects/{project_id}/file?path=notes.md")
    assert read_file.status_code == 200, read_file.text
    read_file_body = read_file.json()

    assert "state_version" in read_file_body
    assert "version" not in read_file_body
    assert read_file_body["entity_class"] == FILE_ENTITY_CLASS
    assert read_file_body["entity_id"] == "notes.md"

    updated_file = client.put(
        f"/api/projects/{project_id}/file?path=notes.md",
        json={"content": "updated\n", "source": "agent", "source_id": "file-source"},
        headers={"X-Changed-By": "embedded-agent"},
    )
    assert updated_file.status_code == 200, updated_file.text
    updated_file_body = updated_file.json()
    wait_for_condition(lambda: len(file_events) >= 1)
    file_event = file_events[-1].data

    assert updated_file_body["state_version"] == read_file_body["state_version"] + 1
    assert updated_file_body["source_id"] == "file-source"
    assert file_event["entity_class"] == FILE_ENTITY_CLASS
    assert file_event["entity_id"] == "notes.md"
    assert file_event["version"] == updated_file_body["state_version"]
    assert file_event["source"] == "agent"
    assert file_event["source_id"] == "file-source"
    assert file_event["changed_by"] == "embedded-agent"


def test_adr045_websocket_contracts_use_event_version_and_state_version_response(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    workflow = build_linear_workflow(opened_project, workflow_id="contract-ws-flow")
    client.post("/api/workflows/", json=workflow)

    with client.websocket_connect("/ws") as websocket:
        workflow["description"] = "websocket update"
        response = client.put(
            "/api/workflows/contract-ws-flow",
            json=workflow,
            headers={"X-Source-Id": "workflow-ws-source"},
        )
        assert response.status_code == 200, response.text
        workflow_message = websocket.receive_json()

    workflow_data = workflow_message["data"]
    assert workflow_message["type"] == WORKFLOW_CHANGED
    assert workflow_data["version"] == response.json()["state_version"]
    assert workflow_data["source_id"] == "workflow-ws-source"
    assert datetime.fromisoformat(workflow_data["timestamp"])

    with client.websocket_connect("/ws") as websocket:
        response = client.put(
            f"/api/projects/{project_id}/file?path=analysis.py",
            json={"content": "print('saved')\n", "source_id": "file-ws-source"},
        )
        assert response.status_code == 200, response.text
        file_message = websocket.receive_json()

    file_data = file_message["data"]
    assert file_message["type"] == FILE_CHANGED_EVENT_TYPE
    assert file_data["version"] == response.json()["state_version"]
    assert file_data["entity_class"] == FILE_ENTITY_CLASS
    assert file_data["entity_id"] == "analysis.py"
    assert file_data["source_id"] == "file-ws-source"
    assert datetime.fromisoformat(file_data["timestamp"])


def test_adr045_watcher_contract_distinguishes_external_and_first_party_writes(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    target = opened_project / "watcher-notes.md"
    target.write_text("base\n", encoding="utf-8")
    base = client.get(f"/api/projects/{project_id}/file?path=watcher-notes.md")
    assert base.status_code == 200, base.text
    base_version = base.json()["state_version"]

    captured: list[dict[str, object]] = []
    handler = _ProjectFileHandler(
        project_dir=opened_project,
        broadcast=lambda payload: captured.append(payload),
        loop=None,
        runtime=runtime,
    )

    target.write_text("external\n", encoding="utf-8")
    handler.on_any_event(FileModifiedEvent(str(target)))
    assert len(captured) == 1
    external_payload = captured[-1]
    assert external_payload["type"] == FILE_CHANGED_EVENT_TYPE
    assert external_payload["source"] == "external"
    assert external_payload["source_id"] is None
    assert external_payload["version"] == base_version + 1

    current_version = runtime.current_entity_version(FILE_ENTITY_CLASS, "watcher-notes.md", path=target)
    runtime.mark_entity_first_party_write(
        FILE_ENTITY_CLASS,
        "watcher-notes.md",
        current_version,
        path=target,
        kind="modified",
        pending=True,
    )
    target.write_text("first party\n", encoding="utf-8")
    handler.on_any_event(FileModifiedEvent(str(target)))

    assert len(captured) == 1
    assert runtime.current_entity_version(FILE_ENTITY_CLASS, "watcher-notes.md", path=target) == current_version
