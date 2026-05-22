"""ADR-045 lineage/git restore race regression coverage."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from scistudio.api.routes.git import _emit_workflow_diff, _snapshot_workflows
from scistudio.api.runtime import ApiRuntime
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent
from tests.api.helpers import build_linear_workflow


def test_git_restore_emits_semantic_modified_event_not_delete_clear(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    payload = build_linear_workflow(opened_project, workflow_id="lineage-restore-race")
    created = client.post("/api/workflows/", json=payload)
    assert created.status_code == 200, created.text
    base_version = created.json()["state_version"]

    before = _snapshot_workflows(opened_project)
    workflow_path = opened_project / "workflows" / "lineage-restore-race.yaml"
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8") + "metadata:\n  restored: true\n",
        encoding="utf-8",
    )

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda event: seen.append(event))

    asyncio.run(
        _emit_workflow_diff(
            runtime,
            opened_project,
            before,
            source="gitRestore",
            source_id="restore-commit-123",
        )
    )

    assert len(seen) == 1
    data = seen[0].data
    assert data["entity_class"] == "workflow"
    assert data["entity_id"] == "lineage-restore-race"
    assert data["workflow_id"] == "lineage-restore-race"
    assert data["source"] == "gitRestore"
    assert data["source_id"] == "restore-commit-123"
    assert data["kind"] == "modified"
    assert data["version"] == base_version + 1
    assert data["path"] == "workflows/lineage-restore-race.yaml"
