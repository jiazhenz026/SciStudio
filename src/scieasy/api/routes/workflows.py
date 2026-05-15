"""Workflow CRUD and execution endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from scieasy.api.deps import get_runtime
from scieasy.api.runtime import ApiRuntime
from scieasy.api.schemas import (
    CancelPropagationResponse,
    ExecuteFromRequest,
    ExecuteFromResponse,
    WorkflowConflictResponse,
    WorkflowCreate,
    WorkflowEdge,
    WorkflowExecutionResponse,
    WorkflowNode,
    WorkflowResponse,
)
from scieasy.blocks.base.state import BlockState
from scieasy.engine.events import WORKFLOW_CHANGED, EngineEvent

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


def _workflow_response(definition: Any, revision: int = 0) -> WorkflowResponse:
    return WorkflowResponse(
        id=definition.id,
        version=definition.version,
        revision=revision,
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


def _parse_if_match(raw: str | None) -> int | None:
    """Parse an ``If-Match`` header value to an int revision.

    Accepts plain integers as well as quoted ETag-style values such as
    ``"3"``. Returns ``None`` when the header is absent. Raises
    ``HTTPException 400`` when the value is malformed — callers that want
    backwards-compat (treat malformed/missing as "no precondition") can
    fall back on the missing-header path.
    """
    if raw is None:
        return None
    stripped = raw.strip().strip('"').strip("'")
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed If-Match header: {raw!r}") from exc


async def _emit_workflow_changed(
    runtime: ApiRuntime,
    *,
    workflow_id: str,
    revision: int,
    changed_by: str | None,
) -> None:
    """Broadcast a ``workflow.changed`` event on the shared EventBus (#718)."""
    await runtime.event_bus.emit(
        EngineEvent(
            event_type=WORKFLOW_CHANGED,
            data={
                "workflow_id": workflow_id,
                "revision": revision,
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

    # #718 part (a): bump revision + broadcast workflow.changed so any
    # connected client (other browser tabs, the embedded coding agent's
    # WS subscriber) invalidates its cache.
    new_revision = runtime.bump_revision(definition.id)
    await _emit_workflow_changed(runtime, workflow_id=definition.id, revision=new_revision, changed_by="import")
    return _workflow_response(definition, revision=new_revision)


@router.post("/import-path", response_model=WorkflowResponse)
async def import_workflow_from_path(body: dict, runtime: RuntimeDep) -> WorkflowResponse:
    """Import a workflow from a filesystem path (returned by the browse dialog).

    #718 part (a): bumps the in-memory revision after re-reading so frontend
    caches keyed off the old revision are invalidated. This is the documented
    escape hatch for "an external editor edited the file" until the
    optimistic-lock pattern fully takes over on the write path.
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

    new_revision = runtime.bump_revision(definition.id)
    await _emit_workflow_changed(runtime, workflow_id=definition.id, revision=new_revision, changed_by="import-path")
    return _workflow_response(definition, revision=new_revision)


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

    new_revision = runtime.bump_revision(definition.id)
    await _emit_workflow_changed(runtime, workflow_id=definition.id, revision=new_revision, changed_by="create")
    return _workflow_response(definition, revision=new_revision)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, runtime: RuntimeDep) -> WorkflowResponse:
    """Retrieve a workflow by its identifier.

    #718 part (a): the response includes the current ``revision`` so clients
    can pass it back as ``If-Match`` on the next ``PUT``.

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
    return _workflow_response(definition, revision=runtime.current_revision(workflow_id))


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    body: WorkflowCreate,
    runtime: RuntimeDep,
    request: Request,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Any:
    """Replace a workflow definition.

    #718 part (a): supports optimistic concurrency via the ``If-Match`` HTTP
    header. When the supplied revision is older than the server's current
    revision, the response is ``412 Precondition Failed`` with the latest
    workflow JSON in the body so the client can rebase its local state.
    Missing or empty ``If-Match`` is accepted for backwards compat (legacy
    UI clients that pre-date this feature continue to work).
    """
    if workflow_id != body.id:
        raise HTTPException(status_code=400, detail="Workflow path/body IDs must match.")

    expected_revision = _parse_if_match(if_match)
    current = runtime.current_revision(workflow_id)
    if expected_revision is not None and expected_revision != current:
        # Stale write — return the latest payload so the client can rebase.
        try:
            latest = runtime.load_workflow(workflow_id)
        except FileNotFoundError as exc:
            # Race: revision exists in memory but file vanished. Treat as 404.
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        conflict = WorkflowConflictResponse(
            detail=(
                f"Workflow revision is stale: expected={expected_revision} current={current}. "
                "Rebase against the included `workflow` payload and retry."
            ),
            current_revision=current,
            workflow=_workflow_response(latest, revision=current),
        )
        return JSONResponse(status_code=412, content=conflict.model_dump())

    try:
        definition = runtime.save_workflow(body.model_dump())
    except ValueError as exc:
        # Cycle detection and other validation errors → 422
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    new_revision = runtime.bump_revision(definition.id)
    # changed_by: prefer an explicit ``X-Changed-By`` header (set by the MCP
    # tool / the embedded agent), else fall back to a generic "api" tag.
    changed_by = request.headers.get("X-Changed-By", "api")
    await _emit_workflow_changed(runtime, workflow_id=definition.id, revision=new_revision, changed_by=changed_by)
    return _workflow_response(definition, revision=new_revision)


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
    """Re-run a workflow from a specific block using checkpointed inputs."""
    try:
        result = runtime.start_workflow(workflow_id, execute_from=body.block_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExecuteFromResponse(**result)
