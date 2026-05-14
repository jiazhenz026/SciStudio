"""Project CRUD and workspace management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from scieasy.api.deps import get_runtime
from scieasy.api.runtime import ApiRuntime
from scieasy.api.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


@router.post("/", response_model=ProjectResponse)
async def create_project(body: ProjectCreate, runtime: RuntimeDep) -> ProjectResponse:
    """Create a new project workspace."""
    try:
        project = runtime.create_project(body.name, body.description, body.path)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProjectResponse(**runtime.project_response(project))


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(runtime: RuntimeDep) -> list[ProjectResponse]:
    """List all projects accessible to the current user."""
    return [ProjectResponse(**runtime.project_response(project)) for project in runtime.list_projects()]


@router.get("/{project_id:path}", response_model=ProjectResponse)
async def get_project(project_id: str, runtime: RuntimeDep) -> ProjectResponse:
    """Retrieve and open a project by identifier or filesystem path."""
    try:
        project = runtime.open_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # ADR-034 Phase 2: refresh the workflow filesystem watcher to point at
    # the newly active project. ``start_for_project`` is idempotent — if the
    # caller re-opens the same project it returns immediately without
    # disturbing the existing observer.
    _restart_workflow_watcher(project.path)
    return ProjectResponse(**runtime.project_response(project))


def _restart_workflow_watcher(project_path: str) -> None:
    """Best-effort: point the global watcher at *project_path*'s workflows/.

    Failure to start the observer is logged but does not affect the project
    open response — the canvas continues to work without auto-refresh and
    the user sees their workflow YAMLs the next time they reload manually.
    """
    import asyncio
    import logging
    from pathlib import Path

    from scieasy.api.routes import workflow_watcher as watcher_module

    watcher = watcher_module.get_active_watcher()
    if watcher is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        watcher.start_for_project(Path(project_path), loop)
    except Exception:
        logging.getLogger(__name__).warning("workflow_watcher: restart for %s failed", project_path, exc_info=True)


@router.put("/{project_id:path}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    runtime: RuntimeDep,
) -> ProjectResponse:
    """Update project metadata."""
    try:
        project = runtime.update_project(project_id, name=body.name, description=body.description)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectResponse(**runtime.project_response(project))


@router.delete("/{project_id:path}", status_code=204)
async def delete_project(project_id: str, runtime: RuntimeDep) -> None:
    """Delete a project and its associated resources."""
    try:
        runtime.delete_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
