"""Project CRUD and workspace management endpoints."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scieasy.api.deps import get_runtime
from scieasy.api.runtime import ApiRuntime
from scieasy.api.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# ADR-036 §3.2 — File read/write endpoints (skeleton, returns 501)
#
# These endpoints back the embedded code editor (Monaco). They serve a single
# project-relative file as text, scoped to a per-project root, with an
# extension allowlist and a hard size cap. The PUT path coordinates with the
# workflow filesystem watcher so the user's own save does not echo back as
# an external-change event.
#
# IMPORTANT — route ordering:
# These ``/{project_id:path}/file`` routes MUST be declared BEFORE the
# greedy ``/{project_id:path}`` GET/PUT/DELETE handlers below. FastAPI
# matches routes in declaration order, and ``{project_id:path}`` would
# otherwise swallow ``/<id>/file`` requests (with ``project_id="<id>/file"``)
# and never reach these handlers. See ADR-036 audit
# (docs/audit/2026-05-14-adr-036-skeleton.md, finding P1-1) for details.
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


def _resolve_project_file(runtime: ApiRuntime, project_id: str, path: str) -> tuple[Path, Path]:
    """Resolve ``project_id`` + relative ``path`` to a sandboxed absolute path.

    Returns ``(project_root, target_absolute_path)``. Raises ``HTTPException``
    with the appropriate status code on any rejection. This is the shared
    sandbox check used by both GET and PUT — kept as a helper so both
    endpoints enforce the rules identically.

    Rejection codes (per ADR-036 §3.2):
      - 404: project unknown
      - 400: empty path / contains ``..`` segment / path is a directory
      - 403: resolved path escapes project root (symlink, traversal)
      - 415: extension not in :data:`ADR036_FILE_ALLOWLIST`

    Size cap and existence/UTF-8 checks are done by the caller because
    they apply differently to read vs. write.
    """
    project = runtime.known_projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not path:
        raise HTTPException(status_code=400, detail="path query parameter is required")
    # Reject ``..`` segments early — same belt-and-braces as project_tree.
    parts = path.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=403, detail="Path traversal is not allowed")

    project_root = Path(os.path.realpath(project.path))
    candidate = os.path.realpath(os.path.join(str(project_root), path))
    # CodeQL py/path-injection canonical sanitiser: realpath + commonpath.
    try:
        if os.path.commonpath([str(project_root), candidate]) != str(project_root):
            raise HTTPException(status_code=403, detail="Path escapes project root")
    except ValueError as exc:
        # commonpath raises on different drives (Windows) — treat as escape.
        raise HTTPException(status_code=403, detail="Path escapes project root") from exc

    target = Path(candidate)
    if target.suffix.lower() not in ADR036_FILE_ALLOWLIST:
        raise HTTPException(
            status_code=415,
            detail=f"Extension {target.suffix!r} not in editor allowlist",
        )
    return project_root, target


@router.get("/{project_id:path}/file", response_model=FileReadResponse)
async def read_project_file(
    project_id: str,
    runtime: RuntimeDep,
    path: str = "",
) -> FileReadResponse:
    """Read a project-relative file as UTF-8 text. (ADR-036 §3.2)

    Sandbox + allowlist + size cap per ADR-036 §3.2. The full rationale and
    edge-case matrix lives in the ADR; the helper :func:`_resolve_project_file`
    enforces sandbox + allowlist; size and UTF-8 checks happen here.
    """
    _, target = _resolve_project_file(runtime, project_id, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    try:
        stat = target.stat()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"stat failed: {exc}") from exc

    if stat.st_size > ADR036_FILE_SIZE_CAP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"File size {stat.st_size} exceeds editor cap {ADR036_FILE_SIZE_CAP_BYTES} bytes"),
        )

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # Binary file flagged as text by extension — refuse rather than
        # serve mojibake into Monaco.
        raise HTTPException(
            status_code=415,
            detail=f"File is not valid UTF-8: {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read failed: {exc}") from exc

    return FileReadResponse(
        content=content,
        mtime=stat.st_mtime,
        size=stat.st_size,
        encoding="utf-8",
    )


@router.put("/{project_id:path}/file", response_model=FileWriteResponse)
async def write_project_file(
    project_id: str,
    runtime: RuntimeDep,
    body: FileWriteRequest,
    path: str = "",
) -> FileWriteResponse:
    """Write a project-relative file atomically. (ADR-036 §3.2)

    Sandbox / allowlist / size cap per ADR-036 §3.2. Size cap is checked
    BEFORE touching disk so 413 rejects never leave a partial tmpfile.

    Atomic write: ``tempfile.NamedTemporaryFile`` in the destination's
    parent dir, write content, ``os.replace(tmp, target)``. The rename is
    atomic on POSIX and Windows (``os.replace`` documentation guarantees
    this). Any failure before the rename leaves the destination untouched.

    Self-write suppression: BEFORE the rename, call ``mark_self_write``
    on the workflow watcher with the destination path so the watcher's
    debounce filter discards the immediately-following modify/move event.
    Coordinated this way (mark, then rename) so the watcher's
    ``(path, mtime, size)`` triple matches the freshly-renamed file.
    """
    from scieasy.api.routes.workflow_watcher import mark_self_write

    _, target = _resolve_project_file(runtime, project_id, path)

    encoded = body.content.encode("utf-8")
    if len(encoded) > ADR036_FILE_SIZE_CAP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"Content size {len(encoded)} exceeds editor cap {ADR036_FILE_SIZE_CAP_BYTES} bytes"),
        )

    if not target.parent.exists():
        # We do not auto-create directory trees; reject explicitly so the
        # frontend can surface a clear error rather than silently inventing
        # folders behind the user's back.
        raise HTTPException(status_code=404, detail="Parent directory does not exist")
    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    # Atomic write: tempfile in same dir + os.replace.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".__scieasy_write_", suffix=target.suffix, dir=str(target.parent))
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(encoded)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        # Mark self-write BEFORE the rename so the watcher's debounce
        # filter sees the call land before the FS event fires. The watcher
        # captures (path, mtime, size) lazily — calling it after writing
        # the tmpfile but before the rename is fine because mark_self_write
        # itself stats the destination path lazily on event match.
        try:
            mark_self_write(target)
        except Exception:
            # Self-write suppression is best-effort; failure here just
            # means the watcher will echo a modify event the frontend
            # then ignores via existing dedup.
            logger.debug("mark_self_write raised", exc_info=True)
        os.replace(tmp_path, target)
        # Re-mark after the replace so the (path, mtime, size) triple
        # matches the actual on-disk file the watcher will see.
        try:
            mark_self_write(target)
        except Exception:
            logger.debug("mark_self_write (post-replace) raised", exc_info=True)
    except HTTPException:
        # Clean up tmpfile, re-raise the HTTPException as-is.
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise
    except OSError as exc:
        # Disk full / permissions / simulated rename failures: clean up
        # the tmpfile and surface a 500 instead of a raw traceback.
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"write failed: {exc}") from exc

    # TODO(I36c, ADR-036 §3.5): if target falls under ``<project>/blocks/``
    # and target.suffix == ".py", trigger ``BlockRegistry.hot_reload()``
    # gated on lint pass. Owned by Phase 2C.

    try:
        stat = target.stat()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"post-write stat failed: {exc}") from exc

    return FileWriteResponse(mtime=stat.st_mtime, size=stat.st_size)


# ---------------------------------------------------------------------------
# Greedy ``/{project_id:path}`` handlers — declared AFTER the more specific
# ``/{project_id:path}/file`` routes above so FastAPI matches the file
# routes first. See ADR-036 audit P1-1 for why this ordering matters.
# ---------------------------------------------------------------------------


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
