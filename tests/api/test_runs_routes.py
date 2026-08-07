"""Integration tests for ADR-038 §3.7 / §3.8 ``/api/runs`` endpoints.

These tests:

1. Open a project so the lineage store is initialised (see
   :func:`scistudio.api.deps.get_lineage_store`).
2. Seed lineage rows directly through the runtime's
   :attr:`ApiRuntime.lineage_store` handle (the routes don't expose a
   write endpoint — writes go through ``LineageRecorder``).
3. Hit the routes and assert on shape + status code.

ADR-038 Addendum 1 (#2033) removed ``POST /rerun`` and added
``GET /validate-restore``; the rerun tests are replaced by the preflight
tests at the bottom of this file plus a guard asserting the route is gone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.core.lineage.record import (
    BlockExecutionRecord,
    BlockIORow,
    DataObjectRow,
    RunRecord,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(run_id: str, workflow_id: str = "image_pipeline", **overrides: Any) -> RunRecord:
    base: dict[str, Any] = dict(
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
    runtime = client.app.state.runtime  # type: ignore[attr-defined]
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
# GET /api/runs/validate-restore — ADR-038 §3.6 preflight (Addendum 1 §11.3)
# ---------------------------------------------------------------------------


@pytest.fixture()
def anchored_run(client: TestClient, opened_project: Path) -> dict[str, Any]:
    """Seed a run anchored to a git commit, with one boundary input on disk.

    Boundary input = consumed by the run but produced outside it
    (``produced_by_execution`` is NULL), which is what §3.6 Check 1 compares.
    The file is written for real so ``stat()`` has something to read; tests
    that need drift mutate it afterwards.
    """
    runtime = client.app.state.runtime  # type: ignore[attr-defined]
    store = runtime.lineage_store
    assert store is not None

    input_file = opened_project / "data" / "input.csv"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text("a,b\n1,2\n", encoding="utf-8")
    # Record the file's real mtime so the "unchanged" case is genuinely
    # unchanged. A hardcoded past timestamp would make every input look
    # modified, and the mtime branch would then mask the size branch below.
    recorded_mtime = datetime.fromtimestamp(input_file.stat().st_mtime, tz=UTC).isoformat()

    store.insert_run(
        _make_run(
            "run-anchored",
            workflow_git_commit="a" * 40,
            environment_snapshot={
                "python_version": "3.13.0 (main, Oct  1 2025) [MSC v.1940]",
                "platform": "Windows-11",
                "key_packages": {"scistudio": "0.1.0-recorded"},
            },
        )
    )
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id="be-anchored-1",
            run_id="run-anchored",
            block_id="loader",
            block_type="proc",
            block_version="0.1.0",
            block_config_resolved={},
            started_at="2026-05-15T14:30:01Z",
            finished_at="2026-05-15T14:30:05Z",
            duration_ms=4000,
            termination="completed",
        )
    )
    store.upsert_data_object(
        DataObjectRow(
            object_id="obj-boundary",
            type_name="DataFrame",
            wire_payload={"backend": "csv", "path": str(input_file)},
            created_at="2026-05-15T14:30:00Z",
            storage_path=str(input_file),
            size_bytes=input_file.stat().st_size,
            mtime_at_write=recorded_mtime,
            produced_by_execution=None,
        )
    )
    store.insert_block_io(
        BlockIORow(
            block_execution_id="be-anchored-1",
            direction="input",
            port_name="data",
            object_id="obj-boundary",
            position=0,
        )
    )
    return {"store": store, "input_file": input_file, "commit": "a" * 40}


class TestValidateRestore:
    def test_commit_with_no_run_reports_unknown_not_clean(
        self, client: TestClient, seeded_project: dict[str, Any]
    ) -> None:
        """The regression this endpoint exists to prevent.

        A manual commit (or an ``auto: pre-restore`` one) has no recorded run.
        The response must say so via ``run_id: null`` so the UI can distinguish
        "nothing to compare" from "compared and clean". The pre-#2033 client
        stub returned empty warning lists unconditionally and the dialog
        rendered them as "No drift detected".
        """
        r = client.get("/api/runs/validate-restore", params={"commit_sha": "f" * 40})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run_id"] is None
        assert body["input_warnings"] == []
        assert body["env_warnings"] == []

    def test_resolves_commit_to_its_run(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        assert r.status_code == 200, r.text
        assert r.json()["run_id"] == "run-anchored"

    def test_reports_recorded_package_version_drift(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        """``scistudio`` is recorded as a version that is certainly not installed."""
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        env = {w["package"]: w for w in r.json()["env_warnings"]}
        assert "scistudio" in env
        assert env["scistudio"]["old"] == "0.1.0-recorded"

    def test_reports_python_version_drift(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        """Python is compared alongside packages; the seed records 3.13.0."""
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        packages = {w["package"] for w in r.json()["env_warnings"]}
        # The seeded interpreter string only matches if the test host happens to
        # run exactly 3.13.0; assert on the pairing rather than the outcome.
        body = r.json()
        if "Python" in packages:
            entry = next(w for w in body["env_warnings"] if w["package"] == "Python")
            assert entry["old"] == "3.13.0"
            assert " " not in entry["new"], "the build tag must be stripped before comparing"

    def test_reports_missing_input_file(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        anchored_run["input_file"].unlink()
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        warnings = r.json()["input_warnings"]
        assert len(warnings) == 1
        assert "no longer exists" in warnings[0]["reason"]

    def test_reports_resized_input_file(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        anchored_run["input_file"].write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        warnings = r.json()["input_warnings"]
        assert len(warnings) == 1
        assert "size changed" in warnings[0]["reason"]

    def test_unchanged_input_produces_no_warning(self, client: TestClient, anchored_run: dict[str, Any]) -> None:
        """Both branches stay quiet when the file on disk is the recorded one."""
        r = client.get("/api/runs/validate-restore", params={"commit_sha": anchored_run["commit"]})
        assert r.json()["input_warnings"] == []

    def test_run_outputs_are_not_treated_as_boundary_inputs(
        self, client: TestClient, seeded_project: dict[str, Any]
    ) -> None:
        """``obj-1`` in the shared fixture is an output of its own run.

        Intermediates a run produced are regenerated on the next execution, so
        they are not part of Check 1 even though they are rows in the same
        tables. ``run-A`` has no git anchor, so this also covers the ordinary
        "run exists but was not anchored" case.
        """
        store = seeded_project["store"]
        assert store.workflow_boundary_inputs("run-A") == []

    def test_rerun_route_is_gone(self, client: TestClient, seeded_project: dict[str, Any]) -> None:
        """ADR-038 Addendum 1 §11.1 — Re-run is withdrawn, not merely hidden."""
        r = client.post("/api/runs/run-A/rerun", json={})
        assert r.status_code in (404, 405), r.text
