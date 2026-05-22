"""ADR-045 external-editor race regression coverage."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from watchdog.events import FileModifiedEvent

from scistudio.api.routes.projects import FILE_CHANGED_EVENT_TYPE
from scistudio.api.routes.workflow_watcher import _ProjectFileHandler
from scistudio.api.runtime import FILE_ENTITY_CLASS, ApiRuntime


def test_external_file_edit_emits_versioned_file_changed(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    target = opened_project / "notes.md"
    target.write_text("base\n", encoding="utf-8")
    base = client.get(f"/api/projects/{project_id}/file?path=notes.md")
    assert base.status_code == 200, base.text
    base_version = base.json()["state_version"]

    captured: list[dict[str, object]] = []
    handler = _ProjectFileHandler(
        project_dir=opened_project,
        broadcast=lambda payload: captured.append(payload),
        loop=None,
        runtime=runtime,
    )

    target.write_text("external edit\n", encoding="utf-8")
    handler.on_any_event(FileModifiedEvent(str(target)))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["type"] == FILE_CHANGED_EVENT_TYPE
    assert payload["entity_class"] == FILE_ENTITY_CLASS
    assert payload["entity_id"] == "notes.md"
    assert payload["path"] == "notes.md"
    assert payload["project_id"] == project_id
    assert payload["source"] == "external"
    assert payload["source_id"] is None
    assert payload["kind"] == "modified"
    assert payload["version"] == base_version + 1


def test_first_party_file_write_pending_signature_suppresses_watcher_echo(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    target = opened_project / "notes.md"
    target.write_text("base\n", encoding="utf-8")
    base = client.get(f"/api/projects/{project_id}/file?path=notes.md")
    assert base.status_code == 200, base.text
    base_version = base.json()["state_version"]

    captured: list[dict[str, object]] = []
    handler = _ProjectFileHandler(
        project_dir=opened_project,
        broadcast=lambda payload: captured.append(payload),
        loop=None,
        runtime=runtime,
    )

    runtime.mark_entity_first_party_write(
        FILE_ENTITY_CLASS,
        "notes.md",
        base_version,
        path=target,
        kind="modified",
        pending=True,
    )
    target.write_text("api save\n", encoding="utf-8")
    handler.on_any_event(FileModifiedEvent(str(target)))

    assert captured == []
    assert runtime.current_entity_version(FILE_ENTITY_CLASS, "notes.md", path=target) == base_version


def test_file_changed_events_reach_websocket_clients(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    project_id = runtime.require_active_project().id
    target = opened_project / "analysis.py"
    target.write_text("print('base')\n", encoding="utf-8")
    base = client.get(f"/api/projects/{project_id}/file?path=analysis.py")
    assert base.status_code == 200, base.text
    base_version = base.json()["state_version"]

    with client.websocket_connect("/ws") as websocket:
        response = client.put(
            f"/api/projects/{project_id}/file?path=analysis.py",
            json={"content": "print('saved')\n", "source_id": "tab-save-1"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        message = websocket.receive_json()

    assert message["type"] == FILE_CHANGED_EVENT_TYPE
    data = message["data"]
    assert body["state_version"] == base_version + 1
    assert data["version"] == body["state_version"]
    assert data["entity_class"] == FILE_ENTITY_CLASS
    assert data["entity_id"] == "analysis.py"
    assert data["source"] == "canvas"
    assert data["source_id"] == "tab-save-1"
