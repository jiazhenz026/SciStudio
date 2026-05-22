"""ADR-045 editable file state version-vector backend tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.routes.projects import FILE_CHANGED_EVENT_TYPE
from scistudio.api.runtime import FILE_ENTITY_CLASS, ApiRuntime
from scistudio.engine.events import EngineEvent
from tests.api.helpers import wait_for_condition


def _open(client: TestClient, project_path: Path) -> str:
    response = client.post(
        "/api/projects/",
        json={"name": "T", "description": "", "path": str(project_path)},
    )
    assert response.status_code == 200, response.text
    project_id = response.json()["id"]
    opened = client.get(f"/api/projects/{project_id}")
    assert opened.status_code == 200, opened.text
    return project_id


def test_file_get_returns_state_version_without_version_field(
    client: TestClient,
    project_parent: Path,
) -> None:
    project_id = _open(client, project_parent / "read-version")
    project_root = Path(client.app.state.runtime.known_projects[project_id].path)
    target = project_root / "notes.md"
    target.write_text("# hello\n", encoding="utf-8")

    response = client.get(f"/api/projects/{project_id}/file?path=notes.md")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["content"] == "# hello\n"
    assert "version" not in body
    assert isinstance(body["state_version"], int)
    assert body["entity_class"] == FILE_ENTITY_CLASS
    assert body["entity_id"] == "notes.md"
    assert body["source"] is None
    assert body["source_id"] is None
    assert body["kind"] == "current"
    assert body["timestamp"]


def test_file_put_bumps_state_version_and_emits_file_changed(
    client: TestClient,
    runtime: ApiRuntime,
    project_parent: Path,
) -> None:
    project_id = _open(client, project_parent / "write-version")
    project_root = Path(runtime.known_projects[project_id].path)
    target = project_root / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    base_version = client.get(f"/api/projects/{project_id}/file?path=notes.md").json()["state_version"]

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(FILE_CHANGED_EVENT_TYPE, lambda event: seen.append(event))

    response = client.put(
        f"/api/projects/{project_id}/file?path=notes.md",
        json={"content": "new\n", "source": "agent", "source_id": "file-source-123"},
        headers={"X-Changed-By": "embedded-agent"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    wait_for_condition(lambda: len(seen) >= 1)
    event = seen[-1].data

    assert "version" not in body
    assert body["state_version"] == base_version + 1
    assert body["entity_class"] == FILE_ENTITY_CLASS
    assert body["entity_id"] == "notes.md"
    assert body["source"] == "agent"
    assert body["source_id"] == "file-source-123"
    assert body["kind"] == "modified"
    assert event["entity_class"] == FILE_ENTITY_CLASS
    assert event["entity_id"] == "notes.md"
    assert event["version"] == body["state_version"]
    assert event["source"] == "agent"
    assert event["source_id"] == "file-source-123"
    assert event["kind"] == "modified"
    assert event["path"] == "notes.md"
    assert event["project_id"] == project_id
    assert event["changed_by"] == "embedded-agent"
    assert runtime.is_recent_first_party_entity_write(
        FILE_ENTITY_CLASS,
        "notes.md",
        version=body["state_version"],
        path=target,
        kind="modified",
    )


def test_file_put_created_kind_uses_project_relative_entity_id(
    client: TestClient,
    runtime: ApiRuntime,
    project_parent: Path,
) -> None:
    project_id = _open(client, project_parent / "created-version")
    project_root = Path(runtime.known_projects[project_id].path)
    (project_root / "docs").mkdir()

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(FILE_CHANGED_EVENT_TYPE, lambda event: seen.append(event))

    response = client.put(
        f"/api/projects/{project_id}/file?path=docs/new.md",
        json={"content": "created\n", "source_id": "browser-write"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    wait_for_condition(lambda: len(seen) >= 1)
    event = seen[-1].data

    assert body["kind"] == "created"
    assert body["source"] == "canvas"
    assert body["source_id"] == "browser-write"
    assert body["entity_id"] == "docs/new.md"
    assert event["kind"] == "created"
    assert event["source"] == "canvas"
    assert event["source_id"] == "browser-write"
    assert event["entity_id"] == "docs/new.md"
    assert (project_root / "docs" / "new.md").read_text(encoding="utf-8") == "created\n"


def test_file_state_versions_are_scoped_per_project_relative_file(
    client: TestClient,
    project_parent: Path,
) -> None:
    project_id = _open(client, project_parent / "scoped-version")
    project_root = Path(client.app.state.runtime.known_projects[project_id].path)
    left = project_root / "left.md"
    right = project_root / "right.md"
    left.write_text("left\n", encoding="utf-8")
    right.write_text("right\n", encoding="utf-8")

    left_version = client.get(f"/api/projects/{project_id}/file?path=left.md").json()["state_version"]
    right_version = client.get(f"/api/projects/{project_id}/file?path=right.md").json()["state_version"]

    updated_left = client.put(
        f"/api/projects/{project_id}/file?path=left.md",
        json={"content": "left changed\n"},
    ).json()
    fetched_right = client.get(f"/api/projects/{project_id}/file?path=right.md").json()

    assert updated_left["state_version"] == left_version + 1
    assert fetched_right["state_version"] == right_version
