"""The seven session MCP tools, against a scripted session API.

ADR-054 spec 5 T-006, FR-019 to FR-024 (issue #2254).

The real session is covered by spec 3's own suite, so what is asserted here is
what these tools *are*: the request each one makes of the session API, the shape
of what it hands back, and the two rules that would be quiet to break —
``open_explore_session`` must not move the person's focus (FR-019), and no tool
may reach past the session API (FR-024).

The session API is therefore scripted rather than real. Every fake below is
shaped like the object the session hands out, records what was asked of it, and
answers with fixed data, so a test that says "``read_notebook`` asks for the
graph" fails when the tool stops asking rather than when a kernel misbehaves.

:func:`test_no_session_tool_reaches_past_the_session_api` is the load-bearing
one. FR-024 is a structural claim, so it gets a structural assertion: the whole
package is parsed and every import — module scope *and* function body, which is
where a shortcut would actually be written — is held to an allowlist, and every
attribute access is held against the names that would reach the kernel, the
notebook file, or the queue directly.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Coroutine, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp import tools_explore as tools_explore_pkg
from scistudio.ai.agent.mcp._focus import MODE_CANVAS, MODE_EXPLORE, MODE_PAUSE, NoExploreSessionError
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_explore import (
    _models,
    _service,
    append_cell,
    check_packaging,
    get_bindings,
    open_explore_session,
    package_notebook,
    read_notebook,
    run_cell,
)
from scistudio.explore.packaging import PackagingProblem, PackagingProblemKind, PackagingRefusedError
from scistudio.explore.session import CellMark, SessionError

_T = TypeVar("_T")

NOTEBOOK = "explore/qc.ipynb"
OTHER_NOTEBOOK = "explore/other.ipynb"

#: The seven tools this task registers, exactly as they are registered. S5-B4
#: writes these into the catalogs and the count assertions.
SESSION_TOOL_NAMES = frozenset(
    {
        "open_explore_session",
        "read_notebook",
        "append_cell",
        "run_cell",
        "get_bindings",
        "check_packaging",
        "package_notebook",
    }
)

#: The four that write. FR-025's sibling assertion in ``test_mcp_fastmcp.py``
#: requires a ``next_step`` on every write-class result model.
WRITE_CLASS = frozenset({"open_explore_session", "append_cell", "run_cell", "package_notebook"})


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run one tool coroutine. The repository does not install pytest-asyncio."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# The scripted session API
# ---------------------------------------------------------------------------


@dataclass
class _Cell:
    """Shaped like :class:`scistudio.explore.notebook.NotebookCell`."""

    cell_id: str
    source: str = ""
    cell_type: str = "code"
    enabled: bool = True
    outputs: tuple[Mapping[str, Any], ...] = ()
    execution_count: int | None = None


@dataclass(frozen=True)
class _Edge:
    reader: str
    definer: str
    name: str
    origin: str = "observed"


@dataclass(frozen=True)
class _UnresolvedRead:
    cell_id: str
    name: str


@dataclass
class _Graph:
    cells: tuple[str, ...] = ()
    edges: tuple[_Edge, ...] = ()
    unresolved_reads: tuple[_UnresolvedRead, ...] = ()
    unknown_binding_cells: tuple[str, ...] = ()
    changed_sets: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class _OutputDeclaration:
    keywords: tuple[str, ...] = ()
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Facts:
    cell_id: str
    outputs: tuple[_OutputDeclaration, ...] = ()


@dataclass(frozen=True)
class _Binding:
    name: str
    type_name: str
    native_type_name: str
    type_module: str
    summary: str


@dataclass(frozen=True)
class _Observation:
    changed_names: frozenset[str]


@dataclass
class _Request:
    cell_id: str
    request_id: str = "req-1"
    state: str = "queued"


class _Session:
    """Shaped like :class:`scistudio.explore.session.ExploreSession`.

    Only the members the tools are allowed to touch exist. A tool that reached
    for the kernel, the queue, or the notebook store would raise
    :class:`AttributeError` here as well as failing the structural test — the
    two assertions are deliberately redundant, because one is about what the
    code says and the other about what it does.
    """

    def __init__(self, relative_path: str = NOTEBOOK) -> None:
        self.relative_path = relative_path
        self.session_id = f"sess-{relative_path}"
        self.has_kernel = True
        self.needs_restart = False
        self.current_cell = "cell-b"
        self.notebook_commit = "abc123"
        self.bound_run = None
        self.document = object()
        self.calls: list[tuple[str, Any]] = []
        self.reloaded = 0
        self.refusal: BaseException | None = None
        self.drains = True
        self._cells = [
            _Cell("cell-a", "import pandas as pd", execution_count=1),
            _Cell(
                "cell-b",
                "df = pd.read_csv(path)",
                outputs=(MappingProxyType({"output_type": "stream", "name": "stdout", "text": ["loaded\n"]}),),
                execution_count=2,
            ),
            _Cell("cell-c", "scistudio.output(table=df)", enabled=False),
        ]
        self._marks = {"cell-c": frozenset({CellMark.NEVER_RUN})}
        self._bindings = (_Binding("df", "DataFrame", "DataFrame", "pandas.core.frame", "12 x 3"),)
        self.graph = _Graph(
            cells=("cell-a", "cell-b"),
            edges=(_Edge(reader="cell-b", definer="cell-a", name="pd"),),
            unresolved_reads=(_UnresolvedRead(cell_id="cell-b", name="path"),),
            unknown_binding_cells=("cell-c",),
            changed_sets={"cell-a": frozenset({"pd"}), "cell-b": frozenset({"df"})},
        )
        self.facts = (
            _Facts("cell-a"),
            _Facts("cell-b"),
            _Facts("cell-c", outputs=(_OutputDeclaration(keywords=("table",), arguments=("df",)),)),
        )
        self.last_bound_by = {"df": "cell-b"}
        self.observations: dict[str, _Observation] = {"cell-b": _Observation(frozenset({"df"}))}

    # -- reads -----------------------------------------------------------

    def cells(self) -> tuple[_Cell, ...]:
        self.calls.append(("cells", None))
        return tuple(self._cells)

    @property
    def marks_by_cell(self) -> Mapping[str, frozenset[CellMark]]:
        return dict(self._marks)

    def marks(self, cell_id: str) -> frozenset[CellMark]:
        return self._marks.get(cell_id, frozenset())

    def bindings(self) -> tuple[_Binding, ...]:
        self.calls.append(("bindings", None))
        return self._bindings

    def cell_marks(self) -> object:
        self.calls.append(("cell_marks", None))
        return object()

    def binding_types(self) -> dict[str, str]:
        self.calls.append(("binding_types", None))
        return {"df": "DataFrame"}

    # -- writes ----------------------------------------------------------

    def insert_cell(self, source: str = "", *, after: str | None = None) -> str:
        self.calls.append(("insert_cell", (source, after)))
        cell_id = f"cell-new-{len(self._cells)}"
        self._cells.append(_Cell(cell_id, source))
        return cell_id

    def run_cell(self, cell_id: str) -> _Request:
        self.calls.append(("run_cell", cell_id))
        if self.refusal is not None:
            raise self.refusal
        return _Request(cell_id=cell_id, state="queued")

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        self.calls.append(("wait_until_idle", timeout))
        return self.drains

    def reload_if_changed(self) -> bool:
        self.reloaded += 1
        return False


class _Service:
    """Shaped like :class:`scistudio.explore.session.SessionService`."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.calls: list[tuple[str, Any]] = []
        self.events: list[Any] = []
        self.sessions: dict[str, _Session] = {}
        self.open_error: BaseException | None = None

    def _session(self, path: str) -> _Session:
        return self.sessions.setdefault(path, _Session(path))

    def open_over_block_outputs(self, block_id: str, *, run_id: str | None = None, name: str | None = None) -> _Session:
        self.calls.append(("open_over_block_outputs", (block_id, run_id, name)))
        if self.open_error is not None:
            raise self.open_error
        return self._session(NOTEBOOK)

    def open_over_file(self, path: str, *, name: str | None = None) -> _Session:
        self.calls.append(("open_over_file", (path, name)))
        if self.open_error is not None:
            raise self.open_error
        return self._session(NOTEBOOK)

    def open_notebook(self, path: str, *, bound_run: Any = None) -> _Session:
        self.calls.append(("open_notebook", str(path)))
        return self._session(str(path))

    def publish(self, event: Any) -> None:
        self.events.append(event)


@dataclass
class _StubContext:
    """The context the tools read. ``get_session_service`` is the hook of F-B3-1.

    Carrying it here means no test ever builds a real ``SessionService``: the
    fallback path in ``_service`` is production wiring, and a unit test that
    exercised it would be testing a project directory, not a tool.
    """

    project_dir: Path | None
    _service_obj: Any = None
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    active_workflow_id: str | None = "wf-1"
    workspace_focus: dict[str, Any] | None = None

    def get_session_service(self) -> Any:
        return self._service_obj


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "explore").mkdir(parents=True)
    (root / "explore" / "qc.ipynb").write_text("{}", encoding="utf-8")
    (root / "explore" / "other.ipynb").write_text("{}", encoding="utf-8")
    return root


@pytest.fixture
def service(project: Path) -> _Service:
    return _Service(project)


@pytest.fixture
def ctx(project: Path, service: _Service) -> Iterator[_StubContext]:
    """The person is focused on ``explore/qc.ipynb``."""
    stub = _StubContext(
        project_dir=project,
        _service_obj=service,
        workspace_focus={"mode": MODE_EXPLORE, "session_path": NOTEBOOK, "current_cell_id": "cell-b"},
    )
    _context.set_context(stub)  # type: ignore[arg-type]
    _service.reset_fallback_services()
    try:
        yield stub
    finally:
        _context.set_context(None)
        _service.reset_fallback_services()


@pytest.fixture(autouse=True)
def _scripted_packaging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Script the packaging seam for every test in this module.

    ``check_packaging`` and ``package_notebook`` are pure functions of a real
    :class:`~scistudio.explore.notebook.NotebookDocument`, and the session here
    is scripted, so the seam is scripted too. The tests that are *about*
    packaging replace these again with their own recorders; a later
    ``monkeypatch.setattr`` in a test body wins over this one.
    """
    from scistudio.explore import packaging as packaging_module

    monkeypatch.setattr(packaging_module, "check_packaging", lambda document, **kwargs: _Plan())
    monkeypatch.setattr(packaging_module, "package_notebook", lambda document, **kwargs: _Packaged())


def _focused(service: _Service) -> _Session:
    return service._session(NOTEBOOK)


def _asked(session: _Session, name: str) -> list[Any]:
    return [payload for call, payload in session.calls if call == name]


# ---------------------------------------------------------------------------
# FR-019 — open_explore_session
# ---------------------------------------------------------------------------


def test_open_explore_session_opens_over_a_blocks_outputs_through_the_service(
    ctx: _StubContext, service: _Service
) -> None:
    result = _run(open_explore_session(source="block_outputs", block_id="normalise", run_id="run-7", name="qc"))

    assert ("open_over_block_outputs", ("normalise", "run-7", "qc")) in service.calls
    assert result.session_path == NOTEBOOK
    assert result.opened_over == "block_outputs"
    assert result.has_kernel is True
    assert [cell.cell_id for cell in result.cells] == ["cell-a", "cell-b", "cell-c"]


def test_open_explore_session_opens_over_a_file_through_the_service(ctx: _StubContext, service: _Service) -> None:
    result = _run(open_explore_session(source="file", path="data/raw/signal.csv"))

    assert ("open_over_file", ("data/raw/signal.csv", None)) in service.calls
    assert result.opened_over == "file"
    assert result.session_path == NOTEBOOK


def test_open_explore_session_does_not_change_the_focus(ctx: _StubContext, service: _Service) -> None:
    """FR-019: the person's focus is the person's."""
    before = dict(ctx.workspace_focus or {})

    result = _run(open_explore_session(source="file", path="data/raw/signal.csv"))

    assert ctx.workspace_focus == before
    assert result.focus_unchanged is True
    assert result.focused_session_path == NOTEBOOK


def test_open_explore_session_does_not_change_a_canvas_focus_either(ctx: _StubContext, service: _Service) -> None:
    ctx.workspace_focus = {"mode": MODE_CANVAS, "workflow_id": "wf-1"}
    before = dict(ctx.workspace_focus)

    result = _run(open_explore_session(source="file", path="data/raw/signal.csv"))

    assert ctx.workspace_focus == before
    assert result.focused_session_path is None
    assert result.session_path == NOTEBOOK


def test_open_explore_session_refuses_an_unknown_source(ctx: _StubContext, service: _Service) -> None:
    with pytest.raises(_service.SessionToolError) as refusal:
        _run(open_explore_session(source="magic"))

    assert "block_outputs" in str(refusal.value)
    assert service.calls == []


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [({"source": "block_outputs"}, "block_id"), ({"source": "file"}, "path")],
)
def test_open_explore_session_names_the_argument_it_needs(
    ctx: _StubContext, service: _Service, kwargs: dict[str, str], missing: str
) -> None:
    with pytest.raises(_service.SessionToolError) as refusal:
        _run(open_explore_session(**kwargs))

    assert missing in str(refusal.value)
    assert service.calls == []


# ---------------------------------------------------------------------------
# FR-020 — read_notebook
# ---------------------------------------------------------------------------


def test_read_notebook_returns_cells_bindings_declared_outputs_and_the_graph(
    ctx: _StubContext, service: _Service
) -> None:
    result = _run(read_notebook())

    assert result.session_path == NOTEBOOK
    assert [cell.cell_id for cell in result.cells] == ["cell-a", "cell-b", "cell-c"]

    disabled = next(cell for cell in result.cells if cell.cell_id == "cell-c")
    assert disabled.enabled is False
    assert disabled.marks == ["never_run"]

    ran = next(cell for cell in result.cells if cell.cell_id == "cell-b")
    assert ran.source == "df = pd.read_csv(path)"
    assert [output.text for output in ran.outputs] == ["loaded\n"]
    assert ran.execution_count == 2

    by_name = {binding.name: binding for binding in result.bindings}
    assert by_name["df"].exists_in_kernel is True
    assert by_name["df"].type_name == "DataFrame"
    assert by_name["df"].last_bound_by == "cell-b"
    # ``table`` is declared but has never been bound: reported, not omitted.
    assert by_name["table"].exists_in_kernel is False

    assert result.declared_outputs[0].cell_id == "cell-c"
    assert result.declared_outputs[0].names == ["table"]

    assert result.graph.cells == ["cell-a", "cell-b"]
    assert result.graph.edges[0].reader == "cell-b"
    assert result.graph.unresolved_reads[0].name == "path"
    assert result.graph.changed_sets == {"cell-a": ["pd"], "cell-b": ["df"]}


def test_read_notebook_asks_the_session_for_the_bindings_it_reports(ctx: _StubContext, service: _Service) -> None:
    _run(read_notebook())

    assert _asked(_focused(service), "bindings") == [None]


# ---------------------------------------------------------------------------
# FR-021 — append_cell
# ---------------------------------------------------------------------------


def test_append_cell_inserts_after_the_sessions_current_cell(ctx: _StubContext, service: _Service) -> None:
    result = _run(append_cell(source="df = df.dropna()"))

    session = _focused(service)
    assert _asked(session, "insert_cell") == [("df = df.dropna()", "cell-b")]
    assert result.after == "cell-b"
    assert result.cell_id.startswith("cell-new-")
    assert result.source == "df = df.dropna()"


def test_append_cell_appends_at_the_end_when_no_cell_is_current(ctx: _StubContext, service: _Service) -> None:
    _focused(service).current_cell = None

    result = _run(append_cell(source="print(df)"))

    assert _asked(_focused(service), "insert_cell") == [("print(df)", None)]
    assert result.after is None


# ---------------------------------------------------------------------------
# FR-021 — run_cell
# ---------------------------------------------------------------------------


def test_run_cell_submits_and_returns_outputs_and_changed_names(ctx: _StubContext, service: _Service) -> None:
    result = _run(run_cell(cell_id="cell-b"))

    session = _focused(service)
    assert _asked(session, "run_cell") == ["cell-b"]
    assert _asked(session, "wait_until_idle") == [tools_explore_pkg.tools.QUEUE_DRAIN_TIMEOUT]
    assert result.refused is False
    assert result.completed is True
    assert result.changed_names == ["df"]
    assert [output.text for output in result.outputs] == ["loaded\n"]
    assert result.errored is False
    assert result.request_id == "req-1"


def test_run_cell_reports_a_cell_that_raised_without_calling_it_a_refusal(ctx: _StubContext, service: _Service) -> None:
    session = _focused(service)
    session._cells[1].outputs = (
        MappingProxyType(
            {
                "output_type": "error",
                "ename": "KeyError",
                "evalue": "'path'",
                "traceback": ["Traceback...\n", "KeyError: 'path'\n"],
            }
        ),
    )

    result = _run(run_cell(cell_id="cell-b"))

    assert result.refused is False
    assert result.errored is True
    assert result.outputs[0].ename == "KeyError"
    assert "KeyError" in result.outputs[0].text


def test_run_cell_returns_the_queues_refusal_as_a_result(ctx: _StubContext, service: _Service) -> None:
    """FR-021: a refusal is a result, not an exception to swallow."""
    session = _focused(service)
    session.refusal = SessionError("Cell 'cell-c' is disabled, so it is not in the graph. Enable it first.")

    result = _run(run_cell(cell_id="cell-c"))

    assert result.refused is True
    assert result.refusal_kind == "not_runnable"
    assert "disabled" in (result.refusal or "")
    assert result.outputs == []
    # It refused before waiting: nothing was queued to wait for.
    assert _asked(session, "wait_until_idle") == []


def test_run_cell_returns_an_unknown_cell_as_a_refusal(ctx: _StubContext, service: _Service) -> None:
    _focused(service).refusal = KeyError("cell-zzz")

    result = _run(run_cell(cell_id="cell-zzz"))

    assert result.refused is True
    assert result.refusal_kind == "unknown_cell"
    assert "read_notebook" in (result.refusal or "")


def test_run_cell_returns_a_stopping_queue_as_a_refusal(ctx: _StubContext, service: _Service) -> None:
    _focused(service).refusal = RuntimeError("The execution queue is stopping; it accepts no further requests.")

    result = _run(run_cell(cell_id="cell-b"))

    assert result.refused is True
    assert result.refusal_kind == "queue_unavailable"


def test_run_cell_says_so_when_the_queue_did_not_drain(ctx: _StubContext, service: _Service) -> None:
    _focused(service).drains = False

    result = _run(run_cell(cell_id="cell-b", timeout_seconds=1.0))

    assert result.refused is False
    assert result.completed is False
    assert "still going" in result.next_step


# ---------------------------------------------------------------------------
# FR-022 — get_bindings
# ---------------------------------------------------------------------------


def test_get_bindings_returns_the_union_with_liveness(ctx: _StubContext, service: _Service) -> None:
    result = _run(get_bindings())

    assert result.session_path == NOTEBOOK
    assert result.has_kernel is True
    names = [binding.name for binding in result.bindings]
    assert names == sorted(names)
    assert set(names) == {"df", "pd", "table"}
    assert result.count == 3
    live = {binding.name: binding.exists_in_kernel for binding in result.bindings}
    assert live == {"df": True, "pd": False, "table": False}


def test_get_bindings_does_not_read_the_cells(ctx: _StubContext, service: _Service) -> None:
    """FR-022's whole point is that it is the cheap question."""
    _run(get_bindings())

    assert _asked(_focused(service), "cells") == []


# ---------------------------------------------------------------------------
# FR-023 — check_packaging and package_notebook
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Port:
    name: str
    direction: str
    data_type: str
    extension: str
    bound_name: str = ""


@dataclass(frozen=True)
class _Plan:
    cells: tuple[str, ...] = ()
    inputs: tuple[_Port, ...] = ()
    outputs: tuple[_Port, ...] = ()
    problems: tuple[PackagingProblem, ...] = ()

    @property
    def is_packageable(self) -> bool:
        return not any(problem.refuses for problem in self.problems)


@dataclass(frozen=True)
class _Packaged:
    block_name: str = "qc"
    class_name: str = "QcBlock"
    declaration_path: Path = Path("/project/blocks/qc.py")
    notebook_path: Path = Path("/project/blocks/qc.ipynb")
    notebook_commit: str = "abc123"
    cells: tuple[str, ...] = ("cell-a", "cell-b")
    inputs: tuple[_Port, ...] = ()
    outputs: tuple[_Port, ...] = ()
    on_new_input: str = "replay"
    problems: tuple[PackagingProblem, ...] = ()


def _refusal_problem() -> PackagingProblem:
    return PackagingProblem(
        kind=PackagingProblemKind.NO_DECLARED_OUTPUT,
        message="This notebook declares no scistudio.output, so there is nothing to package.",
    )


def test_check_packaging_returns_the_report(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.explore import packaging as packaging_module

    seen: dict[str, Any] = {}

    def _fake_check(document: Any, **kwargs: Any) -> _Plan:
        seen["document"] = document
        seen["kwargs"] = kwargs
        return _Plan(
            cells=("cell-a", "cell-b"),
            outputs=(_Port(name="table", direction="output", data_type="DataFrame", extension=".parquet"),),
        )

    monkeypatch.setattr(packaging_module, "check_packaging", _fake_check)

    result = _run(check_packaging())

    session = _focused(service)
    assert seen["document"] is session.document
    assert set(seen["kwargs"]) == {"marks", "bindings", "observations", "file_ports"}
    assert seen["kwargs"]["bindings"] == {"df": "DataFrame"}
    assert _asked(session, "wait_until_idle") == [tools_explore_pkg.tools.QUEUE_DRAIN_TIMEOUT]
    assert result.is_packageable is True
    assert result.cells == ["cell-a", "cell-b"]
    assert result.outputs[0].name == "table"
    assert result.notebook_commit == "abc123"


def test_check_packaging_refuses_rather_than_answering_from_marks_that_are_not_final(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.explore import packaging as packaging_module

    def _never_called(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - must not run
        raise AssertionError("packaging was checked before the queue drained")

    monkeypatch.setattr(packaging_module, "check_packaging", _never_called)
    _focused(service).drains = False

    result = _run(check_packaging(timeout_seconds=1.0))

    assert result.is_packageable is False
    assert result.problems[0].kind == "queue_not_drained"
    assert result.problems[0].refuses is True


def test_package_notebook_returns_the_block_id(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.explore import packaging as packaging_module

    seen: dict[str, Any] = {}

    def _fake_package(document: Any, **kwargs: Any) -> _Packaged:
        seen["document"] = document
        seen["kwargs"] = kwargs
        return _Packaged()

    monkeypatch.setattr(packaging_module, "package_notebook", _fake_package)

    result = _run(package_notebook(block_name="qc"))

    assert seen["kwargs"]["block_name"] == "qc"
    assert seen["kwargs"]["notebook_commit"] == "abc123"
    assert seen["kwargs"]["project_dir"] == service.project_dir
    assert result.packaged is True
    assert result.block_id == "QcBlock"
    assert result.block_name == "qc"
    assert result.cells == ["cell-a", "cell-b"]
    assert result.refusal is None
    # FR-057: the person sees a block the agent packaged through their own event.
    assert [str(event.type) for event in service.events] == ["packaged"]


def test_package_notebook_returns_the_report_when_packaging_is_refused(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-023: a refusal is the report, not an exception."""
    from scistudio.explore import packaging as packaging_module

    problem = _refusal_problem()

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise PackagingRefusedError([problem])

    monkeypatch.setattr(packaging_module, "package_notebook", _refuse)

    result = _run(package_notebook(block_name="qc"))

    assert result.packaged is False
    assert result.block_id is None
    assert [entry.message for entry in result.problems] == [problem.message]
    assert result.problems[0].refuses is True
    assert result.refusal is not None
    assert service.events == []


def test_package_notebook_refuses_a_notebook_that_has_never_run(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.explore import packaging as packaging_module

    def _never_called(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - must not run
        raise AssertionError("packaged a notebook with no commit")

    monkeypatch.setattr(packaging_module, "package_notebook", _never_called)
    _focused(service).notebook_commit = None

    result = _run(package_notebook(block_name="qc"))

    assert result.packaged is False
    assert result.problems[0].kind == "no_notebook_commit"
    assert "Run a cell first" in result.problems[0].message


def test_package_notebook_returns_an_invalid_argument_as_a_refusal(
    ctx: _StubContext, service: _Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.explore import packaging as packaging_module

    def _reject(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("on_new_input must be 'replay' or 'ask', not 'maybe'.")

    monkeypatch.setattr(packaging_module, "package_notebook", _reject)

    result = _run(package_notebook(block_name="qc", on_new_input="maybe"))

    assert result.packaged is False
    assert result.problems[0].kind == "invalid_argument"


# ---------------------------------------------------------------------------
# FR-005 — the focus, the explicit path, and the refusal
# ---------------------------------------------------------------------------


#: Every tool that acts on a session. ``open_explore_session`` is deliberately
#: absent: it creates one, so it neither needs a focus nor may move it.
FOCUSED_TOOLS: tuple[tuple[str, Any, dict[str, Any]], ...] = (
    ("read_notebook", read_notebook, {}),
    ("append_cell", append_cell, {"source": "x = 1"}),
    ("run_cell", run_cell, {"cell_id": "cell-b"}),
    ("get_bindings", get_bindings, {}),
    ("check_packaging", check_packaging, {}),
    ("package_notebook", package_notebook, {"block_name": "qc"}),
)


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=[entry[0] for entry in FOCUSED_TOOLS])
def test_every_session_tool_acts_on_the_focused_session(
    ctx: _StubContext, service: _Service, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    _run(tool(**kwargs))

    assert ("open_notebook", NOTEBOOK) in service.calls


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=[entry[0] for entry in FOCUSED_TOOLS])
def test_an_explicit_session_path_wins_over_the_focus(
    ctx: _StubContext, service: _Service, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    _run(tool(session_path=OTHER_NOTEBOOK, **kwargs))

    assert ("open_notebook", OTHER_NOTEBOOK) in service.calls
    assert ("open_notebook", NOTEBOOK) not in service.calls


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=[entry[0] for entry in FOCUSED_TOOLS])
@pytest.mark.parametrize("mode", [MODE_CANVAS, MODE_PAUSE])
def test_every_session_tool_refuses_when_the_person_is_not_in_a_session(
    ctx: _StubContext, service: _Service, name: str, tool: Any, kwargs: dict[str, Any], mode: str
) -> None:
    ctx.workspace_focus = {"mode": mode, "workflow_id": "wf-1"}

    with pytest.raises(NoExploreSessionError) as refusal:
        _run(tool(**kwargs))

    assert "open_explore_session" in str(refusal.value)
    assert service.calls == []


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=[entry[0] for entry in FOCUSED_TOOLS])
def test_every_session_tool_refuses_a_stale_focus(
    ctx: _StubContext, service: _Service, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    """FR-004: the focused notebook is gone, so the focus names nothing to act on."""
    ctx.workspace_focus = {"mode": MODE_EXPLORE, "session_path": "explore/deleted.ipynb"}

    with pytest.raises(NoExploreSessionError) as refusal:
        _run(tool(**kwargs))

    message = str(refusal.value)
    assert "explore/deleted.ipynb" in message
    assert "stale" in message
    assert "open_explore_session" in message
    assert service.calls == []


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=[entry[0] for entry in FOCUSED_TOOLS])
def test_an_explicit_path_still_works_over_a_stale_focus(
    ctx: _StubContext, service: _Service, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    """FR-005's escape hatch: an explicit path is how the agent works elsewhere."""
    ctx.workspace_focus = {"mode": MODE_EXPLORE, "session_path": "explore/deleted.ipynb"}

    _run(tool(session_path=OTHER_NOTEBOOK, **kwargs))

    assert ("open_notebook", OTHER_NOTEBOOK) in service.calls


def test_a_session_tool_reloads_a_notebook_that_changed_on_disk(ctx: _StubContext, service: _Service) -> None:
    """The session API's own answer to an outside edit, before any tool reads."""
    _run(read_notebook())

    assert _focused(service).reloaded == 1


# ---------------------------------------------------------------------------
# FR-024 — the structural assertion
# ---------------------------------------------------------------------------


PACKAGE_ROOT = Path(tools_explore_pkg.__file__).resolve().parent

#: What a session tool may import from SciStudio, at any depth and in any scope.
#: ``scistudio.explore.session`` is the session API and
#: ``scistudio.explore.packaging`` is the packaging seam FR-056 names, called
#: with the session's own marks, bindings and observations exactly as
#: ``api/routes/explore.py`` calls it. Nothing else in ``scistudio.explore`` is
#: a tool's to reach.
ALLOWED_SCISTUDIO_IMPORTS = frozenset(
    {
        "scistudio.explore.session",
        "scistudio.explore.packaging",
        "scistudio.core.metadata_store",
        "scistudio.core.versioning.git_engine",
    }
)

#: The three FR-024 names the rule is about, plus the two modules that would be
#: the way to reach them. Named separately from the allowlist so the intent
#: survives someone widening the allowlist for an unrelated reason.
FORBIDDEN_IMPORTS = frozenset(
    {
        "scistudio.explore.kernel",
        "scistudio.explore.kernel_bridge",
        "scistudio.explore.queue",
        "scistudio.explore.notebook",
        "scistudio.explore.notebook_api",
    }
)

#: Attributes that reach the kernel, the notebook file, or the queue *through*
#: a session object, which no import would ever reveal. ``ExploreSession``
#: exposes ``queue``, ``kernel`` and ``bridge`` publicly, so FR-024 is only
#: enforceable if the call graph is checked as well as the import graph.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "queue",
        "kernel",
        "bridge",
        "_queue",
        "_kernel",
        "_bridge",
        "_store",
        "_document",
        "start_kernel",
        "stop_kernel",
        "restart_kernel",
        "report_kernel_died",
        "interrupt",
        "stripped_notebook",
        "note_branch_commit",
        "note_explore_commit",
    }
)


def _package_modules() -> list[Path]:
    modules = sorted(PACKAGE_ROOT.rglob("*.py"))
    assert modules, "the session tool package has no modules to check"
    return modules


def _imported_modules(tree: ast.AST, module_name: str) -> set[str]:
    """Every module name imported anywhere in *tree*, function bodies included."""
    found: set[str] = set()
    package = module_name.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                found.add(f"{base}.{node.module}" if node.module else base)
            elif node.module:
                found.add(node.module)
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_no_session_tool_reaches_past_the_session_api() -> None:
    """FR-024, asserted structurally over the whole package at every depth.

    A shortcut past the session API would be written as a lazy import inside a
    function body — that is the only place it would look natural — so the walk
    covers every scope rather than only module scope.
    """
    offenders: dict[str, set[str]] = {}
    for path in _package_modules():
        module_name = "scistudio.ai.agent.mcp.tools_explore" + ("" if path.name == "__init__.py" else f".{path.stem}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = _imported_modules(tree, module_name)
        scistudio_imports = {
            name for name in imported if name.startswith("scistudio.") and not name.startswith("scistudio.ai.agent.mcp")
        }
        # A ``from X import Y`` records both ``X`` and ``X.Y``; keep the ones
        # that are not covered by an allowed module or one of its members.
        bad = {
            name
            for name in scistudio_imports
            if name not in ALLOWED_SCISTUDIO_IMPORTS
            and not any(name.startswith(f"{allowed}.") for allowed in ALLOWED_SCISTUDIO_IMPORTS)
        }
        if bad:
            offenders[path.name] = bad

    assert offenders == {}, (
        f"FR-024: these session tool modules import outside the session API: {offenders}. "
        f"A session tool goes through the session API and reaches neither the kernel, the notebook file, "
        f"nor the queue."
    )


def test_no_session_tool_module_imports_the_kernel_the_notebook_file_or_the_queue() -> None:
    """The same rule stated as FR-024 states it, so the intent is legible."""
    for path in _package_modules():
        module_name = "scistudio.ai.agent.mcp.tools_explore" + ("" if path.name == "__init__.py" else f".{path.stem}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = _imported_modules(tree, module_name)
        assert not (imported & FORBIDDEN_IMPORTS), f"{path.name} imports {sorted(imported & FORBIDDEN_IMPORTS)}"


def test_no_session_tool_reaches_the_kernel_or_the_queue_through_a_session_object() -> None:
    """``ExploreSession.queue`` is public, so the import graph alone is not enough."""
    offenders: dict[str, set[str]] = {}
    for path in _package_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        reached = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES
        }
        if reached:
            offenders[path.name] = reached

    assert offenders == {}, (
        f"FR-024: these session tool modules reach past the session API through an attribute: {offenders}. "
        f"Every execution passes through the session service; a tool that reached its queue, kernel or "
        f"notebook store would be a second door."
    )


def test_the_session_tools_hold_the_service_in_one_place() -> None:
    """One module owns the reference, so FR-024 has one place to be checked."""
    holders = set()
    for path in _package_modules():
        text = path.read_text(encoding="utf-8")
        if "SessionService" in text and path.name != "__init__.py":
            holders.add(path.name)
    assert holders == {"_service.py"}, f"the session service is constructed in {sorted(holders)}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_the_seven_session_tools_are_registered_under_one_category() -> None:
    tools = _run(mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) >= SESSION_TOOL_NAMES, f"missing: {sorted(SESSION_TOOL_NAMES - set(by_name))}"
    tagged = {tool.name for tool in tools if "category:session" in (tool.tags or set())}
    assert tagged == SESSION_TOOL_NAMES


def test_every_write_class_session_tool_result_carries_a_next_step() -> None:
    """ADR-040 §3.2, which ``test_mcp_fastmcp.py`` asserts across every group."""
    models = {
        "open_explore_session": _models.OpenExploreSessionResult,
        "append_cell": _models.AppendCellResult,
        "run_cell": _models.RunCellResult,
        "package_notebook": _models.PackageNotebookResult,
    }
    assert set(models) == WRITE_CLASS
    for name, model in models.items():
        assert "next_step" in model.model_fields, f"{name}: result model missing next_step"


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def test_a_binary_output_is_reported_by_mime_type_rather_than_by_value(ctx: _StubContext, service: _Service) -> None:
    """An agent cannot look at a PNG, and its base64 would cost it the notebook."""
    _focused(service)._cells[1].outputs = (
        MappingProxyType(
            {
                "output_type": "display_data",
                "data": {"image/png": "iVBORw0KGgo" * 5000, "text/plain": "<Figure size 640x480>"},
            }
        ),
    )

    result = _run(read_notebook())

    output = next(cell for cell in result.cells if cell.cell_id == "cell-b").outputs[0]
    assert output.mime_types == ["image/png", "text/plain"]
    assert output.text == "<Figure size 640x480>"
    assert "iVBORw0KGgo" not in output.text


def test_a_long_output_is_bounded_and_says_so(ctx: _StubContext, service: _Service) -> None:
    _focused(service)._cells[1].outputs = (
        MappingProxyType({"output_type": "stream", "name": "stdout", "text": "x" * (_models.OUTPUT_TEXT_LIMIT + 500)}),
    )

    result = _run(read_notebook())

    output = next(cell for cell in result.cells if cell.cell_id == "cell-b").outputs[0]
    assert len(output.text) == _models.OUTPUT_TEXT_LIMIT
    assert output.truncated is True
