"""Tests for workflow management endpoints (list, import, import-path, browse)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.helpers import build_linear_workflow


def test_list_workflows_returns_saved_ids(client: TestClient, opened_project: Path) -> None:
    """GET /api/workflows/list should return IDs of workflows saved in the project."""
    # #879: every project ships with the auto-scaffolded `main` workflow, so
    # the initial list is `["main"]`, not empty.
    response = client.get("/api/workflows/list")
    assert response.status_code == 200
    assert response.json() == ["main"]

    # Create a workflow
    payload = build_linear_workflow(opened_project, workflow_id="list-test")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    # Now should appear in list
    response = client.get("/api/workflows/list")
    assert response.status_code == 200
    assert "list-test" in response.json()


def test_import_workflow_from_yaml_file(client: TestClient, opened_project: Path) -> None:
    """POST /api/workflows/import should accept a YAML upload and save it."""
    # First create a workflow to get a valid YAML file
    payload = build_linear_workflow(opened_project, workflow_id="import-source")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    # Read the saved YAML
    yaml_path = opened_project / "workflows" / "import-source.yaml"
    assert yaml_path.exists()
    yaml_content = yaml_path.read_bytes()

    # Delete the original so we can verify import creates it fresh
    yaml_path.unlink()
    assert not yaml_path.exists()

    # Import via file upload
    response = client.post(
        "/api/workflows/import",
        files={"file": ("import-source.yaml", yaml_content, "application/x-yaml")},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "import-source"
    assert yaml_path.exists()


def test_import_workflow_rejects_non_yaml(client: TestClient, opened_project: Path) -> None:
    """POST /api/workflows/import should reject non-YAML files."""
    response = client.post(
        "/api/workflows/import",
        files={"file": ("data.json", b'{"not": "yaml"}', "application/json")},
    )
    assert response.status_code == 400


def test_import_workflow_from_path(client: TestClient, opened_project: Path) -> None:
    """POST /api/workflows/import-path should import from a filesystem path."""
    # Create a workflow YAML file outside the project
    payload = build_linear_workflow(opened_project, workflow_id="path-import-test")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    # Copy the YAML to a temp location
    source = opened_project / "workflows" / "path-import-test.yaml"
    assert source.exists()
    yaml_content = source.read_bytes()

    external_path = opened_project.parent / "external-workflow.yaml"
    external_path.write_bytes(yaml_content)

    # Delete original
    source.unlink()

    # Import from external path
    response = client.post(
        "/api/workflows/import-path",
        json={"path": str(external_path)},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "path-import-test"
    assert source.exists()  # Should be saved back into project workflows dir


def test_import_path_rejects_missing_file(client: TestClient, opened_project: Path) -> None:
    """POST /api/workflows/import-path should 404 on missing file."""
    response = client.post(
        "/api/workflows/import-path",
        json={"path": "/nonexistent/workflow.yaml"},
    )
    assert response.status_code == 404


def test_import_path_rejects_non_yaml(client: TestClient, opened_project: Path) -> None:
    """POST /api/workflows/import-path should reject non-YAML files."""
    json_file = opened_project.parent / "data.json"
    json_file.write_text("{}")

    response = client.post(
        "/api/workflows/import-path",
        json={"path": str(json_file)},
    )
    assert response.status_code == 400
