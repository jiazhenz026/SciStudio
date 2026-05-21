"""Tests for ``ApiRuntime._build_lineage_recorder(parent_run_id=...)`` (D38-3.2).

Closes audit D38-3.1a P2 / D38-3.1b P2-4: the rerun route should stamp
``parent_run_id`` on the new run so the rerun chain is queryable
(``SELECT * FROM runs WHERE parent_run_id = ?``).

These tests exercise the lineage recorder construction path directly
rather than driving full ``start_workflow`` (which requires an asyncio
event loop and would race with the test runner).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from scistudio.core.lineage.record import RunRecord
from scistudio.workflow.definition import WorkflowDefinition


@pytest.fixture()
def runtime_with_project(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))

    app = create_app()
    with TestClient(app) as client:
        runtime = client.app.state.runtime
        parent_dir = tmp_path / "projects"
        parent_dir.mkdir()
        resp = client.post(
            "/api/projects/",
            json={"name": "RerunParent", "description": "", "path": str(parent_dir)},
        )
        assert resp.status_code == 200
        yield runtime


class TestBuildLineageRecorderParentRunId:
    def test_parent_run_id_recorded_in_runs_row(self, runtime_with_project) -> None:
        """When parent_run_id is passed, the runs row carries that link."""
        runtime = runtime_with_project
        if runtime.lineage_store is None:
            pytest.skip("lineage store unavailable in this environment")

        # Seed a parent run so the FK on parent_run_id is satisfied.
        runtime.lineage_store.insert_run(
            RunRecord(
                run_id="run-historical",
                workflow_id="main",
                workflow_yaml_snapshot="",
                started_at="2026-05-15T00:00:00",
                status="completed",
                environment_snapshot={},
            )
        )

        workflow = WorkflowDefinition(id="main")
        recorder = runtime._build_lineage_recorder(
            workflow_id="main",
            workflow=workflow,
            execute_from=None,
            parent_run_id="run-historical",
        )
        assert recorder is not None
        # Clean up subscriptions before next assertion lookup.
        recorder.dispose()

        rows = runtime.lineage_store.list_runs(workflow_id="main")
        latest = [r for r in rows if r["run_id"] == recorder.run_id]
        assert len(latest) == 1
        assert latest[0]["parent_run_id"] == "run-historical"

    def test_no_parent_run_id_when_unset(self, runtime_with_project) -> None:
        runtime = runtime_with_project
        if runtime.lineage_store is None:
            pytest.skip("lineage store unavailable in this environment")

        workflow = WorkflowDefinition(id="main")
        recorder = runtime._build_lineage_recorder(
            workflow_id="main",
            workflow=workflow,
            execute_from=None,
        )
        assert recorder is not None
        recorder.dispose()

        rows = runtime.lineage_store.list_runs(workflow_id="main")
        latest = [r for r in rows if r["run_id"] == recorder.run_id]
        assert len(latest) == 1
        assert latest[0]["parent_run_id"] is None
