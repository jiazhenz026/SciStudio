"""Tests for project management endpoints."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def test_project_crud_and_path_opening(client: TestClient, project_parent: Path) -> None:
    """Projects should be creatable, listable, updatable, openable, and deletable."""
    first = client.post(
        "/api/projects/",
        json={"name": "Alpha", "description": "first", "path": str(project_parent)},
    )
    second = client.post(
        "/api/projects/",
        json={"name": "Beta", "description": "second", "path": str(project_parent)},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()

    workflow = {
        "id": "demo-workflow",
        "nodes": [],
        "edges": [],
        "metadata": {},
    }
    create_workflow = client.post("/api/workflows/", json=workflow)
    assert create_workflow.status_code == 200

    listed = client.get("/api/projects/")
    assert listed.status_code == 200
    projects = {entry["name"]: entry for entry in listed.json()}
    # #879: every project ships with the auto-scaffolded `main` workflow, so
    # Beta sees its own `main` + the explicit `demo-workflow` created above.
    assert projects["Beta"]["workflow_count"] == 2

    updated = client.put(
        f"/api/projects/{second_payload['id']}",
        json={"name": "Beta Updated", "description": "renamed"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Beta Updated"

    by_path = client.get(f"/api/projects/{quote(second_payload['path'], safe='')}")
    assert by_path.status_code == 200
    assert by_path.json()["id"] == second_payload["id"]

    # Verify data/exchange is created alongside other data subdirs (#565).
    project_path = Path(second_payload["path"])
    assert (project_path / "data" / "exchange").is_dir()

    deleted = client.delete(f"/api/projects/{first_payload['id']}")
    assert deleted.status_code == 204
    assert not Path(first_payload["path"]).exists()


def test_workflow_save_without_active_project_returns_session_conflict(client: TestClient) -> None:
    """Backend session loss should be distinguishable from workflow validation errors."""
    workflow = {
        "id": "main",
        "nodes": [],
        "edges": [],
        "metadata": {},
    }

    created = client.post("/api/workflows/", json=workflow)
    assert created.status_code == 409
    assert created.json()["detail"] == "No project is currently open."

    updated = client.put("/api/workflows/main", json=workflow)
    assert updated.status_code == 409
    assert updated.json()["detail"] == "No project is currently open."


def test_execute_workflow_sets_engine_api_url_for_workers(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AIBlock worker subprocesses need the engine API callback URL."""
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)

    def fake_start_workflow(workflow_id: str, **_: Any) -> dict[str, str]:
        assert os.environ["SCISTUDIO_ENGINE_API_URL"] == "http://testserver"
        return {"workflow_id": workflow_id, "status": "running", "message": "started"}

    monkeypatch.setattr(runtime, "start_workflow", fake_start_workflow)
    response = client.post("/api/workflows/main/execute")
    assert response.status_code == 200


def test_list_projects_sorted_by_last_opened(client: TestClient, project_parent: Path) -> None:
    """list_projects should return projects sorted by last_opened descending."""
    # Create two projects
    first = client.post(
        "/api/projects/",
        json={"name": "Older", "description": "first", "path": str(project_parent)},
    )
    assert first.status_code == 200

    # Small delay so timestamps differ
    time.sleep(0.05)

    second = client.post(
        "/api/projects/",
        json={"name": "Newer", "description": "second", "path": str(project_parent)},
    )
    assert second.status_code == 200

    listed = client.get("/api/projects/")
    assert listed.status_code == 200
    names = [entry["name"] for entry in listed.json()]
    # "Newer" was created (and thus opened) more recently, so it comes first
    assert names.index("Newer") < names.index("Older")


def test_create_project_scaffolds_a_folder_for_results(client: TestClient, project_parent: Path) -> None:
    """A new project has somewhere to save results, next to where inputs land.

    ``data/raw`` had no counterpart, so the only folders a user could save into
    were named after storage formats — ``data/parquet``, ``data/zarr`` — which
    asks them to know what a parquet is before they can choose where their
    result goes (owner decision, 2026-08-11).
    """
    resp = client.post(
        "/api/projects/",
        json={"name": "WithProcessed", "description": "", "path": str(project_parent)},
    )
    assert resp.status_code == 200

    project_path = Path(resp.json()["path"])
    assert (project_path / "data" / "processed").is_dir()
    assert (project_path / "data" / "raw").is_dir()


def test_create_project_scaffolds_empty_main_workflow(client: TestClient, project_parent: Path) -> None:
    """#879: ``POST /api/projects/`` must scaffold ``workflows/main.yaml``.

    Without the scaffold the default ``main`` canvas tab is divorced from
    disk until the user manually saves, which breaks View source (#878),
    file-watcher rehydration, and agent introspection.
    """
    import yaml as yaml_mod

    resp = client.post(
        "/api/projects/",
        json={"name": "WithMain", "description": "", "path": str(project_parent)},
    )
    assert resp.status_code == 200
    project_path = Path(resp.json()["path"])

    main_yaml = project_path / "workflows" / "main.yaml"
    assert main_yaml.is_file(), "create_project should scaffold workflows/main.yaml"

    loaded = yaml_mod.safe_load(main_yaml.read_text(encoding="utf-8"))
    # The serializer wraps the workflow under a ``workflow`` key.
    workflow = loaded.get("workflow") if isinstance(loaded, dict) else None
    assert workflow is not None, "main.yaml should contain a ``workflow`` root key"
    assert workflow.get("id") == "main"
    assert workflow.get("nodes") in (None, [])
    assert workflow.get("edges") in (None, [])


def test_list_projects_prunes_deleted_directories(client: TestClient, project_parent: Path) -> None:
    """list_projects should prune entries whose project directory no longer exists."""
    resp = client.post(
        "/api/projects/",
        json={"name": "Ephemeral", "description": "will be deleted", "path": str(project_parent)},
    )
    assert resp.status_code == 200
    project_path = Path(resp.json()["path"])

    # Verify project appears in listing
    listed = client.get("/api/projects/")
    ids = [entry["id"] for entry in listed.json()]
    assert resp.json()["id"] in ids

    # Delete the project directory outside the API (simulate external deletion).
    # ADR-039: auto-init creates ``.git/`` with read-only object files on
    # Windows; the runtime's force-rmtree helper handles chmod + retries.
    # The runtime's prune logic now keys on either ``is_dir()`` OR
    # ``project.yaml.is_file()`` returning False, so partial cleanup
    # (e.g. sqlite WAL residue) still triggers prune.
    from scistudio.api.runtime import _rmtree_force

    _rmtree_force(project_path)
    # Best-effort: force-unlink project.yaml if it lingers.
    import contextlib as _contextlib

    with _contextlib.suppress(PermissionError, OSError):
        (project_path / "project.yaml").unlink(missing_ok=True)

    # Next listing should prune the stale entry
    listed2 = client.get("/api/projects/")
    ids2 = [entry["id"] for entry in listed2.json()]
    assert resp.json()["id"] not in ids2


# ---------------------------------------------------------------------------
# ADR-055 Spec 2 FR-005 (#2279): the PUT file route runs the shared write path
# in ``scistudio.api.runtime._file_writes`` that the MCP author tools use.
# ---------------------------------------------------------------------------


def _open_project(client: TestClient, project_parent: Path, name: str) -> tuple[str, Path]:
    response = client.post("/api/projects/", json={"name": name, "description": "", "path": str(project_parent)})
    assert response.status_code == 200, response.text
    project_id = str(response.json()["id"])
    client.get(f"/api/projects/{project_id}")
    return project_id, Path(response.json()["path"])


def test_put_file_runs_the_shared_write_helper(
    client: TestClient, project_parent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.api.runtime import _file_writes

    calls: list[dict[str, Any]] = []
    original = _file_writes.write_project_file

    async def _spy(runtime: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return await original(runtime, **kwargs)

    monkeypatch.setattr(_file_writes, "write_project_file", _spy)
    project_id, root = _open_project(client, project_parent, "SharedHelper")

    response = client.put(f"/api/projects/{project_id}/file?path=notes.md", json={"content": "# hi\n"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(calls) == 1
    assert calls[0]["expected_state_version"] is None
    assert calls[0]["source"] == "canvas"
    assert body["kind"] == "created"
    assert body["entity_id"] == "notes.md"
    assert body["source"] == "canvas"
    assert (root / "notes.md").read_text(encoding="utf-8") == "# hi\n"


def test_put_file_expected_state_version_rejects_stale_writes(client: TestClient, project_parent: Path) -> None:
    """#2279 decision 5: optional conflict check; without it the route is unchanged."""
    project_id, root = _open_project(client, project_parent, "Versioned")
    url = f"/api/projects/{project_id}/file?path=doc.md"

    first = client.put(url, json={"content": "one\n"})
    assert first.status_code == 200, first.text
    v1 = first.json()["state_version"]
    second = client.put(url, json={"content": "two\n", "expected_state_version": v1})
    assert second.status_code == 200, second.text
    v2 = second.json()["state_version"]
    assert v2 > v1

    stale = client.put(url, json={"content": "three\n", "expected_state_version": v1})
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["condition"] == "stale_version"
    assert detail["expected_state_version"] == v1
    assert detail["current_state_version"] == v2
    assert (root / "doc.md").read_text(encoding="utf-8") == "two\n"

    # Without the optional field the route behaves exactly as before: last write wins.
    unconditional = client.put(url, json={"content": "four\n"})
    assert unconditional.status_code == 200
    assert (root / "doc.md").read_text(encoding="utf-8") == "four\n"


def test_observed_version_counts_an_unobserved_disk_edit_once(runtime: ApiRuntime, opened_project: Path) -> None:
    from scistudio.api.runtime import _file_writes

    target = opened_project / "external.md"
    target.write_text("a\n", encoding="utf-8")
    first = _file_writes.observed_entity_version(runtime, "external.md", target)
    later = target.stat().st_mtime_ns + 5_000_000_000
    os.utime(target, ns=(later, later))
    bumped = _file_writes.observed_entity_version(runtime, "external.md", target)
    again = _file_writes.observed_entity_version(runtime, "external.md", target)
    assert bumped == first + 1
    assert again == bumped


def test_project_file_service_confines_to_the_active_project(
    runtime: ApiRuntime, opened_project: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x", encoding="utf-8")
    inside = opened_project / "inside.md"
    inside.write_text("x", encoding="utf-8")
    assert runtime.project_files.state_version(outside) is None
    assert (runtime.project_files.state_version(inside) or 0) >= 1
