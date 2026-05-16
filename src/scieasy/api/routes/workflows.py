"""Workflow CRUD and execution endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from scieasy.api.deps import get_runtime
from scieasy.api.runtime import ApiRuntime
from scieasy.api.schemas import (
    CancelPropagationResponse,
    ExecuteFromRequest,
    ExecuteFromResponse,
    WorkflowCreate,
    WorkflowEdge,
    WorkflowExecutionResponse,
    WorkflowNode,
    WorkflowResponse,
)
from scieasy.blocks.base.state import BlockState
from scieasy.engine.events import WORKFLOW_CHANGED, EngineEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


def _mark_self_write(path: Path) -> None:
    """ADR-034 Phase 2: tell the FS watcher this YAML write was canvas-originated.

    Suppresses the next ``workflow.changed`` event for ``(path, mtime, size)``
    so the watcher does not echo the canvas's own save back at the canvas.
    Silent no-op when the watcher singleton has not been installed (e.g. in
    pure-route unit tests).
    """
    try:
        from scieasy.api.routes.workflow_watcher import mark_self_write as _mark

        _mark(path)
    except Exception:
        # Watcher failures must not affect the user-facing save response.
        import logging

        logging.getLogger(__name__).debug("workflow_watcher: mark_self_write failed for %s", path, exc_info=True)


def _workflow_response(definition: Any) -> WorkflowResponse:
    return WorkflowResponse(
        id=definition.id,
        version=definition.version,
        description=definition.description,
        nodes=[
            WorkflowNode(
                id=node.id,
                block_type=node.block_type,
                config=node.config,
                execution_mode=node.execution_mode,
                layout=node.layout,
            )
            for node in definition.nodes
        ],
        edges=[WorkflowEdge(source=edge.source, target=edge.target) for edge in definition.edges],
        metadata=definition.metadata,
    )


async def _emit_workflow_changed(
    runtime: ApiRuntime,
    *,
    workflow_id: str,
    changed_by: str | None,
) -> None:
    """Broadcast a ``workflow.changed`` event on the shared EventBus.

    Originally introduced by #718 part (a) carrying a ``revision`` field; the
    counter was removed in ADR-039 §5.2 / D39-2.1. The event itself still
    fires after every successful workflow write so other browser tabs (or
    the embedded coding agent's WS subscriber) can invalidate their cached
    view. Cross-process / cross-session durable history now lives in git.
    """
    await runtime.event_bus.emit(
        EngineEvent(
            event_type=WORKFLOW_CHANGED,
            data={
                "workflow_id": workflow_id,
                "changed_by": changed_by,
            },
        )
    )


@router.get("/list", response_model=list[str])
async def list_workflows(runtime: RuntimeDep) -> list[str]:
    """List workflow IDs available in the active project."""
    try:
        return runtime.list_project_workflows()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import", response_model=WorkflowResponse)
async def import_workflow(file: UploadFile, runtime: RuntimeDep) -> WorkflowResponse:
    """Import an external YAML workflow file into the active project."""
    if not file.filename or not file.filename.endswith((".yaml", ".yml")):
        raise HTTPException(status_code=400, detail="Only .yaml/.yml files are accepted.")
    try:
        content = await file.read()
        import tempfile

        from scieasy.workflow.serializer import load_yaml, save_yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="wb") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            definition = load_yaml(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        out_path = runtime.workflow_path(definition.id)
        save_yaml(definition, out_path)
        _mark_self_write(out_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ADR-034 Phase 2: broadcast workflow.changed so any connected client
    # (other browser tabs, the embedded coding agent's WS subscriber)
    # invalidates its cache.
    await _emit_workflow_changed(runtime, workflow_id=definition.id, changed_by="import")
    return _workflow_response(definition)


@router.post("/import-path", response_model=WorkflowResponse)
async def import_workflow_from_path(body: dict, runtime: RuntimeDep) -> WorkflowResponse:
    """Import a workflow from a filesystem path (returned by the browse dialog).

    Emits ``workflow.changed`` after the write so other clients refetch
    (ADR-034 Phase 2). Durable history of the change lives in git per
    ADR-039.
    """
    file_path = body.get("path")
    if not file_path:
        raise HTTPException(status_code=400, detail="Missing 'path' field.")
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    if path.suffix.lower() not in (".yaml", ".yml"):
        raise HTTPException(status_code=400, detail="Only .yaml/.yml files are accepted.")
    try:
        from scieasy.workflow.serializer import load_yaml, save_yaml

        definition = load_yaml(path)
        out_path = runtime.workflow_path(definition.id)
        save_yaml(definition, out_path)
        _mark_self_write(out_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _emit_workflow_changed(runtime, workflow_id=definition.id, changed_by="import-path")
    return _workflow_response(definition)


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(body: WorkflowCreate, runtime: RuntimeDep) -> WorkflowResponse:
    """Create a new workflow from the supplied graph definition."""
    try:
        definition = runtime.save_workflow(body.model_dump())
    except ValueError as exc:
        # Cycle detection and other validation errors → 422
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _emit_workflow_changed(runtime, workflow_id=definition.id, changed_by="create")
    return _workflow_response(definition)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, runtime: RuntimeDep) -> WorkflowResponse:
    """Retrieve a workflow by its identifier.

    A YAML on disk that fails pydantic validation (e.g. an agent wrote it
    with the wrong edge shape) returns **422** with the structured
    pydantic error list under ``detail.errors`` — NOT 500, which would
    crash the canvas. The agent can then read the same payload via the
    MCP ``get_workflow`` tool and self-correct. The schema itself stays
    strict; we surface the error rather than papering over it.
    """
    from pydantic import ValidationError

    try:
        definition = runtime.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Workflow '{workflow_id}' on disk failed schema validation.",
                "errors": exc.errors(),
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workflow_response(definition)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    body: WorkflowCreate,
    runtime: RuntimeDep,
    request: Request,
) -> WorkflowResponse:
    """Replace a workflow definition.

    ADR-039 §5.2 / D39-2.1: the in-memory ``If-Match`` revision check has
    been removed. Cross-tab concurrency now relies on the existing
    ``workflow.changed`` event (filesystem watcher echoes external edits)
    plus durable git history (ADR-039) for after-the-fact reconciliation.
    Last-write-wins on the file save itself — same model as VS Code.
    """
    if workflow_id != body.id:
        raise HTTPException(status_code=400, detail="Workflow path/body IDs must match.")

    try:
        definition = runtime.save_workflow(body.model_dump())
    except ValueError as exc:
        # Cycle detection and other validation errors → 422
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # changed_by: prefer an explicit ``X-Changed-By`` header (set by the MCP
    # tool / the embedded agent), else fall back to a generic "api" tag.
    changed_by = request.headers.get("X-Changed-By", "api")
    await _emit_workflow_changed(runtime, workflow_id=definition.id, changed_by=changed_by)
    return _workflow_response(definition)


@router.post("/export-path")
async def export_workflow_to_path(body: dict, runtime: RuntimeDep) -> dict:
    """Export / save a workflow YAML to an arbitrary filesystem path.

    Expects ``{"workflow_id": str, "path": str}``.  The workflow must
    already exist in the project.  The file is written using
    ``save_yaml`` so the output is a valid SciEasy workflow YAML.
    """
    workflow_id = body.get("workflow_id")
    file_path = body.get("path")
    if not workflow_id or not file_path:
        raise HTTPException(status_code=400, detail="Missing 'workflow_id' or 'path' field.")
    try:
        definition = runtime.load_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    from scieasy.workflow.serializer import save_yaml

    target = Path(file_path)
    try:
        save_yaml(definition, target)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _mark_self_write(target)
    return {"status": "ok", "path": str(target)}


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, runtime: RuntimeDep) -> None:
    """Delete a workflow."""
    runtime.delete_workflow(workflow_id)


@router.post("/{workflow_id}/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(workflow_id: str, runtime: RuntimeDep) -> WorkflowExecutionResponse:
    """Start execution of a workflow."""
    try:
        result = runtime.start_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkflowExecutionResponse(**result)


@router.post("/{workflow_id}/pause", response_model=WorkflowExecutionResponse)
async def pause_workflow(workflow_id: str, runtime: RuntimeDep) -> WorkflowExecutionResponse:
    """Pause a running workflow."""
    try:
        run = runtime.get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await run.scheduler.pause()
    return WorkflowExecutionResponse(workflow_id=workflow_id, status="paused", message="Pause requested.")


@router.post("/{workflow_id}/resume", response_model=WorkflowExecutionResponse)
async def resume_workflow(workflow_id: str, runtime: RuntimeDep) -> WorkflowExecutionResponse:
    """Resume a paused workflow."""
    try:
        run = runtime.get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await run.scheduler.resume()
    return WorkflowExecutionResponse(workflow_id=workflow_id, status="running", message="Workflow resumed.")


@router.post("/{workflow_id}/cancel", response_model=CancelPropagationResponse)
async def cancel_workflow(workflow_id: str, runtime: RuntimeDep) -> CancelPropagationResponse:
    """Cancel an entire workflow."""
    try:
        run = runtime.get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await run.scheduler.cancel_workflow()
    block_states = run.scheduler.block_states()
    cancelled = sorted(block_id for block_id, state in block_states.items() if state == BlockState.CANCELLED)
    skipped = sorted(block_id for block_id, state in block_states.items() if state == BlockState.SKIPPED)
    return CancelPropagationResponse(
        cancelled_blocks=cancelled,
        skipped_blocks=skipped,
        skip_reasons=dict(run.scheduler.skip_reasons),
    )


@router.post("/{workflow_id}/blocks/{block_id}/cancel", response_model=CancelPropagationResponse)
async def cancel_block(
    workflow_id: str,
    block_id: str,
    runtime: RuntimeDep,
) -> CancelPropagationResponse:
    """Cancel a single block within a workflow."""
    try:
        run = runtime.get_run(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await run.scheduler.cancel_block(block_id)
    block_states = run.scheduler.block_states()
    cancelled = [node_id for node_id, state in block_states.items() if state == BlockState.CANCELLED]
    skipped = [node_id for node_id, state in block_states.items() if state == BlockState.SKIPPED]
    return CancelPropagationResponse(
        cancelled_blocks=sorted(cancelled),
        skipped_blocks=sorted(skipped),
        skip_reasons=dict(run.scheduler.skip_reasons),
    )


@router.post("/{workflow_id}/execute-from", response_model=ExecuteFromResponse)
async def execute_from_workflow(
    workflow_id: str,
    body: ExecuteFromRequest,
    runtime: RuntimeDep,
) -> ExecuteFromResponse:
    """Re-run a workflow from a specific block using checkpointed inputs.

    Hotfix #992: stamp ``runs.parent_run_id`` on the new run to point at
    the most-recent completed run of this workflow. Per ADR-038 §3.6a the
    new run's ``parent_run_id`` "points at the historical run whose outputs
    are reused"; the checkpoint mirrors the on-disk state at the most
    recent terminal block event, so the most recent completed run is
    semantically that parent. Previously the route called
    ``start_workflow(execute_from=...)`` without forwarding a
    ``parent_run_id``, leaving the column NULL — the Lineage tab had no
    way to render the re-run chain link required by §3.8.
    """
    parent_run_id: str | None = None
    lineage_store = getattr(runtime, "lineage_store", None)
    if lineage_store is not None:
        try:
            recent = lineage_store.list_runs(workflow_id=workflow_id, limit=1)
            if recent:
                parent_run_id = recent[0].get("run_id")
        except Exception:
            # Best-effort: a lineage lookup failure must not block the
            # actual re-run. The run will just have parent_run_id=NULL
            # as the pre-#992 default did.
            logger.warning(
                "execute_from_workflow: parent_run_id lookup failed (non-fatal)",
                exc_info=True,
            )
    try:
        result = runtime.start_workflow(
            workflow_id,
            execute_from=body.block_id,
            parent_run_id=parent_run_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExecuteFromResponse(**result)
