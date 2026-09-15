"""Project CRUD and workspace management endpoints."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.file_contracts import ADR036_FILE_ALLOWLIST
from scistudio.api.file_contracts import FILE_CHANGED_EVENT_TYPE as FILE_CHANGED_EVENT_TYPE
from scistudio.api.mcp_lifecycle import ensure_project_mcp_server
from scistudio.api.runtime import FILE_ENTITY_CLASS, ApiRuntime, _file_writes

# ADR-036 §3.5 (I36c) string event type for the WS-broadcast that fires after
# a successful, lint-passing PUT to ``blocks/*.py``. ADR-055 Spec 2 (#2279)
# moved its definition beside the shared write path; re-exported here because
# callers and tests import it from this module.
from scistudio.api.runtime._file_writes import BLOCKS_RELOADED_EVENT_TYPE as BLOCKS_RELOADED_EVENT_TYPE
from scistudio.api.runtime._file_writes import (
    FileWriteConflictError,
    ProjectFileWriteError,
)
from scistudio.api.runtime._runs import ProjectRunsLiveError
from scistudio.api.schemas import (
    ActiveProjectResponse,
    EndProjectRunsRequest,
    EndProjectRunsResponse,
    LiveRunResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectRunsResponse,
    ProjectUpdate,
)
from scistudio.tutorials.projects import is_tutorial_entry

_API_SOURCES = {"canvas", "agent", "gitRestore", "import", "external"}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: The 409 ``detail.code`` a request that would leave a project with live runs gets.
PROJECT_RUNS_LIVE = "project_runs_live"


def _runs_live_conflict(exc: ProjectRunsLiveError) -> HTTPException:
    """The 409 a switch that would end live runs answers."""
    return HTTPException(
        status_code=409,
        detail={"code": PROJECT_RUNS_LIVE, "message": str(exc), "run_ids": exc.run_ids},
    )


@router.post("/", response_model=ProjectResponse)
async def create_project(request: Request, body: ProjectCreate, runtime: RuntimeDep) -> ProjectResponse:
    """Create a new project workspace."""
    try:
        project = runtime.create_project(body.name, body.description, body.path)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProjectRunsLiveError as exc:
        raise _runs_live_conflict(exc) from exc
    await ensure_project_mcp_server(request.app, runtime, Path(project.path))
    return ProjectResponse(**runtime.project_response(project))


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(runtime: RuntimeDep) -> list[ProjectResponse]:
    """List the user's projects, excluding tutorial projects.

    Learning Center: this one response feeds all three surfaces
    the requirement names — the recent-project list, the projects dropdown, and
    the welcome pane — so filtering it is the whole of the hiding. A tutorial
    project is a disposable teaching artifact that restarting and clearing both
    delete; a user who wandered into one and started real
    analysis would lose it, so the only way back in is the Learning Center.

    The filter is here rather than in
    :meth:`scistudio.api.runtime.ApiRuntime.list_projects` because that method
    is the runtime's answer to "which projects exist", which the Learning Center
    needs unfiltered, and because also requires marked projects to stay
    fully operable through every other route — ``GET``/``PUT``/``DELETE`` and
    the file endpoints all resolve through ``runtime.known_projects``, which
    this leaves untouched.
    """
    # Development references: ADR-053, FR-065, FR-066, FR-073.
    return [
        ProjectResponse(**runtime.project_response(project))
        for project in runtime.list_projects()
        if not is_tutorial_entry(project)
    ]


@router.get("/active", response_model=ActiveProjectResponse)
async def get_active_project(runtime: RuntimeDep) -> ActiveProjectResponse:
    """Return the project this backend already has open, without re-opening it.

    ``GET /api/projects/{id}`` re-opens a project, which resets the data
    catalog, rebuilds the registries and stores, and restarts the watcher. A
    second GUI client (the page ``open_gui`` hands an agent) attaches to the
    desktop session through this read instead, so it has no side effects.
    ``project`` is ``null`` when no project is open.

    Declared before the greedy ``/{project_id:path}`` handlers so ``active`` is
    not taken for a project id.
    """
    # Development references: #2385.
    project = runtime.active_project
    if project is None:
        return ActiveProjectResponse(project=None, active_workflow_id=None)
    return ActiveProjectResponse(
        project=ProjectResponse(**runtime.project_response(project)),
        active_workflow_id=runtime.active_workflow_id,
    )


@router.get("/active/runs", response_model=ProjectRunsResponse)
async def get_active_project_runs(runtime: RuntimeDep) -> ProjectRunsResponse:
    """List the active project's workflow runs that have not finished.

    Switching to another project ends every one of them, so the GUI reads this
    before a switch and asks the user to confirm when it is not empty. Declared
    before the greedy ``/{project_id:path}`` handlers.
    """
    # Development references: #2433.
    runs = [
        LiveRunResponse(run_id=run.run_id, workflow_id=workflow_id)
        for workflow_id, run in list(runtime.workflow_runs.items())
        if not run.task.done()
    ]
    project = runtime.active_project
    return ProjectRunsResponse(project_id=project.id if project is not None else None, runs=runs)


@router.post("/active/end-runs", response_model=EndProjectRunsResponse)
async def end_active_project_runs(body: EndProjectRunsRequest, runtime: RuntimeDep) -> EndProjectRunsResponse:
    """Cancel every live run of the active project and wait until each has ended.

    The GUI calls this once the user has confirmed leaving a project with live
    runs, then switches. The request names the project and the runs the user was
    shown; it is refused with 409 when another client has since opened a
    different project, or started a run the user did not confirm. The wait is
    bounded: a run that ignores cancellation is recorded as ``cancelled`` and the
    call returns. Closing a browser never reaches this; only an explicit switch
    does.
    """
    # Development references: #2433, #2327.
    project = runtime.active_project
    if project is None or project.id != body.project_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "project_changed",
                "message": "Another window opened a different project; nothing was cancelled.",
                "active_project_id": project.id if project is not None else None,
            },
        )
    if body.run_ids is not None:
        unconfirmed = sorted(
            str(run.run_id) for run in runtime.live_workflow_runs() if str(run.run_id) not in set(body.run_ids)
        )
        if unconfirmed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "project_runs_changed",
                    "message": "A run started after you confirmed; nothing was cancelled.",
                    "run_ids": unconfirmed,
                },
            )
    ended = await runtime.end_project_runs()
    return EndProjectRunsResponse(ended_run_ids=ended)


# ---------------------------------------------------------------------------
# ADR-036 搂3.2 鈥?File read/write endpoints (skeleton, returns 501)
#
# These endpoints back the embedded code editor (Monaco). They serve a single
# project-relative file as text, scoped to a per-project root, with an
# extension allowlist and a hard size cap. The PUT path coordinates with the
# workflow filesystem watcher so the user's own save does not echo back as
# an external-change event.
#
# IMPORTANT 鈥?route ordering:
# These ``/{project_id:path}/file`` routes MUST be declared BEFORE the
# greedy ``/{project_id:path}`` GET/PUT/DELETE handlers below. FastAPI
# matches routes in declaration order, and ``{project_id:path}`` would
# otherwise swallow ``/<id>/file`` requests (with ``project_id="<id>/file"``)
# and never reach these handlers. See ADR-036 audit
# (docs/audit/2026-05-14-adr-036-skeleton.md, finding P1-1) for details.
#
# Implementation phase agents (I36a) replace each ``raise NotImplementedError``
# below with the real handler. Read the docstring + comment block above each
# stub before coding 鈥?it captures the full contract the handler must honour.
# ---------------------------------------------------------------------------


ADR036_FILE_SIZE_CAP_BYTES: int = 10 * 1024 * 1024
"""Hard upper bound on file size returned/accepted by GET/PUT (per  搂3.2)."""
# Development references: ADR-036.


class FileReadResponse(BaseModel):
    """Response body for the GET file endpoint.

    The handler returns this exact shape; tests assert it stays stable.
    """

    content: str
    mtime: float
    size: int
    encoding: str = "utf-8"
    state_version: int
    entity_class: str = FILE_ENTITY_CLASS
    entity_id: str
    source: str | None = None
    source_id: str | None = None
    kind: str = "current"
    timestamp: str


class FileWriteRequest(BaseModel):
    """Request body for the PUT file endpoint."""

    content: str
    source: str | None = None
    source_id: str | None = None
    create_parent_dirs: bool = False
    expected_state_version: int | None = Field(
        default=None,
        description=(
            "Optional. The state_version the client last read. When set and the file has "
            "changed since, the write is rejected with 409 instead of overwriting it."
        ),
    )


class FileWriteResponse(BaseModel):
    """Response body for the PUT file endpoint."""

    mtime: float
    size: int
    state_version: int
    entity_class: str = FILE_ENTITY_CLASS
    entity_id: str
    source: str
    source_id: str | None = None
    kind: str
    timestamp: str


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


# ADR-055 Spec 2 FR-005 (#2279): the write path lives in
# ``scistudio.api.runtime._file_writes`` so the MCP author tools share it; these
# names stay importable from this module for existing callers and tests.
_project_relative_entity_id = _file_writes.project_relative_entity_id
_emit_file_changed = _file_writes.emit_file_changed
_project_dropin_dir = _file_writes.project_dropin_dir
_is_under_project_blocks_dir = _file_writes.is_under_project_blocks_dir
_maybe_reload_blocks_after_save = _file_writes.maybe_reload_blocks_after_save


def _is_new_custom_block_scaffold_path(path: str) -> bool:
    """Return True only for the ``blocks/<name>.py`` scaffold path."""
    # Development references: ADR-036.
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    return (
        len(parts) == 2 and parts[0] == "blocks" and Path(parts[1]).name == parts[1] and Path(parts[1]).suffix == ".py"
    )


def _request_source_id(request: Request, body: FileWriteRequest) -> str | None:
    return body.source_id or request.headers.get("X-Source-Id") or request.headers.get("X-File-Source-Id")


def _request_source(request: Request, body: FileWriteRequest) -> str:
    explicit = body.source or request.headers.get("X-File-Source") or request.headers.get("X-Source")
    if explicit in _API_SOURCES:
        return explicit
    changed_by = request.headers.get("X-Changed-By")
    if changed_by and changed_by not in {"api", "canvas"}:
        return "agent"
    return "canvas"


def _resolve_project_file(runtime: ApiRuntime, project_id: str, path: str) -> tuple[Path, Path]:
    """Resolve ``project_id`` + relative ``path`` to a sandboxed absolute path.

    Returns ``(project_root, target_absolute_path)``. Raises ``HTTPException``
    with the appropriate status code on any rejection. This is the shared
    sandbox check used by both GET and PUT 鈥?kept as a helper so both
    endpoints enforce the rules identically.

    Rejection codes (per  搂3.2):
      404: project unknown
      400: empty path / contains ``..`` segment / path is a directory
      403: resolved path escapes project root (symlink, traversal)
      415: extension not in :data:`ADR036_FILE_ALLOWLIST`

    Size cap and existence/UTF-8 checks are done by the caller because
    they apply differently to read vs. write.
    """
    # Development references: ADR-036.
    project = runtime.known_projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    if not path:
        raise HTTPException(status_code=400, detail="path query parameter is required")
    # Reject ``..`` segments early 鈥?same belt-and-braces as project_tree.
    parts = path.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise HTTPException(status_code=403, detail="Path traversal is not allowed")

    project_root = Path(os.path.realpath(project.path))
    root_str = str(project_root)
    candidate = os.path.realpath(os.path.join(root_str, path))
    # CodeQL py/path-injection sanitiser: the realpath-normalised candidate must
    # start with the root plus a separator -- the guard CodeQL models (it does
    # not model ``commonpath``). The separator keeps a sibling such as
    # ``<root>-other`` out; a different drive on Windows fails the prefix too.
    # The root itself is never a file, so it is refused with the escapes.
    prefix = root_str if root_str.endswith(os.sep) else root_str + os.sep
    if not candidate.startswith(prefix):
        raise HTTPException(status_code=403, detail="Path escapes project root")

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
    """Read a project-relative file as UTF-8 text.

    Enforce project containment, the extension allowlist, and the size limit.
    Reject files that cannot be decoded as UTF-8.
    """
    # Development references: ADR-036.
    project_root, target = _resolve_project_file(runtime, project_id, path)

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
        # Binary file flagged as text by extension 鈥?refuse rather than
        # serve mojibake into Monaco.
        raise HTTPException(
            status_code=415,
            detail=f"File is not valid UTF-8: {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read failed: {exc}") from exc

    entity_id = _project_relative_entity_id(project_root, target)
    state_version = runtime.current_entity_version(FILE_ENTITY_CLASS, entity_id, path=target)

    return FileReadResponse(
        content=content,
        mtime=stat.st_mtime,
        size=stat.st_size,
        encoding="utf-8",
        state_version=state_version,
        entity_id=entity_id,
        timestamp=_now_iso(),
    )


@router.put("/{project_id:path}/file", response_model=FileWriteResponse)
async def write_project_file(
    project_id: str,
    runtime: RuntimeDep,
    body: FileWriteRequest,
    request: Request,
    path: str = "",
) -> FileWriteResponse:
    """Write a project-relative file atomically.

    Sandbox, extension allowlist, and size limit. Size cap is checked
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
    # Development references: ADR-036.
    project_root, target = _resolve_project_file(runtime, project_id, path)

    encoded = body.content.encode("utf-8")
    if len(encoded) > ADR036_FILE_SIZE_CAP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"Content size {len(encoded)} exceeds editor cap {ADR036_FILE_SIZE_CAP_BYTES} bytes"),
        )

    if body.create_parent_dirs and _is_new_custom_block_scaffold_path(path):
        registered_project_root = Path(os.path.realpath(runtime.known_projects[project_id].path))
        blocks_dir = registered_project_root / "blocks"
        if not blocks_dir.exists():
            blocks_dir.mkdir()
    if not target.parent.exists():
        # We do not auto-create directory trees; reject explicitly so the
        # frontend can surface a clear error rather than silently inventing
        # folders behind the user's back.
        raise HTTPException(status_code=404, detail="Parent directory does not exist")
    if target.exists() and target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    # ADR-055 Spec 2 FR-005 (#2279): the atomic write, the watcher self-write
    # marks, the lint-gated registry reload (ADR-036 §3.5 / ADR-053 FR-062),
    # and the ``file.changed`` event are the shared write path the MCP author
    # tools use too. ``target`` is returned by _resolve_project_file only after
    # realpath + commonpath sandbox validation against ``project_root``.
    # lgtm[py/path-injection]
    try:
        change = await _file_writes.write_project_file(
            runtime,
            project_id=project_id,
            project_root=project_root,
            target=target,
            content=body.content,
            source=_request_source(request, body),
            source_id=_request_source_id(request, body),
            changed_by=request.headers.get("X-Changed-By"),
            expected_state_version=body.expected_state_version,
        )
    except FileWriteConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
    except ProjectFileWriteError as exc:
        # Disk full / permissions / simulated rename failures surface as a 500
        # with the same "write failed: ..." / "post-write stat failed: ..."
        # detail the route always returned.
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    assert change.mtime is not None and change.size is not None  # a completed write always stats
    return FileWriteResponse(
        mtime=change.mtime,
        size=change.size,
        state_version=change.version,
        entity_id=change.entity_id,
        source=change.payload["source"],
        source_id=change.payload["source_id"],
        kind=change.kind,
        timestamp=change.payload["timestamp"],
    )


# ---------------------------------------------------------------------------
# Greedy ``/{project_id:path}`` handlers 鈥?declared AFTER the more specific
# ``/{project_id:path}/file`` routes above so FastAPI matches the file
# routes first. See ADR-036 audit P1-1 for why this ordering matters.
# ---------------------------------------------------------------------------


@router.get("/{project_id:path}", response_model=ProjectResponse)
async def get_project(request: Request, project_id: str, runtime: RuntimeDep) -> ProjectResponse:
    """Retrieve and open a project by identifier or filesystem path."""
    try:
        project = runtime.open_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectRunsLiveError as exc:
        raise _runs_live_conflict(exc) from exc
    await ensure_project_mcp_server(request.app, runtime, Path(project.path))
    # ADR-034 Phase 2: refresh the workflow filesystem watcher to point at
    # the newly active project. ``start_for_project`` is idempotent 鈥?if the
    # caller re-opens the same project it returns immediately without
    # disturbing the existing observer.
    _restart_workflow_watcher(project.path)
    return ProjectResponse(**runtime.project_response(project))


def _restart_workflow_watcher(project_path: str) -> None:
    """Best-effort: point the global watcher at *project_path*'s workflows/.

    Failure to start the observer is logged but does not affect the project
    open response 鈥?the canvas continues to work without auto-refresh and
    the user sees their workflow YAMLs the next time they reload manually.
    """
    import asyncio
    import logging
    from pathlib import Path

    from scistudio.api.routes import workflow_watcher as watcher_module

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
    except ProjectRunsLiveError as exc:
        raise _runs_live_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
