"""Project CRUD and workspace management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# ADR-036 §3.2 — File read/write endpoints (skeleton, returns 501)
#
# These endpoints back the embedded code editor (Monaco). They serve a single
# project-relative file as text, scoped to a per-project root, with an
# extension allowlist and a hard size cap. The PUT path coordinates with the
# workflow filesystem watcher so the user's own save does not echo back as
# an external-change event.
#
# Implementation phase agents (I36a) replace each ``raise NotImplementedError``
# below with the real handler. Read the docstring + comment block above each
# stub before coding — it captures the full contract the handler must honour.
# ---------------------------------------------------------------------------


# Module-level constants — implementation phase wires them in. Defining them
# here in the skeleton makes the contract obvious and also gives the test
# stubs something to import without forcing the real handler to exist.
ADR036_FILE_ALLOWLIST: tuple[str, ...] = (
    ".py",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".log",
)
"""Allowed file extensions for ADR-036 file GET/PUT (per ADR-036 §3.2)."""

ADR036_FILE_SIZE_CAP_BYTES: int = 10 * 1024 * 1024
"""Hard upper bound on file size returned/accepted by GET/PUT (per ADR-036 §3.2)."""


class FileReadResponse(BaseModel):
    """Skeleton — response body shape for GET file endpoint (per ADR-036 §3.2).

    The real handler returns this exact shape; tests assert the shape stays
    stable.
    """

    content: str
    mtime: float
    size: int
    encoding: str = "utf-8"


class FileWriteRequest(BaseModel):
    """Skeleton — request body shape for PUT file endpoint (per ADR-036 §3.2)."""

    content: str


class FileWriteResponse(BaseModel):
    """Skeleton — response body shape for PUT file endpoint (per ADR-036 §3.2)."""

    mtime: float
    size: int


@router.get("/{project_id:path}/file", response_model=FileReadResponse)
async def read_project_file(
    project_id: str,
    runtime: RuntimeDep,
    path: str = "",
) -> FileReadResponse:
    """Read a project-relative file as UTF-8 text. (ADR-036 §3.2 — SKELETON)

    Implementation plan (per ADR-036 §3.2):
      1. Resolve ``project_id`` -> project root via ``runtime.known_projects``;
         raise HTTPException(404) if unknown.
      2. Resolve the supplied ``path`` against the project root using the
         existing ``_resolve_safe_path`` helper at
         ``src/scieasy/api/routes/filesystem.py:47-65`` (mirror the realpath +
         commonpath sanitiser pattern). Reject path traversal with HTTP 403.
      3. Validate extension is in ``ADR036_FILE_ALLOWLIST`` -> else HTTP 415.
      4. Stat the file; reject size > ``ADR036_FILE_SIZE_CAP_BYTES`` with
         HTTP 413.
      5. ``open(target, encoding="utf-8")`` and return content + mtime + size.

    Edge cases:
      - File does not exist -> HTTP 404.
      - File is a directory -> HTTP 400.
      - File contains invalid UTF-8 -> HTTP 415 (binary file not editable).
      - ``path`` is empty -> HTTP 400 (must specify a file).
      - Symlink escapes project root after resolve -> HTTP 403.

    Test plan (must be added by I36a):
      - test_read_file_happy_path: existing .py file returns content + mtime.
      - test_read_file_404_missing
      - test_read_file_403_traversal: path="../../etc/passwd" rejected.
      - test_read_file_415_extension: .exe rejected.
      - test_read_file_413_size: file > 10 MB rejected.
      - test_read_file_400_directory: path points at a directory.

    References: ADR-036 §3.2; sanitiser at ``filesystem.py:47-65``;
    similar project-scoped pattern at ``project_tree`` above.
    """
    raise NotImplementedError("ADR-036 skeleton — implementation phase I36a fills this in")


@router.put("/{project_id:path}/file", response_model=FileWriteResponse)
async def write_project_file(
    project_id: str,
    runtime: RuntimeDep,
    body: FileWriteRequest,
    path: str = "",
) -> FileWriteResponse:
    """Write a project-relative file atomically. (ADR-036 §3.2 — SKELETON)

    Implementation plan (per ADR-036 §3.2):
      1. Same resolve/safe-path/allowlist/size-cap checks as GET. The size
         cap applies to ``len(body.content.encode("utf-8"))`` BEFORE writing.
      2. Atomic write: ``tempfile.NamedTemporaryFile(dir=target.parent,
         delete=False)`` -> write -> ``os.replace(tmp, target)``. Never write
         partial state into the destination file.
      3. Coordinate with the workflow watcher: BEFORE the rename, call
         ``mark_self_write(target)`` (see
         ``src/scieasy/api/routes/workflow_watcher.py:415``) so the watcher
         does not echo this write as an external-change event. The
         coordination MUST be done before ``os.replace`` because the watcher
         picks up the rename event near-instantaneously on most platforms.
      4. ``stat`` the new file and return ``{mtime, size}``.
      5. (Out of scope for this endpoint, owned by I36c) — Phase 2C wires
         a follow-up: if path falls under ``<project>/blocks/`` and is .py,
         trigger ``BlockRegistry.hot_reload()`` gated on lint pass. Do NOT
         implement that here; just leave a TODO comment so I36c finds it.

    Edge cases:
      - Parent directory does not exist -> HTTP 404 (we do not auto-create).
      - File exists and is read-only -> HTTP 403.
      - Disk full mid-write -> tempfile cleanup, HTTP 500.
      - ``content`` decodes to > 10 MB -> HTTP 413 BEFORE touching disk.
      - Concurrent PUT to the same path -> last writer wins; rename is atomic
        so no torn writes.

    Test plan (must be added by I36a):
      - test_write_file_happy_path: roundtrips content + mtime advances.
      - test_write_file_atomic: simulate failure mid-write, target file
        remains old content (NEVER partial).
      - test_write_file_self_write_suppression: install a fake watcher,
        verify ``mark_self_write`` was called with the target path BEFORE
        the file appeared on disk.
      - test_write_file_413_size: 11 MB content rejected before write.
      - test_write_file_403_traversal
      - test_write_file_415_extension

    References: ADR-036 §3.2; ``mark_self_write`` at
    ``workflow_watcher.py:415``; existing self-write pattern in
    ``runtime.save_workflow``.
    """
    raise NotImplementedError("ADR-036 skeleton — implementation phase I36a fills this in")
