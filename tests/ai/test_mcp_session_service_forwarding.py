"""The session tools act on the person's session service, never on a second one.

ADR-054 spec 5 FR-024 (issue #2254), closing follow-up **F-B3-1** in
``docs/planning/adr-054-assembly-followups.md``.

The bug this file exists to hold shut was invisible to every unit test that came
before it, because it is not a bug in what a tool asks the session API for — it
is a bug in *which session* answers. Under the topology the desktop app runs,
``scistudio mcp-bridge`` proxies the agent's stdio into the running GUI's
in-process MCP server, so the seven session tools execute inside the very
process that already holds the person's
:class:`~scistudio.explore.session.SessionService`. With no way to reach it, the
tools stood a second service up beside it: two ``NotebookStore`` documents over
one file, and an appended cell that reached the person only when their own
session next reloaded.

So the assertions here are about **object identity and the event stream**, not
about content. A content assertion would pass on the broken wiring: the routes
call ``reload_if_changed`` before answering, so a cell written to the file by a
second service shows up in ``GET /sessions/{id}/cells`` anyway. What does not
survive a second service is that the tool and the routes hold *the same*
``SessionService`` and *the same* ``ExploreSession``, and that a cell the agent
appends is broadcast on the WebSocket the person's window is already listening
to — which is exactly what FR-024 promises and what
``test_a_cell_the_tool_appends_reaches_the_person_s_event_stream`` fails without.

The attached tests therefore drive the real FastAPI app: the production
``MCPContext`` is the ``_RuntimeAdapter`` defined inside
``scistudio.api.app.lifespan``, and a member that adapter does not forward never
reaches a tool however correct both ends are. The detached tests use a stub
context instead, because "there is no backend" is precisely the condition an app
fixture cannot produce.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp._context import MCPContext
from scistudio.ai.agent.mcp.tools_explore import _service, append_cell
from scistudio.api.app import create_app
from scistudio.api.routes import explore
from scistudio.api.runtime import ApiRuntime
from scistudio.explore.notebook import new_code_cell, new_notebook, write_notebook

_T = TypeVar("_T")

NOTEBOOK = "explore/qc.ipynb"


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run one tool coroutine. The repository does not install pytest-asyncio."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# The attached topology: a real app, and the adapter its lifespan installs
# ---------------------------------------------------------------------------


def _point_home_at(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the runtime's user-level project registry to *target*."""
    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: target))


@pytest.fixture(scope="module")
def _module_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """One isolated SciStudio home for the whole module."""
    home = tmp_path_factory.mktemp("sessvc-home")
    with pytest.MonkeyPatch.context() as monkeypatch:
        _point_home_at(home, monkeypatch)
        yield home


@pytest.fixture(scope="module")
def client(_module_home: Path) -> Iterator[TestClient]:
    """One live app for the whole module, lifespan and all.

    Module-scoped for the reason ``tests/ai/test_workspace_focus.py`` gives:
    what each test needs is the production ``MCPContext``, which is per-process,
    and the CI parallel phase runs on a 600s budget this track is already close
    to. Isolation comes from the ``project`` fixture — a project per test — and
    from tearing the session services down after each one.
    """
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_session_state(client: TestClient) -> Iterator[None]:
    """Leave no session service, and no borrowed context, behind a test.

    Three registries here are process-global — ``api.routes.explore._services``,
    the detached cache in ``tools_explore._service``, and the MCP context slot —
    so a test that left one populated would decide the next test's answer.

    It takes ``client`` so that the module's app is up *before* the snapshot is
    taken; an autouse fixture runs ahead of the test's own, and one that
    snapshotted an empty slot would restore emptiness over the adapter the
    lifespan installed. ``test_workspace_focus.py`` orders its equivalent
    fixture the same way, for the same reason.
    """
    installed = _context.get_optional_context()
    _service.reset_fallback_services()
    try:
        yield
    finally:
        _context.set_context(installed)
        _service.reset_fallback_services()
        explore.shutdown_session_services()


def _runtime_of(test_client: TestClient) -> ApiRuntime:
    """The ``ApiRuntime`` behind a client (``TestClient.app`` is typed as ASGI)."""
    return test_client.app.state.runtime  # type: ignore[attr-defined,no-any-return]


@pytest.fixture()
def project(client: TestClient, tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    """A fresh project, opened through the API, holding one real notebook.

    Named after the test so a failure in the module-scoped app names the test
    that left the state behind.
    """
    parent = tmp_path / "projects"
    parent.mkdir(parents=True, exist_ok=True)
    response = client.post(
        "/api/projects/",
        json={"name": f"Sessvc {request.node.name}", "description": "spec 5 FR-024", "path": str(parent)},
    )
    assert response.status_code == 200, response.text
    root = Path(response.json()["path"])
    notebook = root / NOTEBOOK
    notebook.parent.mkdir(parents=True, exist_ok=True)
    write_notebook(notebook, new_notebook([new_code_cell("x = 1")]))
    return root


def _open_through_the_routes(client: TestClient, path: str = NOTEBOOK) -> str:
    """Open a session the way the person's window does. Returns its id."""
    response = client.post("/api/explore/sessions", json={"source": "notebook", "path": path})
    assert response.status_code == 200, response.text
    return str(response.json()["session_id"])


def test_the_tools_resolve_the_service_the_routes_serve(client: TestClient, project: Path) -> None:
    """F-B3-1: the same object, not an equal one — that is the whole bug.

    Both orders are asserted. Whichever of the two callers arrives at the
    registry first, the second must find what the first built rather than
    standing up its own beside it.
    """
    runtime = _runtime_of(client)

    tool_service, origin = _service.resolve_session_service()
    route_service = explore.live_session_service(runtime)

    assert tool_service is route_service
    assert origin.origin == _service.ORIGIN_RUNTIME
    assert not origin.is_detached
    assert "get_session_service" in origin.detail
    assert _service._fallback_services == {}, "a detached service was built while a backend was attached"

    # And the other way round: the routes first, the tools second.
    _service.reset_fallback_services()
    _open_through_the_routes(client)
    assert _service.session_service() is route_service
    assert _service._fallback_services == {}


def test_the_tools_and_the_routes_hold_the_same_session_object(client: TestClient, project: Path) -> None:
    """One notebook, one ``ExploreSession`` — including across the two callers.

    ``SessionService.open_notebook`` guarantees at most one session per notebook
    *per service*, so this assertion is only meaningful once both callers share
    a service. Before the fix it held two sessions over one file, each with its
    own ``NotebookStore`` document.
    """
    runtime = _runtime_of(client)
    session_id = _open_through_the_routes(client)

    route_service = explore.live_session_service(runtime)
    assert route_service is not None
    route_session = route_service.session_for(session_id)
    tool_session = _service.session_for(NOTEBOOK)

    assert tool_session is route_session
    assert tool_session.session_id == session_id


def test_a_cell_the_tool_appends_reaches_the_person_s_event_stream(client: TestClient, project: Path) -> None:
    """FR-024's promise, asserted on the socket rather than on the file.

    "It appears in the person's notebook through the same events their own edits
    produce" is a claim about ``broadcast_session_event``, which
    ``api.routes.explore`` subscribes to every service **it** builds. A detached
    service has no such subscriber, so the cell lands on disk and the person's
    open window learns nothing until it reloads — which is why this asserts the
    frame and not the notebook's contents.
    """
    session_id = _open_through_the_routes(client)
    frames: list[dict[str, Any]] = []
    explore.register_explore_subscriber(frames.append)
    try:
        result = _run(append_cell(source="y = x + 1", session_path=NOTEBOOK))
    finally:
        explore.unregister_explore_subscriber(frames.append)

    inserted = [
        frame
        for frame in frames
        if frame["type"] == "explore.analysis_updated" and frame["data"].get("reason") == "cell_inserted"
    ]
    assert inserted, f"the agent's cell produced no analysis_updated frame; saw {[f['type'] for f in frames]}"
    assert inserted[-1]["session_id"] == session_id
    assert inserted[-1]["data"]["cell_id"] == result.cell_id


def test_the_adapter_forwards_no_service_when_no_project_is_open(client: TestClient) -> None:
    """The one condition the accessor answers with ``None`` rather than raising.

    ``get_session_service`` answers a route with a 409 when no project is open;
    a 409 is a route's answer, so ``live_session_service`` turns it into ``None``
    and the tool side raises its own refusal instead.
    """
    runtime = _runtime_of(client)
    open_project = runtime.active_project
    runtime.active_project = None
    try:
        assert explore.live_session_service(runtime) is None
        context = _context.get_context()
        assert context.get_session_service() is None
        with pytest.raises(_service.SessionToolError, match="No project is open"):
            _service.session_service()
    finally:
        runtime.active_project = open_project


# ---------------------------------------------------------------------------
# The detached topology: a standalone bridge, with no backend to ask
# ---------------------------------------------------------------------------


@dataclass
class _StubContext:
    """A context with no session service — a standalone ``scistudio mcp-bridge``."""

    project_dir: Path | None
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    active_workflow_id: str | None = None
    workspace_focus: dict[str, Any] | None = None


@dataclass
class _NoServiceContext(_StubContext):
    """A context that has the accessor and reports no live service through it."""

    def get_session_service(self) -> Any | None:
        return None


@dataclass
class _RaisingContext(_StubContext):
    """A context whose accessor is there and cannot answer."""

    def get_session_service(self) -> Any | None:
        raise RuntimeError("the registry is gone")


@pytest.fixture()
def detached_project(tmp_path: Path) -> Path:
    root = tmp_path / "detached"
    (root / "explore").mkdir(parents=True)
    return root


@pytest.fixture()
def built(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every detached build, and hand back a sentinel instead of a service.

    A real :class:`~scistudio.explore.session.SessionService` here would be a
    test of a project directory rather than of the resolution rule, and would
    leave a commit thread running.
    """
    seen: list[Path] = []

    def build(project_dir: Path) -> Any:
        seen.append(project_dir)
        return object()

    monkeypatch.setattr(_service, "_build_service", build)
    return seen


def test_a_context_with_no_accessor_gets_a_detached_service_that_says_so(
    detached_project: Path, built: list[Path], caplog: pytest.LogCaptureFixture
) -> None:
    """The standalone bridge case: build one, and never quietly."""
    _context.set_context(_StubContext(project_dir=detached_project))  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="scistudio.ai.agent.mcp.tools_explore._service"):
        service, origin = _service.resolve_session_service()

    assert built == [detached_project.resolve()]
    assert origin.is_detached
    assert origin.origin == _service.ORIGIN_DETACHED
    assert origin.project_dir == str(detached_project.resolve())
    assert "carries no session service accessor" in origin.detail
    assert "only when that window reloads the file" in origin.detail
    assert any(origin.detail in record.getMessage() for record in caplog.records), (
        "a detached service was built without announcing it"
    )
    # Cached, so a process never holds more than one per project.
    assert _service.session_service() is service
    assert built == [detached_project.resolve()]


def test_the_detached_warning_names_the_condition_it_found(detached_project: Path, built: list[Path]) -> None:
    """A runtime that *has* the accessor and reports nothing reads differently.

    A standalone bridge and an attached backend with a closed project are both
    detached and are not the same problem, so the origin distinguishes them.
    """
    _context.set_context(_NoServiceContext(project_dir=detached_project))  # type: ignore[arg-type]
    _, reported = _service.resolve_session_service()
    assert "get_session_service reports no live service" in reported.detail

    _service.reset_fallback_services()
    _context.set_context(_RaisingContext(project_dir=detached_project))  # type: ignore[arg-type]
    _, raised = _service.resolve_session_service()
    assert "get_session_service raised" in raised.detail
    assert built == [detached_project.resolve(), detached_project.resolve()]


def test_the_detached_warning_is_announced_once_per_project(
    detached_project: Path, built: list[Path], caplog: pytest.LogCaptureFixture
) -> None:
    """Observable, not deafening: once per project, and again after a reset."""
    _context.set_context(_StubContext(project_dir=detached_project))  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="scistudio.ai.agent.mcp.tools_explore._service"):
        for _ in range(3):
            _service.session_service()
        assert len(caplog.records) == 1

        _service.reset_fallback_services()
        _service.session_service()
        assert len(caplog.records) == 2


def test_a_context_with_no_project_refuses_rather_than_building(built: list[Path]) -> None:
    """No project, no notebook tree, no service — and a refusal that says so."""
    _context.set_context(_StubContext(project_dir=None))  # type: ignore[arg-type]
    with pytest.raises(_service.SessionToolError, match="No project is open"):
        _service.resolve_session_service()
    assert built == []


def test_the_protocol_declares_the_name_the_tools_ask_for() -> None:
    """The two ends of the crossing, pinned to each other.

    ``MCPContext`` declares the member and ``tools_explore._service`` reads it by
    name through ``getattr``, so nothing but this assertion connects them: a
    rename on either side would leave the tools silently detached in production
    while every scripted-context unit test went on passing.
    """
    assert _service.SESSION_SERVICE_ACCESSORS[0] == "get_session_service"
    assert hasattr(MCPContext, "get_session_service")
    assert callable(MCPContext.get_session_service)
