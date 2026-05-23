"""Tests for the ``/api/ai/active-context`` endpoint.

ADR-040 Addendum 5 / #1488. The endpoint is the frontend → backend
bridge that surfaces the editor's current workflow id to the chat
agent (via the runtime field + persistence file).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def test_post_sets_active_workflow_id(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """A valid POST sets the runtime field and echoes the value back."""
    response = client.post(
        "/api/ai/active-context",
        json={"workflow_id": "calibration"},
    )
    assert response.status_code == 200
    assert response.json() == {"workflow_id": "calibration"}
    assert runtime.active_workflow_id == "calibration"


def test_post_persists_to_disk(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """The endpoint writes ``<project>/.scistudio/active_workflow.json``."""
    client.post("/api/ai/active-context", json={"workflow_id": "calibration"})
    target = opened_project / ".scistudio" / "active_workflow.json"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"workflow_id": "calibration"}


def test_post_none_clears_active_workflow_id(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """Posting ``null`` clears the field and writes null to disk."""
    client.post("/api/ai/active-context", json={"workflow_id": "calibration"})
    response = client.post("/api/ai/active-context", json={"workflow_id": None})
    assert response.status_code == 200
    assert response.json() == {"workflow_id": None}
    assert runtime.active_workflow_id is None
    target = opened_project / ".scistudio" / "active_workflow.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"workflow_id": None}


def test_empty_string_is_normalised_to_none(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    """Empty string MUST normalise to None per ``set_active_workflow_id``."""
    response = client.post("/api/ai/active-context", json={"workflow_id": ""})
    assert response.status_code == 200
    assert response.json() == {"workflow_id": None}
    assert runtime.active_workflow_id is None


def test_post_works_without_project_open(client: TestClient, runtime: ApiRuntime) -> None:
    """No active project → no disk write, but runtime field still updates."""
    response = client.post(
        "/api/ai/active-context",
        json={"workflow_id": "orphan"},
    )
    assert response.status_code == 200
    assert response.json() == {"workflow_id": "orphan"}
    assert runtime.active_workflow_id == "orphan"
