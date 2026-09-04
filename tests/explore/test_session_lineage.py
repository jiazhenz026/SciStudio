"""The seam between the session service and the lineage it feeds (#2240).

``tests/explore/test_explore_lineage.py`` proves that
:class:`~scistudio.explore.lineage.ExploreLineage` writes what FR-051 to FR-055
ask for **when it is called**. These tests ask the other half of the question:
that a real :class:`~scistudio.explore.session.SessionService` calls it, and
that the rows it leaves behind are the ones
:func:`~scistudio.core.lineage.retention.plan_retention` reads.

The one that matters most is not about provenance. Retention refuses to sweep
while ``sessions_in_progress()`` is non-empty, so an unwritten anchor does not
merely lose a record — it lets the planner reclaim a live session's objects out
from under the person exploring. The mirror of that is a row left ``running``
by a process that died, which would block every sweep for ever; both directions
are pinned here.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from scistudio.core.lineage.record import ExploreSessionRecord, RunRecord
from scistudio.core.lineage.retention import plan_retention
from scistudio.core.lineage.store import LineageStore
from scistudio.core.versioning._commit_ops import _explore_session_ref
from scistudio.core.versioning.git_engine import GitEngine
from scistudio.explore.lineage import CELL_BLOCK_TYPE
from scistudio.explore.session import BoundRun, PortArtefact, SessionService

needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

_IDLE_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Iterator[LineageStore]:
    """An in-memory lineage store, closed after the services that used it."""
    opened = LineageStore(":memory:")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture
def project_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``scistudio`` importable from a kernel started in the project directory.

    A source checkout reaches the interpreter through a *relative*
    ``PYTHONPATH=./src``, which stops resolving the moment a process starts
    somewhere else — and the session deliberately starts its kernel in the
    project.
    """
    import scistudio

    root = Path(scistudio.__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    entries = [str(root), *(entry for entry in existing.split(os.pathsep) if entry)]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(entries))


@pytest.fixture
def services(tmp_path: Path, project_pythonpath: None) -> Iterator[Callable[..., SessionService]]:
    """Hand out session services and shut every one of them down.

    Shutdown runs *before* the ``store`` fixture closes, because a service that
    closes its session rows needs a store that is still open. Fixture teardown
    is last-in-first-out and ``store`` is requested first by every test here.
    """
    made: list[SessionService] = []

    def make(project_dir: Path | None = None, **kwargs: object) -> SessionService:
        service = SessionService(project_dir or tmp_path, **kwargs)  # type: ignore[arg-type]
        made.append(service)
        return service

    try:
        yield make
    finally:
        for service in reversed(made):
            service.shutdown()


@pytest.fixture
def repository(tmp_path: Path) -> GitEngine:
    """A throwaway repository with one commit, standing in for a project."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "workflow.json").write_text('{"blocks": []}\n', encoding="utf-8")
    engine = GitEngine(repo)
    engine.init_repository(repo)
    return engine


# ---------------------------------------------------------------------------
# FR-052: the anchor
# ---------------------------------------------------------------------------


def test_a_file_session_writes_its_anchor_with_the_notebook_it_opened(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """FR-052: the row parallels ``runs`` — path, content, how it was opened."""
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")

    row = store.get_explore_session(session.session_id)
    assert row is not None
    assert row["notebook_path"] == session.relative_path
    assert row["status"] == "running"
    assert row["opened_over"] == "file"
    assert row["bound_run_id"] is None
    assert session.relative_path.endswith(".ipynb")
    assert "scistudio.load" in row["notebook_snapshot"], "the snapshot is not the notebook that was opened"


def test_a_session_opened_over_a_run_records_the_run_it_was_opened_over(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """FR-052's ``bound_run_id``, the session-side counterpart of ``parent_run_id``."""
    store.insert_run(
        RunRecord(
            run_id="run-7",
            workflow_id="wf",
            workflow_yaml_snapshot="id: wf\n",
            started_at="2026-09-04T12:00:00+00:00",
            status="completed",
            environment_snapshot={},
        )
    )

    class _Resolver:
        def latest_block_outputs(self, block_id: str) -> BoundRun:
            return BoundRun(
                run_id="run-7",
                block_id=block_id,
                opened_over="block_outputs",
                ports=(PortArtefact(name="signal", type_name="Array", backend="zarr", path="signal"),),
            )

        def run_block_outputs(self, run_id: str, block_id: str) -> BoundRun | None:
            return None

        def paused_run_inputs(self, run_id: str, block_id: str) -> BoundRun | None:
            return None

    service = services(lineage_store=store, block_outputs=_Resolver())
    session = service.open_over_block_outputs("peaks")

    row = store.get_explore_session(session.session_id)
    assert row is not None
    assert (row["opened_over"], row["bound_run_id"]) == ("block_outputs", "run-7")


def test_closing_a_session_closes_its_row(store: LineageStore, services: Callable[..., SessionService]) -> None:
    """FR-052: a closed session is closed in the table, with a finish time."""
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    service.close(session)

    row = store.get_explore_session(session.session_id)
    assert row is not None
    assert row["status"] == "closed"
    assert row["finished_at"]
    assert not row["provenance_degraded"]


def test_a_service_without_a_lineage_store_opens_and_closes_regardless(
    services: Callable[..., SessionService],
) -> None:
    """A project with no lineage database still explores; it just records nothing."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    assert service.close(session) is None


# ---------------------------------------------------------------------------
# FR-055: what retention is told
# ---------------------------------------------------------------------------


def test_retention_is_blocked_while_a_session_is_open_and_released_when_it_closes(
    store: LineageStore, services: Callable[..., SessionService], tmp_path: Path
) -> None:
    """FR-055, read through the planner rather than through the store.

    ``plan_retention`` is what actually decides whether a session's objects are
    reclaimable, and the reason to assert against it rather than against
    ``sessions_in_progress()`` is that the guard is the point: an open session
    must block the sweep, and a closed one must stop blocking it.
    """
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")

    blocked = plan_retention(store, tmp_path)
    assert blocked.blocked_reason is not None
    assert "explore session" in blocked.blocked_reason

    service.close(session)
    released = plan_retention(store, tmp_path)
    assert released.blocked_reason != blocked.blocked_reason


def test_a_row_left_running_by_a_dead_process_is_closed_as_crashed(
    store: LineageStore, services: Callable[..., SessionService], tmp_path: Path
) -> None:
    """A session that ends by process death must not pin the planner for ever.

    Only :meth:`SessionService.close` closes a row, and a killed application
    never reaches it. The next service over the same project is the one that
    can tell: it is the sole owner of that project's sessions, so a row still
    ``running`` when it starts belonged to an owner that is gone.
    """
    store.insert_explore_session(
        ExploreSessionRecord(
            session_id="from-a-process-that-died",
            notebook_path="explore/signal.ipynb",
            notebook_snapshot="{}",
            started_at="2026-09-04T09:00:00+00:00",
            status="running",
        )
    )
    assert store.sessions_in_progress() == ["from-a-process-that-died"]

    services(lineage_store=store)

    assert store.sessions_in_progress() == []
    row = store.get_explore_session("from-a-process-that-died")
    assert row is not None
    assert row["status"] == "crashed", "a session lost to a crash must not read as a clean close"
    assert plan_retention(store, tmp_path).blocked_reason != (
        "1 explore session(s) still open; retention will not sweep while a session can still produce objects."
    )


# ---------------------------------------------------------------------------
# FR-053: the cell-run record
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_a_cell_run_records_the_commit_that_carries_the_notebook_it_ran(
    store: LineageStore, services: Callable[..., SessionService], repository: GitEngine
) -> None:
    """FR-053: the record's ``block_version`` is the commit of FR-028.

    Not the commit the notebook was at when the cell started — the commit that
    run produced, which is what makes the row reachable from the session's ref.
    It is written on the commit thread for that reason.
    """
    service = services(repository.project_path, git_engine=repository, lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "recorded = 1")

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    executions = store.list_session_block_executions(session.session_id)
    assert [row["block_id"] for row in executions] == [first]
    record = executions[0]
    assert record["block_type"] == CELL_BLOCK_TYPE
    assert record["run_id"] is None, "a cell run is anchored to the session, not to a run"
    assert record["termination"] == "completed"
    assert record["block_version"] == session.notebook_commit

    ref = _explore_session_ref(session.session_id)
    on_ref = repository._run(["rev-parse", ref]).stdout.strip()
    assert record["block_version"] == on_ref, "the record names a commit that is not on the session's ref"

    row = store.get_explore_session(session.session_id)
    assert row is not None
    assert row["notebook_git_commit"] == on_ref


@needs_kernel
@pytest.mark.serial
def test_a_cell_run_is_recorded_even_when_the_project_has_no_repository(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """The run happened; a project with no git engine writes no commit to name.

    A service built without one "runs and marks perfectly well and writes no
    history", and dropping the lineage row with the history would make a
    session's provenance depend on whether the person had run ``git init``.
    """
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "recorded = 1")

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    executions = store.list_session_block_executions(session.session_id)
    assert [row["block_id"] for row in executions] == [first]
    assert executions[0]["block_version"] == ""


@needs_kernel
@pytest.mark.serial
def test_a_cell_that_raised_is_recorded_as_an_error_with_its_message(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """FR-053's ``termination``: a failed cell is a record, not a missing one."""
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "raise ValueError('the cell said so')")

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    executions = store.list_session_block_executions(session.session_id)
    assert executions
    assert executions[0]["termination"] == "error"
    assert "the cell said so" in executions[0]["termination_detail"]


# ---------------------------------------------------------------------------
# A store that refuses does not stop the exploring
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FR-051: the blocks a cell called
# ---------------------------------------------------------------------------


#: A block and its registration, written where the session's kernel can import
#: it. The kernel is a separate process and cannot import this test module, and
#: the registry resolves a spec to ``module_path`` + ``class_name`` when it
#: instantiates, so the block has to live in a module importable under exactly
#: the name the spec records.
_PROBE_BLOCK_MODULE = '''
"""A block, its registration, and an adapter the kernel can resolve it through."""

from typing import Any, ClassVar

from scistudio.blocks.base import Block, BlockConfig, OutputPort
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types import Text
from scistudio.explore.block_call import BlockCallAdapter
from scistudio.explore.kernel_bridge import record_block_call_lineage, set_block_call_adapter


class Greeter(Block):
    """Returns its ``greeting`` configuration as a Text output."""

    name = "Greeter"
    version = "1.0.0"
    input_ports: ClassVar[list] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[Text])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the configured greeting."""
        return {"out": Text(content=config.get("greeting", "hello"))}


def install(session_id: str) -> None:
    """Register Greeter and install an adapter that reports to the session."""
    registry = BlockRegistry()
    spec = BlockSpec(
        name=Greeter.name,
        type_name=Greeter.name.lower(),
        version=Greeter.version,
        module_path=__name__,
        class_name=Greeter.__name__,
        base_category="process",
        input_ports=[],
        output_ports=list(Greeter.output_ports),
        execution_mode=Greeter.execution_mode.value,
    )
    registry._registry[spec.name] = spec
    registry._aliases[spec.type_name] = spec.name
    set_block_call_adapter(
        BlockCallAdapter(registry=registry, session_id=session_id, on_call=record_block_call_lineage)
    )
'''


def _install_probe_block(session: object, tmp_path: Path, cell_id: str) -> None:
    """Make ``blocks.run("Greeter", ...)`` resolvable in *session*'s kernel."""
    module_dir = tmp_path / "probe"
    module_dir.mkdir(exist_ok=True)
    (module_dir / "scistudio_probe_block.py").write_text(_PROBE_BLOCK_MODULE, encoding="utf-8")
    session.set_cell_source(  # type: ignore[attr-defined]
        cell_id,
        "import sys\n"
        f"sys.path.insert(0, {str(module_dir)!r})\n"
        "import scistudio_probe_block\n"
        f"scistudio_probe_block.install({session.session_id!r})",  # type: ignore[attr-defined]
    )
    session.run_cell(cell_id)  # type: ignore[attr-defined]
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)  # type: ignore[attr-defined]


@needs_kernel
@pytest.mark.serial
def test_a_block_a_cell_called_is_recorded_against_the_session(
    store: LineageStore, services: Callable[..., SessionService], tmp_path: Path
) -> None:
    """FR-051 end to end: a cell calls a block and a row exists afterwards (#2240).

    The adapter fires its hook *inside the kernel*, where there is no store to
    write to, so nothing about this works unless the session drains the kernel
    after the run and writes what comes back. Asserted through a real kernel
    and a real block rather than through the bridge alone, because the inline
    call a person writes never touches the bridge's own block-call action —
    which is the gap this closes.
    """
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    _install_probe_block(session, tmp_path, first)

    call_cell = session.insert_cell('greeting = blocks.run("Greeter", greeting="from a cell")', after=first)
    session.run_cell(call_cell)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    calls = [
        row for row in store.list_session_block_executions(session.session_id) if row["block_type"] != CELL_BLOCK_TYPE
    ]
    assert len(calls) == 1, f"the block call left {len(calls)} rows"
    record = calls[0]
    assert record["session_id"] == session.session_id, "FR-051's foreign key does not point at the session"
    assert record["run_id"] is None, "a call from a cell belongs to a session, not to a workflow run"
    assert record["block_id"] == call_cell, "the record does not name the cell that made the call"
    assert record["block_type"] == "greeter"
    assert record["block_version"] == "1.0.0"
    assert record["termination"] == "completed"

    edges = store.list_block_io(record["block_execution_id"])
    assert [(edge["direction"], edge["port_name"]) for edge in edges] == [("output", "out")]
    assert store.get_data_object(edges[0]["object_id"]) is not None, "the edge points at no data object"


@needs_kernel
@pytest.mark.serial
def test_a_cell_that_called_no_block_writes_no_call_record(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """The ordinary cell. A drain that invented a row would be worse than none."""
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "plain = 1 + 1")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    rows = store.list_session_block_executions(session.session_id)
    assert [row["block_type"] for row in rows] == [CELL_BLOCK_TYPE]


# ---------------------------------------------------------------------------
# FR-034: the environment every record names
# ---------------------------------------------------------------------------


def test_the_environment_store_sits_beside_the_lineage_database(
    services: Callable[..., SessionService], tmp_path: Path
) -> None:
    """FR-034's snapshots live where the project's other internal artefacts do.

    Not a new convention: ``.scistudio/`` already holds ``lineage.db`` — the
    database these snapshots are referenced *from* — as well as ``previews/``
    and ``logs/``, and it is already excluded from the project's file scans, so
    nothing here reaches the person's project tree or their commits.
    """
    service = services()

    assert service.environments.root == tmp_path / ".scistudio" / "environments"
    assert not service.environments.root.exists(), "the store wrote a directory before it held anything"


@needs_kernel
@pytest.mark.serial
def test_a_cell_run_names_the_environment_it_ran_in(
    store: LineageStore, services: Callable[..., SessionService]
) -> None:
    """FR-034: stored once per distinct environment, and referenced from records (#2240).

    ``environment_ref`` was ``None`` on every row: the store existed and nothing
    constructed it. A reference that names nothing is worse than no column,
    because a person reading the row cannot tell an unrecorded environment from
    an environment with nothing in it — so the reference is asserted to resolve,
    not merely to be non-null.
    """
    service = services(lineage_store=store)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "recorded = 1")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    rows = store.list_session_block_executions(session.session_id)
    assert rows, "the cell run left no record to carry a reference"
    reference = rows[0]["environment_ref"]
    assert reference, "the record names no environment"
    assert session.environment_ref == reference
    snapshot = service.environments.get(reference)
    assert snapshot is not None, "the reference names a snapshot the store does not hold"
    assert snapshot.python_version, "the stored snapshot describes no interpreter"


@needs_kernel
@pytest.mark.serial
def test_the_environment_of_a_second_session_is_stored_once(
    services: Callable[..., SessionService],
) -> None:
    """ "Stored once per distinct environment" (FR-034), asked of two kernels.

    Two sessions in one project run in the same environment, so the second
    capture must cost a hash and no second file — which is the whole reason the
    store is content-addressed rather than a snapshot per session.
    """
    service = services()
    first = service.open_over_file("data/raw/signal.csv")
    first.start_kernel()
    second = service.open_over_file("data/raw/other.csv")
    second.start_kernel()

    assert first.environment_ref == second.environment_ref
    assert len(service.environments.references()) == 1


def test_a_store_that_refuses_the_anchor_still_opens_the_session_and_says_so(
    services: Callable[..., SessionService], tmp_path: Path
) -> None:
    """The session's own docstring: a failed lineage write degrades, never refuses.

    :class:`~scistudio.explore.lineage.ExploreLineage` deliberately does not
    swallow store failures, so the service is where the decision lives — and the
    decision is that a person exploring keeps exploring, with the row saying its
    provenance is incomplete.
    """
    store = LineageStore(":memory:")
    service = services(lineage_store=store)
    store.close()  # every lineage write from here on raises

    session = service.open_over_file("data/raw/signal.csv")
    assert session.cells(), "a refused lineage write must not stop a session opening"
    assert service.close(session) is None
