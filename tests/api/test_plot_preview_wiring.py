"""End-to-end producer -> consumer wiring tests for ADR-048 SPEC 2 plot previews.

Issue #1606 (P0): the original SPEC 2 implementation left the plot-preview path
DEAD-WIRED. ``run_plot_job`` wrote a display artifact to the preview cache, but
NOTHING registered that artifact so the routed
:class:`~scistudio.previewers.PreviewService` could reach the core
``PlotPreviewer`` (``core.plot.basic``) at runtime — there was no API route, no
catalog registration, and no UI trigger. The pre-existing unit test
(``test_preview_plot_jobs.test_artifact_consumable_by_plot_previewer``) called
``plot_previewer`` DIRECTLY with a hand-built request, proving only that the
viewer *can* render a file — exactly the gap that let the dead-wire ship.

These tests exercise the REAL wiring with NO mocks of the wiring itself:

    run_plot_job (producer)
      -> POST /api/plots/run  (the new route)
        -> ApiRuntime.register_plot_artifact  (catalog registration)
          -> POST /api/previews/sessions  (routed PreviewService)
            -> PreviewRouter resolves core.plot.basic
              -> plot_previewer renders a PLOT envelope  (the consumer)

If any link in that chain is missing or mis-wired, these tests fail. They are
the mandatory end-to-end proof that a produced plot artifact actually reaches
the PlotPreviewer at runtime (FR-031 / SC-010).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.plot.runtime import preview_cache_dir

pytest.importorskip("pandas")
pytest.importorskip("matplotlib")


# ---------------------------------------------------------------------------
# Minimal real scheduler-output state. ``run_plot_job`` reads the bound
# target's latest recorded output from ``ctx.workflow_runs[*].scheduler.
# _block_outputs`` (read-only). The lifespan installs the live ApiRuntime as
# the MCP context, so we seed a recorded output directly on the runtime — the
# same shape the engine emits — and let the REAL route/runtime do everything
# else.
# ---------------------------------------------------------------------------


class _StubScheduler:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self._block_outputs = block_outputs


class _DoneTask:
    """Mimics the ``asyncio.Task`` surface the runtime + lifespan teardown read.

    ``_BoundedRegistry``'s eviction predicate and the app-lifespan teardown both
    call ``run.task.done()``; a finished task is a no-op for both.
    """

    def done(self) -> bool:
        return True

    def cancel(self) -> bool:  # pragma: no cover - teardown never cancels a done task
        return False


class _StubRun:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self.scheduler = _StubScheduler(block_outputs)
        self.task = _DoneTask()


def _seed_block_output(runtime: ApiRuntime, project: Path) -> None:
    """Record a CSV block output for node_a/measurements (the plot target)."""
    csv = project / "measurements.csv"
    csv.write_text("x,y\n" + "\n".join(f"{i},{i * 2}" for i in range(20)), encoding="utf-8")
    runtime.workflow_runs["run_1"] = _StubRun(  # type: ignore[assignment]
        {
            "node_a": {
                "measurements": {
                    "backend": "filesystem",
                    "path": str(csv),
                    "format": "csv",
                    "metadata": {"type_chain": ["DataFrame"]},
                }
            }
        }
    )


def _write_workflow_and_plot(client: TestClient, project: Path) -> None:
    """Create a workflow + a ``plots/p1`` manifest whose render writes an SVG.

    The manifest is written directly (the exact shape ``scaffold_plot`` emits)
    so the plot binds to ``main / node_a / measurements`` without depending on a
    ``demo.segment`` block spec being registered in this environment — the plot
    runtime resolves its input from the recorded scheduler output by node id +
    port, not from the block registry.
    """
    wf_dir = project / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "main.yaml").write_text(
        "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_a\n    block_type: demo.segment\n    config:\n      label: Seg\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    plot_dir = project / "plots" / "p1"
    plot_dir.mkdir(parents=True, exist_ok=True)
    (plot_dir / "plot.yaml").write_text(
        "schema_version: 1\n"
        "id: p1\n"
        "title: P1\n"
        "target:\n"
        "  workflow_path: workflows/main.yaml\n"
        "  workflow_id: main\n"
        "  node_id: node_a\n"
        "  output_port: measurements\n"
        "  display_label: Seg / measurements\n"
        "script:\n"
        "  language: python\n"
        "  path: render.py\n"
        "  entrypoint: render\n",
        encoding="utf-8",
    )
    (plot_dir / "render.py").write_text(
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    df = collection.items.open_one()\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.scatter(df['x'], df['y'], s=4)\n"
            "    return fig\n"
        ),
        encoding="utf-8",
    )


def test_plot_run_route_registers_artifact_and_preview_session_renders_plot(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """The whole chain: run route -> catalog reg -> preview session -> PLOT envelope.

    This is the regression guard for the #1606 dead-wire: it fails if the run
    route does not exist, does not register the artifact, the record is not
    classified as a plot_artifact target, the router does not resolve
    core.plot.basic, or the PlotPreviewer does not render the produced SVG.
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    catalog_count_before = len(runtime.data_catalog)

    # 1. Producer: run the plot job through the NEW route.
    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "succeeded", body
    data_ref = body["data_ref"]
    assert data_ref, "the run route must register the artifact and return a catalog data_ref"
    assert body["cache_key"]
    assert body["recorded_type"] == "PlotArtifact"
    assert body["source"]["node_id"] == "node_a"
    assert body["source"]["output_port"] == "measurements"
    assert data_ref in runtime.data_catalog
    assert len(runtime.data_catalog) == catalog_count_before + 1

    # The artifact really exists on disk at the FR-026 cache layout.
    cache_dir = preview_cache_dir(opened_project, "main", "node_a", "measurements", "p1")
    assert (cache_dir / "current.svg").is_file()

    # 2. Consumer: open a routed preview session with the returned data_ref.
    #    This is the exact call the frontend PreviewHost makes; it must resolve
    #    the core PlotPreviewer and render a PLOT envelope.
    session = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "plot_artifact",
                "ref": data_ref,
                "recorded_type": body["recorded_type"],
                "type_chain": body["type_chain"],
                "source": body["source"],
            },
            "query": {},
        },
    )
    assert session.status_code == 200, session.text
    env = session.json()
    # The produced artifact reaches the PlotPreviewer at runtime (FR-031/SC-010).
    assert env["previewer_id"] == "core.plot.basic", env
    assert env["kind"] == "plot", env
    assert env["payload"]["format"] == "svg"
    # SVG is sanitized + embedded inline by the previewer (sandboxed).
    assert env["payload"]["sandboxed"] is True
    assert "svg" in env["payload"]
    # Export resource is offered so the user can save the figure.
    assert any(r["resource_id"] == "export" for r in env["resources"])


def test_plot_list_route_filters_manifests_to_selected_block(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """The App Shell can discover plots bound to the selected block."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    plot_dir = opened_project / "plots" / "p2"
    plot_dir.mkdir(parents=True, exist_ok=True)
    (plot_dir / "plot.yaml").write_text(
        "schema_version: 1\n"
        "id: p2\n"
        "title: P2\n"
        "target:\n"
        "  workflow_path: workflows/main.yaml\n"
        "  workflow_id: main\n"
        "  node_id: node_b\n"
        "  output_port: other\n"
        "  display_label: Other / other\n"
        "script:\n"
        "  language: python\n"
        "  path: render.py\n"
        "  entrypoint: render\n",
        encoding="utf-8",
    )
    (plot_dir / "render.py").write_text("def render(collection):\n    return None\n", encoding="utf-8")

    resp = client.get("/api/plots", params={"workflow_id": "main", "node_id": "node_a"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["plots"][0]["plot_id"] == "p1"
    assert body["plots"][0]["node_id"] == "node_a"
    assert body["plots"][0]["output_port"] == "measurements"


def test_plot_list_route_flags_broken_target_after_node_deleted(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """bug#7 / PR #1712: list_plots flags a plot whose bound node was deleted.

    The app shell uses this ``broken`` flag to surface a relink entry point for
    plots whose source block was deleted/recreated (their old node_id vanishes).
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    # While node_a still exists, p1 is healthy.
    healthy = client.get("/api/plots", params={"workflow_id": "main"})
    assert healthy.status_code == 200, healthy.text
    p1_healthy = next(p for p in healthy.json()["plots"] if p["plot_id"] == "p1")
    assert p1_healthy["broken"] is False
    # #1721: the bound port's core type is surfaced for the plot card. The
    # ``demo.segment`` block is intentionally unregistered in this environment,
    # so resolution degrades to an empty string rather than erroring.
    assert "output_type" in p1_healthy
    assert p1_healthy["output_type"] == ""

    # Delete/recreate the source block: node_a is replaced by a fresh node id,
    # so the plot's bound target no longer resolves.
    (opened_project / "workflows" / "main.yaml").write_text(
        "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_fresh\n    block_type: demo.segment\n    config:\n      label: Seg\n"
        "  edges: []\n",
        encoding="utf-8",
    )

    broken = client.get("/api/plots", params={"workflow_id": "main"})
    assert broken.status_code == 200, broken.text
    p1_broken = next(p for p in broken.json()["plots"] if p["plot_id"] == "p1")
    assert p1_broken["broken"] is True
    # A broken target resolves to no type; the field stays an empty string.
    assert p1_broken["output_type"] == ""


def test_plot_create_route_scaffolds_manifest_and_render_script(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """The app shell can create a new plot from a selected workflow output target."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    targets = client.get("/api/plots/targets", params={"workflow_id": "main"})
    assert targets.status_code == 200, targets.text
    body = targets.json()
    assert body["count"] >= 1
    target_id = body["targets"][0]["target_id"]

    created = client.post(
        "/api/plots",
        json={
            "plot_id": "quick_plot",
            "target_id": target_id,
            "title": "Quick Plot",
            "language": "python",
        },
    )

    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["plot_id"] == "quick_plot"
    assert payload["manifest_path"] == "plots/quick_plot/plot.yaml"
    assert payload["script_path"] == "plots/quick_plot/render.py"
    manifest = opened_project / "plots" / "quick_plot" / "plot.yaml"
    script = opened_project / "plots" / "quick_plot" / "render.py"
    assert manifest.is_file()
    assert script.is_file()
    manifest_text = manifest.read_text(encoding="utf-8")
    assert "id: quick_plot" in manifest_text
    assert "title: Quick Plot" in manifest_text
    assert "node_id:" in manifest_text
    script_text = script.read_text(encoding="utf-8")
    assert "def render(collection):" in script_text
    assert "context" not in script_text


def test_plot_relink_route_rebinds_manifest_target(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """bug#7: POST /api/plots/{id}/relink re-points a plot at a new target.

    Simulates deleting the original block and creating a fresh identical one
    (new node id), which leaves the plot's target broken, then relinks the plot
    to the new target and asserts the manifest target is rewritten and valid.
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    # Replace node_a with a fresh identical node (new id) — the plot's bound
    # target node_a no longer exists.
    (opened_project / "workflows" / "main.yaml").write_text(
        "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_fresh\n    block_type: demo.segment\n    config:\n      label: Seg\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    runtime.workflow_runs["run_1"] = _StubRun(  # type: ignore[assignment]
        {
            "node_fresh": {
                "measurements": {
                    "backend": "filesystem",
                    "path": str(opened_project / "measurements.csv"),
                    "format": "csv",
                    "metadata": {"type_chain": ["DataFrame"]},
                }
            }
        }
    )

    targets = client.get("/api/plots/targets", params={"workflow_id": "main"})
    assert targets.status_code == 200, targets.text
    # ``demo.segment`` is not a registered block in this environment, so
    # discovery emits the node's target keyed on the synthetic 'output' port.
    new_target = next(t for t in targets.json()["targets"] if t["node_id"] == "node_fresh")
    new_port = new_target["output_port"]

    resp = client.post("/api/plots/p1/relink", json={"target_id": new_target["target_id"]})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plot_id"] == "p1"
    assert body["manifest_path"] == "plots/p1/plot.yaml"
    assert body["target"]["node_id"] == "node_fresh"
    assert body["target"]["output_port"] == new_port
    assert body["valid"] is True, body["errors"]
    # The manifest on disk now binds to the fresh node.
    manifest_text = (opened_project / "plots" / "p1" / "plot.yaml").read_text(encoding="utf-8")
    assert "node_id: node_fresh" in manifest_text


def test_plot_relink_route_unknown_target_returns_400(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    resp = client.post("/api/plots/p1/relink", json={"target_id": "tgt_nope"})

    assert resp.status_code == 400
    assert "unknown target_id" in resp.json()["detail"]


def test_plot_relink_route_unknown_plot_returns_404(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    targets = client.get("/api/plots/targets", params={"workflow_id": "main"})
    assert targets.status_code == 200, targets.text
    target_id = targets.json()["targets"][0]["target_id"]

    resp = client.post("/api/plots/does-not-exist/relink", json={"target_id": target_id})

    assert resp.status_code == 404


def test_plot_preview_resource_save_writes_export_to_user_selected_path(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Save/export uses the session resource path and writes the selected file."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    session = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "plot_artifact",
                "ref": body["data_ref"],
                "recorded_type": body["recorded_type"],
                "type_chain": body["type_chain"],
                "source": body["source"],
            },
            "query": {},
        },
    )
    assert session.status_code == 200, session.text
    env = session.json()
    sid = env["session_id"]
    export_dir = opened_project / "exports"
    export_dir.mkdir()
    destination = export_dir / "chosen-name.svg"

    save = client.post(
        f"/api/previews/sessions/{sid}/resources/export/save",
        json={"destination_path": str(destination), "params": {"format": "svg"}},
    )

    assert save.status_code == 200, save.text
    payload = save.json()
    assert payload["path"] == str(destination.resolve())
    assert payload["filename"] == "chosen-name.svg"
    assert payload["mime_type"] == "image/svg+xml"
    assert destination.is_file()
    assert "<svg" in destination.read_text(encoding="utf-8")


def test_plot_preview_resource_save_rejects_relative_destination_path(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Save/export must not treat malformed native-dialog paths as cwd-relative files."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    session = client.post(
        "/api/previews/sessions",
        json={
            "target": {
                "kind": "plot_artifact",
                "ref": body["data_ref"],
                "recorded_type": body["recorded_type"],
                "type_chain": body["type_chain"],
                "source": body["source"],
            },
            "query": {},
        },
    )
    assert session.status_code == 200, session.text
    sid = session.json()["session_id"]

    save = client.post(
        f"/api/previews/sessions/{sid}/resources/export/save",
        json={
            "destination_path": "file Macintosh HD:Users:jiazhenz:Desktop:spectrum.svg",
            "params": {"format": "svg"},
        },
    )

    assert save.status_code == 400
    assert "absolute file path" in save.json()["detail"]


def test_registered_plot_artifact_classifies_as_plot_target(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """``register_plot_artifact`` stamps the record so it routes to PLOT_ARTIFACT.

    Guards the catalog-classification half of the wiring: the record carries the
    ``plot_artifact`` metadata flag and ``type_name='PlotArtifact'`` so
    ``_target_kind_for_record`` returns ``TargetKind.PLOT_ARTIFACT`` and the
    routed query is enriched with the artifact's ``_storage``.
    """
    from scistudio.api.runtime._data import _target_kind_for_record
    from scistudio.previewers import TargetKind

    svg = opened_project / "out.svg"
    svg.write_text("<svg><rect width='1' height='1'/></svg>", encoding="utf-8")
    record = runtime.register_plot_artifact(
        svg,
        cache_key="plot_abc",
        workflow_id="main",
        node_id="node_a",
        output_port="measurements",
        plot_id="p1",
    )
    assert record.type_name == "PlotArtifact"
    assert record.metadata["plot_artifact"] is True
    assert record.metadata["source"]["node_id"] == "node_a"
    assert _target_kind_for_record(record, None) is TargetKind.PLOT_ARTIFACT

    # enrich_preview_query supplies the artifact storage the previewer reads.
    enriched = runtime.enrich_preview_query(record.id, {})
    # StorageReference normalizes path separators; compare resolved paths.
    assert Path(enriched["_storage"]["path"]) == svg


def test_plot_run_route_unknown_plot_returns_404(
    client: TestClient,
    opened_project: Path,
) -> None:
    resp = client.post("/api/plots/run", json={"plot_id": "does-not-exist"})
    assert resp.status_code == 404


def test_failed_plot_run_returns_status_without_data_ref(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A failing render returns failure status and NO data_ref (no empty preview)."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    # Overwrite the render with one that raises.
    (opened_project / "plots" / "p1" / "render.py").write_text(
        "def render(collection):\n    raise ValueError('boom')\n",
        encoding="utf-8",
    )
    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "failed"
    assert body["data_ref"] is None
    assert body["errors"]


def test_plot_run_offloads_blocking_job_off_the_event_loop(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route runs the blocking plot job in a worker thread, not the loop.

    Regression guard for the Codex review on #1606: ``run_plot_job`` launches a
    render subprocess and blocks for up to the absolute timeout, so the async
    handler offloads it via ``starlette.concurrency.run_in_threadpool``. If a
    future edit calls ``run_plot_job`` directly on the event loop again, this
    test fails because the job would execute on the main thread.
    """
    import threading

    from scistudio.plot import runtime as plot_runtime

    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    main_thread_id = threading.get_ident()
    seen: dict[str, int] = {}
    real_run_plot_job = plot_runtime.run_plot_job

    def _spy(*args: Any, **kwargs: Any) -> Any:
        seen["thread_id"] = threading.get_ident()
        return real_run_plot_job(*args, **kwargs)

    monkeypatch.setattr(plot_runtime, "run_plot_job", _spy)

    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "succeeded"
    # The blocking job ran on a worker thread, not the event-loop thread.
    assert "thread_id" in seen, "run_plot_job was not invoked"
    assert seen["thread_id"] != main_thread_id
