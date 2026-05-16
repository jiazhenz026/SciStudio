"""Integration tests for ADR-038 §3.7 / §3.8 ``/api/runs`` endpoints.

These tests:

1. Open a project so the lineage store is initialised (see
   :func:`scieasy.api.deps.get_lineage_store`).
2. Seed lineage rows directly through the runtime's
   :attr:`ApiRuntime.lineage_store` handle (the routes don't expose a
   write endpoint — writes go through ``LineageRecorder``).
3. Hit the four routes and assert on shape + status code.

The ``POST /rerun`` test patches :meth:`ApiRuntime.start_workflow` to a
no-op stub so we don't spin up the scheduler / worker pool inside the
test. The routes layer is what's under test here, not the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(run_id: str, workflow_id: str = "image_pipeline", **overrides: Any) -> RunRecord:
    base = dict(
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_yaml_snapshot=f"id: {workflow_id}\n",
        started_at="2026-05-15T14:30:00Z",
        status="completed",
        environment_snapshot={"python": "3.13"},
        finished_at="2026-05-15T14:30:09Z",
    )
    base.update(overrides)
    return RunRecord(**base)


@pytest.fixture()
def seeded_project(client: TestClient, opened_project: Path) -> dict[str, Any]:
    """Open a project and seed one run + one block_execution into the lineage store."""
    runtime = client.app.state.runtime
    store = runtime.lineage_store
    assert store is not None, "lineage store should be initialised on project open"

    store.insert_run(_make_run("run-A"))
    store.insert_run(_make_run("run-B", workflow_id="other_workflow"))
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id="be-A-1",
            run_id="run-A",
            block_id="loader",
            block_type="proc",
            block_version="0.1.0",
            block_config_resolved={"path": "in.tif"},
            started_at="2026-05-15T14:30:01Z",
            finished_at="2026-05-15T14:30:05Z",
            duration_ms=4000,
            termination="completed",
        )
    )
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-1",
            type_name="DataFrame",
            wire_payload={"backend": "arrow", "path": "/proj/data/x.parquet"},
            created_at="2026-05-15T14:30:05Z",
            storage_path="/proj/data/x.parquet",
            produced_by_execution="be-A-1",
        )
    )
    store.insert_block_io(
        BlockIORow(
            block_execution_id="be-A-1",
            direction="output",
            port_name="result",
            object_id="obj-1",
            position=0,
        )
    )
    return {"project_dir": opened_project, "runtime": runtime, "store": store}


# ---------------------------------------------------------------------------
# GET /api/runs — list
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_returns_seeded_runs(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs")
        assert r.status_code == 200, r.text
        body = r.json()
        run_ids = [row["run_id"] for row in body["runs"]]
        assert "run-A" in run_ids
        assert "run-B" in run_ids
        assert body["offset"] == 0
        assert body["limit"] == 50
        assert body["has_more"] is False

    def test_filters_by_workflow_id(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs?workflow_id=image_pipeline")
        assert r.status_code == 200
        run_ids = [row["run_id"] for row in r.json()["runs"]]
        assert run_ids == ["run-A"]

    def test_pagination_offset_limit(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs?offset=0&limit=1")
        assert r.status_code == 200
        body = r.json()
        assert len(body["runs"]) == 1
        assert body["has_more"] is True

    def test_rejects_negative_offset(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs?offset=-1")
        assert r.status_code == 422

    def test_rejects_excessive_limit(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs?limit=10000")
        assert r.status_code == 422

    def test_requires_active_project(self, client: TestClient) -> None:
        """No project open → 400 from ``get_lineage_store``."""
        r = client.get("/api/runs")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id} — detail
# ---------------------------------------------------------------------------


class TestGetRun:
    def test_returns_run_and_block_executions(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/run-A")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run"]["run_id"] == "run-A"
        assert body["run"]["workflow_id"] == "image_pipeline"
        assert isinstance(body["block_executions"], list)
        assert len(body["block_executions"]) == 1
        assert body["block_executions"][0]["block_id"] == "loader"

    def test_inlines_block_io_inputs_outputs(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        """Hotfix #996: per-block I/O DataObjects must be inlined per ADR-038 §3.7 Q4b."""
        r = client.get("/api/runs/run-A")
        assert r.status_code == 200, r.text
        be = r.json()["block_executions"][0]
        # Both keys present (empty list if no rows).
        assert "inputs" in be and "outputs" in be
        # Seeded fixture has 1 output edge → "obj-1" / DataFrame.
        assert be["inputs"] == []
        assert len(be["outputs"]) == 1
        out = be["outputs"][0]
        assert out["port_name"] == "result"
        assert out["object_id"] == "obj-1"
        assert out["type_name"] == "DataFrame"
        assert out["storage_path"] == "/proj/data/x.parquet"
        # wire_payload is intentionally excluded from the response.
        assert "wire_payload" not in out

    def test_unknown_run_id_returns_404(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/does-not-exist")
        assert r.status_code == 404
        assert "does-not-exist" in r.json()["detail"]

    def test_empty_run_id_segment_routes_elsewhere(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        """``GET /api/runs/`` collapses to the list endpoint (trailing slash)."""
        r = client.get("/api/runs/")
        # FastAPI redirects /api/runs/ → /api/runs by default; either 200 or 307 is acceptable.
        assert r.status_code in (200, 307)

    def test_health_endpoint_not_shadowed_by_run_id_route(
        self, client: TestClient, seeded_project: dict[str, Any]
    ) -> None:
        """The literal ``/_health`` route must be matched before ``/{run_id}``."""
        r = client.get("/api/runs/_health")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"runs", "block_executions", "data_objects", "block_io"}


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}/methods — markdown
# ---------------------------------------------------------------------------


class TestGetRunMethods:
    def test_returns_markdown_body(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/run-A/methods")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/markdown")
        body = r.text
        assert body.startswith("# Methods")
        assert "run-A" in body
        assert "image_pipeline" in body
        assert "### `loader`" in body

    def test_unknown_run_returns_404(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/does-not-exist/methods")
        assert r.status_code == 404

    def test_content_type_advertises_utf8(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/run-A/methods")
        assert "charset" in r.headers["content-type"]

    def test_methods_body_includes_block_io(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        r = client.get("/api/runs/run-A/methods")
        # The single output object is surfaced in the **Outputs:** table.
        assert "**Outputs:**" in r.text
        assert "obj-1" in r.text


# ---------------------------------------------------------------------------
# POST /api/runs/{run_id}/rerun — queue new run
# ---------------------------------------------------------------------------


class TestRerunRun:
    @pytest.fixture(autouse=True)
    def patch_start_workflow(self, monkeypatch: pytest.MonkeyPatch, seeded_project: dict[str, Any]) -> dict[str, Any]:
        """Replace ``ApiRuntime.start_workflow`` with a deterministic stub.

        The route delegates to ``runtime.start_workflow``; we want to verify
        the route correctly threads ``execute_from_block_id`` through and
        surfaces the result, not actually spin up the scheduler.
        """
        calls: list[dict[str, Any]] = []
        runtime = seeded_project["runtime"]

        def _fake_start(
            self: Any,
            workflow_id: str,
            *,
            execute_from: str | None = None,
            parent_run_id: str | None = None,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "workflow_id": workflow_id,
                    "execute_from": execute_from,
                    "parent_run_id": parent_run_id,
                }
            )
            return {
                "workflow_id": workflow_id,
                "status": "started",
                "message": "stubbed",
                "reused_blocks": [],
                "reset_blocks": [],
            }

        monkeypatch.setattr(type(runtime), "start_workflow", _fake_start)
        return {"calls": calls}

    def test_returns_started_envelope(
        self, client: TestClient, seeded_project: dict[str, Any], patch_start_workflow: dict[str, Any]
    ) -> None:
        r = client.post("/api/runs/run-A/rerun", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rerun_of"] == "run-A"
        assert body["workflow_id"] == "image_pipeline"
        assert body["execute_from_block_id"] is None
        assert body["result"]["status"] == "started"
        # D38-3.2: rerun route stamps the historical run_id as the new
        # run's parent_run_id (closes D38-3.1a P2 / D38-3.1b P2-4).
        assert patch_start_workflow["calls"] == [
            {"workflow_id": "image_pipeline", "execute_from": None, "parent_run_id": "run-A"}
        ]

    def test_threads_execute_from_block_id(
        self, client: TestClient, seeded_project: dict[str, Any], patch_start_workflow: dict[str, Any]
    ) -> None:
        r = client.post(
            "/api/runs/run-A/rerun",
            json={"execute_from_block_id": "preprocess"},
        )
        assert r.status_code == 200, r.text
        assert patch_start_workflow["calls"] == [
            {"workflow_id": "image_pipeline", "execute_from": "preprocess", "parent_run_id": "run-A"}
        ]

    def test_unknown_run_returns_404(
        self, client: TestClient, seeded_project: dict[str, Any], patch_start_workflow: dict[str, Any]
    ) -> None:
        r = client.post("/api/runs/no-such/rerun", json={})
        assert r.status_code == 404

    def test_value_error_surfaces_as_400(
        self,
        client: TestClient,
        seeded_project: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``ApiRuntime.start_workflow`` raises ``ValueError`` when execute_from has no checkpoint."""
        runtime = seeded_project["runtime"]

        def _raises(
            self: Any,
            workflow_id: str,
            *,
            execute_from: str | None = None,
            parent_run_id: str | None = None,
        ) -> dict[str, Any]:
            raise ValueError("Run the full workflow at least once before using 'Run from here'")

        monkeypatch.setattr(type(runtime), "start_workflow", _raises)
        r = client.post("/api/runs/run-A/rerun", json={"execute_from_block_id": "B"})
        assert r.status_code == 400
        assert "Run from here" in r.json()["detail"]

    def test_missing_workflow_yaml_returns_404(
        self,
        client: TestClient,
        seeded_project: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime = seeded_project["runtime"]

        def _raises(
            self: Any,
            workflow_id: str,
            *,
            execute_from: str | None = None,
            parent_run_id: str | None = None,
        ) -> dict[str, Any]:
            raise FileNotFoundError(f"workflow {workflow_id} not found")

        monkeypatch.setattr(type(runtime), "start_workflow", _raises)
        r = client.post("/api/runs/run-A/rerun", json={})
        assert r.status_code == 404

    def test_rejects_invalid_body_type(
        self, client: TestClient, seeded_project: dict[str, Any], patch_start_workflow: dict[str, Any]
    ) -> None:
        """Non-string ``execute_from_block_id`` is rejected by pydantic."""
        r = client.post("/api/runs/run-A/rerun", json={"execute_from_block_id": 12345})
        assert r.status_code == 422
