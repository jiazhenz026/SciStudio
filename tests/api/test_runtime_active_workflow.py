"""Tests for ApiRuntime active_workflow_id persistence.

ADR-040 Addendum 5 / #1488. The runtime mirrors ``active_workflow_id``
to ``<project>/.scistudio/active_workflow.json`` so the value survives
backend restart and project switches restore the correct per-project
workflow id.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def test_load_from_disk_on_project_open(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """An existing active_workflow.json is loaded when the project opens."""
    # Pre-seed the persistence file as though a prior backend run wrote it.
    scistudio_dir = opened_project / ".scistudio"
    scistudio_dir.mkdir(parents=True, exist_ok=True)
    (scistudio_dir / "active_workflow.json").write_text(json.dumps({"workflow_id": "calibration"}), encoding="utf-8")

    # Re-open the same project — simulates a backend restart.
    project_id = next(iter(runtime.known_projects.keys()))
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert runtime.active_workflow_id == "calibration"


def test_missing_file_leaves_field_none(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """A project without an active_workflow.json starts with no active id."""
    assert runtime.active_workflow_id is None


def test_malformed_json_clears_field(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """A corrupt persistence file leaves the field None without raising."""
    target = opened_project / ".scistudio" / "active_workflow.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not valid json", encoding="utf-8")

    project_id = next(iter(runtime.known_projects.keys()))
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert runtime.active_workflow_id is None


def test_publish_writes_payload(runtime: ApiRuntime, opened_project: Path) -> None:
    """Calling ``set_active_workflow_id`` persists to disk immediately."""
    runtime.set_active_workflow_id("calibration")
    target = opened_project / ".scistudio" / "active_workflow.json"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"workflow_id": "calibration"}


def test_set_none_writes_null(runtime: ApiRuntime, opened_project: Path) -> None:
    """Clearing the field writes ``{"workflow_id": null}`` (not deletion)."""
    runtime.set_active_workflow_id("calibration")
    runtime.set_active_workflow_id(None)
    target = opened_project / ".scistudio" / "active_workflow.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"workflow_id": None}
