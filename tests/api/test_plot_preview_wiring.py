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
              -> the mounted plot panel reads the artifact  (the consumer)

The last link ends one hop further on than it used to. ``core.plot.basic`` is a
sandboxed HTML panel now (ADR-054 Phase B), so the session envelope names the
panel to mount and the figure itself is fetched by the panel through
``/api/panels/contexts`` reads. The chain being guarded is the same one; the
proof that it reaches the figure is a read rather than a payload.

If any link in that chain is missing or mis-wired, these tests fail. They are
the mandatory end-to-end proof that a produced plot artifact actually reaches
its previewer at runtime (FR-031 / SC-010).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
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


# #2362: ``workflow_runs`` is keyed by WORKFLOW ID — that is what
# ``ApiRuntime.start_workflow`` registers a run under, and what the plot layer,
# ``get_run`` and ``cancel_run`` all look one up by. The invented ``"run_1"``
# key only worked while the plot layer scanned every run and matched on
# ``(node_id, output_port)`` alone. These fixtures write the workflow ``main``.
_WORKFLOW_ID = "main"


class _StubRun:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self.scheduler = _StubScheduler(block_outputs)
        self.task = _DoneTask()


def _seed_block_output(runtime: ApiRuntime, project: Path) -> None:
    """Record a CSV block output for node_a/measurements (the plot target)."""
    csv = project / "measurements.csv"
    csv.write_text("x,y\n" + "\n".join(f"{i},{i * 2}" for i in range(20)), encoding="utf-8")
    runtime.workflow_runs[_WORKFLOW_ID] = _StubRun(  # type: ignore[assignment]
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


def _panel_context(client: TestClient, *, ref: str, kind: str = "plot_artifact") -> str:
    """Open the panel context a mounted plot panel reads through.

    A core previewer is a panel now, so the figure a session used to carry in
    its payload is fetched by the panel itself. Tests that pinned the rendered
    format, the bytes, or the Save choice follow the same path the frame does.
    """
    response = client.post("/api/panels/contexts", json={"kind": "preview", "target": {"kind": kind, "ref": ref}})
    assert response.status_code == 200, response.text
    return str(response.json()["context_id"])


def _panel_read(
    client: TestClient, context_id: str, ref: str, op: str, params: dict[str, Any] | None = None
) -> httpx.Response:
    return client.post(
        f"/api/panels/contexts/{context_id}/read",
        json={"ref": ref, "op": op, "params": params or {}},
    )


def test_plot_run_route_registers_artifact_and_preview_session_renders_plot(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """The whole chain: run route -> catalog reg -> preview session -> the figure.

    This is the regression guard for the #1606 dead-wire: it fails if the run
    route does not exist, does not register the artifact, the record is not
    classified as a plot_artifact target, the router does not resolve
    core.plot.basic, or the produced SVG never reaches the panel that shows it.
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
    #    the core plot previewer and answer with the panel to mount.
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
    # The produced artifact reaches the core plot previewer at runtime
    # (FR-031/SC-010). The envelope names the panel to mount; the figure arrives
    # through the panel's own reads, so the rest of the chain is checked there.
    assert env["previewer_id"] == "core.plot.basic", env
    assert env["kind"] == "panel", env
    assert env["panel"]["id"] == "core.plot.basic"

    # 3. The panel opens a read context on the same target. Saving the figure
    #    was an `export` session resource the envelope advertised; a sandboxed
    #    frame cannot run a file dialog, so the host offers it as a context
    #    service instead — the same capability, moved to the side that has it.
    opened = client.post(
        "/api/panels/contexts",
        json={"kind": "preview", "target": {"kind": "plot_artifact", "ref": data_ref}},
    )
    assert opened.status_code == 200, opened.text
    context = opened.json()
    assert context["panel"]["id"] == "core.plot.basic"
    assert "save" in context["services"]

    # 4. The read reaches the SVG the render really produced: the preferred
    #    format is the primary the panel is handed, and asking for it grants a
    #    URL that serves those bytes. The scrubbing applied on the way out is
    #    pinned against the serving route itself, in
    #    tests/panels/test_plot_artifact_reads.py::TestServedSvg.
    info = _panel_read(client, context["context_id"], data_ref, "artifact.info").json()
    assert info["name"] == "current.svg"
    assert info["mime_type"] == "image/svg+xml"

    granted = _panel_read(client, context["context_id"], data_ref, "artifact.file", {"variant": "svg"})
    assert granted.status_code == 200, granted.text
    served = client.get(granted.json()["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in served.text


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


def test_plot_delete_route_removes_manifest_and_render_script(
    client: TestClient,
    opened_project: Path,
) -> None:
    """DELETE removes the confined plot directory and the plot disappears from the list."""
    _write_workflow_and_plot(client, opened_project)
    plot_dir = opened_project / "plots" / "p1"
    assert (plot_dir / "plot.yaml").is_file()
    assert (plot_dir / "render.py").is_file()

    deleted = client.delete("/api/plots/p1")

    assert deleted.status_code == 204, deleted.text
    assert not plot_dir.exists()
    listed = client.get("/api/plots", params={"workflow_id": "main"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["plots"] == []


def test_plot_delete_route_rejects_invalid_or_unknown_ids(
    client: TestClient,
    opened_project: Path,
) -> None:
    """Invalid ids cannot escape plots/, and unknown valid ids return 404."""
    _write_workflow_and_plot(client, opened_project)

    invalid = client.delete("/api/plots/bad!id")
    unknown = client.delete("/api/plots/does-not-exist")

    assert invalid.status_code == 400, invalid.text
    assert unknown.status_code == 404, unknown.text
    assert (opened_project / "plots" / "p1" / "render.py").is_file()


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
    runtime.workflow_runs[_WORKFLOW_ID] = _StubRun(  # type: ignore[assignment]
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


def _run_and_open_session(client: TestClient) -> tuple[str, dict[str, Any]]:
    """Run p1 and open a preview session; return (session_id, envelope)."""
    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "succeeded", body
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
    return env["session_id"], env


def test_plot_run_renders_all_allowed_formats_as_siblings(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Approach B (#1918): a figure run writes one cache sibling per allowed format.

    The preview still uses the preferred (svg) primary, but pdf/png/jpg siblings
    exist so Save/Export can produce a valid file in any of them without
    re-rendering (the figure is closed immediately after render).
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)

    run = client.post("/api/plots/run", json={"plot_id": "p1"})
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "succeeded"

    cache_dir = preview_cache_dir(opened_project, "main", "node_a", "measurements", "p1")
    for name in ("current.svg", "current.pdf", "current.png", "current.jpg"):
        assert (cache_dir / name).is_file(), name
    # Magic bytes confirm the siblings are genuinely re-rendered, not renamed SVG.
    assert (cache_dir / "current.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (cache_dir / "current.pdf").read_bytes()[:5] == b"%PDF-"


def test_plot_preview_exposes_available_formats(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """The formats the run rendered are the ones the Save menu may offer.

    The compiled viewer was handed the set in its payload. A panel cannot glob
    the cache directory from inside its frame, so it asks: ``artifact.info``
    reports the formats that exist beside the primary, in the order the menu
    presents them. The promise the product makes is unchanged — the menu never
    lists a format the run did not write.
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    _sid, env = _run_and_open_session(client)
    ref = env["target"]["ref"]

    context = _panel_context(client, ref=ref)
    info = _panel_read(client, context, ref, "artifact.info").json()
    # Canonical Save-menu order rather than directory order, and the primary the
    # panel shows is the manifest's preferred format.
    assert info["formats"] == ["svg", "pdf", "png", "jpeg"]
    assert info["name"] == "current.svg"


@pytest.mark.parametrize(
    ("fmt", "ext", "magic"),
    [
        ("pdf", "pdf", b"%PDF-"),
        ("png", "png", b"\x89PNG\r\n\x1a\n"),
    ],
)
def test_plot_save_in_chosen_format_writes_valid_file(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    fmt: str,
    ext: str,
    magic: bytes,
) -> None:
    """Saving as pdf/png writes the matching sibling's real bytes, not the SVG."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    sid, _env = _run_and_open_session(client)

    export_dir = opened_project / "exports"
    export_dir.mkdir()
    destination = export_dir / f"chosen.{ext}"
    save = client.post(
        f"/api/previews/sessions/{sid}/resources/export/save",
        json={"destination_path": str(destination), "params": {"format": fmt}},
    )
    assert save.status_code == 200, save.text
    assert destination.is_file()
    assert destination.read_bytes()[: len(magic)] == magic


def test_plot_save_jpeg_resolves_jpg_sibling(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A jpeg request resolves the on-disk .jpg sibling and writes JPEG bytes."""
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    sid, _env = _run_and_open_session(client)

    export_dir = opened_project / "exports"
    export_dir.mkdir()
    destination = export_dir / "chosen.jpg"
    save = client.post(
        f"/api/previews/sessions/{sid}/resources/export/save",
        json={"destination_path": str(destination), "params": {"format": "jpeg"}},
    )
    assert save.status_code == 200, save.text
    assert destination.is_file()
    # JPEG SOI marker.
    assert destination.read_bytes()[:2] == b"\xff\xd8"


def test_plot_save_unrendered_format_errors_cleanly(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Requesting a format that was not rendered errors, never writes a corrupt file.

    The plot's manifest allows only svg/png, so a pdf save must be rejected with
    a clear error rather than dumping the primary bytes under a .pdf extension.
    """
    _seed_block_output(runtime, opened_project)
    _write_workflow_and_plot(client, opened_project)
    # Restrict the manifest to svg (primary) + png; pdf/jpeg are not rendered.
    (opened_project / "plots" / "p1" / "plot.yaml").write_text(
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
        "  entrypoint: render\n"
        "outputs:\n"
        "  preferred_format: svg\n"
        "  allowed_formats:\n"
        "    - svg\n"
        "    - png\n",
        encoding="utf-8",
    )
    sid, env = _run_and_open_session(client)
    ref = env["target"]["ref"]

    # The menu the panel can offer is bounded by what the run actually wrote,
    # and the refusal now happens where the panel asks for the file: a format
    # that was not rendered has no file to grant, so the read is a 404 rather
    # than a grant pointing at the primary's bytes under the wrong name.
    context = _panel_context(client, ref=ref)
    info = _panel_read(client, context, ref, "artifact.info").json()
    assert info["formats"] == ["svg", "png"]

    refused = _panel_read(client, context, ref, "artifact.file", {"variant": "pdf"})
    assert refused.status_code == 404, refused.text
    assert "not rendered" in refused.text

    export_dir = opened_project / "exports"
    export_dir.mkdir()
    destination = export_dir / "chosen.pdf"
    save = client.post(
        f"/api/previews/sessions/{sid}/resources/export/save",
        json={"destination_path": str(destination), "params": {"format": "pdf"}},
    )
    assert save.status_code >= 400, save.text
    assert not destination.exists()
    assert "not rendered" in save.text


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
