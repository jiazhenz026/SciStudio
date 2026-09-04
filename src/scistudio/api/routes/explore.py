"""The Explore Session API — the only door onto the session runtime.

ADR-054 spec 3 (``docs/specs/adr-054-explore-session.md``), task T-017:

* **FR-056** — every operation the session offers has a route here: open over a
  block's outputs, a file, or a paused run; list; close; commit to branch; read
  and write cells; run one cell, the stale set, or a cell with its upstream;
  toggle a cell enabled; interrupt; restart; the graph, the marks, and the
  bindings; a windowed read of a variable; the emission of a snippet from a
  panel; the kernel list and ending a kernel; a packaging check and packaging.
* **FR-057** — every session event reaches the frontend over the WebSocket hub
  the workflow already uses. :func:`register_explore_subscriber` is what
  ``scistudio.api.ws`` subscribes with, so a client keeps **one** connection.
* **FR-058** — nothing here reaches the kernel except through the service's
  queue and bridge. Every route in this module calls a method on
  :class:`~scistudio.explore.session.SessionService` or on one of its
  :class:`~scistudio.explore.session.ExploreSession` objects, and this module
  imports neither :mod:`scistudio.explore.kernel` nor
  :mod:`scistudio.explore.kernel_bridge`. A test in
  ``tests/api/test_explore_routes.py`` pins that import set, because "the
  route module is a door" is the kind of rule a single convenient import ends.

**The route module is a door, not a place to put logic.** Where an operation
needs a decision — which cells the stale set holds, whether a snippet may be
admitted, whether a notebook can be packaged — the decision is the session's or
packaging's and this module only translates it into a status code and a body.

**The refusal shape (FR-058).** Every refusal the session raises comes back as
a ``4xx`` whose ``detail`` is an object::

    {"detail": {"error": "<kind>", "message": "<text>", ...}}

``error`` is a stable machine-readable kind from :data:`_REFUSALS`; ``message``
is the session's own text; the remaining fields are whatever that refusal
carries (the panel and statement of a refused emission, the packaging problems
of a refused notebook). A refusal must never surface as a bare ``500``: a 500
tells the frontend nothing, and the emission path in particular has a side
effect to undo — which is why
:meth:`~scistudio.explore.session.ExploreSession.emit_snippet` removes the cell
it inserted before re-raising, and why a route test asserts the notebook is
unchanged after a refused emission rather than merely asserting the status code.

**Sessions are addressed by id.** The path parameter is the ``session_id`` the
open and list responses carry, never a notebook path: a project-relative path
holds ``/`` and would swallow the rest of the route. Reopening a notebook the
list reported as closed is ``POST /api/explore/sessions`` with
``source="notebook"``.

**Mounting.** ``create_app`` must ``include_router(explore.router)`` for these
routes to exist in the running application; the spec's affected-file table does
not name ``src/scistudio/api/app.py``, so that one line is the integrating
change and is tracked on issue #2240.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime
from scistudio.explore.notebook import NotebookStoreError
from scistudio.explore.queue import PanelFrozenError, SnippetRefusedError
from scistudio.explore.session import (
    BoundRun,
    ExploreSession,
    NothingToExploreError,
    SessionError,
    SessionEvent,
    SessionEventType,
    SessionService,
    UnknownSessionError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/explore", tags=["explore"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: Every WebSocket frame this subsystem publishes is prefixed, so a session
#: event can never collide with an engine event type on the shared hub (FR-057).
EXPLORE_EVENT_PREFIX = "explore."


# ---------------------------------------------------------------------------
# The service registry (one SessionService per project)
# ---------------------------------------------------------------------------

#: Resolved project directory -> the service that owns its sessions and kernels.
#: Module state rather than runtime state because ``ApiRuntime`` belongs to
#: another agent's write set; the registry is keyed by path so a project switch
#: reaches a different service rather than a stale one.
_services: dict[str, SessionService] = {}
_services_lock = threading.Lock()


def _build_service(project_dir: Path, runtime: ApiRuntime) -> SessionService:
    """Construct the session service for *project_dir*.

    The test seam: ``tests/api/test_explore_routes.py`` monkeypatches this to
    hand back a service with fake kernel and bridge factories, so the routes
    under test are the real ones while no ipykernel process is spawned.

    The git engine is best-effort. A project without a repository still opens,
    runs, and marks perfectly well; it writes no history, which is what
    :class:`~scistudio.explore.session.SessionService` documents for a service
    built without one.
    """
    git_engine = None
    try:
        from scistudio.core.versioning.git_engine import GitEngine

        candidate = GitEngine(project_dir)
        if candidate.is_repository(project_dir):
            git_engine = candidate
    except Exception:  # a missing git binary must not stop a session opening
        logger.warning("explore: no git engine for %s; sessions will write no history", project_dir, exc_info=True)

    return SessionService(
        project_dir,
        git_engine=git_engine,
        lineage_store=getattr(runtime, "lineage_store", None),
    )


def get_session_service(runtime: RuntimeDep) -> SessionService:
    """The session service for the active project, created on first use.

    Raises:
        HTTPException: 409 when no project is open. Every route here is about a
            notebook inside a project, so there is nothing to answer without one.
    """
    try:
        project = runtime.require_active_project()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"error": "no_active_project", "message": str(exc)}) from exc

    project_dir = Path(project.path).resolve()
    key = str(project_dir)
    with _services_lock:
        service = _services.get(key)
        if service is None:
            service = _build_service(project_dir, runtime)
            service.subscribe(broadcast_session_event)
            _services[key] = service
    return service


ServiceDep = Annotated[SessionService, Depends(get_session_service)]


# TODO(#2240): nothing in the running application calls this yet, and nothing
#   calls SessionService.retire_kernels on a branch change (FR-014). Both hang
#   off the same integrating change: create_app must include this router, and
#   the git branch-switch route must retire the project's kernels. Neither
#   src/scistudio/api/app.py nor src/scistudio/api/routes/git.py is in this
#   task's write set (ADR-054 spec 3 §4.2 lists neither file).
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/2240
def shutdown_session_services(*, commit: bool = False) -> None:
    """Shut every registered service down. Used by application teardown and tests."""
    with _services_lock:
        services = list(_services.values())
        _services.clear()
    for service in services:
        try:
            service.shutdown(commit=commit)
        except Exception:  # teardown must not raise
            logger.warning("explore: a session service failed to shut down", exc_info=True)


# ---------------------------------------------------------------------------
# The events (FR-057)
# ---------------------------------------------------------------------------

_ExploreSubscriber = Callable[[dict[str, Any]], None]
_explore_subscribers: set[_ExploreSubscriber] = set()
_explore_subscribers_lock = threading.Lock()


def register_explore_subscriber(callback: _ExploreSubscriber) -> None:
    """Receive every session event as a WebSocket frame.

    ``scistudio.api.ws.websocket_handler`` registers one subscriber per live
    connection, which is what puts the session events on the hub the workflow
    already uses rather than on a second socket (FR-057). Idempotent.
    """
    with _explore_subscribers_lock:
        _explore_subscribers.add(callback)


def unregister_explore_subscriber(callback: _ExploreSubscriber) -> None:
    """Remove a subscriber. Silently no-ops, so WS teardown can never raise."""
    with _explore_subscribers_lock:
        _explore_subscribers.discard(callback)


def serialise_session_event(event: SessionEvent) -> dict[str, Any]:
    """Render a :class:`SessionEvent` as the frame the frontend receives.

    The shape mirrors ``scistudio.api.ws.serialise_event``: a ``type``, the
    identifier the event is about, the payload under ``data``, and a timestamp.
    The type is prefixed with ``explore.`` so it cannot collide with an engine
    event type on the shared hub.
    """
    return {
        "type": f"{EXPLORE_EVENT_PREFIX}{event.type.value}",
        "session_id": event.session_id,
        "data": dict(event.payload),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def broadcast_session_event(event: SessionEvent) -> None:
    """Fan a session event out to every live WebSocket subscriber.

    Called by the session service on whichever thread published the event —
    the queue's worker thread for a cell run, the commit writer's thread for a
    commit. Each subscriber is responsible for reaching its own event loop
    safely; this side only guarantees it never raises into the session, because
    a subscriber's bug must not fail a cell run.
    """
    frame = serialise_session_event(event)
    with _explore_subscribers_lock:
        snapshot = list(_explore_subscribers)
    for callback in snapshot:
        try:
            callback(frame)
        except Exception:
            logger.warning("explore: a WebSocket subscriber raised on %s", frame["type"], exc_info=True)


# ---------------------------------------------------------------------------
# The refusal shape (FR-058)
# ---------------------------------------------------------------------------

#: Exception type -> (status code, machine-readable kind). Order matters: the
#: first entry whose type matches wins, so the specific subclasses are listed
#: before ``SessionError``, which every session refusal derives from.
_REFUSALS: tuple[tuple[type[BaseException], int, str], ...] = (
    (UnknownSessionError, 404, "session_not_found"),
    (NothingToExploreError, 409, "nothing_to_explore"),
    (SnippetRefusedError, 422, "snippet_refused"),
    (PanelFrozenError, 409, "panel_frozen"),
    (NotebookStoreError, 422, "notebook_unreadable"),
    (FileNotFoundError, 404, "notebook_not_found"),
    (SessionError, 409, "session_refused"),
)

#: ``(module, class name)`` -> ``(status code, kind)`` for the refusals raised by
#: modules this one must not import.
#:
#: ``scistudio.explore.kernel`` imports ``jupyter_client`` at module scope, and
#: ``scistudio.explore.packaging`` pulls in the block registry and the Code
#: Block; importing either here would make the whole API layer pay for a kernel
#: stack it may not have, at import time, on every start. Matching by name over
#: the raised exception's MRO costs nothing and needs no import, and the route
#: tests raise each of these through a route so a renamed class fails a test
#: rather than silently degrading to a 500.
_REFUSALS_BY_NAME: dict[tuple[str, str], tuple[int, str]] = {
    ("scistudio.explore.kernel", "KernelTimeoutError"): (504, "kernel_timeout"),
    ("scistudio.explore.kernel", "KernelDiedError"): (409, "kernel_died"),
    ("scistudio.explore.kernel", "KernelNotRunningError"): (409, "kernel_not_running"),
    ("scistudio.explore.kernel", "KernelLaunchError"): (502, "kernel_launch_failed"),
    ("scistudio.explore.kernel_bridge", "BridgeProtocolError"): (502, "bridge_error"),
    ("scistudio.explore.kernel_bridge", "BridgeError"): (502, "bridge_error"),
    ("scistudio.explore.packaging", "PackagingRefusedError"): (422, "packaging_refused"),
}


def _classify(exc: BaseException) -> tuple[int, str] | None:
    """The status code and kind for *exc*, or ``None`` when it is not a refusal.

    The by-name table is consulted first and over the whole MRO, so a subclass
    of ``KernelDiedError`` still reads as a dead kernel, and
    ``PackagingRefusedError`` — which is a ``ValueError`` — is not mistaken for
    something generic.
    """
    for ancestor in type(exc).__mro__:
        found = _REFUSALS_BY_NAME.get((getattr(ancestor, "__module__", ""), ancestor.__name__))
        if found is not None:
            return found
    for exc_type, status_code, kind in _REFUSALS:
        if isinstance(exc, exc_type):
            return status_code, kind
    return None


def _refusal_detail(exc: BaseException, kind: str) -> dict[str, Any]:
    """The body of a refusal: the kind, the session's own text, and its fields."""
    detail: dict[str, Any] = {"error": kind, "message": str(exc)}
    if isinstance(exc, SnippetRefusedError):
        detail["panel"] = exc.panel
        detail["statement"] = exc.statement
    elif isinstance(exc, PanelFrozenError):
        detail["panel"] = exc.panel
        detail["names"] = sorted(exc.names)
    elif kind == "packaging_refused":
        detail["problems"] = [problem.model_dump() for problem in _problem_models(getattr(exc, "problems", ()))]
    return detail


@contextmanager
def _refusals() -> Iterator[None]:
    """Translate a session refusal into the documented error shape (FR-058).

    Anything this does not recognise is left alone and becomes a 500, because a
    refusal shape that swallowed a genuine bug would hide it: the mapping is a
    closed list of things the session says *on purpose*.
    """
    try:
        yield
    except HTTPException:
        raise
    except BaseException as exc:
        classified = _classify(exc)
        if classified is None:
            raise
        status_code, kind = classified
        raise HTTPException(status_code=status_code, detail=_refusal_detail(exc, kind)) from exc


def _cell_or_404(session: ExploreSession, cell_id: str) -> None:
    """Refuse an unknown cell as a 404 rather than as the session's ``KeyError``."""
    try:
        session.document.cell(cell_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "cell_not_found", "message": f"No cell with id {cell_id!r} in this notebook."},
        ) from exc


async def _session(service: SessionService, session_id: str) -> ExploreSession:
    """The open session with *session_id*, or a 404 in the documented shape.

    A closed session is not a special case: closing removes it from the service,
    so asking about it afterwards is asking about a session that is not open.
    """
    with _refusals():
        return service.session_for(session_id)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class OpenSessionRequest(BaseModel):
    """Open a session (FR-056), over one of the sources FR-002 names.

    ``source`` selects which:

    * ``block_outputs`` — over the outputs of ``block_id``, from its most recent
      completed run or from ``run_id`` when one is given.
    * ``file`` — over ``path``, a file in the project's data tree.
    * ``paused_run`` — over the inputs ``block_id`` received in ``run_id``.
    * ``notebook`` — reopen the notebook at ``path``. Not a fourth source of
      FR-002: it is how a notebook the session list reported as closed is opened
      again, and it binds to nothing.
    """

    source: str = Field(description="block_outputs, file, paused_run, or notebook")
    block_id: str | None = Field(default=None, description="Required for block_outputs and paused_run.")
    run_id: str | None = Field(default=None, description="Required for paused_run; optional for block_outputs.")
    path: str | None = Field(default=None, description="Required for file and notebook.")
    name: str | None = Field(default=None, description="Notebook file stem; defaults per source.")


class PortModel(BaseModel):
    """One port of the run a session is bound to."""

    name: str
    type_name: str
    backend: str
    path: str
    format: str | None = None


class BoundRunModel(BaseModel):
    """The run a session is bound to, and the ports it was opened over."""

    run_id: str
    block_id: str
    opened_over: str
    ports: list[PortModel]


class CellModel(BaseModel):
    """One cell of the notebook, with the session's marks on it."""

    cell_id: str | None
    cell_type: str
    source: str
    enabled: bool
    marks: list[str]


class SessionModel(BaseModel):
    """An open session, as every route that returns one reports it."""

    session_id: str
    notebook_path: str
    has_kernel: bool
    needs_restart: bool
    current_cell: str | None
    notebook_commit: str | None
    bound_run: BoundRunModel | None
    cells: list[CellModel]


class SessionListItem(BaseModel):
    """One row of the session list (FR-006)."""

    notebook_path: str
    session_id: str | None
    has_kernel: bool
    is_open: bool
    readable: bool


class SessionListResponse(BaseModel):
    """Every notebook in the project's explore directory."""

    sessions: list[SessionListItem]


class CloseSessionResponse(BaseModel):
    """What closing a session produced."""

    session_id: str
    notebook_path: str
    branch_commit: str | None


class CommitResponse(BaseModel):
    """The branch commit, or ``None`` when the project has no git engine."""

    session_id: str
    sha: str | None


class CellsResponse(BaseModel):
    """The notebook's cells, as read (FR-056)."""

    session_id: str
    cells: list[CellModel]


class WriteCellRequest(BaseModel):
    """Replace one cell's source (FR-056)."""

    source: str


class InsertCellRequest(BaseModel):
    """Insert a cell, after ``after`` or at the end."""

    source: str = ""
    after: str | None = None


class EnabledRequest(BaseModel):
    """Toggle whether a cell is in the graph and may run (FR-056)."""

    enabled: bool


class RequestModel(BaseModel):
    """One queued execution request."""

    request_id: str
    cell_id: str
    kind: str
    state: str
    panel: str | None = None


class RunResponse(BaseModel):
    """What a run control enqueued — never more than it says it does."""

    session_id: str
    requests: list[RequestModel]


class KernelStateResponse(BaseModel):
    """The session's kernel after an interrupt or a restart."""

    session_id: str
    state: str
    pid: int | None
    memory_bytes: int | None
    needs_restart: bool


class EdgeModel(BaseModel):
    """One dependency edge: a reading cell, the cell that defines the name, the name."""

    reader: str
    definer: str
    name: str
    origin: str


class UnresolvedReadModel(BaseModel):
    """A read no enabled cell above resolves."""

    cell_id: str
    name: str


class GraphResponse(BaseModel):
    """The dependency graph over the enabled code cells (FR-056)."""

    session_id: str
    cells: list[str]
    edges: list[EdgeModel]
    unresolved_reads: list[UnresolvedReadModel]
    unknown_binding_cells: list[str]
    changed_sets: dict[str, list[str]]


class OutOfOrderReadModel(BaseModel):
    """Why a cell is marked out of order: the name and the two cells."""

    name: str
    definer: str | None
    last_binder: str | None


class CellMarksModel(BaseModel):
    """One cell's marks, and the reasons behind an out-of-order one."""

    cell_id: str
    marks: list[str]
    out_of_order_reads: list[OutOfOrderReadModel]


class MarksResponse(BaseModel):
    """Every marked cell, and which cell last bound each name (FR-056)."""

    session_id: str
    marks: list[CellMarksModel]
    stale: list[str]
    out_of_order: list[str]
    never_run: list[str]
    last_bound_by: dict[str, str]


class BindingModel(BaseModel):
    """One name, its type as the kernel reports it, and whether it is bound.

    ``exists_in_kernel`` is the half FR-056 asks for beyond the type name: a
    name the notebook changes but the kernel does not hold is a name the person
    has not run yet, and the difference is what the panel list is for. Names the
    kernel does not hold carry no type.
    """

    name: str
    exists_in_kernel: bool
    type_name: str | None = None
    type_module: str | None = None
    summary: str | None = None
    last_bound_by: str | None = None


class BindingsResponse(BaseModel):
    """The bindings with their type names and whether each exists (FR-056)."""

    session_id: str
    has_kernel: bool
    bindings: list[BindingModel]


class WindowRequest(BaseModel):
    """A windowed read of one variable, through the bridge (FR-056)."""

    name: str
    query: dict[str, Any] | None = None


class WindowResponse(BaseModel):
    """The preview envelope, exactly as the same provider returns it elsewhere."""

    session_id: str
    name: str
    envelope: dict[str, Any]


class EmitSnippetRequest(BaseModel):
    """A snippet a panel emitted into the notebook (FR-018, FR-056)."""

    source: str
    panel: str
    bound_names: list[str] = Field(default_factory=list)


class EmitSnippetResponse(BaseModel):
    """The cell the emission created and the request it enqueued."""

    session_id: str
    cell_id: str
    request: RequestModel


class KernelListItem(BaseModel):
    """One row of the kernel list (FR-016)."""

    session_id: str
    notebook_path: str
    state: str
    pid: int | None
    memory_bytes: int | None
    python_executable: str
    started_at: float | None


class KernelListResponse(BaseModel):
    """Every live kernel in the project, with its memory."""

    kernels: list[KernelListItem]


class PackagingProblemModel(BaseModel):
    """One reason packaging refuses, with the cells it is about."""

    kind: str
    message: str
    cell_ids: list[str]
    names: list[str]


class PackagedPortModel(BaseModel):
    """One port the generated block would declare."""

    name: str
    direction: str
    data_type: str
    extension: str
    bound_name: str


class PackagingCheckRequest(BaseModel):
    """Ask whether the notebook can be packaged, writing nothing (FR-039)."""

    file_ports: dict[str, str] = Field(
        default_factory=dict,
        description="Port name to notebook variable, for a session opened over a file (FR-038).",
    )


class PackagingCheckResponse(BaseModel):
    """The plan: the slice, the ports, and every refusal reason."""

    session_id: str
    is_packageable: bool
    cells: list[str]
    inputs: list[PackagedPortModel]
    outputs: list[PackagedPortModel]
    problems: list[PackagingProblemModel]


class PackageRequest(PackagingCheckRequest):
    """Package the notebook into a Code Block (FR-037, FR-041, FR-044)."""

    block_name: str
    on_new_input: str = Field(default="replay", description="replay or ask (FR-044, FR-046).")


class PackageResponse(BaseModel):
    """What packaging wrote."""

    session_id: str
    block_name: str
    class_name: str
    declaration_path: str
    notebook_path: str
    notebook_commit: str
    cells: list[str]
    inputs: list[PackagedPortModel]
    outputs: list[PackagedPortModel]
    on_new_input: str


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _cell_models(session: ExploreSession) -> list[CellModel]:
    marks = session.marks_by_cell
    return [
        CellModel(
            cell_id=cell.cell_id,
            cell_type=cell.cell_type,
            source=cell.source,
            enabled=cell.enabled,
            marks=sorted(mark.value for mark in marks.get(cell.cell_id or "", frozenset())),
        )
        for cell in session.cells()
    ]


def _bound_run_model(bound: BoundRun | None) -> BoundRunModel | None:
    if bound is None:
        return None
    return BoundRunModel(
        run_id=bound.run_id,
        block_id=bound.block_id,
        opened_over=bound.opened_over,
        ports=[
            PortModel(name=p.name, type_name=p.type_name, backend=p.backend, path=p.path, format=p.format)
            for p in bound.ports
        ],
    )


def _session_model(session: ExploreSession) -> SessionModel:
    return SessionModel(
        session_id=session.session_id,
        notebook_path=session.relative_path,
        has_kernel=session.has_kernel,
        needs_restart=session.needs_restart,
        current_cell=session.current_cell,
        notebook_commit=session.notebook_commit,
        bound_run=_bound_run_model(session.bound_run),
        cells=_cell_models(session),
    )


def _request_model(request: Any) -> RequestModel:
    return RequestModel(
        request_id=request.request_id,
        cell_id=request.cell_id,
        kind=str(request.kind),
        state=str(request.state),
        panel=request.panel,
    )


def _kernel_state_response(session: ExploreSession) -> KernelStateResponse:
    status = session.kernel_status()
    return KernelStateResponse(
        session_id=session.session_id,
        state=status.state if status is not None else "not-started",
        pid=status.pid if status is not None else None,
        memory_bytes=status.memory_bytes if status is not None else None,
        needs_restart=session.needs_restart,
    )


def _port_models(ports: Any) -> list[PackagedPortModel]:
    return [
        PackagedPortModel(
            name=port.name,
            direction=port.direction,
            data_type=port.data_type,
            extension=port.extension,
            bound_name=port.bound_name,
        )
        for port in ports
    ]


def _problem_models(problems: Any) -> list[PackagingProblemModel]:
    return [
        PackagingProblemModel(
            kind=str(problem.kind),
            message=problem.message,
            cell_ids=list(problem.cell_ids),
            names=list(problem.names),
        )
        for problem in problems
    ]


# ---------------------------------------------------------------------------
# FR-056: open, list, close, commit to branch
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionModel)
async def open_session(service: ServiceDep, payload: OpenSessionRequest) -> SessionModel:
    """Open a session over a block's outputs, a file, a paused run, or a notebook.

    No kernel is started: a session opens with a notebook and nothing running,
    and the first run is what launches ipykernel.
    """

    def _open() -> ExploreSession:
        source = payload.source
        if source == "block_outputs":
            if not payload.block_id:
                raise _bad_request("block_id is required to open over a block's outputs.")
            return service.open_over_block_outputs(payload.block_id, run_id=payload.run_id, name=payload.name)
        if source == "paused_run":
            if not payload.block_id or not payload.run_id:
                raise _bad_request("block_id and run_id are both required to open over a paused run.")
            return service.open_over_paused_run(payload.run_id, payload.block_id, name=payload.name)
        if source == "file":
            if not payload.path:
                raise _bad_request("path is required to open over a file.")
            return service.open_over_file(payload.path, name=payload.name)
        if source == "notebook":
            if not payload.path:
                raise _bad_request("path is required to reopen a notebook.")
            return service.open_notebook(payload.path)
        raise _bad_request(
            f"{source!r} is not a session source; expected 'block_outputs', 'file', 'paused_run', or 'notebook'."
        )

    with _refusals():
        session = await run_in_threadpool(_open)
    return _session_model(session)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": "invalid_request", "message": message})


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(service: ServiceDep) -> SessionListResponse:
    """Every notebook in the project's explore directory, open or not (FR-006).

    A notebook that is on disk but cannot be parsed is listed with
    ``readable=false`` rather than omitted, because a notebook that vanished
    from the list is harder to explain than one that says it is broken.
    """
    listings = await run_in_threadpool(service.list_sessions)
    return SessionListResponse(
        sessions=[
            SessionListItem(
                notebook_path=listing.notebook_path,
                session_id=listing.session_id,
                has_kernel=listing.has_kernel,
                is_open=listing.is_open,
                readable=listing.readable,
            )
            for listing in listings
        ]
    )


@router.get("/sessions/{session_id}", response_model=SessionModel)
async def get_session(service: ServiceDep, session_id: str) -> SessionModel:
    """One open session, its cells, and its marks."""
    session = await _session(service, session_id)
    return _session_model(session)


@router.delete("/sessions/{session_id}", response_model=CloseSessionResponse)
async def close_session(
    service: ServiceDep,
    session_id: str,
    commit: Annotated[bool, Query(description="Write the branch commit when the notebook changed.")] = True,
) -> CloseSessionResponse:
    """End a session: its kernel, its notebook, and one branch commit (FR-006, FR-036)."""
    session = await _session(service, session_id)
    notebook_path = session.relative_path
    with _refusals():
        sha = await run_in_threadpool(lambda: service.close(session, commit=commit))
    return CloseSessionResponse(session_id=session_id, notebook_path=notebook_path, branch_commit=sha)


@router.post("/sessions/{session_id}/commit", response_model=CommitResponse)
async def commit_session_to_branch(
    service: ServiceDep,
    session_id: str,
    message: Annotated[str | None, Body(embed=True)] = None,
) -> CommitResponse:
    """Write one commit of the notebook, outputs stripped, to the branch (FR-036).

    ``sha`` is ``null`` when the project has no git engine, which is what a
    project without a repository gets rather than an error.
    """
    session = await _session(service, session_id)
    with _refusals():
        sha = await run_in_threadpool(lambda: service.commit_to_branch(session, message=message))
    return CommitResponse(session_id=session_id, sha=sha)


# ---------------------------------------------------------------------------
# FR-056: read and write cells, toggle enabled
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/cells", response_model=CellsResponse)
async def read_cells(service: ServiceDep, session_id: str) -> CellsResponse:
    """The notebook's cells with their sources, enabled flags, and marks."""
    session = await _session(service, session_id)
    return CellsResponse(session_id=session_id, cells=_cell_models(session))


@router.put("/sessions/{session_id}/cells/{cell_id}", response_model=CellsResponse)
async def write_cell(
    service: ServiceDep,
    session_id: str,
    cell_id: str,
    payload: WriteCellRequest,
) -> CellsResponse:
    """Replace one cell's source. The analysis re-runs and an event is published."""
    session = await _session(service, session_id)
    _cell_or_404(session, cell_id)
    with _refusals():
        await run_in_threadpool(lambda: session.set_cell_source(cell_id, payload.source))
    return CellsResponse(session_id=session_id, cells=_cell_models(session))


@router.post("/sessions/{session_id}/cells", response_model=CellsResponse)
async def insert_cell(service: ServiceDep, session_id: str, payload: InsertCellRequest) -> CellsResponse:
    """Insert a cell after ``after``, or at the end when it is absent."""
    session = await _session(service, session_id)
    if payload.after is not None:
        _cell_or_404(session, payload.after)
    with _refusals():
        await run_in_threadpool(lambda: session.insert_cell(payload.source, after=payload.after))
    return CellsResponse(session_id=session_id, cells=_cell_models(session))


@router.put("/sessions/{session_id}/cells/{cell_id}/enabled", response_model=CellsResponse)
async def set_cell_enabled(
    service: ServiceDep,
    session_id: str,
    cell_id: str,
    payload: EnabledRequest,
) -> CellsResponse:
    """Toggle whether a cell is in the graph and may run (FR-056)."""
    session = await _session(service, session_id)
    _cell_or_404(session, cell_id)
    with _refusals():
        await run_in_threadpool(lambda: session.set_cell_enabled(cell_id, enabled=payload.enabled))
    return CellsResponse(session_id=session_id, cells=_cell_models(session))


# ---------------------------------------------------------------------------
# FR-056: run one cell, run the stale set, run with upstream
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/cells/{cell_id}/run", response_model=RunResponse)
async def run_cell(service: ServiceDep, session_id: str, cell_id: str) -> RunResponse:
    """Enqueue one cell — the cell named, and nothing else (FR-017)."""
    session = await _session(service, session_id)
    _cell_or_404(session, cell_id)
    with _refusals():
        request = await run_in_threadpool(lambda: session.run_cell(cell_id))
    return RunResponse(session_id=session_id, requests=[_request_model(request)])


@router.post("/sessions/{session_id}/run-stale", response_model=RunResponse)
async def run_stale(service: ServiceDep, session_id: str) -> RunResponse:
    """Enqueue the stale cells in written order and nothing else (FR-024)."""
    session = await _session(service, session_id)
    with _refusals():
        requests = await run_in_threadpool(session.run_stale)
    return RunResponse(session_id=session_id, requests=[_request_model(r) for r in requests])


@router.post("/sessions/{session_id}/cells/{cell_id}/run-with-upstream", response_model=RunResponse)
async def run_with_upstream(service: ServiceDep, session_id: str, cell_id: str) -> RunResponse:
    """Enqueue the cell with the part of its backward slice that needs re-running (FR-024)."""
    session = await _session(service, session_id)
    _cell_or_404(session, cell_id)
    with _refusals():
        requests = await run_in_threadpool(lambda: session.run_with_upstream(cell_id))
    return RunResponse(session_id=session_id, requests=[_request_model(r) for r in requests])


# ---------------------------------------------------------------------------
# FR-056: interrupt, restart
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/interrupt", response_model=KernelStateResponse)
async def interrupt_session(service: ServiceDep, session_id: str) -> KernelStateResponse:
    """Interrupt the running cell without ending the session (FR-013)."""
    session = await _session(service, session_id)
    with _refusals():
        await run_in_threadpool(session.interrupt)
    return _kernel_state_response(session)


@router.post("/sessions/{session_id}/restart", response_model=KernelStateResponse)
async def restart_session(service: ServiceDep, session_id: str) -> KernelStateResponse:
    """Start a fresh kernel and reset every mark to never-run (FR-013, FR-023)."""
    session = await _session(service, session_id)
    with _refusals():
        await run_in_threadpool(session.restart_kernel)
    return _kernel_state_response(session)


# ---------------------------------------------------------------------------
# FR-056: the graph, the marks, the bindings
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/graph", response_model=GraphResponse)
async def get_graph(service: ServiceDep, session_id: str) -> GraphResponse:
    """The dependency graph over the enabled code cells (FR-056)."""
    session = await _session(service, session_id)
    graph = session.graph
    return GraphResponse(
        session_id=session_id,
        cells=list(graph.cells),
        edges=[
            EdgeModel(reader=edge.reader, definer=edge.definer, name=edge.name, origin=str(edge.origin))
            for edge in graph.edges
        ],
        unresolved_reads=[UnresolvedReadModel(cell_id=read.cell_id, name=read.name) for read in graph.unresolved_reads],
        unknown_binding_cells=list(graph.unknown_binding_cells),
        changed_sets={cell_id: sorted(names) for cell_id, names in graph.changed_sets.items()},
    )


@router.get("/sessions/{session_id}/marks", response_model=MarksResponse)
async def get_marks(service: ServiceDep, session_id: str) -> MarksResponse:
    """Every marked cell, why an out-of-order mark was raised, and the binder map."""
    session = await _session(service, session_id)
    marks_by_cell = session.marks_by_cell
    return MarksResponse(
        session_id=session_id,
        marks=[
            CellMarksModel(
                cell_id=cell_id,
                marks=sorted(mark.value for mark in marks),
                out_of_order_reads=[
                    OutOfOrderReadModel(name=read.name, definer=read.definer, last_binder=read.last_binder)
                    for read in session.out_of_order_reads(cell_id)
                ],
            )
            for cell_id, marks in sorted(marks_by_cell.items())
        ],
        stale=list(session.stale_cells()),
        out_of_order=list(session.out_of_order_cells()),
        never_run=list(session.never_run_cells()),
        last_bound_by=dict(session.last_bound_by),
    )


@router.get("/sessions/{session_id}/bindings", response_model=BindingsResponse)
async def get_bindings(service: ServiceDep, session_id: str) -> BindingsResponse:
    """The bindings with their type names and whether each exists in the kernel (FR-056).

    The set of names is the union of what the kernel holds now and what the
    analysis says the notebook's cells change or declare as outputs, so a name
    the notebook produces but the kernel has not bound yet is reported as
    ``exists_in_kernel=false`` rather than being absent from the answer.
    """
    session = await _session(service, session_id)
    with _refusals():
        bound = await run_in_threadpool(session.bindings)

    by_name = {binding.name: binding for binding in bound}
    known: set[str] = set(by_name)
    for changed in session.graph.changed_sets.values():
        known.update(changed)
    for fact in session.facts:
        for declaration in fact.outputs:
            known.update(declaration.keywords)
            known.update(declaration.arguments)

    last_bound_by = session.last_bound_by
    bindings = []
    for name in sorted(known):
        binding = by_name.get(name)
        bindings.append(
            BindingModel(
                name=name,
                exists_in_kernel=binding is not None,
                type_name=binding.type_name if binding is not None else None,
                type_module=binding.type_module if binding is not None else None,
                summary=binding.summary if binding is not None else None,
                last_bound_by=last_bound_by.get(name),
            )
        )
    return BindingsResponse(session_id=session_id, has_kernel=session.has_kernel, bindings=bindings)


# ---------------------------------------------------------------------------
# FR-056: a windowed read, and the emission of a snippet from a panel
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/window", response_model=WindowResponse)
async def window_variable(service: ServiceDep, session_id: str, payload: WindowRequest) -> WindowResponse:
    """A windowed read of one variable, through the bridge (FR-056, T-010).

    A read, not a submission: it queues behind a running cell in the kernel and
    completes when the cell does, which is the shallow freeze ADR-054 §6.3
    accepts.
    """
    session = await _session(service, session_id)
    with _refusals():
        envelope = await run_in_threadpool(lambda: session.window(payload.name, query=payload.query))
    return WindowResponse(session_id=session_id, name=payload.name, envelope=envelope)


@router.post("/sessions/{session_id}/snippets", response_model=EmitSnippetResponse)
async def emit_snippet(service: ServiceDep, session_id: str, payload: EmitSnippetRequest) -> EmitSnippetResponse:
    """Admit a snippet a panel emitted, insert it, and enqueue it (FR-018, FR-025).

    Admission happens before anything is inserted, and a refusal at submission
    removes the cell again, so a refused emission leaves the notebook exactly as
    it was. That is what the ``snippet_refused`` and ``panel_frozen`` shapes
    promise, and what a route test asserts by comparing the cell list either
    side of the refusal.
    """
    session = await _session(service, session_id)
    with _refusals():
        cell_id, request = await run_in_threadpool(
            lambda: session.emit_snippet(payload.source, panel=payload.panel, bound_names=payload.bound_names)
        )
    return EmitSnippetResponse(session_id=session_id, cell_id=cell_id, request=_request_model(request))


# ---------------------------------------------------------------------------
# FR-056: the kernel list and ending a kernel
# ---------------------------------------------------------------------------


@router.get("/kernels", response_model=KernelListResponse)
async def list_kernels(service: ServiceDep) -> KernelListResponse:
    """Every live kernel in the project, with its session and its memory (FR-016).

    Each reading is taken from outside the process, so the list answers while
    every kernel in it is stuck in a long cell.
    """
    listings = await run_in_threadpool(service.kernels)
    return KernelListResponse(
        kernels=[
            KernelListItem(
                session_id=listing.session_id,
                notebook_path=listing.notebook_path,
                state=listing.status.state,
                pid=listing.status.pid,
                memory_bytes=listing.status.memory_bytes,
                python_executable=listing.status.python_executable,
                started_at=listing.status.started_at,
            )
            for listing in listings
        ]
    )


@router.delete("/kernels/{session_id}", response_model=KernelStateResponse)
async def end_kernel(service: ServiceDep, session_id: str) -> KernelStateResponse:
    """Terminate one session's kernel process, leaving the session open (FR-016)."""
    session = await _session(service, session_id)
    with _refusals():
        await run_in_threadpool(lambda: service.end_kernel(session_id))
    return _kernel_state_response(session)


# ---------------------------------------------------------------------------
# FR-056: a packaging check, and packaging
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/packaging/check", response_model=PackagingCheckResponse)
async def check_session_packaging(
    service: ServiceDep,
    session_id: str,
    payload: PackagingCheckRequest,
) -> PackagingCheckResponse:
    """Answer whether the notebook can be packaged, and what it would produce (FR-039).

    Writes nothing, and collects every refusal rather than stopping at the
    first: a person fixing a notebook wants the whole list.

    The marks and the bound types are the session's and are passed in as
    arguments, because packaging is a pure function of the notebook and what it
    is given and never reaches into a session to find them.
    """
    from scistudio.explore.packaging import check_packaging

    session = await _session(service, session_id)
    with _refusals():
        plan = await run_in_threadpool(
            lambda: check_packaging(
                session.document,
                marks=session.cell_marks(),
                bindings=session.binding_types(),
                observations=session.observations,
                file_ports=payload.file_ports,
            )
        )
    return PackagingCheckResponse(
        session_id=session_id,
        is_packageable=plan.is_packageable,
        cells=list(plan.cells),
        inputs=_port_models(plan.inputs),
        outputs=_port_models(plan.outputs),
        problems=_problem_models(plan.problems),
    )


@router.post("/sessions/{session_id}/package", response_model=PackageResponse)
async def package_session(service: ServiceDep, session_id: str, payload: PackageRequest) -> PackageResponse:
    """Package the notebook's declared-output slice into a Code Block (FR-037).

    Refuses in the documented shape when any check of FR-039 refuses, with every
    problem under ``detail.problems``; nothing is written in that case.

    The ``packaged`` event of FR-057 is published from here because packaging is
    a module-level function of the notebook and the marks rather than a method
    on the service — the service is what owns the event stream, so the route
    hands the event to it rather than inventing a second channel.
    """
    from scistudio.explore.packaging import package_notebook

    session = await _session(service, session_id)
    commit = session.notebook_commit
    if not commit:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_notebook_commit",
                "message": (
                    "This notebook has no commit yet, and a packaged block's version is the commit it was "
                    "packaged from (FR-041). Run a cell first."
                ),
            },
        )

    def _package() -> Any:
        return package_notebook(
            session.document,
            project_dir=service.project_dir,
            block_name=payload.block_name,
            notebook_commit=commit,
            marks=session.cell_marks(),
            bindings=session.binding_types(),
            observations=session.observations,
            file_ports=payload.file_ports,
            on_new_input=payload.on_new_input,
        )

    with _refusals():
        packaged = await run_in_threadpool(_package)

    service.publish(
        SessionEvent(
            type=SessionEventType.PACKAGED,
            session_id=session.session_id,
            payload={
                "block_name": packaged.block_name,
                "class_name": packaged.class_name,
                "declaration_path": str(packaged.declaration_path),
                "notebook_path": str(packaged.notebook_path),
                "notebook_commit": packaged.notebook_commit,
                "cells": list(packaged.cells),
                "on_new_input": packaged.on_new_input,
            },
        )
    )
    return PackageResponse(
        session_id=session_id,
        block_name=packaged.block_name,
        class_name=packaged.class_name,
        declaration_path=str(packaged.declaration_path),
        notebook_path=str(packaged.notebook_path),
        notebook_commit=packaged.notebook_commit,
        cells=list(packaged.cells),
        inputs=_port_models(packaged.inputs),
        outputs=_port_models(packaged.outputs),
        on_new_input=packaged.on_new_input,
    )
