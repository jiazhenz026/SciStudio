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

from scistudio.ai.agent.mcp.tools_plot.runtime import preview_cache_dir
from scistudio.api.runtime import ApiRuntime

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
            "def render(collection, context):\n"
            "    df = context.to_dataframe(collection, max_rows=1000)\n"
            "    fig, ax = context.plt.subplots()\n"
            "    ax.scatter(df['x'], df['y'], s=4)\n"
            "    return context.save_figure(fig, 'figure.svg')\n"
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
        "def render(collection, context):\n    raise ValueError('boom')\n",
        encoding="utf-8",
    )
    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "failed"
    assert body["data_ref"] is None
    assert body["errors"]
