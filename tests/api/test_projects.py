"""Tests for project management endpoints."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient


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

    # Delete the project directory outside the API (simulate external deletion)
    shutil.rmtree(project_path)

    # Next listing should prune the stale entry
    listed2 = client.get("/api/projects/")
    ids2 = [entry["id"] for entry in listed2.json()]
    assert resp.json()["id"] not in ids2
