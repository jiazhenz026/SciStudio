"""A second GUI window re-opening the active project keeps its data ids.

A GUI window that attaches to a running backend opens the project the backend
already has open. That re-open used to empty the data catalog, and a panel
target is only ever resolved through the catalog, so every window already
showing that project's outputs got ``403 unauthorized_ref`` on its next
preview. Switching to another project still retires the ids.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient


def _register_outputs(client: TestClient, project: Path) -> dict[str, str]:
    runtime = client.app.state.runtime
    first, second = project / "a.npy", project / "b.npy"
    np.save(first, np.arange(4))
    np.save(second, np.arange(5))
    single = runtime.register_output_payload(
        {"backend": "filesystem", "path": str(first), "format": "npy", "metadata": {}}
    )
    collection = runtime.register_output_payload(
        {
            "_collection": True,
            "item_type": "Array",
            "items": [
                {"backend": "filesystem", "path": str(first), "format": "npy", "metadata": {}},
                {"backend": "filesystem", "path": str(second), "format": "npy", "metadata": {}},
            ],
        }
    )
    return {"data_ref": single["data_ref"], "collection_ref": collection["collection_ref"]}


def _panel_status(client: TestClient, kind: str, ref: str) -> int:
    response = client.post("/api/panels/contexts", json={"kind": "preview", "target": {"kind": kind, "ref": ref}})
    return response.status_code


def _active_project_id(client: TestClient) -> str:
    return client.get("/api/projects/active").json()["project"]["id"]


def test_reopening_the_active_project_keeps_panel_targets(client: TestClient, opened_project: Path) -> None:
    refs = _register_outputs(client, opened_project)
    for kind, ref in refs.items():
        assert _panel_status(client, kind, ref) == 200

    assert client.get(f"/api/projects/{_active_project_id(client)}").status_code == 200

    for kind, ref in refs.items():
        assert _panel_status(client, kind, ref) == 200, kind


def test_switching_projects_retires_panel_targets(
    client: TestClient, opened_project: Path, project_parent: Path
) -> None:
    refs = _register_outputs(client, opened_project)
    other = client.post("/api/projects/", json={"name": "Other", "description": "", "path": str(project_parent)})
    assert other.status_code == 200, other.text

    for kind, ref in refs.items():
        assert _panel_status(client, kind, ref) == 403, kind
