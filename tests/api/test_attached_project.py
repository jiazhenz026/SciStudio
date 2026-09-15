"""Attached ``open_gui`` views stay bound to the project they attached to (#2385).

The backend has a single active project and workflow routes resolve through
it. A page attached through the ``open_gui`` deep link sends the project id it
verified; once the active project is a different one, those requests must be
refused so the page cannot read or write the project the user switched to.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api._attached_project import ATTACHED_PROJECT_CHANGED, ATTACHED_PROJECT_HEADER
from scistudio.api.runtime import ApiRuntime

_WORKFLOW = {"id": "main", "nodes": [], "edges": [], "metadata": {"title": "edited"}}


def _create(client: TestClient, parent: Path, name: str) -> dict:
    response = client.post("/api/projects/", json={"name": name, "description": "", "path": str(parent)})
    assert response.status_code == 200
    return response.json()


def test_unbound_requests_are_untouched(client: TestClient, opened_project: Path) -> None:
    """The desktop window, the agent, and plain tabs send no header and pass."""
    assert client.get("/api/workflows/main").status_code == 200


def test_bound_request_to_the_active_project_passes(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    response = client.get("/api/workflows/main", headers={ATTACHED_PROJECT_HEADER: runtime.active_project.id})
    assert response.status_code == 200


def test_bound_write_is_refused_after_a_project_switch(client: TestClient, project_parent: Path) -> None:
    """A write bound to project A never lands in project B after the owner switches."""
    first = _create(client, project_parent, "Alpha")
    second = _create(client, project_parent, "Beta")  # creating Beta makes it the active project
    target = Path(second["path"]) / "workflows" / "main.yaml"
    before = target.read_text(encoding="utf-8")

    response = client.put("/api/workflows/main", json=_WORKFLOW, headers={ATTACHED_PROJECT_HEADER: first["id"]})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == ATTACHED_PROJECT_CHANGED
    assert detail["attachedProjectId"] == first["id"]
    assert detail["activeProjectId"] == second["id"]
    assert target.read_text(encoding="utf-8") == before


def test_bound_reopen_is_refused(client: TestClient, runtime: ApiRuntime, project_parent: Path) -> None:
    """A stale attached page cannot switch the session back by re-opening its project."""
    first = _create(client, project_parent, "Alpha")
    second = _create(client, project_parent, "Beta")

    response = client.get(f"/api/projects/{first['id']}", headers={ATTACHED_PROJECT_HEADER: first["id"]})

    assert response.status_code == 409
    assert runtime.active_project.id == second["id"]


def test_bound_request_is_refused_when_no_project_is_open(client: TestClient) -> None:
    response = client.get("/api/workflows/list", headers={ATTACHED_PROJECT_HEADER: "project-gone"})
    assert response.status_code == 409
    assert response.json()["detail"]["activeProjectId"] is None
