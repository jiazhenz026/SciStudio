"""Per-project unique workflow id enforcement (#1836).

Two workflow files in one project that share the same internal ``id`` break
the unique-id invariant: target/workflow discovery walks every
``workflows/*.yaml`` and surfaces phantom plot targets whose nodes are not on
the open canvas. Saving/importing a workflow now rejects a write that would
create or perpetuate such a collision (409 Conflict) instead of silently
merging.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from tests.api.helpers import build_linear_workflow


def _plant_duplicate_sibling(opened_project: Path, *, canonical_id: str) -> Path:
    """Copy the canonical workflow file to a second, differently-named file
    that keeps the same internal id — the duplicate-id collision."""
    canonical = opened_project / "workflows" / f"{canonical_id}.yaml"
    assert canonical.exists()
    sibling = opened_project / "workflows" / f"{canonical_id}-copy.yaml"
    shutil.copyfile(canonical, sibling)
    return sibling


def test_find_workflow_id_conflict_detects_sibling(
    client: TestClient, runtime: ApiRuntime, opened_project: Path
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="flow-x")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    # No collision yet: only the canonical file declares the id.
    assert runtime.find_workflow_id_conflict("flow-x") is None
    # A genuinely unique id never collides.
    assert runtime.find_workflow_id_conflict("never-used") is None

    sibling = _plant_duplicate_sibling(opened_project, canonical_id="flow-x")
    conflict = runtime.find_workflow_id_conflict("flow-x")
    assert conflict is not None
    assert conflict.resolve() == sibling.resolve()


def test_create_workflow_rejects_duplicate_id(client: TestClient, opened_project: Path) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="flow-x")
    assert client.post("/api/workflows/", json=payload).status_code == 200
    _plant_duplicate_sibling(opened_project, canonical_id="flow-x")

    # Re-saving the id now that a duplicate sibling exists must 409, not merge.
    resp = client.post("/api/workflows/", json=payload)
    assert resp.status_code == 409
    assert "unique per project" in resp.json()["detail"]


def test_import_path_rejects_duplicate_id(client: TestClient, opened_project: Path, tmp_path: Path) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="flow-x")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    # A valid external file that declares the same id as an existing sibling.
    external = tmp_path / "external-flow-x.yaml"
    shutil.copyfile(opened_project / "workflows" / "flow-x.yaml", external)
    _plant_duplicate_sibling(opened_project, canonical_id="flow-x")

    resp = client.post("/api/workflows/import-path", json={"path": str(external)})
    assert resp.status_code == 409
    assert "unique per project" in resp.json()["detail"]


def test_import_path_without_conflict_still_succeeds(client: TestClient, opened_project: Path, tmp_path: Path) -> None:
    """Re-importing an id to its canonical home is not a conflict."""
    payload = build_linear_workflow(opened_project, workflow_id="flow-y")
    assert client.post("/api/workflows/", json=payload).status_code == 200

    external = tmp_path / "external-flow-y.yaml"
    shutil.copyfile(opened_project / "workflows" / "flow-y.yaml", external)

    resp = client.post("/api/workflows/import-path", json={"path": str(external)})
    assert resp.status_code == 200
