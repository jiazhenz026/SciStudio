"""Plot-job run + preview-wiring endpoint (ADR-048 SPEC 2 FR-031 / SC-010).

This route is the producer -> consumer link the original SPEC 2 implementation
left dead-wired (#1606). ``run_plot_job`` writes a display-only artifact to the
preview cache, but nothing registered that artifact so the routed
:class:`~scistudio.previewers.PreviewService` could reach the core
``PlotPreviewer`` (``core.plot.basic``) at runtime, and no API surface let the
GUI trigger a plot run and open the preview.

``POST /api/plots/run``:

1. Executes the plot job via the SPEC 2 runtime ``run_plot_job`` (imported from
   the ``ai`` layer — ``api`` sits *above* ``ai`` in the dependency graph, so
   this import direction is allowed; the reverse is forbidden by the
   import-linter contracts).
2. On success, registers the produced ``current.*`` artifact as a previewable
   catalog ``DataRecord`` stamped with ``plot_artifact`` metadata via
   :meth:`ApiRuntime.register_plot_artifact`.
3. Returns the catalog ``data_ref`` (+ cache key + display source) so the
   frontend opens a routed ``plot_artifact`` preview session through the
   existing ``POST /api/previews/sessions`` API — rendering the produced figure
   in the preview panel through the core ``PlotPreviewer``.

A plot job remains PREVIEW-ONLY: this route never registers a workflow node,
edits workflow YAML, creates a downstream collection, or claims lineage
(FR-025). It only reads the in-memory scheduler outputs (inside ``run_plot_job``)
and writes under ``.scistudio/previews/``.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import PlotListItem, PlotListResponse, PlotRunRequest, PlotRunResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plots", tags=["plots"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


@router.get("", response_model=PlotListResponse)
async def list_plots(
    runtime: RuntimeDep,
    workflow_id: Annotated[str | None, Query()] = None,
    node_id: Annotated[str | None, Query()] = None,
    output_port: Annotated[str | None, Query()] = None,
) -> PlotListResponse:
    """List project-local plot manifests, optionally filtered to a block output."""
    from scistudio.ai.agent.mcp.tools_plot.validation import load_plot

    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    project_root = Path(project.path).resolve()
    plots_dir = project_root / "plots"
    if not plots_dir.is_dir():
        return PlotListResponse(plots=[], count=0)

    items: list[PlotListItem] = []
    warnings: list[str] = []
    for manifest_path in sorted(plots_dir.glob("*/plot.yaml")):
        try:
            loaded = load_plot(plot_id=manifest_path.parent.name)
        except Exception as exc:
            warnings.append(f"{_project_relative(project_root, manifest_path)}: {exc}")
            continue
        target = loaded.manifest.target
        if workflow_id is not None and target.workflow_id != workflow_id:
            continue
        if node_id is not None and target.node_id != node_id:
            continue
        if output_port is not None and target.output_port != output_port:
            continue
        items.append(
            PlotListItem(
                plot_id=loaded.plot_id,
                title=loaded.manifest.title,
                workflow_id=target.workflow_id,
                node_id=target.node_id,
                output_port=target.output_port,
                display_label=target.display_label,
                language=loaded.manifest.script.language,
                preferred_format=loaded.manifest.outputs.preferred_format,
                manifest_path=_project_relative(project_root, loaded.manifest_path),
                script_path=_project_relative(project_root, loaded.script_path),
            )
        )
    items.sort(key=lambda item: (item.title.lower() or item.plot_id.lower(), item.plot_id.lower()))
    return PlotListResponse(plots=items, count=len(items), warnings=warnings)


@router.post("/run", response_model=PlotRunResponse)
async def run_plot(payload: PlotRunRequest, runtime: RuntimeDep) -> PlotRunResponse:
    """Run a plot job and register its artifact for routed preview (FR-031 / SC-010).

    The response's ``data_ref`` is the catalog id the frontend passes to
    ``POST /api/previews/sessions`` with ``target.kind="plot_artifact"`` to
    render the produced plot through the core ``PlotPreviewer``.
    """
    # Import inside the handler so the ``api`` import surface stays light and the
    # allowed ``api -> ai`` dependency edge is exercised lazily.
    from scistudio.ai.agent.mcp.tools_plot.runtime import run_plot_job
    from scistudio.ai.agent.mcp.tools_plot.validation import (
        LoadedPlot,
        PlotNotFoundError,
        load_plot,
    )

    try:
        loaded: LoadedPlot = load_plot(plot_id=payload.plot_id)
    except PlotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # No project open / no runtime context.
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        # ``run_plot_job`` launches a render subprocess and blocks for up to the
        # manifest/absolute timeout. Offload it to a worker thread so a long
        # render or timeout does not stall the event loop and starve other
        # async API / SSE / WebSocket requests served by this worker.
        result = await run_in_threadpool(
            partial(
                run_plot_job,
                plot_id=payload.plot_id,
                run_id=payload.run_id,
                timeout_seconds=payload.timeout_seconds,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    manifest_target = loaded.manifest.target
    source = {
        "workflow_id": manifest_target.workflow_id,
        "node_id": manifest_target.node_id,
        "output_port": manifest_target.output_port,
    }

    # Register the produced artifact only on a successful run that actually wrote
    # a display artifact. A failed / empty run returns status + errors with no
    # data_ref so the frontend shows the failure instead of an empty preview.
    data_ref: str | None = None
    recorded_type = "PlotArtifact"
    type_chain: list[str] = []
    if result.status == "succeeded" and result.artifact_paths:
        if result.data_ref:
            data_ref = result.data_ref
            recorded_type = result.recorded_type or "PlotArtifact"
            type_chain = list(result.type_chain) if result.type_chain else [recorded_type]
        else:
            record = runtime.register_plot_artifact(
                result.artifact_paths[0],
                cache_key=result.cache_key,
                workflow_id=manifest_target.workflow_id,
                node_id=manifest_target.node_id,
                output_port=manifest_target.output_port,
                plot_id=payload.plot_id,
            )
            data_ref = record.id
            recorded_type = record.type_name
            type_chain = list(record.type_chain) if record.type_chain else [record.type_name]

    return PlotRunResponse(
        status=result.status,
        data_ref=data_ref,
        recorded_type=recorded_type,
        type_chain=type_chain,
        cache_key=result.cache_key,
        artifact_paths=list(result.artifact_paths),
        source=source,
        warnings=list(result.warnings),
        errors=list(result.errors),
    )


def _project_relative(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return str(path)
