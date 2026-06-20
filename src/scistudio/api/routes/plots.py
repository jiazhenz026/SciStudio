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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    PlotCreateRequest,
    PlotCreateResponse,
    PlotListItem,
    PlotListResponse,
    PlotRelinkRequest,
    PlotRelinkResponse,
    PlotRunRequest,
    PlotRunResponse,
    PlotTargetItem,
    PlotTargetListResponse,
)

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
    """List project-local plot manifests, optionally filtered to a block output.

    Each item carries a ``broken`` flag (bug#7 / PR #1712 review): the bound
    target (node_id + output_port) is re-resolved against its workflow so the
    app shell can flag plots whose source block was deleted/recreated and
    surface a relink entry point for them. Targets are discovered once per
    workflow path and reused across plots.
    """
    from scistudio.ai.agent.mcp.tools_plot.targets import discover_targets
    from scistudio.ai.agent.mcp.tools_plot.validation import load_plot

    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    project_root = Path(project.path).resolve()
    plots_dir = project_root / "plots"
    if not plots_dir.is_dir():
        return PlotListResponse(plots=[], count=0)

    # Per-request cache: workflow_path -> set of node_ids still present in the
    # workflow, or None when target discovery failed (then ``broken`` stays
    # False to avoid false alarms on an unreadable workflow).
    #
    # Detection is node-level on purpose: the bug#7 scenario is "source block
    # deleted/recreated" (the bound node_id vanishes). Matching node_id +
    # output_port would false-positive on plots bound to blocks whose type is
    # not registered in the current environment, because discovery then emits a
    # synthetic port set that won't include the manifest's real port.
    node_cache: dict[str, set[str] | None] = {}

    def _is_broken(wf_path: str, node: str) -> bool:
        if wf_path not in node_cache:
            try:
                discovered = discover_targets(workflow_path=wf_path, include_unavailable=True)
            except Exception as exc:  # discovery is best-effort for the broken flag
                logger.debug("list_plots: target discovery failed for %r: %s", wf_path, exc)
                node_cache[wf_path] = None
            else:
                node_cache[wf_path] = {t.node_id for t in discovered}
        nodes = node_cache[wf_path]
        if nodes is None:
            return False
        return node not in nodes

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
                broken=_is_broken(target.workflow_path, target.node_id),
            )
        )
    items.sort(key=lambda item: (item.title.lower() or item.plot_id.lower(), item.plot_id.lower()))
    return PlotListResponse(plots=items, count=len(items), warnings=warnings)


@router.get("/targets", response_model=PlotTargetListResponse)
async def list_plot_targets(
    runtime: RuntimeDep,
    workflow_id: Annotated[str | None, Query()] = None,
    workflow_path: Annotated[str | None, Query()] = None,
    node_id: Annotated[str | None, Query()] = None,
    output_port: Annotated[str | None, Query()] = None,
    include_unavailable: Annotated[bool, Query()] = True,
) -> PlotTargetListResponse:
    """List workflow output targets a new plot can bind to."""
    from scistudio.ai.agent.mcp.tools_plot.targets import discover_targets

    try:
        runtime.require_active_project()
        targets = discover_targets(workflow_path=workflow_path, include_unavailable=include_unavailable)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items: list[PlotTargetItem] = []
    for target in targets:
        if workflow_id is not None and target.workflow_id != workflow_id:
            continue
        if node_id is not None and target.node_id != node_id:
            continue
        if output_port is not None and target.output_port != output_port:
            continue
        items.append(_target_item(target))
    return PlotTargetListResponse(targets=items, count=len(items))


@router.post("", response_model=PlotCreateResponse)
async def create_plot(payload: PlotCreateRequest, runtime: RuntimeDep) -> PlotCreateResponse:
    """Create ``plots/<id>/plot.yaml`` plus a render script from the plot template."""
    from scistudio.ai.agent.mcp.tools_plot.scaffold import PlotScaffoldError, scaffold_plot_files
    from scistudio.ai.agent.mcp.tools_plot.targets import resolve_target_by_id

    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    target = resolve_target_by_id(payload.target_id)
    if target is None:
        raise HTTPException(status_code=400, detail="Unknown plot target. Choose a block output from the target list.")

    warnings: list[str] = []
    if not target.latest_output_available:
        warnings.append("The bound block output has no recorded data yet. Run the workflow before running this plot.")
    try:
        manifest_path, script_path, bytes_written = scaffold_plot_files(
            Path(project.path).resolve(),
            payload.plot_id,
            target,
            payload.language,
            payload.title,
            payload.overwrite,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlotScaffoldError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create plot files: {exc}") from exc

    project_root = Path(project.path).resolve()
    return PlotCreateResponse(
        plot_id=payload.plot_id,
        manifest_path=_project_relative(project_root, manifest_path),
        script_path=_project_relative(project_root, script_path),
        bytes_written=bytes_written,
        warnings=warnings,
        target=_target_item(target),
    )


@router.post("/{plot_id}/relink", response_model=PlotRelinkResponse)
async def relink_plot_route(plot_id: str, payload: PlotRelinkRequest, runtime: RuntimeDep) -> PlotRelinkResponse:
    """Re-point an existing plot at a new workflow output target (bug#7, strict 1:1).

    Rewrites only the manifest ``target`` block from the supplied ``target_id``
    (resolved exactly like ``POST /api/plots``), re-validates the plot, and
    returns the new target plus validation diagnostics so the UI can confirm a
    previously broken target is now valid.
    """
    from scistudio.ai.agent.mcp.tools_plot.relink import PlotRelinkError, relink_plot
    from scistudio.ai.agent.mcp.tools_plot.targets import resolve_target_by_id
    from scistudio.ai.agent.mcp.tools_plot.validation import PlotNotFoundError

    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        outcome = relink_plot(plot_id, payload.target_id)
    except PlotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlotRelinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update plot manifest: {exc}") from exc

    project_root = Path(project.path).resolve()
    # relink_plot already proved target_id resolves (else PlotRelinkError),
    # so this re-resolution only rebuilds the full PlotTargetItem for the UI.
    target = resolve_target_by_id(payload.target_id)
    if target is None:  # pragma: no cover - target vanished between relink and re-resolve
        raise HTTPException(status_code=409, detail="Plot target became unavailable during relink.")
    return PlotRelinkResponse(
        plot_id=outcome.plot_id,
        manifest_path=_project_relative(project_root, outcome.manifest_path),
        target=_target_item(target),
        valid=outcome.valid,
        errors=list(outcome.errors),
        warnings=list(outcome.warnings),
    )


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


def _target_item(target: Any) -> PlotTargetItem:
    return PlotTargetItem(
        target_id=str(target.target_id),
        workflow_path=str(target.workflow_path),
        workflow_id=target.workflow_id,
        node_id=str(target.node_id),
        node_label=str(target.node_label or ""),
        block_type=str(target.block_type),
        output_port=str(target.output_port),
        output_type=str(target.output_type or ""),
        is_collection=bool(target.is_collection),
        latest_run_id=target.latest_run_id,
        latest_output_available=bool(target.latest_output_available),
        diagnostics=list(target.diagnostics or []),
    )
