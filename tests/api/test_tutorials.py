from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_run_first_workflow_bootstrap_creates_real_project(
    client: TestClient,
    project_parent: Path,
) -> None:
    response = client.post(
        "/api/tutorials/run-first-workflow/bootstrap",
        json={"parent_path": str(project_parent)},
    )

    assert response.status_code == 200
    body = response.json()
    project = body["project"]
    project_root = Path(project["path"])

    assert body["tutorial_id"] == "run-first-scistudio-workflow"
    assert project["name"] == "Run Your First SciStudio Workflow"
    assert body["dataset_path"] == "data/raw/cell_viability_fluorescence.csv"
    assert (project_root / body["dataset_path"]).is_file()
    assert (project_root / "workflows" / "main.yaml").is_file()
    assert "treated_5uM,3,12380" in (project_root / body["dataset_path"]).read_text(encoding="utf-8")
    assert body["custom_block_type"] == "normalize_fluorescence"
    assert body["negative_control"] == "neg_control"
    assert body["positive_control"] == "pos_control"


def test_run_first_workflow_bootstrap_uses_unique_project_name(
    client: TestClient,
    project_parent: Path,
) -> None:
    first = client.post(
        "/api/tutorials/run-first-workflow/bootstrap",
        json={"parent_path": str(project_parent)},
    )
    second = client.post(
        "/api/tutorials/run-first-workflow/bootstrap",
        json={"parent_path": str(project_parent)},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["project"]["path"] != second.json()["project"]["path"]
    assert second.json()["project"]["name"] == "Run Your First SciStudio Workflow 2"
