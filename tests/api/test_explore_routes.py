"""The Explore Session API: every operation, every event, every refusal shape.

ADR-054 spec 3 (``docs/specs/adr-054-explore-session.md``) task T-017 — FR-056,
FR-057, and FR-058. Three things about how these are written are deliberate.

**Every FR-056 operation is exercised through its route, not through the service
behind it.** A test that calls ``SessionService.run_stale`` proves the session
works and proves nothing about whether a route reaches it, decodes its body, or
renders its answer. ``test_every_operation_of_fr_056_has_a_route`` pins the
table both ways: an operation with no route fails it, and a route nobody named
fails it too, so the surface cannot drift in either direction unnoticed.

**The event tests compare a sequence, not a set.** Every event type appearing
somewhere is a much weaker claim than the events arriving in the order a client
has to render: ``cell_output`` before ``changed_names`` before the idle
``cell_state`` is what lets a frontend show output while the marks are still
settling. A set-equality assertion passes on a runtime that emits them backwards.

**The refusal tests assert what is left behind, not only the status code.** A
bare ``500`` with an orphaned side effect is a shape this repository has shipped
before, and the emission path is where it would happen again: a snippet that is
refused after its cell was inserted leaves a cell nobody asked for. Those tests
compare the cell list either side of the refusal.

Most tests drive a **fake kernel** — a namespace, a real
:func:`~scistudio.explore.fingerprint.fingerprint` over it, and a bridge that
answers from it — because the routes are the subject and an ipykernel process is
not. The marks, the observations, and the staleness those tests assert are real:
the fake executes the cell's source and the fingerprints are computed by the
same function the real bridge uses. The tests that need a real kernel say so and
skip without one.

Routes are found on ``create_app()``'s application rather than mounted onto it
here. They were mounted here while ``create_app`` did not include the router; it
does now (#2240), and ``_require_explore_routes`` asserts that instead, so a lost
``include_router`` fails this module rather than being papered over by it. The
ordering constraint mounting has to respect is pinned in
``tests/api/test_explore_mount.py``, which these tests found by violating it.
"""

from __future__ import annotations

import ast
import importlib.util
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import explore
from scistudio.explore.fingerprint import Fingerprint, fingerprint
from scistudio.explore.kernel_bridge import Binding, BridgeError
from scistudio.explore.notebook_api import MODE_ENV_VAR, SESSION_MODE
from scistudio.explore.session import (
    BoundRun,
    PortArtefact,
    SessionEventType,
    SessionService,
)
from tests.api.helpers import served_paths

needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

_IDLE_TIMEOUT = 40.0


# ---------------------------------------------------------------------------
# The fake kernel: a namespace, and a bridge that answers from it
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeStatus:
    """What ``KernelHandle.status()`` returns, with the fields the routes read."""

    state: str
    pid: int | None
    memory_bytes: int | None
    python_executable: str = "python-under-test"
    started_at: float | None = None
    interrupt_mode: str = "signal"


@dataclass(frozen=True)
class _FakeError:
    ename: str
    evalue: str
    traceback: tuple[str, ...] = ()


@dataclass(frozen=True)
class _FakeOutput:
    output_type: str
    name: str | None = None
    text: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: _FakeError | None = None


@dataclass(frozen=True)
class _FakeResult:
    status: str
    outputs: tuple[_FakeOutput, ...] = ()
    execution_count: int | None = None
    error: _FakeError | None = None


class _FakeKernel:
    """One "kernel": a namespace and an ``exec`` over it.

    It answers every method ``ExploreSession`` calls on a
    :class:`~scistudio.explore.kernel.KernelHandle`. ``block_on`` lets a test
    hold a cell mid-run, which is the only way to reach the freeze rule of
    FR-025 through a route.
    """

    def __init__(self, kernel_id: str) -> None:
        self.kernel_id = kernel_id
        self.namespace: dict[str, Any] = {}
        self.executed: list[str] = []
        self.interrupts = 0
        self.restarts = 0
        self.stopped = 0
        self.starts = 0
        self.block_on: str | None = None
        self.released = threading.Event()
        self.entered = threading.Event()
        self.raise_on_interrupt: BaseException | None = None
        self._alive = False
        self._state = "not-started"
        self._counter = 0

    # -- lifecycle ------------------------------------------------------

    def start(self) -> None:
        self.starts += 1
        self._alive = True
        self._state = "idle"

    def is_alive(self) -> bool:
        return self._alive

    def status(self) -> _FakeStatus:
        return _FakeStatus(
            state=self._state,
            pid=4242 if self._alive else None,
            memory_bytes=1024 if self._alive else None,
            started_at=1.0 if self._alive else None,
        )

    def interrupt(self) -> None:
        if self.raise_on_interrupt is not None:
            raise self.raise_on_interrupt
        self.interrupts += 1
        self.released.set()

    def restart(self) -> None:
        self.restarts += 1
        self.namespace.clear()
        self._alive = True
        self._state = "idle"

    def stop(self) -> None:
        self.stopped += 1
        self._alive = False
        self._state = "not-started"

    def die(self) -> None:
        """The process went away without being stopped by us (FR-015)."""
        self._alive = False
        self._state = "dead"

    # -- execution ------------------------------------------------------

    def execute(self, source: str) -> _FakeResult:
        self.executed.append(source)
        self._state = "busy"
        if self.block_on is not None and self.block_on in source:
            self.entered.set()
            self.released.wait(timeout=_IDLE_TIMEOUT)
        self._counter += 1
        try:
            exec(source, self.namespace)  # running the cell's source is the point of a kernel
        except BaseException as exc:  # a cell that raises is an ordinary result
            self._state = "idle"
            return _FakeResult(
                status="error",
                outputs=(
                    _FakeOutput(
                        output_type="error",
                        error=_FakeError(ename=type(exc).__name__, evalue=str(exc)),
                    ),
                ),
                execution_count=self._counter,
                error=_FakeError(ename=type(exc).__name__, evalue=str(exc)),
            )
        self._state = "idle"
        return _FakeResult(
            status="ok",
            outputs=(_FakeOutput(output_type="stream", name="stdout", text=""),),
            execution_count=self._counter,
        )


#: Native type name -> SciStudio type name. The real bridge does this
#: translation because it is the only side holding the object; the fake does the
#: same for the one type the packaging tests use, so a packaged port is typed the
#: way FR-038 types it rather than by a name packaging cannot resolve.
_SCISTUDIO_TYPE_NAMES = {"str": "Text"}


class _FakeBridge:
    """Answers fingerprints, bindings, and windows from the fake kernel's namespace."""

    def __init__(self, kernel: _FakeKernel) -> None:
        self.kernel = kernel
        self.installed: dict[str, Any] | None = None
        self.window_error: BaseException | None = None
        self.windows: list[tuple[str, Mapping[str, Any] | None]] = []

    def install(self, **kwargs: Any) -> dict[str, Any]:
        """Record what the session installed. Nothing is injected.

        The real bridge binds the helpers inside the kernel; here the cell's own
        ``import scistudio`` reaches the real module, because the harness sets
        the notebook mode this process runs in (FR-010).
        """
        self.installed = kwargs
        return {"ok": True}

    def _visible(self) -> dict[str, Any]:
        """Every top-level name the cell bound, modules its own ``import`` bound included.

        A module is a real binding: the analysis counts ``import scistudio`` as
        changing ``scistudio``, and an observation that omitted it would take
        that definer away and leave the next cell's ``scistudio.output(...)``
        reading a name nothing above it changes.
        """
        return {name: value for name, value in self.kernel.namespace.items() if not name.startswith("_")}

    def fingerprints(self) -> dict[str, Fingerprint]:
        return {name: fingerprint(value) for name, value in self._visible().items()}

    def bindings(self) -> tuple[Binding, ...]:
        return tuple(
            Binding(
                name=name,
                type_name=_SCISTUDIO_TYPE_NAMES.get(type(value).__name__, type(value).__name__),
                type_module=type(value).__module__,
                summary=repr(value)[:60],
            )
            for name, value in sorted(self._visible().items())
        )

    def window(self, name: str, *, query: Mapping[str, Any] | None = None, project_dir: str | None = None) -> Any:
        if self.window_error is not None:
            raise self.window_error
        self.windows.append((name, query))
        if name not in self.kernel.namespace:
            raise BridgeError(f"{name!r} is not bound in this kernel.")
        return {"kind": "window", "name": name, "value": repr(self.kernel.namespace[name]), "query": dict(query or {})}


class _FakeGitEngine:
    """The two commit calls the session service makes, and nothing else."""

    def __init__(self) -> None:
        self.branch_commits: list[tuple[dict[str, bytes], str]] = []
        self.ref_commits: list[tuple[str, dict[str, bytes], str]] = []

    def explore_session_ref(self, session_id: str) -> str:
        return f"refs/scistudio/explore/{session_id}"

    def commit_entries_to_branch(self, entries: Mapping[str, bytes], message: str) -> str:
        self.branch_commits.append((dict(entries), message))
        return f"branch{len(self.branch_commits):040d}"[:40]

    def commit_entries_to_ref(self, ref: str, entries: Mapping[str, bytes], message: str) -> str:
        self.ref_commits.append((ref, dict(entries), message))
        return f"ref{len(self.ref_commits):040d}"[:40]


class _StubResolver:
    """A :class:`~scistudio.explore.session.BlockOutputResolver` a test controls."""

    def __init__(self) -> None:
        self.latest: BoundRun | None = None
        self.by_run: BoundRun | None = None
        self.paused: BoundRun | None = None

    def latest_block_outputs(self, block_id: str) -> BoundRun | None:
        return self.latest

    def run_block_outputs(self, run_id: str, block_id: str) -> BoundRun | None:
        return self.by_run

    def paused_run_inputs(self, run_id: str, block_id: str) -> BoundRun | None:
        return self.paused


def _bound_run(*, opened_over: str = "block_outputs") -> BoundRun:
    return BoundRun(
        run_id="run-1",
        block_id="loader",
        opened_over=opened_over,
        ports=(PortArtefact(name="table", type_name="DataFrame", backend="local", path="a/b.csv", format="csv"),),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _require_explore_routes(app: Any) -> None:
    """Fail loudly if ``create_app`` stopped mounting the explore router.

    These tests used to include the router themselves, because ``create_app``
    did not (#2240). It does now, and including it here again would hide the
    regression this assertion exists to catch: with a private ``include_router``
    in the fixture, every test below would keep passing on an application that
    serves none of these routes.

    The mounting *position* is the other half, and it is not asserted here.
    ``tests/api/test_explore_mount.py`` owns it, because proving it needs a built
    SPA on disk. The short version: the ``SPAStaticFiles`` mount at ``/`` matches
    every path, ``/api/explore/...`` included, and answers it with its own 404,
    so the router has to be included above it.
    """
    mounted = set(served_paths(app))
    missing = {getattr(route, "path", "") for route in explore.router.routes} - mounted
    assert not missing, f"create_app no longer mounts the explore router: {sorted(missing)}"


@dataclass
class _Harness:
    """Everything a test needs to drive the routes and inspect what happened."""

    client: TestClient
    project_dir: Path
    kernels: list[_FakeKernel]
    bridges: list[_FakeBridge]
    resolver: _StubResolver
    git: _FakeGitEngine | None
    events: list[dict[str, Any]]

    def service(self) -> SessionService:
        """The live service, for the two things no route offers.

        The queue runs on a worker thread, so a test that asserts on a run's
        effects has to wait for it, and waiting is not an operation of FR-056.
        Reporting that a kernel process died is the handle's own ``on_death``
        callback, and has no route either — it is something that happens *to*
        the session. Nothing else in this module reaches past the routes: the
        project directory comes from the fixture, and every assertion about
        behaviour is made against an HTTP response or against the filesystem.
        """
        services = list(explore._services.values())
        assert len(services) == 1, f"expected exactly one session service, found {len(services)}"
        return services[0]

    def wait_idle(self, timeout: float = _IDLE_TIMEOUT) -> None:
        for session in self.service().sessions():
            assert session.wait_until_idle(timeout), "the execution queue did not drain"

    def open_file_session(self, path: str = "data/raw/signal.csv") -> dict[str, Any]:
        response = self.client.post("/api/explore/sessions", json={"source": "file", "path": path})
        assert response.status_code == 200, response.text
        return response.json()

    def types(self) -> list[str]:
        return [frame["type"] for frame in self.events]


@pytest.fixture
def harness(
    client: TestClient,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Harness]:
    """A client whose explore routes are mounted and whose kernels are fakes."""
    kernels: list[_FakeKernel] = []
    bridges: list[_FakeBridge] = []
    resolver = _StubResolver()
    config: dict[str, Any] = {"git": None}
    events: list[dict[str, Any]] = []

    def make_kernel(session: Any) -> _FakeKernel:
        kernel = _FakeKernel(session.session_id)
        kernels.append(kernel)
        return kernel

    def make_bridge(handle: _FakeKernel) -> _FakeBridge:
        bridge = _FakeBridge(handle)
        bridges.append(bridge)
        return bridge

    def build(project_dir: Path, runtime: Any) -> SessionService:
        return SessionService(
            project_dir,
            git_engine=config["git"],
            block_outputs=resolver,
            kernel_factory=make_kernel,
            bridge_factory=make_bridge,
        )

    monkeypatch.setattr(explore, "_build_service", build)
    # The real bridge launches the kernel with this set (``session_kernel_env``);
    # the fake kernel is this process, so the helpers a cell imports need it here.
    monkeypatch.setenv(MODE_ENV_VAR, SESSION_MODE)
    _require_explore_routes(client.app)

    explore.register_explore_subscriber(events.append)
    harness = _Harness(
        client=client,
        project_dir=opened_project,
        kernels=kernels,
        bridges=bridges,
        resolver=resolver,
        git=None,
        events=events,
    )
    harness_config = config
    try:
        yield harness
    finally:
        explore.unregister_explore_subscriber(events.append)
        explore.shutdown_session_services()
        harness_config.clear()


@pytest.fixture
def git_harness(harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    """The same harness, with a fake git engine so commits have a sha.

    Rebuilt rather than mutated, because the service is created on the first
    explore request and takes its git engine then.
    """
    git = _FakeGitEngine()
    kernels, bridges, resolver = harness.kernels, harness.bridges, harness.resolver

    def make_kernel(session: Any) -> _FakeKernel:
        kernel = _FakeKernel(session.session_id)
        kernels.append(kernel)
        return kernel

    def make_bridge(handle: _FakeKernel) -> _FakeBridge:
        bridge = _FakeBridge(handle)
        bridges.append(bridge)
        return bridge

    def build(project_dir: Path, runtime: Any) -> SessionService:
        return SessionService(
            project_dir,
            git_engine=git,
            block_outputs=resolver,
            kernel_factory=make_kernel,
            bridge_factory=make_bridge,
        )

    monkeypatch.setattr(explore, "_build_service", build)
    harness.git = git
    return harness


def _set_source(harness: _Harness, session_id: str, cell_id: str, source: str) -> dict[str, Any]:
    response = harness.client.put(
        f"/api/explore/sessions/{session_id}/cells/{cell_id}",
        json={"source": source},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _insert(harness: _Harness, session_id: str, source: str, after: str | None = None) -> str:
    before = {
        cell["cell_id"] for cell in harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]
    }
    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/cells",
        json={"source": source, "after": after},
    )
    assert response.status_code == 200, response.text
    after_ids = [cell["cell_id"] for cell in response.json()["cells"]]
    new = [cell_id for cell_id in after_ids if cell_id not in before]
    assert len(new) == 1, f"insert produced {len(new)} new cells"
    return str(new[0])


def _run(harness: _Harness, session_id: str, cell_id: str) -> dict[str, Any]:
    response = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{cell_id}/run")
    assert response.status_code == 200, response.text
    harness.wait_idle()
    return response.json()


@pytest.fixture
def abc_session(harness: _Harness) -> tuple[str, tuple[str, str, str]]:
    """User Story 2's A, B, C fixture, run in order through the routes.

    Three cells that each bind ``df``, the second and third reading the one
    above. At the end nothing carries a mark, which is the state Story 2 opens
    with.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "df = [1, 2, 3, 4]")
    cell_b = _insert(harness, session_id, "df = df[:3]", after=first)
    cell_c = _insert(harness, session_id, "df = df[:2]", after=cell_b)
    for cell_id in (first, cell_b, cell_c):
        _run(harness, session_id, cell_id)
    return session_id, (first, cell_b, cell_c)


# ---------------------------------------------------------------------------
# FR-056: the surface itself
# ---------------------------------------------------------------------------

#: Every operation FR-056 names, and the route that offers it. This is the
#: checklist the spec sentence becomes, kept as data so the test below can fail
#: in both directions: an operation with no route, and a route no operation asks
#: for. Opening's three sources share one route because FR-056 names "open" once
#: and FR-002 names the sources.
FR_056_OPERATIONS: tuple[tuple[str, str, str], ...] = (
    ("open", "POST", "/api/explore/sessions"),
    ("list", "GET", "/api/explore/sessions"),
    ("close", "DELETE", "/api/explore/sessions/{session_id}"),
    ("commit-to-branch", "POST", "/api/explore/sessions/{session_id}/commit"),
    ("read cells", "GET", "/api/explore/sessions/{session_id}/cells"),
    ("write cells", "PUT", "/api/explore/sessions/{session_id}/cells/{cell_id}"),
    ("write cells (insert)", "POST", "/api/explore/sessions/{session_id}/cells"),
    ("run one cell", "POST", "/api/explore/sessions/{session_id}/cells/{cell_id}/run"),
    ("run the stale set", "POST", "/api/explore/sessions/{session_id}/run-stale"),
    (
        "run with upstream",
        "POST",
        "/api/explore/sessions/{session_id}/cells/{cell_id}/run-with-upstream",
    ),
    ("toggle enabled", "PUT", "/api/explore/sessions/{session_id}/cells/{cell_id}/enabled"),
    ("interrupt", "POST", "/api/explore/sessions/{session_id}/interrupt"),
    ("restart", "POST", "/api/explore/sessions/{session_id}/restart"),
    ("the graph", "GET", "/api/explore/sessions/{session_id}/graph"),
    ("the marks", "GET", "/api/explore/sessions/{session_id}/marks"),
    ("the bindings", "GET", "/api/explore/sessions/{session_id}/bindings"),
    ("a windowed read of a variable", "POST", "/api/explore/sessions/{session_id}/window"),
    ("the emission of a snippet from a panel", "POST", "/api/explore/sessions/{session_id}/snippets"),
    ("the kernel list", "GET", "/api/explore/kernels"),
    ("ending a kernel", "DELETE", "/api/explore/kernels/{session_id}"),
    ("a packaging check", "POST", "/api/explore/sessions/{session_id}/packaging/check"),
    ("packaging", "POST", "/api/explore/sessions/{session_id}/package"),
)

#: The one route that is not an FR-056 operation: reading a session back is what
#: every other route's answer is a slice of, and the frontend needs it after a
#: reconnect. Named here so the surface test still fails on an unlisted route.
NON_FR_056_ROUTES: frozenset[tuple[str, str]] = frozenset({("GET", "/api/explore/sessions/{session_id}")})


def _router_surface() -> set[tuple[str, str]]:
    surface: set[tuple[str, str]] = set()
    for route in explore.router.routes:
        for method in sorted(getattr(route, "methods", ())):
            if method in {"HEAD", "OPTIONS"}:
                continue
            surface.add((method, route.path))
    return surface


def test_every_operation_of_fr_056_has_a_route() -> None:
    """FR-056's sentence, item by item, against the router (SC-013).

    Both directions matter. A missing route means an operation the frontend
    cannot reach; an unlisted route means a surface nobody wrote down, which is
    how an API grows a door the spec does not describe.
    """
    named = {(method, path) for _, method, path in FR_056_OPERATIONS}
    surface = _router_surface()

    missing = sorted(named - surface)
    assert not missing, f"FR-056 operations with no route: {missing}"

    unlisted = sorted(surface - named - NON_FR_056_ROUTES)
    assert not unlisted, f"routes no FR-056 operation asks for: {unlisted}"


def test_the_route_module_never_imports_the_kernel_or_the_bridge() -> None:
    """FR-058: the API reaches the kernel only through the service's queue and bridge.

    Import is the cheapest way that rule gets broken — one ``from
    scistudio.explore.kernel import KernelHandle`` to "just check the pid", and
    the route module is holding a process handle. The check is over the whole
    file, function bodies included, because a deferred import runs too.
    """
    path = Path(explore.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    forbidden = [
        name for name in imported if name.startswith(("scistudio.explore.kernel", "jupyter_client", "ipykernel"))
    ]
    assert not forbidden, f"the route module must not import the kernel or its client: {forbidden}"


# ---------------------------------------------------------------------------
# FR-056: open, list, close, commit
# ---------------------------------------------------------------------------


def test_open_over_a_file_returns_a_session_with_a_generated_first_cell(harness: _Harness) -> None:
    """Opening over a file gives a notebook whose first cell loads it (FR-002, FR-004)."""
    body = harness.open_file_session("data/raw/signal.csv")

    assert body["session_id"]
    assert body["notebook_path"].startswith("explore/")
    assert body["has_kernel"] is False, "a session opens with no kernel (US1 scenario 1)"
    assert body["bound_run"] is None
    assert len(body["cells"]) == 1
    assert "signal.csv" in body["cells"][0]["source"]
    assert body["cells"][0]["marks"] == ["never_run"]


def test_open_over_block_outputs_binds_the_run_and_names_its_ports(harness: _Harness) -> None:
    """FR-003: the ports of the bound run come back with the session."""
    harness.resolver.latest = _bound_run()

    response = harness.client.post(
        "/api/explore/sessions",
        json={"source": "block_outputs", "block_id": "loader"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["bound_run"]["run_id"] == "run-1"
    assert body["bound_run"]["opened_over"] == "block_outputs"
    assert [port["name"] for port in body["bound_run"]["ports"]] == ["table"]
    assert "table" in body["cells"][0]["source"], "the generated first cell names the port"


def test_open_over_block_outputs_can_name_a_run(harness: _Harness) -> None:
    """``run_id`` binds to that run rather than to the most recent one."""
    harness.resolver.latest = None
    harness.resolver.by_run = _bound_run()

    response = harness.client.post(
        "/api/explore/sessions",
        json={"source": "block_outputs", "block_id": "loader", "run_id": "run-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["bound_run"]["run_id"] == "run-1"


def test_open_over_a_paused_run_binds_its_inputs(harness: _Harness) -> None:
    """FR-002: a run paused at a block is explored over the inputs it received."""
    harness.resolver.paused = _bound_run(opened_over="paused_run")

    response = harness.client.post(
        "/api/explore/sessions",
        json={"source": "paused_run", "block_id": "loader", "run_id": "run-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["bound_run"]["opened_over"] == "paused_run"


def test_open_over_a_notebook_returns_the_session_the_list_reported(harness: _Harness) -> None:
    """A notebook the list reports as closed can be opened again by path."""
    opened = harness.open_file_session()
    session_id = opened["session_id"]
    notebook_path = opened["notebook_path"]
    assert harness.client.delete(f"/api/explore/sessions/{session_id}").status_code == 200

    response = harness.client.post("/api/explore/sessions", json={"source": "notebook", "path": notebook_path})

    assert response.status_code == 200, response.text
    assert response.json()["notebook_path"] == notebook_path
    assert response.json()["session_id"] == session_id, "the id lives in the notebook's metadata"


def test_list_reports_open_and_closed_notebooks(harness: _Harness) -> None:
    """FR-006: every notebook in the explore directory, with whether it has a kernel."""
    first = harness.open_file_session("data/raw/one.csv")
    second = harness.open_file_session("data/raw/two.csv")
    assert harness.client.delete(f"/api/explore/sessions/{second['session_id']}").status_code == 200

    body = harness.client.get("/api/explore/sessions").json()

    by_path = {row["notebook_path"]: row for row in body["sessions"]}
    assert by_path[first["notebook_path"]]["is_open"] is True
    assert by_path[second["notebook_path"]]["is_open"] is False
    assert all(row["readable"] for row in body["sessions"])


def test_close_writes_the_notebook_and_forgets_the_session(harness: _Harness) -> None:
    """Closing ends the session; asking about it afterwards is a 404."""
    session = harness.open_file_session()
    session_id = session["session_id"]

    response = harness.client.delete(f"/api/explore/sessions/{session_id}")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "session_id": session_id,
        "notebook_path": session["notebook_path"],
        "branch_commit": None,
    }
    assert harness.client.get(f"/api/explore/sessions/{session_id}").status_code == 404


def test_close_without_a_git_engine_reports_no_branch_commit(harness: _Harness) -> None:
    """A project with no repository closes cleanly and writes no history."""
    session = harness.open_file_session()
    response = harness.client.delete(f"/api/explore/sessions/{session['session_id']}")
    assert response.json()["branch_commit"] is None


def test_commit_to_branch_returns_the_sha_and_strips_outputs(git_harness: _Harness) -> None:
    """FR-036: one commit of the notebook, outputs stripped, on the branch."""
    session = git_harness.open_file_session()
    session_id = session["session_id"]

    response = git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})

    assert response.status_code == 200, response.text
    sha = response.json()["sha"]
    assert sha, "a commit with a git engine has a sha"
    entries, message = git_harness.git.branch_commits[-1]
    assert message == "checkpoint"
    payload = next(iter(entries.values()))
    assert b'"outputs"' in payload, "a notebook always has an outputs key"
    assert b'"output_type"' not in payload, "the committed notebook carries no output values"


def test_commit_without_a_git_engine_is_not_an_error(harness: _Harness) -> None:
    """``sha`` is null rather than a 500 when the project has no repository."""
    session = harness.open_file_session()
    response = harness.client.post(f"/api/explore/sessions/{session['session_id']}/commit", json={"message": None})
    assert response.status_code == 200, response.text
    assert response.json()["sha"] is None


# ---------------------------------------------------------------------------
# FR-056: read and write cells, toggle enabled
# ---------------------------------------------------------------------------


def test_read_cells_reports_source_enabled_and_marks(harness: _Harness) -> None:
    session = harness.open_file_session()
    body = harness.client.get(f"/api/explore/sessions/{session['session_id']}/cells").json()

    assert body["session_id"] == session["session_id"]
    assert body["cells"][0]["cell_type"] == "code"
    assert body["cells"][0]["enabled"] is True
    assert body["cells"][0]["marks"] == ["never_run"]


def test_write_cell_replaces_the_source(harness: _Harness) -> None:
    session = harness.open_file_session()
    first = session["cells"][0]["cell_id"]

    body = _set_source(harness, session["session_id"], first, "answer = 42")

    assert body["cells"][0]["source"] == "answer = 42"


def test_insert_cell_lands_after_the_named_cell(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]

    inserted = _insert(harness, session_id, "b = 1", after=first)
    last = _insert(harness, session_id, "c = 2", after=inserted)

    ids = [cell["cell_id"] for cell in harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]]
    assert ids == [first, inserted, last]


def test_toggle_enabled_takes_a_cell_out_of_the_graph(harness: _Harness) -> None:
    """A disabled cell is not in the graph, which is what stops it running (FR-056)."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    second = _insert(harness, session_id, "b = 1", after=first)

    body = harness.client.put(
        f"/api/explore/sessions/{session_id}/cells/{second}/enabled",
        json={"enabled": False},
    ).json()

    assert [cell["enabled"] for cell in body["cells"]] == [True, False]
    graph = harness.client.get(f"/api/explore/sessions/{session_id}/graph").json()
    assert second not in graph["cells"]

    harness.client.put(
        f"/api/explore/sessions/{session_id}/cells/{second}/enabled",
        json={"enabled": True},
    )
    graph = harness.client.get(f"/api/explore/sessions/{session_id}/graph").json()
    assert second in graph["cells"]


# ---------------------------------------------------------------------------
# FR-056: the three run controls
# ---------------------------------------------------------------------------


def test_run_one_cell_enqueues_only_that_cell(harness: _Harness, abc_session: tuple[str, tuple[str, str, str]]) -> None:
    """FR-017: the cell the person named, and nothing else."""
    session_id, (first, _b, _c) = abc_session

    body = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run").json()
    harness.wait_idle()

    assert [request["cell_id"] for request in body["requests"]] == [first]


def test_run_stale_enqueues_the_stale_set_and_nothing_else(
    harness: _Harness,
    abc_session: tuple[str, tuple[str, str, str]],
) -> None:
    """FR-024: the stale set, not the out-of-order cells and not the never-run ones."""
    session_id, (first, cell_b, cell_c) = abc_session
    _run(harness, session_id, first)  # re-running A makes B and C stale

    marks = harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()
    assert marks["stale"] == [cell_b, cell_c]

    body = harness.client.post(f"/api/explore/sessions/{session_id}/run-stale").json()
    harness.wait_idle()

    assert [request["cell_id"] for request in body["requests"]] == [cell_b, cell_c]


def test_run_with_upstream_skips_an_undisturbed_upstream(harness: _Harness) -> None:
    """FR-024's skip rule, on a chain where each cell binds its own name.

    The named cell always runs. An upstream cell is skipped only when it carries
    no mark **and** every name it changes is still last bound by it, which on
    this chain is true of both cells above.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    cell_a = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, cell_a, "a = 1")
    cell_b = _insert(harness, session_id, "b = a + 1", after=cell_a)
    cell_c = _insert(harness, session_id, "c = b + 1", after=cell_b)
    for cell_id in (cell_a, cell_b, cell_c):
        _run(harness, session_id, cell_id)

    body = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{cell_c}/run-with-upstream").json()
    harness.wait_idle()
    assert [request["cell_id"] for request in body["requests"]] == [cell_c]

    _run(harness, session_id, cell_a)  # A re-runs, so B is stale and must be re-run with C
    body = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{cell_c}/run-with-upstream").json()
    harness.wait_idle()
    assert [request["cell_id"] for request in body["requests"]] == [cell_b, cell_c], (
        "A still last-binds 'a' and carries no mark, so it is skipped; B is stale, so it runs"
    )


def test_run_with_upstream_re_runs_a_chain_that_rebinds_one_name(
    harness: _Harness,
    abc_session: tuple[str, tuple[str, str, str]],
) -> None:
    """The other half of the skip rule, on Story 2's fixture.

    Every cell of A, B, C binds ``df``, so after all three have run only C is
    still the last binder. A and B therefore fail the second clause of FR-024's
    skip test even though neither carries a mark, and running C with its
    upstream re-runs the whole chain. This is the case that would be wrong if
    the rule were read as "skip anything unmarked".
    """
    session_id, (first, cell_b, cell_c) = abc_session

    body = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{cell_c}/run-with-upstream").json()
    harness.wait_idle()

    assert [request["cell_id"] for request in body["requests"]] == [first, cell_b, cell_c]


def test_running_a_cell_actually_reaches_the_kernel(harness: _Harness) -> None:
    """The route is wired to the queue, not merely to a request object."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 7")

    _run(harness, session_id, first)

    assert harness.kernels[0].namespace["value"] == 7
    assert harness.kernels[0].executed == ["value = 7"]


def test_running_a_disabled_cell_is_refused_not_silently_skipped(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    harness.client.put(f"/api/explore/sessions/{session_id}/cells/{first}/enabled", json={"enabled": False})

    response = harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "session_refused"
    assert "disabled" in response.json()["detail"]["message"]


# ---------------------------------------------------------------------------
# FR-056: interrupt and restart
# ---------------------------------------------------------------------------


def test_interrupt_reaches_the_kernel_without_ending_the_session(harness: _Harness) -> None:
    """FR-013: the session survives an interrupt."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    response = harness.client.post(f"/api/explore/sessions/{session_id}/interrupt")

    assert response.status_code == 200, response.text
    assert harness.kernels[0].interrupts == 1
    assert harness.client.get(f"/api/explore/sessions/{session_id}").status_code == 200


def test_interrupt_before_a_kernel_exists_is_a_refusal_not_a_500(harness: _Harness) -> None:
    session = harness.open_file_session()
    response = harness.client.post(f"/api/explore/sessions/{session['session_id']}/interrupt")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "session_refused"
    assert "no kernel" in response.json()["detail"]["message"]


def test_restart_resets_every_mark_to_never_run(harness: _Harness) -> None:
    """FR-013, FR-023: the namespace is gone, so every mark goes with it."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)
    assert harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()["never_run"] == []

    response = harness.client.post(f"/api/explore/sessions/{session_id}/restart")

    assert response.status_code == 200, response.text
    assert response.json()["needs_restart"] is False
    marks = harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()
    assert marks["never_run"] == [first]
    assert marks["last_bound_by"] == {}
    assert harness.kernels[0].restarts == 1


# ---------------------------------------------------------------------------
# FR-056: the graph, the marks, the bindings
# ---------------------------------------------------------------------------


def test_the_graph_reports_cells_edges_and_changed_sets(
    harness: _Harness,
    abc_session: tuple[str, tuple[str, str, str]],
) -> None:
    session_id, (first, cell_b, cell_c) = abc_session

    graph = harness.client.get(f"/api/explore/sessions/{session_id}/graph").json()

    assert graph["cells"] == [first, cell_b, cell_c]
    assert {(edge["reader"], edge["definer"], edge["name"]) for edge in graph["edges"]} == {
        (cell_b, first, "df"),
        (cell_c, cell_b, "df"),
    }
    assert graph["changed_sets"][first] == ["df"]
    assert graph["unresolved_reads"] == []


def test_the_marks_report_the_reason_an_out_of_order_read_was_raised(
    harness: _Harness,
    abc_session: tuple[str, tuple[str, str, str]],
) -> None:
    """FR-019: the mark carries which read was out of order, and against which cell."""
    session_id, (first, cell_b, cell_c) = abc_session
    _run(harness, session_id, cell_c)  # C reads df, which B last bound — but C is written below B

    marks = harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()

    by_cell = {row["cell_id"]: row for row in marks["marks"]}
    assert "out_of_order" in by_cell[cell_c]["marks"]
    reason = by_cell[cell_c]["out_of_order_reads"][0]
    assert reason["name"] == "df"
    assert reason["definer"] == cell_b
    assert reason["last_binder"] == cell_c
    assert marks["last_bound_by"]["df"] == cell_c
    assert first not in by_cell or by_cell[first]["marks"] == []


def test_bindings_report_type_names_and_whether_each_exists_in_the_kernel(harness: _Harness) -> None:
    """FR-056: the type name for what is bound, and the fact for what is not."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "greeting = 'hi'")
    _insert(harness, session_id, "not_yet = greeting + '!'", after=first)
    _run(harness, session_id, first)

    body = harness.client.get(f"/api/explore/sessions/{session_id}/bindings").json()

    by_name = {row["name"]: row for row in body["bindings"]}
    assert body["has_kernel"] is True
    assert by_name["greeting"]["exists_in_kernel"] is True
    assert by_name["greeting"]["type_name"] == "Text"
    assert by_name["greeting"]["last_bound_by"] == first
    assert by_name["not_yet"]["exists_in_kernel"] is False
    assert by_name["not_yet"]["type_name"] is None


def test_bindings_without_a_kernel_report_every_name_as_absent(harness: _Harness) -> None:
    """A session with no kernel binds nothing; that is an answer, not an error."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    _set_source(harness, session_id, session["cells"][0]["cell_id"], "greeting = 'hi'")

    body = harness.client.get(f"/api/explore/sessions/{session_id}/bindings").json()

    assert body["has_kernel"] is False
    assert [row["name"] for row in body["bindings"]] == ["greeting"]
    assert body["bindings"][0]["exists_in_kernel"] is False


# ---------------------------------------------------------------------------
# FR-056: a windowed read, and the emission of a snippet
# ---------------------------------------------------------------------------


def test_a_windowed_read_returns_the_bridge_envelope(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "table = [1, 2, 3]")
    _run(harness, session_id, first)

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/window",
        json={"name": "table", "query": {"page": 2}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["envelope"]["kind"] == "window"
    assert harness.bridges[0].windows == [("table", {"page": 2})]


def test_a_windowed_read_without_a_kernel_is_a_refusal(harness: _Harness) -> None:
    session = harness.open_file_session()
    response = harness.client.post(
        f"/api/explore/sessions/{session['session_id']}/window",
        json={"name": "table"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "session_refused"


def test_emitting_a_snippet_inserts_it_after_the_current_cell_and_runs_it(harness: _Harness) -> None:
    """FR-018: an admitted emission becomes a cell and a queued request."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "table = [1, 2, 3]")
    _run(harness, session_id, first)

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/snippets",
        json={"source": "subset = table[:2]", "panel": "table-panel"},
    )
    harness.wait_idle()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request"]["panel"] == "table-panel"
    cells = harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]
    assert [cell["cell_id"] for cell in cells] == [first, body["cell_id"]]
    assert harness.kernels[0].namespace["subset"] == [1, 2]


# ---------------------------------------------------------------------------
# FR-056: the kernel list and ending a kernel
# ---------------------------------------------------------------------------


def test_the_kernel_list_reports_every_live_kernel_with_its_memory(harness: _Harness) -> None:
    """FR-016: the list answers from outside the process."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    _set_source(harness, session_id, session["cells"][0]["cell_id"], "value = 1")
    _run(harness, session_id, session["cells"][0]["cell_id"])

    body = harness.client.get("/api/explore/kernels").json()

    assert len(body["kernels"]) == 1
    row = body["kernels"][0]
    assert row["session_id"] == session_id
    assert row["state"] == "idle"
    assert row["pid"] == 4242
    assert row["memory_bytes"] == 1024


def test_a_session_with_no_kernel_is_not_in_the_kernel_list(harness: _Harness) -> None:
    harness.open_file_session()
    assert harness.client.get("/api/explore/kernels").json()["kernels"] == []


def test_ending_a_kernel_leaves_the_session_open(harness: _Harness) -> None:
    """FR-016: the process goes; the notebook and the session stay."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    response = harness.client.delete(f"/api/explore/kernels/{session_id}")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "not-started"
    assert harness.kernels[0].stopped == 1
    assert harness.client.get(f"/api/explore/sessions/{session_id}").status_code == 200
    assert harness.client.get("/api/explore/kernels").json()["kernels"] == []


# ---------------------------------------------------------------------------
# FR-056: packaging
# ---------------------------------------------------------------------------


def _packageable_session(harness: _Harness) -> tuple[str, str, str]:
    """A session whose declared-output slice has run cleanly, in two cells.

    The first cell carries ``import scistudio`` because the declaration in the
    second reads that name, and packaging refuses a slice that reads a name no
    enabled cell above it changes — which is why the generated first cell
    carries the same import.

    Two cells rather than one because the interesting refusals are about a
    *slice*: a one-cell notebook cannot have an upstream cell go stale
    underneath its declaration.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "import scistudio\nresult = 'hello'")
    second = _insert(harness, session_id, "scistudio.output(answer=result)", after=first)
    _run(harness, session_id, first)
    _run(harness, session_id, second)
    return session_id, first, second


def test_the_packaging_check_reports_the_slice_and_the_ports(git_harness: _Harness) -> None:
    """FR-039: the check writes nothing and says what packaging would produce."""
    session_id, first, second = _packageable_session(git_harness)
    blocks_before = sorted((git_harness.project_dir / "blocks").glob("*"))

    body = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/packaging/check",
        json={},
    ).json()

    assert body["is_packageable"] is True, body["problems"]
    assert body["cells"] == [first, second]
    assert [port["name"] for port in body["outputs"]] == ["answer"]
    assert body["outputs"][0]["data_type"] == "Text"
    assert sorted((git_harness.project_dir / "blocks").glob("*")) == blocks_before


def test_the_packaging_check_names_every_refusal_rather_than_the_first(harness: _Harness) -> None:
    """A person fixing a notebook wants the whole list (FR-039)."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "import scistudio\nresult = missing_name\nscistudio.output(answer=result)")

    body = harness.client.post(f"/api/explore/sessions/{session_id}/packaging/check", json={}).json()

    kinds = {problem["kind"] for problem in body["problems"]}
    assert body["is_packageable"] is False
    assert "never_run_cell" in kinds, "the cell has not run"
    assert "unresolved_read" in kinds, "and it reads a name nothing above it binds"
    assert all(problem["message"] for problem in body["problems"])


def test_packaging_writes_the_declaration_and_the_notebook_copy(git_harness: _Harness) -> None:
    """FR-037: two files and no others, and the notebook it came from is untouched."""
    session_id, _first, _second = _packageable_session(git_harness)
    git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})
    notebook_before = (
        git_harness.project_dir / git_harness.client.get(f"/api/explore/sessions/{session_id}").json()["notebook_path"]
    ).read_bytes()

    response = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Signal Summary"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["class_name"] == "SignalSummary"
    assert body["on_new_input"] == "replay"
    assert [port["name"] for port in body["outputs"]] == ["answer"]
    assert Path(body["declaration_path"]).is_file()
    assert Path(body["notebook_path"]).is_file()
    assert (
        git_harness.project_dir / git_harness.client.get(f"/api/explore/sessions/{session_id}").json()["notebook_path"]
    ).read_bytes() == notebook_before


def test_packaging_without_a_notebook_commit_is_refused_with_a_reason(harness: _Harness) -> None:
    """FR-041: a packaged block's version is the commit it was packaged from.

    A project with no git engine writes no history, so a session in one has no
    commit to be the block's version. That is a refusal with a reason rather
    than a block declaring an empty version, which would fail much later and
    somewhere else.
    """
    session_id, _first, _second = _packageable_session(harness)

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Too Early"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "no_notebook_commit"


def test_packaging_a_stale_slice_is_refused_with_every_problem_named(git_harness: _Harness) -> None:
    """A refusal from packaging is the documented shape, not a bare 500 (FR-058).

    Re-running the first cell leaves the declaring cell below it stale, which is
    exactly the state FR-039 refuses: the value the declaration would package is
    not the value the cell computed.
    """
    session_id, first, second = _packageable_session(git_harness)
    git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})
    _run(git_harness, session_id, first)
    assert git_harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()["stale"] == [second]

    response = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Refused Block"},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "packaging_refused"
    assert [problem["kind"] for problem in detail["problems"]] == ["stale_cell"]
    assert detail["problems"][0]["cell_ids"] == [second]
    assert all(problem["message"] for problem in detail["problems"])
    blocks = git_harness.project_dir / "blocks"
    assert not list(blocks.glob("refused_block*")), "nothing is written when packaging refuses"


def test_packaging_rejects_an_unknown_interaction_policy(git_harness: _Harness) -> None:
    """FR-044: ``on_new_input`` is ``replay`` or ``ask``, and nothing else."""
    session_id, _first, _second = _packageable_session(git_harness)
    git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})

    response = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Bad Policy", "on_new_input": "sometimes"},
    )

    assert response.status_code == 500, "an unrecognised ValueError is a bug, not a documented refusal"


# ---------------------------------------------------------------------------
# FR-057: the events, in order, on the one connection
# ---------------------------------------------------------------------------


def test_the_event_sequence_of_a_cell_run(harness: _Harness) -> None:
    """FR-057, as a **sequence**: what a client renders depends on the order.

    ``cell_output`` before ``changed_names`` before the idle ``cell_state`` is
    what lets a frontend show output while the marks are still settling. A test
    that asserted the *set* of types would pass on a runtime that emitted them
    backwards, which is the bug that would be hardest to find later.

    This harness has no git engine, so no explore commit is queued and nothing
    arrives from the commit thread: every frame below is published on the
    thread that did the work, in the order it did it.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]

    harness.events.clear()
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    assert harness.types() == [
        "explore.analysis_updated",
        "explore.kernel_state",
        "explore.cell_state",
        "explore.cell_output",
        "explore.changed_names",
        "explore.cell_state",
        "explore.analysis_updated",
    ]

    edited, ran = (frame for frame in harness.events if frame["type"] == "explore.analysis_updated")
    assert edited["data"]["reason"] == "cell_edited"
    assert ran["data"]["reason"] == "cell_ran"
    running, idle = (frame for frame in harness.events if frame["type"] == "explore.cell_state")
    assert running["data"]["state"] == "running"
    assert idle["data"]["state"] == "idle"
    assert idle["data"]["marks"] == {}
    changed = next(frame for frame in harness.events if frame["type"] == "explore.changed_names")
    assert changed["data"]["changed"] == ["value"]
    output = next(frame for frame in harness.events if frame["type"] == "explore.cell_output")
    assert output["data"]["status"] == "ok"


def test_the_event_sequence_of_committing_and_closing(git_harness: _Harness) -> None:
    """The other half of the sequence, where a git engine is present.

    The explore commit one cell run queues is written on the commit thread and
    would interleave with anything published afterwards, so it is drained
    first — draining is not an operation of FR-056 and has no route. What is
    asserted here is the order of what the *routes* then publish: the branch
    commit, the kernel going away, and the session closing, in that order.
    """
    session = git_harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(git_harness, session_id, first, "value = 1")
    _run(git_harness, session_id, first)
    assert git_harness.service().wait_for_commits(timeout=_IDLE_TIMEOUT), "the commit thread did not drain"
    assert [frame for frame in git_harness.events if frame["type"] == "explore.commit_recorded"], (
        "a cell run with a git engine writes one explore commit"
    )

    git_harness.events.clear()
    commit = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"}
    ).json()
    git_harness.client.delete(f"/api/explore/sessions/{session_id}", params={"commit": False})

    assert git_harness.types() == [
        "explore.commit_recorded",
        "explore.kernel_state",
        "explore.session_closed",
    ]
    recorded = git_harness.events[0]
    assert recorded["data"]["sha"] == commit["sha"]
    assert recorded["data"]["ref"] == "branch"
    assert git_harness.events[-1]["data"]["branch_commit"] is None, "closing with commit=false writes nothing"


def test_every_event_type_of_fr_057_reaches_the_hub(git_harness: _Harness) -> None:
    """The whole enumeration, not a convenient subset.

    ``packaged`` is the one no session method publishes — packaging is a
    function of the notebook and the marks rather than a method on the service —
    so it is the one this test would miss if the route stopped publishing it.
    """
    git_harness.events.clear()
    session_id, _first, _second = _packageable_session(git_harness)
    git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})
    response = git_harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Event Coverage"},
    )
    assert response.status_code == 200, response.text
    git_harness.client.delete(f"/api/explore/sessions/{session_id}")

    seen = set(git_harness.types())
    expected = {f"explore.{member.value}" for member in SessionEventType}
    assert expected - seen == set(), f"FR-057 event types that never reached the hub: {sorted(expected - seen)}"


def test_the_packaged_event_carries_what_was_written(git_harness: _Harness) -> None:
    session_id, _first, _second = _packageable_session(git_harness)
    git_harness.client.post(f"/api/explore/sessions/{session_id}/commit", json={"message": "checkpoint"})
    git_harness.events.clear()

    git_harness.client.post(f"/api/explore/sessions/{session_id}/package", json={"block_name": "Payload Check"})

    packaged = next(frame for frame in git_harness.events if frame["type"] == "explore.packaged")
    assert packaged["session_id"] == session_id
    assert packaged["data"]["block_name"] == "Payload Check"
    assert packaged["data"]["class_name"] == "PayloadCheck"
    assert packaged["data"]["notebook_commit"]


def test_session_events_arrive_on_the_workflow_websocket(harness: _Harness) -> None:
    """FR-057: the hub the workflow already uses. One connection, not two.

    Opened before the session so the frame cannot have been buffered from
    before the connection existed, and the workflow's own ``ping``/``pong`` is
    exchanged on the same socket to prove it is that connection and not a
    parallel one that happens to work.
    """
    with harness.client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}

        session = harness.open_file_session()

        frame = websocket.receive_json()
        assert frame["type"] == "explore.session_opened"
        assert frame["session_id"] == session["session_id"]
        assert frame["data"]["opened_over"] == "file"
        assert frame["timestamp"]


def test_a_cell_run_reaches_the_websocket_from_the_queue_thread(harness: _Harness) -> None:
    """The events a run publishes come from a worker thread, and must still arrive.

    ``asyncio.Queue.put_nowait`` called off the event loop does not wake it, so a
    frame enqueued that way sits until something unrelated flushes it. This test
    would time out rather than fail if the marshalling in ``ws.py`` were removed.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")

    with harness.client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}

        harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")
        harness.wait_idle()

        seen: list[str] = []
        for _ in range(5):
            seen.append(websocket.receive_json()["type"])
        assert seen == [
            "explore.kernel_state",
            "explore.cell_state",
            "explore.cell_output",
            "explore.changed_names",
            "explore.cell_state",
        ]


def test_a_subscriber_that_raises_does_not_fail_the_session(harness: _Harness) -> None:
    """A frontend's bug must not fail a cell run."""

    def exploding(_frame: dict[str, Any]) -> None:
        raise RuntimeError("the subscriber is broken")

    explore.register_explore_subscriber(exploding)
    try:
        session = harness.open_file_session()
        session_id = session["session_id"]
        first = session["cells"][0]["cell_id"]
        _set_source(harness, session_id, first, "value = 1")
        _run(harness, session_id, first)
    finally:
        explore.unregister_explore_subscriber(exploding)

    assert harness.kernels[0].namespace["value"] == 1
    assert "explore.cell_output" in harness.types()


def test_unregistering_a_subscriber_stops_its_frames(harness: _Harness) -> None:
    harness.open_file_session()
    assert harness.events, "the subscriber was receiving frames"
    explore.unregister_explore_subscriber(harness.events.append)
    before = len(harness.events)

    harness.open_file_session("data/raw/other.csv")

    assert len(harness.events) == before
    explore.register_explore_subscriber(harness.events.append)


def test_the_frame_shape_matches_the_hub_convention() -> None:
    """A session event renders like every other frame on this socket."""
    from scistudio.explore.session import SessionEvent

    frame = explore.serialise_session_event(
        SessionEvent(type=SessionEventType.CELL_STATE, session_id="s1", payload={"cell_id": "c1"})
    )

    assert set(frame) == {"type", "session_id", "data", "timestamp"}
    assert frame["type"] == "explore.cell_state"
    assert frame["type"].startswith(explore.EXPLORE_EVENT_PREFIX)
    assert frame["data"] == {"cell_id": "c1"}


# ---------------------------------------------------------------------------
# FR-058: the refusal shapes
# ---------------------------------------------------------------------------

#: Every session-scoped route, as ``(method, path suffix, body)``. Used to prove
#: that an unknown session is a 404 in the documented shape on *all* of them,
#: rather than on the one a test happened to pick.
SESSION_SCOPED_ROUTES: tuple[tuple[str, str, dict[str, Any] | None], ...] = (
    ("GET", "", None),
    ("DELETE", "", None),
    ("POST", "/commit", {"message": "m"}),
    ("GET", "/cells", None),
    ("PUT", "/cells/c1", {"source": "x = 1"}),
    ("POST", "/cells", {"source": "x = 1"}),
    ("PUT", "/cells/c1/enabled", {"enabled": False}),
    ("POST", "/cells/c1/run", None),
    ("POST", "/run-stale", None),
    ("POST", "/cells/c1/run-with-upstream", None),
    ("POST", "/interrupt", None),
    ("POST", "/restart", None),
    ("GET", "/graph", None),
    ("GET", "/marks", None),
    ("GET", "/bindings", None),
    ("POST", "/window", {"name": "x"}),
    ("POST", "/snippets", {"source": "x = 1", "panel": "p"}),
    ("POST", "/packaging/check", {}),
    ("POST", "/package", {"block_name": "B"}),
)


@pytest.mark.parametrize(("method", "suffix", "body"), SESSION_SCOPED_ROUTES, ids=lambda v: str(v))
def test_an_unknown_session_is_a_404_in_the_documented_shape(
    harness: _Harness,
    method: str,
    suffix: str,
    body: dict[str, Any] | None,
) -> None:
    """Not one route: every route. A 500 here tells the frontend nothing."""
    response = harness.client.request(method, f"/api/explore/sessions/no-such-session{suffix}", json=body)

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "session_not_found"
    assert detail["message"], "a refusal always says what it refused"


def test_a_closed_session_is_a_404_on_every_route(harness: _Harness) -> None:
    """A closed session is not a special case; the service has forgotten it."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    harness.client.delete(f"/api/explore/sessions/{session_id}")

    for method, suffix, body in SESSION_SCOPED_ROUTES:
        response = harness.client.request(method, f"/api/explore/sessions/{session_id}{suffix}", json=body)
        assert response.status_code == 404, f"{method} {suffix} answered {response.status_code}"
        assert response.json()["detail"]["error"] == "session_not_found"


def test_an_unknown_cell_is_a_404_rather_than_a_key_error(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]

    for method, suffix, body in (
        ("PUT", "/cells/nope", {"source": "x = 1"}),
        ("PUT", "/cells/nope/enabled", {"enabled": False}),
        ("POST", "/cells/nope/run", None),
        ("POST", "/cells/nope/run-with-upstream", None),
        ("POST", "/cells", {"source": "x = 1", "after": "nope"}),
    ):
        response = harness.client.request(method, f"/api/explore/sessions/{session_id}{suffix}", json=body)
        assert response.status_code == 404, f"{method} {suffix} answered {response.status_code}"
        assert response.json()["detail"]["error"] == "cell_not_found"


def test_nothing_to_explore_is_a_refusal_with_a_reason(harness: _Harness) -> None:
    """FR-002: a block whose outputs were never produced."""
    harness.resolver.latest = None

    response = harness.client.post(
        "/api/explore/sessions",
        json={"source": "block_outputs", "block_id": "never-ran"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "nothing_to_explore"
    assert "Run it first" in detail["message"]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        pytest.param({"source": "block_outputs"}, "block_id", id="block-outputs-without-a-block"),
        pytest.param({"source": "paused_run", "block_id": "b"}, "run_id", id="paused-run-without-a-run"),
        pytest.param({"source": "file"}, "path", id="file-without-a-path"),
        pytest.param({"source": "notebook"}, "path", id="notebook-without-a-path"),
        pytest.param({"source": "telepathy"}, "not a session source", id="an-unknown-source"),
    ],
)
def test_an_incomplete_open_request_says_what_is_missing(
    harness: _Harness,
    body: dict[str, Any],
    reason: str,
) -> None:
    response = harness.client.post("/api/explore/sessions", json=body)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "invalid_request"
    assert reason in detail["message"]


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        pytest.param("POST", "/api/explore/sessions", {"block_id": 1}, id="open-with-no-source"),
        pytest.param("PUT", "/cells/{cell}", {"src": "x"}, id="write-cell-with-the-wrong-key"),
        pytest.param("PUT", "/cells/{cell}/enabled", {"enabled": "maybe-not-a-bool"}, id="enabled-not-a-bool"),
        pytest.param("POST", "/window", {"query": {}}, id="window-with-no-name"),
        pytest.param("POST", "/snippets", {"source": "x = 1"}, id="snippet-with-no-panel"),
        pytest.param("POST", "/package", {}, id="package-with-no-block-name"),
    ],
)
def test_a_malformed_body_is_a_422_from_validation(
    harness: _Harness,
    method: str,
    suffix: str,
    body: dict[str, Any],
) -> None:
    """Validation refuses before the session is touched, in FastAPI's own shape."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    cell_id = session["cells"][0]["cell_id"]
    url = suffix if suffix.startswith("/api/") else f"/api/explore/sessions/{session_id}{suffix.format(cell=cell_id)}"

    response = harness.client.request(method, url, json=body)

    assert response.status_code == 422, response.text
    assert "detail" in response.json()


def test_a_refused_emission_leaves_no_cell_behind(harness: _Harness) -> None:
    """FR-018, and the orphan shape this repository has shipped before.

    A refusal that had already inserted the cell would leave a cell nobody
    asked for, and the person would find it later with no idea where it came
    from. The status code is the easy half; the cell list is the assertion that
    matters.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    before = harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/snippets",
        json={"source": "table.drop(index=[3], inplace=True)", "panel": "table-panel"},
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "snippet_refused"
    assert detail["panel"] == "table-panel"
    assert detail["statement"] == "table.drop(index=[3], inplace=True)"
    after = harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]
    assert after == before, "a refused emission must leave the notebook exactly as it was"


def test_a_snippet_that_does_not_parse_is_refused_without_a_cell(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]
    before = harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/snippets",
        json={"source": "table[:", "panel": "p"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "snippet_refused"
    assert harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"] == before


def test_a_frozen_panel_is_refused_and_leaves_no_cell_behind(harness: _Harness) -> None:
    """FR-025: a panel bound to a name the running cell may change is told, not queued.

    The cell is held mid-run by the fake kernel so the freeze rule is reachable
    at all; without a running request there is nothing to be frozen against.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "df = 'hold-me'")
    harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")  # starts the kernel
    harness.wait_idle()

    harness.kernels[0].block_on = "hold-me"
    harness.kernels[0].released.clear()
    harness.kernels[0].entered.clear()
    before = harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"]
    harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")
    assert harness.kernels[0].entered.wait(timeout=_IDLE_TIMEOUT), "the cell never started"

    try:
        response = harness.client.post(
            f"/api/explore/sessions/{session_id}/snippets",
            json={"source": "subset = df", "panel": "df-panel", "bound_names": ["df"]},
        )
    finally:
        harness.kernels[0].block_on = None
        harness.kernels[0].released.set()
        harness.wait_idle()

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["error"] == "panel_frozen"
    assert detail["panel"] == "df-panel"
    assert detail["names"] == ["df"]
    assert harness.client.get(f"/api/explore/sessions/{session_id}/cells").json()["cells"] == before


def test_a_dead_kernel_surfaces_as_a_refusal_not_a_500(harness: _Harness) -> None:
    """FR-015: a kernel killed from outside is reported, and the routes still answer."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    harness.kernels[0].die()
    harness.service().session_for(session_id).report_kernel_died()

    assert harness.client.get("/api/explore/kernels").json()["kernels"] == []
    marks = harness.client.get(f"/api/explore/sessions/{session_id}/marks").json()
    assert marks["never_run"] == [first], "the namespace is gone, so the marks reset"
    assert harness.client.get(f"/api/explore/sessions/{session_id}").json()["needs_restart"] is True


def test_a_bridge_failure_is_a_502_rather_than_a_500(harness: _Harness) -> None:
    """A window the bridge could not answer is an upstream failure, and says so."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "table = [1]")
    _run(harness, session_id, first)
    harness.bridges[0].window_error = BridgeError("the bridge did not answer")

    response = harness.client.post(f"/api/explore/sessions/{session_id}/window", json={"name": "table"})

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["error"] == "bridge_error"
    assert response.json()["detail"]["message"] == "the bridge did not answer"


def test_an_unbound_variable_window_is_a_refusal_with_the_name(harness: _Harness) -> None:
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "table = [1]")
    _run(harness, session_id, first)

    response = harness.client.post(f"/api/explore/sessions/{session_id}/window", json={"name": "absent"})

    assert response.status_code == 502
    assert "absent" in response.json()["detail"]["message"]


def test_an_unrecognised_failure_is_still_a_500(harness: _Harness) -> None:
    """The refusal mapping is a closed list, not a blanket over every exception.

    A translator that turned everything into a tidy 4xx would hide the bugs it
    was written to expose, and the frontend would show "refused" for a defect.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "table = [1]")
    _run(harness, session_id, first)
    harness.bridges[0].window_error = ZeroDivisionError("a genuine bug")

    response = harness.client.post(f"/api/explore/sessions/{session_id}/window", json={"name": "table"})

    assert response.status_code == 500
    assert response.json().get("detail") != {"error": "session_refused"}


def test_no_active_project_is_a_refusal_on_every_collection_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a project there is no explore directory, and that is not a 500."""
    _require_explore_routes(client.app)
    try:
        for method, url, body in (
            ("GET", "/api/explore/sessions", None),
            ("GET", "/api/explore/kernels", None),
            ("POST", "/api/explore/sessions", {"source": "file", "path": "a.csv"}),
        ):
            response = client.request(method, url, json=body)
            assert response.status_code == 409, f"{method} {url} answered {response.status_code}"
            assert response.json()["detail"]["error"] == "no_active_project"
    finally:
        explore.shutdown_session_services()


# ---------------------------------------------------------------------------
# FR-058: the refusal table's keys, against the real classes
# ---------------------------------------------------------------------------


@needs_kernel
def test_the_by_name_refusal_table_names_classes_that_exist() -> None:
    """The kernel refusals are mapped by name because importing them is not free.

    ``scistudio.explore.kernel`` imports ``jupyter_client`` at module scope, so
    the route module maps its exceptions by ``(module, class name)`` rather than
    by ``isinstance``. That is only safe while those names are real: this test
    is what fails when one of them is renamed, instead of the rename silently
    demoting a documented refusal to a 500.
    """
    import importlib

    for module_name, class_name in explore._REFUSALS_BY_NAME:
        module = importlib.import_module(module_name)
        resolved = getattr(module, class_name, None)
        assert resolved is not None, f"{module_name}.{class_name} no longer exists"
        assert issubclass(resolved, BaseException)
        assert resolved.__module__ == module_name
        assert resolved.__name__ == class_name


@pytest.mark.parametrize(
    ("module_name", "class_name", "expected_status"),
    [
        pytest.param("scistudio.explore.kernel", "KernelDiedError", 409, id="dead-kernel"),
        pytest.param("scistudio.explore.kernel", "KernelNotRunningError", 409, id="kernel-not-running"),
        pytest.param("scistudio.explore.kernel", "KernelTimeoutError", 504, id="kernel-timeout"),
        pytest.param("scistudio.explore.kernel", "KernelLaunchError", 502, id="kernel-launch-failed"),
        pytest.param("scistudio.explore.packaging", "PackagingRefusedError", 422, id="packaging-refused"),
    ],
)
def test_a_refusal_from_an_unimported_module_is_classified_by_name(
    module_name: str,
    class_name: str,
    expected_status: int,
) -> None:
    """The classifier, exercised without importing the modules it maps.

    Each stand-in carries the ``__module__`` and ``__name__`` the table keys on,
    which is exactly what the classifier reads.
    ``test_the_by_name_refusal_table_names_classes_that_exist`` is the other
    half: it proves those keys still name the real classes.
    """
    stand_in = type(class_name, (RuntimeError,), {"__module__": module_name})
    classified = explore._classify(stand_in("something went wrong"))
    assert classified is not None, f"{module_name}.{class_name} was not classified"
    assert classified[0] == expected_status


def test_a_subclass_of_a_mapped_refusal_is_still_classified() -> None:
    """A refusal raised as a subclass must not degrade to a 500."""
    base = type("KernelDiedError", (RuntimeError,), {"__module__": "scistudio.explore.kernel"})
    derived = type("KernelDiedLoudlyError", (base,), {"__module__": "somewhere.else"})
    assert explore._classify(derived("gone")) == (409, "kernel_died")


def test_an_unmapped_exception_is_not_classified() -> None:
    assert explore._classify(ZeroDivisionError("a bug")) is None


# ---------------------------------------------------------------------------
# The real kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def real_harness(
    client: TestClient,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Harness]:
    """The routes over a real ipykernel process, launched from this interpreter."""
    import os

    import scistudio

    root = Path(scistudio.__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    entries = [str(root), *(entry for entry in existing.split(os.pathsep) if entry)]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(entries))

    events: list[dict[str, Any]] = []
    _require_explore_routes(client.app)
    explore.register_explore_subscriber(events.append)
    harness = _Harness(
        client=client,
        project_dir=opened_project,
        kernels=[],
        bridges=[],
        resolver=_StubResolver(),
        git=None,
        events=events,
    )
    try:
        yield harness
    finally:
        explore.unregister_explore_subscriber(events.append)
        explore.shutdown_session_services()


@needs_kernel
@pytest.mark.serial
def test_a_real_kernel_runs_a_cell_and_publishes_its_events(real_harness: _Harness) -> None:
    """The whole path, once, against the process the runtime actually launches.

    Every other test here substitutes the kernel, which is right for testing
    routes and wrong for believing they work. This one opens a session, runs a
    cell, reads the binding back through the bindings route, and checks that the
    kernel list reports the process — none of which a fake can prove.
    """
    session = real_harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(real_harness, session_id, first, "greeting = 'hello from the kernel'")

    response = real_harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")
    assert response.status_code == 200, response.text
    real_harness.wait_idle()

    bindings = real_harness.client.get(f"/api/explore/sessions/{session_id}/bindings").json()
    by_name = {row["name"]: row for row in bindings["bindings"]}
    assert by_name["greeting"]["exists_in_kernel"] is True
    assert by_name["greeting"]["type_name"] == "str"

    kernels = real_harness.client.get("/api/explore/kernels").json()["kernels"]
    assert len(kernels) == 1
    assert kernels[0]["pid"], "a real kernel has a process id"

    window = real_harness.client.post(
        f"/api/explore/sessions/{session_id}/window",
        json={"name": "greeting"},
    )
    assert window.status_code == 200, window.text

    assert "explore.cell_output" in real_harness.types()
    assert real_harness.client.delete(f"/api/explore/kernels/{session_id}").status_code == 200


@needs_kernel
@pytest.mark.serial
def test_interrupting_a_real_kernel_ends_a_hung_cell_through_the_route(
    real_harness: _Harness,
    tmp_path: Path,
) -> None:
    """FR-013 against the process: a mocked interrupt is not an interrupt.

    The cell writes a marker before it hangs, and the test waits for the marker
    rather than interrupting after an arbitrary sleep and hoping the cell had
    started — the same discipline ``tests/explore/test_kernel_session.py`` uses,
    and for the same reason: an interrupt that arrives before the loop proves
    nothing.
    """
    marker = tmp_path / "running.marker"
    session = real_harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(
        real_harness,
        session_id,
        first,
        "import pathlib\n"
        f"pathlib.Path({str(marker.as_posix())!r}).write_text('running', encoding='utf-8')\n"
        "while True:\n"
        "    pass\n",
    )

    real_harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")

    deadline = time.monotonic() + _IDLE_TIMEOUT
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.02)
    assert marker.exists(), "the kernel never reached the loop"

    response = real_harness.client.post(f"/api/explore/sessions/{session_id}/interrupt")
    assert response.status_code == 200, response.text
    real_harness.wait_idle()

    outputs = [frame for frame in real_harness.events if frame["type"] == "explore.cell_output"]
    assert outputs, "the interrupted cell still reported a result"
    assert outputs[-1]["data"]["status"] == "error"
    assert outputs[-1]["data"]["outputs"][0]["ename"] == "KeyboardInterrupt"
    assert real_harness.client.delete(f"/api/explore/kernels/{session_id}").status_code == 200


# ---------------------------------------------------------------------------
# FR-058, adversarial: the shapes a route answers when the state is wrong
# (added by the ADR-054 spec 3 adversarial pass, #2240)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "suffix", "body"), SESSION_SCOPED_ROUTES, ids=lambda v: str(v))
def test_a_dead_kernel_never_answers_a_route_with_a_500(
    harness: _Harness,
    method: str,
    suffix: str,
    body: dict[str, Any] | None,
) -> None:
    """FR-015 and FR-058 on *every* route, not on the three a test happened to pick.

    ``test_a_dead_kernel_surfaces_as_a_refusal_not_a_500`` asks three routes.
    The rest are where an unhandled ``KernelDiedError`` would surface as a bare
    500 — the shape that tells a frontend nothing and, in this repository's
    history, the shape that leaves an orphan behind. Any documented refusal is
    an acceptable answer here; a 500, or a body with no ``error``, is not.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    harness.kernels[0].die()
    harness.service().session_for(session_id).report_kernel_died()

    url = f"/api/explore/sessions/{session_id}{suffix.replace('c1', first)}"
    response = harness.client.request(method, url, json=body)
    harness.wait_idle()

    assert response.status_code != 500, f"{method} {suffix} answered a bare 500: {response.text}"
    if response.status_code >= 400:
        detail = response.json().get("detail")
        assert isinstance(detail, dict) and detail.get("error"), (
            f"{method} {suffix} refused without saying what it refused: {response.text}"
        )


@pytest.mark.parametrize(("method", "suffix"), [(m, s) for m, s, b in SESSION_SCOPED_ROUTES if b is not None])
def test_a_body_of_the_wrong_json_type_is_a_422_on_every_route_that_takes_one(
    harness: _Harness,
    method: str,
    suffix: str,
) -> None:
    """Validation, on every route with a body rather than on the six a list names.

    A JSON array where a model is expected is the shape a client sends when it
    serialises the wrong variable, and it must be refused by validation rather
    than reaching the session and becoming an ``AttributeError``.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]

    url = f"/api/explore/sessions/{session_id}{suffix.replace('c1', first)}"
    response = harness.client.request(method, url, json=["not", "a", "model"])

    assert response.status_code == 422, f"{method} {suffix} answered {response.status_code}: {response.text}"
    assert "detail" in response.json()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(["file", "a.csv"], id="a-list"),
        pytest.param("file", id="a-string"),
        pytest.param(7, id="a-number"),
        pytest.param(None, id="null"),
    ],
)
def test_opening_a_session_with_a_body_that_is_not_an_object_is_a_422(harness: _Harness, body: Any) -> None:
    """The open route is the one an unauthenticated client reaches first."""
    response = harness.client.post("/api/explore/sessions", json=body)

    assert response.status_code == 422, response.text
    assert "detail" in response.json()


def test_ending_a_kernel_for_an_unknown_session_is_a_404_not_a_500(harness: _Harness) -> None:
    """The kernel routes are session-scoped too, and are not in SESSION_SCOPED_ROUTES."""
    response = harness.client.delete("/api/explore/kernels/no-such-session")

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error"] == "session_not_found"


def test_ending_a_kernel_that_is_already_gone_is_not_an_error(harness: _Harness) -> None:
    """US7 scenario 2 pressed twice: ending a kernel is a state, not a transition.

    The person's list is a moment old by the time they click, so the second
    click has to be harmless rather than a refusal about a kernel that has
    already gone.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    assert harness.client.delete(f"/api/explore/kernels/{session_id}").status_code == 200
    second = harness.client.delete(f"/api/explore/kernels/{session_id}")

    assert second.status_code == 200, second.text
    assert harness.client.get("/api/explore/kernels").json()["kernels"] == []


def test_closing_a_session_twice_is_a_404_the_second_time_and_leaves_no_kernel(harness: _Harness) -> None:
    """FR-006: closing removes the session, so the second close is about a session that is not open."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 1")
    _run(harness, session_id, first)

    assert harness.client.delete(f"/api/explore/sessions/{session_id}").status_code == 200
    assert harness.kernels[0].stopped >= 1, "closing a session must end its kernel"

    second = harness.client.delete(f"/api/explore/sessions/{session_id}")
    assert second.status_code == 404
    assert second.json()["detail"]["error"] == "session_not_found"
    assert harness.client.get("/api/explore/kernels").json()["kernels"] == []


def test_packaging_a_session_with_no_commit_is_a_refusal_that_writes_nothing(harness: _Harness) -> None:
    """FR-041 through the route: a block's version is the commit it was packaged from.

    The harness has no git engine, so no commit is ever recorded — which is the
    state a project in a directory that is not a repository is permanently in.
    The refusal must name the reason and leave the blocks directory alone.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    blocks = harness.project_dir / "blocks"
    before = sorted(path.name for path in blocks.glob("*")) if blocks.is_dir() else []

    response = harness.client.post(
        f"/api/explore/sessions/{session_id}/package",
        json={"block_name": "Nothing Doing"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error"] == "no_notebook_commit"
    after = sorted(path.name for path in blocks.glob("*")) if blocks.is_dir() else []
    assert after == before, "a refused packaging wrote files"


@pytest.mark.xfail(
    reason=(
        "#2240: FR-039's 'Packaging MUST wait for the queue to drain before checking' is not "
        "implemented anywhere — check_packaging is pure, package_notebook does not wait, and "
        "neither route calls ExploreSession.wait_until_idle."
    ),
    strict=False,
)
def test_a_packaging_check_waits_for_the_queue_to_drain(harness: _Harness) -> None:
    """FR-039, last sentence, and the edge case in spec §2 that explains it.

    "Packaging is requested while a cell is queued or running. Packaging waits
    for the queue to drain, because the slice's marks are not final until it
    has." Here a cell is held mid-run whose completion makes the output cell
    stale. Answered now, the check says the notebook is packageable; answered
    after the queue drains, it says the slice contains a stale cell. Today it
    answers now.

    The failure is not a crash. It is a person being told their notebook is
    ready and packaging a block whose slice was stale by the time the file was
    written.
    """
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 'one'")
    declare = harness.client.post(
        f"/api/explore/sessions/{session_id}/cells",
        json={"source": "import scistudio\nscistudio.output(table=value)", "after": first},
    )
    assert declare.status_code == 200, declare.text
    declared_id = declare.json()["cells"][-1]["cell_id"]
    _run(harness, session_id, first)
    _run(harness, session_id, declared_id)

    clean = harness.client.post(f"/api/explore/sessions/{session_id}/packaging/check", json={}).json()
    assert clean["is_packageable"], f"the fixture is not packageable to begin with: {clean['problems']}"

    harness.kernels[0].block_on = "two"
    harness.kernels[0].released.clear()
    harness.kernels[0].entered.clear()
    _set_source(harness, session_id, first, "value = 'two'")
    harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")
    assert harness.kernels[0].entered.wait(timeout=_IDLE_TIMEOUT), "the held cell never started"

    try:
        answered = harness.client.post(f"/api/explore/sessions/{session_id}/packaging/check", json={})
    finally:
        harness.kernels[0].block_on = None
        harness.kernels[0].released.set()
        harness.wait_idle()

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert not body["is_packageable"], (
        "packaging answered before the queue drained, so it read marks that were not final"
    )
    assert any(problem["kind"] == "stale_cell" for problem in body["problems"]), body["problems"]


def test_a_packaging_check_answers_from_the_marks_as_they_stand_today(harness: _Harness) -> None:
    """The behaviour as delivered, pinned. See the xfail above for why it is wrong."""
    session = harness.open_file_session()
    session_id = session["session_id"]
    first = session["cells"][0]["cell_id"]
    _set_source(harness, session_id, first, "value = 'one'")
    declare = harness.client.post(
        f"/api/explore/sessions/{session_id}/cells",
        json={"source": "import scistudio\nscistudio.output(table=value)", "after": first},
    )
    declared_id = declare.json()["cells"][-1]["cell_id"]
    _run(harness, session_id, first)
    _run(harness, session_id, declared_id)

    harness.kernels[0].block_on = "two"
    harness.kernels[0].released.clear()
    harness.kernels[0].entered.clear()
    _set_source(harness, session_id, first, "value = 'two'")
    harness.client.post(f"/api/explore/sessions/{session_id}/cells/{first}/run")
    assert harness.kernels[0].entered.wait(timeout=_IDLE_TIMEOUT)

    try:
        body = harness.client.post(f"/api/explore/sessions/{session_id}/packaging/check", json={}).json()
    finally:
        harness.kernels[0].block_on = None
        harness.kernels[0].released.set()
        harness.wait_idle()

    assert body["is_packageable"], "the check no longer answers mid-run; update the xfail above"

    after = harness.client.post(f"/api/explore/sessions/{session_id}/packaging/check", json={}).json()
    assert not after["is_packageable"], "and once the queue has drained the same notebook is refused"
    assert any(problem["kind"] == "stale_cell" for problem in after["problems"])
