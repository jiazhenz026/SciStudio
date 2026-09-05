"""The session service: opening, listing, closing, committing, and the kernel list.

ADR-054 T-006 and T-016; FR-001 to FR-006, FR-014, FR-016, and FR-036 of
``docs/specs/adr-054-explore-session.md`` (#2240).

Two of these tests exist because of failures that only show up somewhere else,
long after the cause:

* the generated first cell carries ``import scistudio``, and the test that pins
  it runs the generated notebook through the **dependency analysis** rather than
  through a kernel. In a kernel the import is redundant — the bridge binds the
  name — so it looks like tidy-up waiting to happen. Take it away and packaging
  refuses the notebook an hour later, for an unresolved read, and it reads as a
  packaging bug;
* the branch-switch test asserts that each kernel **process** is gone, not that
  a flag was set. A flag is what a leak looks like from the inside.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psutil
import pytest

from scistudio.api import project_layout
from scistudio.core.lineage.record import BlockExecutionRecord, BlockIORow, DataObjectRow, RunRecord
from scistudio.core.lineage.store import LineageStore
from scistudio.core.versioning._commit_ops import _explore_session_ref
from scistudio.core.versioning.git_engine import GitEngine
from scistudio.explore.dependency_analysis import ANALYSIS_VERSION, analyse_cells, build_graph
from scistudio.explore.notebook import NotebookStore, read_notebook, write_notebook
from scistudio.explore.notebook_api import decode_artefact_reference
from scistudio.explore.session import (
    EXPLORE_DIR_NAME,
    BoundRun,
    CellMark,
    LineageBlockOutputResolver,
    NothingToExploreError,
    PortArtefact,
    SessionEventType,
    SessionService,
    UnknownSessionError,
    first_cell_source,
)

needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

_IDLE_TIMEOUT = 40.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``scistudio`` importable from a kernel started in the project directory.

    A source checkout reaches the interpreter through a *relative*
    ``PYTHONPATH=./src``, which stops resolving the moment a process starts
    somewhere else — and the session deliberately starts its kernel in the
    project, because that is where a notebook's relative paths are read from.
    """
    import scistudio

    root = Path(scistudio.__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    entries = [str(root), *(entry for entry in existing.split(os.pathsep) if entry)]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(entries))


@pytest.fixture
def services(tmp_path: Path, project_pythonpath: None) -> Iterator[Callable[..., SessionService]]:
    """Hand out session services and guarantee every kernel they started is gone."""
    made: list[SessionService] = []

    def make(project_dir: Path | None = None, **kwargs: object) -> SessionService:
        service = SessionService(project_dir or tmp_path, **kwargs)  # type: ignore[arg-type]
        made.append(service)
        return service

    try:
        yield make
    finally:
        for service in made:
            pids = [listing.status.pid for listing in service.kernels()]
            with contextlib.suppress(Exception):
                service.shutdown()
            for pid in pids:
                if pid is not None:
                    _kill_if_alive(pid)


def _kill_if_alive(pid: int) -> None:
    try:
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout=10)
    except psutil.Error:
        return


def _process_gone(pid: int, timeout: float = 10.0) -> bool:
    """Whether ``pid`` is no longer a running process.

    A zombie counts as gone. On POSIX a killed child keeps its pid until its
    parent reaps it, and until then ``pid_exists`` and ``Process.is_running``
    both answer ``True`` — psutil documents ``is_running`` as true for a
    zombie, because the entry is still in the process table. A test that kills
    a kernel out from under the session has no parent standing by to reap it,
    so on Linux this helper would spin for the whole timeout and report a dead
    kernel as alive. Windows has no zombie state, which is why the difference
    showed up only in CI.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        try:
            process = psutil.Process(pid)
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.Error:
            return True
        time.sleep(0.05)
    return False


def test_process_gone_counts_a_zombie_as_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A killed-but-unreaped child must read as gone, not as still running.

    This guards the helper rather than the product, because the helper is what
    was wrong: on POSIX every process the kernel tests kill directly stays in
    the process table as a zombie until something reaps it, and psutil reports
    a zombie as existing and running. Windows has no zombie state, so a helper
    that missed this passed locally and hung for its whole timeout in CI.
    """

    class _Zombie:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def is_running(self) -> bool:
            return True

        def status(self) -> str:
            return psutil.STATUS_ZOMBIE

    monkeypatch.setattr(psutil, "pid_exists", lambda pid: True)
    monkeypatch.setattr(psutil, "Process", _Zombie)

    started = time.monotonic()
    assert _process_gone(4242, timeout=5.0) is True
    assert time.monotonic() - started < 1.0, "a zombie must be recognised at once, not waited out"


class _StubResolver:
    """A resolver over ports a test states directly, with no lineage behind it."""

    def __init__(self, bound: BoundRun | None) -> None:
        self._bound = bound

    def latest_block_outputs(self, block_id: str) -> BoundRun | None:
        return self._bound

    def run_block_outputs(self, run_id: str, block_id: str) -> BoundRun | None:
        return self._bound

    def paused_run_inputs(self, run_id: str, block_id: str) -> BoundRun | None:
        return self._bound


def _bound_run(*ports: str) -> BoundRun:
    return BoundRun(
        run_id="run-1",
        block_id="clean",
        opened_over="block_outputs",
        ports=tuple(
            PortArtefact(name=port, type_name="DataFrame", backend="parquet", path=f"data/parquet/{port}.parquet")
            for port in ports
        ),
    )


# ---------------------------------------------------------------------------
# FR-001, A-003: the explore directory joins the project layout
# ---------------------------------------------------------------------------


def test_the_explore_directory_is_created_with_every_new_project() -> None:
    """A-003: session notebooks live in ``{project}/explore/``."""
    assert project_layout.EXPLORE_DIR_NAME in project_layout.PROJECT_SUBDIRS


def test_the_explore_directory_is_spelled_the_same_in_both_layers() -> None:
    """The two spellings cannot drift, because the explore subsystem must not import the API.

    ``project_layout`` imports its drop-in names from ``core.dropins`` rather
    than respelling them, and says why. It cannot do that here: FR-008 forbids
    ``explore`` importing ``api``, and importing the session service into
    ``project_layout`` would make ``scistudio init`` — a fast mkdir command —
    pay for ``jupyter_client``. This assertion is what replaces the import.
    """
    assert project_layout.EXPLORE_DIR_NAME == EXPLORE_DIR_NAME


# ---------------------------------------------------------------------------
# FR-004: the generated first cell
# ---------------------------------------------------------------------------


def test_the_first_cell_names_every_output_port(services: Callable[..., SessionService]) -> None:
    """FR-004 and US1 scenario 1: one load line per port, the variable named after it."""
    service = services(block_outputs=_StubResolver(_bound_run("signal", "table")))
    session = service.open_over_block_outputs("clean")
    source = session.cells()[0].source
    assert 'signal = scistudio.load(scistudio.input("signal"))' in source
    assert 'table = scistudio.load(scistudio.input("table"))' in source


def test_the_first_cell_of_a_file_session_loads_the_file_by_path(
    services: Callable[..., SessionService],
) -> None:
    """FR-004 and US1 scenario 5."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    assert 'signal = scistudio.load("data/raw/signal.csv")' in session.cells()[0].source


def test_the_generated_notebook_has_no_unresolved_read_for_scistudio(
    services: Callable[..., SessionService],
) -> None:
    """The import is load-bearing for **packaging**, not for the kernel.

    The bridge binds ``scistudio`` in the running kernel, so a notebook without
    the import explores perfectly well and the import looks redundant. The
    dependency analysis reads the *source*: with no import above it, every use
    of ``scistudio`` is an unresolved read, and FR-039 makes packaging refuse the
    whole notebook for it — at the very end, after an hour of the notebook
    working, looking exactly like a packaging bug.

    This runs the generated notebook through the analysis, which is the world
    where the import matters. If someone tidies it away, this fails here rather
    than in packaging.
    """
    service = services(block_outputs=_StubResolver(_bound_run("signal")))
    session = service.open_over_block_outputs("clean")
    cells = [(cell.cell_id or "", cell.source) for cell in session.cells()]
    graph = build_graph(analyse_cells(cells))
    unresolved = {read.name for read in graph.unresolved_reads}
    assert "scistudio" not in unresolved, f"the generated first cell leaves unresolved reads: {unresolved}"
    assert unresolved == set(), f"the generated notebook must analyse clean; got {unresolved}"


def test_a_port_name_that_is_not_an_identifier_still_yields_a_bindable_variable() -> None:
    """A port name is normally an identifier; the generated cell must run when it is not."""
    bound = BoundRun(
        run_id="r",
        block_id="b",
        opened_over="block_outputs",
        ports=(PortArtefact(name="raw table", type_name="DataFrame", backend="parquet", path="p.parquet"),),
    )
    source = first_cell_source(bound_run=bound)
    assert 'raw_table = scistudio.load(scistudio.input("raw table"))' in source
    compile(source, "<first-cell>", "exec")


def test_the_first_cell_does_not_run_when_a_session_opens(
    services: Callable[..., SessionService],
) -> None:
    """FR-004 and US1 scenario 1: 'no kernel is started'."""
    service = services(block_outputs=_StubResolver(_bound_run("signal")))
    session = service.open_over_block_outputs("clean")
    assert session.has_kernel is False
    assert session.kernel_status() is None
    assert service.kernels() == ()
    assert session.marks(session.cells()[0].cell_id or "") == {CellMark.NEVER_RUN}


def test_the_notebook_on_disk_carries_the_analysis_record(
    services: Callable[..., SessionService],
) -> None:
    """The analysis spec's FR-031 is a MUST, and nothing wrote it (#2240 sweep).

    *"The per-cell record MUST be stored under the ``scistudio`` key of the
    cell's metadata ... A notebook-level record under the same key MUST hold the
    analysis version."* Its FR-034 says whose job that is: *"Loading and saving
    the notebook file is the explore-session spec's."*

    The codec was complete on both sides and **neither half had a production
    caller** — ``encode_cell_record``, ``encode_notebook_record`` and
    ``NotebookDocument.set_analysis_record`` were reachable only from tests — so
    no notebook ever carried a record, and this spec's FR-032 ("the record MUST
    be preserved by every write") was true only because there was never a record
    to lose.

    Asserted against the bytes on disk, because "stored in cell metadata" is a
    claim about the file rather than about the in-memory document.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    session.set_cell_source(session.cells()[0].cell_id or "", "import scistudio\nsignal = 1\n")
    session.write()

    written = read_notebook(Path(session.notebook_path))
    record = written.cells[0].scistudio_metadata
    assert record["source_hash"], "the cell carries no analysis record"
    assert "signal" in record["assigned"], "the record does not describe the cell it is attached to"
    assert "edges" not in record, "analysis FR-032: edges must not be stored"
    assert written.scistudio_metadata["analysis_version"] == ANALYSIS_VERSION


def test_storing_the_record_leaves_the_enabled_flag_and_a_foreign_key_alone(
    services: Callable[..., SessionService],
) -> None:
    """Analysis FR-033: keys the analysis does not recognise survive a rewrite.

    The enabled flag (FR-033 of this spec) lives in the same ``scistudio``
    namespace as the record, so a writer that replaced the namespace rather than
    merging into it would silently re-enable every disabled cell.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    cell_id = session.cells()[0].cell_id or ""
    session.set_cell_enabled(cell_id, enabled=False)

    document = session.document
    document.set_analysis_record(cell_id, {"vendor_x": {"keep": "me"}})
    session.set_cell_source(cell_id, "import scistudio\nreanalysed = 1\n")
    session.write()

    namespace = read_notebook(Path(session.notebook_path)).cells[0].scistudio_metadata
    assert namespace["enabled"] is False, "storing the record re-enabled a disabled cell"
    assert namespace["vendor_x"] == {"keep": "me"}, "another tool's key under the same namespace was dropped"
    assert "reanalysed" in namespace["assigned"]


# ---------------------------------------------------------------------------
# FR-002: refusal when there is nothing to explore
# ---------------------------------------------------------------------------


def test_opening_over_a_block_with_no_outputs_is_refused(services: Callable[..., SessionService]) -> None:
    """FR-002 and US1 scenario 2: refused with a message saying there is nothing to explore."""
    service = services(block_outputs=_StubResolver(None))
    with pytest.raises(NothingToExploreError, match="nothing to explore"):
        service.open_over_block_outputs("never-run")
    assert service.sessions() == ()
    assert not (service.explore_dir / "never-run.ipynb").exists()


def test_opening_over_a_block_whose_run_recorded_no_ports_is_refused(
    services: Callable[..., SessionService],
) -> None:
    """A run that produced no output edges is 'nothing to explore' just the same."""
    empty = BoundRun(run_id="r", block_id="b", opened_over="block_outputs", ports=())
    service = services(block_outputs=_StubResolver(empty))
    with pytest.raises(NothingToExploreError):
        service.open_over_block_outputs("b")


def test_a_service_with_no_resolver_says_so_rather_than_pretending(
    services: Callable[..., SessionService],
) -> None:
    service = services()
    with pytest.raises(NothingToExploreError, match="block_outputs or lineage_store"):
        service.open_over_block_outputs("clean")


def test_a_file_session_opens_even_when_the_file_is_missing(services: Callable[..., SessionService]) -> None:
    """Spec §2, edge cases: the notebook is the person's; the first cell fails, not the open."""
    service = services()
    session = service.open_over_file("data/raw/gone.csv")
    assert session.notebook_path.exists()


# ---------------------------------------------------------------------------
# FR-001: the session id, and one kernel per notebook
# ---------------------------------------------------------------------------


def test_the_session_id_is_written_into_the_notebook_and_read_back(
    services: Callable[..., SessionService],
) -> None:
    """FR-001: a random id in the metadata, so a path git refuses never reaches a ref."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    document = read_notebook(session.notebook_path)
    assert document.scistudio_metadata["session_id"] == session.session_id

    service.close(session, commit=False)
    reopened = service.open_notebook(session.notebook_path)
    assert reopened.session_id == session.session_id


def test_the_session_id_is_a_ref_safe_component(services: Callable[..., SessionService]) -> None:
    """FR-001: the id must survive ``git check-ref-format`` as one path component."""
    service = services()
    session = service.open_over_file("data/raw/a name with spaces.csv")
    ref = _explore_session_ref(session.session_id)
    assert ref == f"refs/scistudio/explore/{session.session_id}"


def test_opening_a_notebook_that_already_has_a_session_returns_that_session(
    services: Callable[..., SessionService],
) -> None:
    """FR-001: a notebook has at most one kernel, so a second open is the first session."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    again = service.open_notebook(session.notebook_path)
    assert again is session


def test_two_sessions_over_the_same_block_get_different_notebooks(
    services: Callable[..., SessionService],
) -> None:
    """A second exploration of the same block is a second notebook, not a collision."""
    service = services(block_outputs=_StubResolver(_bound_run("signal")))
    first = service.open_over_block_outputs("clean")
    second = service.open_over_block_outputs("clean")
    assert first.notebook_path != second.notebook_path
    assert first.session_id != second.session_id


def test_the_bound_run_reaches_the_kernel_as_artefact_references(
    services: Callable[..., SessionService],
) -> None:
    """FR-003, FR-010: ``scistudio.input`` resolves to the bound run's port artefact."""
    service = services(block_outputs=_StubResolver(_bound_run("signal")))
    session = service.open_over_block_outputs("clean")
    inputs = session.bound_run.inputs()
    type_name, reference = decode_artefact_reference(inputs["signal"])
    assert type_name == "DataFrame"
    assert reference.path == "data/parquet/signal.parquet"


# ---------------------------------------------------------------------------
# FR-006: listing and closing
# ---------------------------------------------------------------------------


def test_listing_reports_every_notebook_and_whether_it_has_a_kernel(
    services: Callable[..., SessionService],
) -> None:
    """FR-006: every notebook in the explore directory, open or not."""
    service = services()
    open_session = service.open_over_file("data/raw/one.csv")
    closed = service.open_over_file("data/raw/two.csv")
    closed_path = closed.relative_path
    service.close(closed, commit=False)

    listings = {listing.notebook_path: listing for listing in service.list_sessions()}
    assert set(listings) == {open_session.relative_path, closed_path}
    assert listings[open_session.relative_path].is_open is True
    assert listings[open_session.relative_path].has_kernel is False
    assert listings[closed_path].is_open is False
    assert listings[closed_path].session_id is not None


def test_listing_reports_a_damaged_notebook_rather_than_failing(
    services: Callable[..., SessionService],
) -> None:
    """A file that is not a notebook is listed as unreadable; it does not take the list down."""
    service = services()
    service.explore_dir.mkdir(parents=True, exist_ok=True)
    (service.explore_dir / "broken.ipynb").write_text("{not json", encoding="utf-8")
    listings = {listing.notebook_path: listing for listing in service.list_sessions()}
    broken = listings[f"{EXPLORE_DIR_NAME}/broken.ipynb"]
    assert broken.readable is False
    assert broken.session_id is None


def test_closing_a_session_that_is_not_open_says_so(services: Callable[..., SessionService]) -> None:
    service = services()
    with pytest.raises(UnknownSessionError):
        service.close("explore/nothing.ipynb")


def test_closing_writes_the_notebook_and_forgets_the_session(
    services: Callable[..., SessionService],
) -> None:
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 1")
    service.close(session, commit=False)

    assert read_notebook(session.notebook_path).cell(first).source == "k = 1"
    assert service.sessions() == ()


def test_a_session_publishes_opened_and_closed_events(services: Callable[..., SessionService]) -> None:
    """FR-057: the events the frontend builds against, over whatever channel it is given."""
    service = services()
    seen: list[SessionEventType] = []
    service.subscribe(lambda event: seen.append(event.type))
    session = service.open_over_file("data/raw/signal.csv")
    service.close(session, commit=False)
    assert seen[0] is SessionEventType.SESSION_OPENED
    assert SessionEventType.SESSION_CLOSED in seen


# ---------------------------------------------------------------------------
# FR-005: reload on an external edit
# ---------------------------------------------------------------------------


def test_an_external_edit_reloads_the_cells_and_keeps_marks_by_cell_id(
    services: Callable[..., SessionService],
) -> None:
    """FR-005: marks survive by cell id; the kernel namespace is untouched."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    added = session.insert_cell("k = 2", after=first)

    # Someone edits the file in JupyterLab: same ids, different source.
    store = NotebookStore(session.notebook_path)
    document = store.read()
    document.set_cell_source(added, "k = 3")
    store.write(document)

    assert session.reload_if_changed() is True
    assert session.cell_source(added) == "k = 3"
    assert session.marks(added) == {CellMark.NEVER_RUN}
    assert session.reload_if_changed() is False


def test_the_session_does_not_reload_on_its_own_writes(services: Callable[..., SessionService]) -> None:
    """A-012: the session's own write must not look like somebody else's edit."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 9")
    assert session.reload_if_changed() is False


# ---------------------------------------------------------------------------
# The lineage-backed resolver (FR-003)
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> Iterator[LineageStore]:
    lineage_store = LineageStore(":memory:")
    yield lineage_store
    lineage_store.close()


def _seed_completed_run(
    store: LineageStore,
    *,
    run_id: str = "run-1",
    block_id: str = "clean",
    started_at: str = "2026-09-04T12:00:00+00:00",
    port: str = "table",
) -> str:
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id="wf",
            workflow_yaml_snapshot="id: wf\n",
            started_at=started_at,
            finished_at=started_at,
            status="completed",
            environment_snapshot={},
        )
    )
    execution_id = f"exec-{run_id}"
    store.insert_block_execution(
        BlockExecutionRecord(
            block_execution_id=execution_id,
            run_id=run_id,
            block_id=block_id,
            block_type="clean",
            block_version="1",
            block_config_resolved={},
            started_at=started_at,
            termination="completed",
        )
    )
    store.upsert_data_object(
        DataObjectRow(
            object_id=f"obj-{run_id}",
            type_name="DataFrame",
            wire_payload={"format": "parquet"},
            created_at=started_at,
            backend="parquet",
            storage_path=f"data/parquet/{run_id}.parquet",
            produced_by_execution=execution_id,
        )
    )
    store.insert_block_io(
        BlockIORow(
            block_execution_id=execution_id,
            direction="output",
            port_name=port,
            position=0,
            object_id=f"obj-{run_id}",
        )
    )
    return execution_id


def test_the_resolver_binds_the_most_recent_completed_run(store: LineageStore) -> None:
    """FR-003: the most recent completed run of that block, and it records which."""
    _seed_completed_run(store, run_id="old", started_at="2026-09-04T10:00:00+00:00")
    _seed_completed_run(store, run_id="new", started_at="2026-09-04T12:00:00+00:00")
    bound = LineageBlockOutputResolver(store).latest_block_outputs("clean")
    assert bound is not None
    assert bound.run_id == "new"
    assert [port.path for port in bound.ports] == ["data/parquet/new.parquet"]
    assert bound.ports[0].format == "parquet"


def test_the_resolver_answers_nothing_for_a_block_that_never_ran(store: LineageStore) -> None:
    """FR-002: 'a block whose outputs have never been produced'."""
    assert LineageBlockOutputResolver(store).latest_block_outputs("never") is None


def test_the_resolver_reads_a_paused_run_s_inputs(store: LineageStore) -> None:
    """FR-002: a session over the inputs of a run paused at an interactive block."""
    execution_id = _seed_completed_run(store, run_id="paused")
    store.insert_block_io(
        BlockIORow(
            block_execution_id=execution_id,
            direction="input",
            port_name="incoming",
            position=0,
            object_id="obj-paused",
        )
    )
    bound = LineageBlockOutputResolver(store).paused_run_inputs("paused", "clean")
    assert bound is not None
    assert bound.opened_over == "paused_run"
    assert [port.name for port in bound.ports] == ["incoming"]


def test_a_service_built_with_a_lineage_store_resolves_ports_through_it(
    services: Callable[..., SessionService], store: LineageStore
) -> None:
    _seed_completed_run(store)
    service = services(lineage_store=store)
    session = service.open_over_block_outputs("clean")
    assert 'table = scistudio.load(scistudio.input("table"))' in session.cells()[0].source


# ---------------------------------------------------------------------------
# FR-036: the branch commit
# ---------------------------------------------------------------------------


@pytest.fixture
def repository(tmp_path: Path) -> GitEngine:
    """A throwaway repository with one commit, standing in for a project."""
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "workflow.json").write_text('{"blocks": []}\n', encoding="utf-8")
    engine = GitEngine(repo)
    engine.init_repository(repo)
    return engine


def test_committing_to_the_branch_writes_the_notebook_with_outputs_stripped(
    services: Callable[..., SessionService], repository: GitEngine
) -> None:
    """FR-036: one commit on the branch, carrying the notebook the person can read."""
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    sha = service.commit_to_branch(session)
    assert sha is not None

    listed = repository._run(["ls-tree", "-r", "--name-only", "HEAD"]).stdout
    assert session.relative_path in listed


def test_closing_commits_only_when_the_notebook_changed_since_the_last_commit(
    services: Callable[..., SessionService], repository: GitEngine
) -> None:
    """FR-006: 'if the notebook changed since the last branch commit'."""
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    service.commit_to_branch(session)
    head = repository._run(["rev-parse", "HEAD"]).stdout.strip()

    assert session.has_uncommitted_changes() is False
    assert service.close(session) is None
    assert repository._run(["rev-parse", "HEAD"]).stdout.strip() == head


def test_closing_a_changed_notebook_writes_one_branch_commit(
    services: Callable[..., SessionService], repository: GitEngine
) -> None:
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    before = repository._run(["rev-list", "--count", "HEAD"]).stdout.strip()
    sha = service.close(session)
    assert sha is not None
    after = repository._run(["rev-list", "--count", "HEAD"]).stdout.strip()
    assert int(after) == int(before) + 1


def test_a_service_with_no_git_engine_commits_nothing_and_still_closes(
    services: Callable[..., SessionService],
) -> None:
    """A project with no repository still explores; it just keeps no history."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    assert service.commit_to_branch(session) is None
    assert service.close(session) is None


# ---------------------------------------------------------------------------
# T-016, FR-014, FR-016: the kernel list and branch-switch retirement
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_every_live_kernel_is_listed_with_its_session_and_its_memory(
    services: Callable[..., SessionService],
) -> None:
    """FR-016 and US7 scenario 1."""
    service = services()
    first = service.open_over_file("data/raw/one.csv")
    second = service.open_over_file("data/raw/two.csv")
    first.start_kernel()
    second.start_kernel()

    listings = {listing.session_id: listing for listing in service.kernels()}
    assert set(listings) == {first.session_id, second.session_id}
    for listing in listings.values():
        assert listing.status.pid is not None
        assert listing.status.memory_bytes is not None and listing.status.memory_bytes > 0
        assert listing.notebook_path.startswith(f"{EXPLORE_DIR_NAME}/")


@needs_kernel
@pytest.mark.serial
def test_ending_a_kernel_from_the_list_terminates_its_process(
    services: Callable[..., SessionService],
) -> None:
    """FR-016 and US7 scenario 2: the process, not a flag."""
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    pid = session.kernel_status().pid
    assert pid is not None

    service.end_kernel(session.relative_path)
    assert _process_gone(pid), f"the kernel process {pid} outlived end_kernel"
    assert service.kernels() == ()
    assert session.has_kernel is False


@needs_kernel
@pytest.mark.serial
def test_a_branch_change_retires_every_kernel(services: Callable[..., SessionService]) -> None:
    """FR-014 and US7 scenario 3, asserted on the processes.

    A flag saying "retired" is exactly what a leaked kernel looks like from the
    inside, so this records each pid first and then asserts each one is gone.
    """
    service = services()
    sessions = [service.open_over_file(f"data/raw/{name}.csv") for name in ("one", "two", "three")]
    for session in sessions:
        session.start_kernel()
    pids = [session.kernel_status().pid for session in sessions]
    assert all(pid is not None for pid in pids)

    retired = service.retire_kernels()
    assert set(retired) == {session.session_id for session in sessions}
    for pid in pids:
        assert _process_gone(pid), f"the kernel process {pid} survived the branch change"
    assert service.kernels() == ()
    for session in sessions:
        assert session.needs_restart is True


@needs_kernel
@pytest.mark.serial
def test_a_branch_change_writes_every_notebook_before_the_kernels_go(
    services: Callable[..., SessionService],
) -> None:
    """FR-014: 'after writing every open notebook to disk' — nothing typed is lost."""
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "unsaved = 'typed just now'")

    service.retire_kernels()
    assert "unsaved = 'typed just now'" in read_notebook(session.notebook_path).cell(first).source


@needs_kernel
@pytest.mark.serial
def test_a_retired_session_restarts_and_runs_again(services: Callable[..., SessionService]) -> None:
    """US7: 'the sessions report that they need a restart' — and a restart works."""
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    service.retire_kernels()
    assert session.needs_restart is True

    session.restart_kernel()
    assert session.needs_restart is False
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 5")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.last_bound_by["k"] == first


@needs_kernel
@pytest.mark.serial
def test_shutting_the_service_down_leaves_no_kernel_behind(
    services: Callable[..., SessionService],
) -> None:
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    pid = session.kernel_status().pid
    assert pid is not None
    service.shutdown()
    assert _process_gone(pid)


# ---------------------------------------------------------------------------
# FR-027: what a run leaves in the notebook on disk
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_a_rerun_replaces_the_outputs_the_previous_run_left(
    services: Callable[..., SessionService],
) -> None:
    """FR-027: the file shows what the cell last printed, not everything it ever printed."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None

    session.set_cell_source(first, "print('the first run')")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    session.set_cell_source(first, "print('the second run')")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    text = "".join(
        str(output.get("text", "")) for cell in read_notebook(session.notebook_path).cells for output in cell.outputs
    )
    assert "the second run" in text
    assert "the first run" not in text, "the cell accumulated outputs instead of recording the run that just ended"


@needs_kernel
@pytest.mark.serial
def test_a_run_that_printed_nothing_leaves_the_outputs_it_found_alone(
    services: Callable[..., SessionService],
) -> None:
    """The rule the write-back follows, stated where a reader will look for it.

    FR-027 makes the file's outputs something the service **keeps** rather than
    something it owns: a cell may carry an output an editor put there, or one an
    earlier session left, and a silent run is not evidence that the person wants
    it gone. So a run records what it produced and a run that produced nothing
    records nothing — which is also what keeps the "the commit is stripped, the
    file is not" assertions of FR-028 able to fail.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "silent = 1")

    document = read_notebook(session.notebook_path)
    document.set_cell_outputs(
        first,
        [{"output_type": "stream", "name": "stdout", "text": "written by somebody else\n"}],
        execution_count=4,
    )
    write_notebook(session.notebook_path, document)
    assert session.reload_if_changed()

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    kept = read_notebook(session.notebook_path).cell(first).outputs
    assert [output["text"] for output in kept] == ["written by somebody else\n"]


# ---------------------------------------------------------------------------
# FR-028 to FR-030: the commit each cell run produces, off the execution path
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_each_cell_run_commits_to_the_session_ref_and_not_to_the_branch(
    services: Callable[..., SessionService], repository: GitEngine
) -> None:
    """FR-028 and FR-029, and US6 scenario 2: the branch log shows none of them."""
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 1")
    branch_head = repository._run(["rev-parse", "HEAD"]).stdout.strip()

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    ref = _explore_session_ref(session.session_id)
    assert repository._run(["rev-list", "--count", ref]).stdout.strip() == "1"
    assert repository._run(["rev-parse", "HEAD"]).stdout.strip() == branch_head
    assert session.notebook_commit is not None

    committed = repository._run(["show", f"{ref}:{session.relative_path}"]).stdout
    assert '"outputs": []' in committed or '"outputs":[]' in committed


@needs_kernel
@pytest.mark.serial
def test_a_failing_commit_is_reported_once_and_never_blocks_a_run(
    services: Callable[..., SessionService], repository: GitEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-030: retried off the execution path, and reported once when it will not go."""
    service = services(repository.project_path, git_engine=repository)
    reports: list[dict] = []
    service.subscribe(
        lambda event: reports.append(dict(event.payload)) if event.type is SessionEventType.COMMIT_RECORDED else None
    )
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 1")

    def refuse(*args: object, **kwargs: object) -> str:
        raise RuntimeError("the repository is locked")

    monkeypatch.setattr(repository, "commit_entries_to_ref", refuse)

    session.run_cell(first)
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT), "a failing commit must not block the queue"
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    failures = [report for report in reports if report.get("error")]
    assert len(failures) == 1, f"the failure must be reported once, not per run: {failures}"
    assert "locked" in failures[0]["error"]


@needs_kernel
@pytest.mark.serial
def test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart(
    services: Callable[..., SessionService],
) -> None:
    """FR-015 and US7 scenario 4, wired through the handle's death callback.

    The death is noticed the first time anything reads the kernel's state — here
    a status poll, which is what the kernel list does. The marks reset because
    the namespace they describe is gone, and nothing is re-run.
    """
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 5")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(first) == frozenset()

    pid = session.kernel_status().pid
    assert pid is not None
    psutil.Process(pid).kill()
    assert _process_gone(pid)

    assert session.kernel_status().state == "dead"
    assert session.needs_restart is True
    assert session.marks(first) == {CellMark.NEVER_RUN}
    assert session.last_bound_by == {}
    assert service.kernels() == ()
    assert session.queue.pending == ()

    session.restart_kernel()
    assert session.needs_restart is False
