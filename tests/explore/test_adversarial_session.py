"""Adversarial tests for the Explore Session runtime (ADR-054 spec 3, #2240).

These tests exist because eleven agents built this subsystem and every one of
them reported success. They were written the other way round: each one started
as a **behavioural mutation** of the production code that the delivered suite
did not notice, or as a claim in the spec that no test made against a real
process. Nothing here duplicates what
``tests/explore/test_queue_and_marks.py``, ``test_explore_session.py``,
``test_kernel_session.py``, or ``test_packaged_block.py`` already prove.

What is here, and why:

* **The six-cell fixture through the queue.** Spec §4.4 says the queue and the
  marks are tested "on the A, B, C fixture **and on the six-cell fixture** the
  dependency-analysis spec uses". The A, B, C fixture is covered. The six-cell
  fixture was only ever run through the *static* analysis
  (``test_dependency_analysis.py``), never through a kernel and a queue, so the
  one claim it carries that A, B, C cannot — that cell 5, the ``head()`` the
  person left in, is never enqueued by any control — was unproven.

* **The out-of-order mark for a name the kernel has never bound.** Running a
  downstream cell first, on a fresh kernel, is the most ordinary way to produce
  an out-of-order read: the graph names a definer, the kernel names nobody. The
  delivered suite covers ``definer == binder == None`` (an accumulator's first
  run) and ``definer != binder`` where both name a cell, but not the case in
  between; a mutation that skipped it survived the whole ``tests/explore`` run.

* **The kernel under adversity.** A kernel that never starts, a branch switch
  while a cell is executing, two sessions side by side, and the interrupt
  driven through :class:`~scistudio.explore.session.ExploreSession` rather than
  through :class:`~scistudio.explore.kernel.KernelHandle` — the object the API
  actually calls.

* **What a run leaves in git.** Not one commit but several, checked against
  ``git status``, the branch's log, and the branch's index, plus the promise of
  §4.1 that the commit carries the notebook *as captured at execution time*.

Every test that spawns a process carries the ``serial`` marker and registers
what it started with the ``services`` fixture, which reaps on the failure path
as well as the success path.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psutil
import pytest

from scistudio.core.versioning._commit_ops import _explore_session_ref
from scistudio.core.versioning.git_engine import GitEngine
from scistudio.explore.queue import ExecutionRequest
from scistudio.explore.session import CellMark, ExploreSession, SessionService

needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

#: Long enough that a loaded runner spawning a kernel does not flake.
_IDLE_TIMEOUT = 60.0

#: How long a test waits for a kernel-side marker file to prove a cell started.
_MARKER_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Hand out session services and guarantee every kernel they started is gone.

    Every pid is recorded *before* the shutdown, so a session that has already
    forgotten its process is still reaped, and anything that outlives a polite
    shutdown is killed. This runs on the failure path too, which is the point:
    a test that fails while a kernel is spinning must not leave it spinning.
    """
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
    """Kill ``pid`` if it somehow outlived the service that owned it."""
    try:
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout=10)
    except psutil.Error:
        return


def _process_gone(pid: int, timeout: float = 15.0) -> bool:
    """Whether ``pid`` is no longer a running process."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        try:
            if not psutil.Process(pid).is_running():
                return True
        except psutil.Error:
            return True
        time.sleep(0.05)
    return False


def _wait_for_marker(marker: Path, timeout: float = _MARKER_TIMEOUT) -> None:
    """Block until the kernel has proved it reached the code that writes *marker*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"the kernel never reached {marker}")


def _enqueued(action: Callable[[], object]) -> list[str]:
    """Every cell *action* enqueued, in the order it enqueued them."""
    requests = action()
    if isinstance(requests, ExecutionRequest):
        requests = (requests,)
    return [request.cell_id for request in requests]  # type: ignore[union-attr]


def _spin_after_marker(marker: Path) -> str:
    """A cell that announces itself and then spins with no yield point of its own."""
    return (
        "import pathlib\n"
        f"pathlib.Path({str(marker.as_posix())!r}).write_text('running', encoding='utf-8')\n"
        "while True:\n"
        "    pass\n"
    )


# ---------------------------------------------------------------------------
# FR-019: the out-of-order mark when the kernel has never bound the name
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_running_a_downstream_cell_first_is_marked_out_of_order(
    services: Callable[..., SessionService],
) -> None:
    """FR-019 for the case the delivered suite left between the two it covers.

    FR-019 compares the graph's definer with the kernel's last binder and marks
    when they *differ*. The suite covers ``None`` against ``None`` (an
    accumulator's first run, not marked) and one cell against another (the A, B,
    C re-run, marked). The case in between — a real definer against nobody,
    which is what running a downstream cell first on a fresh kernel produces —
    was not covered, and a mutation restricting the mark to a bound name
    survived the whole ``tests/explore`` run.

    The mark is true and it matters: the cell read a value the notebook's
    written order says the cell above produces, and the cell above has not run.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    upstream = session.cells()[0].cell_id
    assert upstream is not None
    session.set_cell_source(upstream, "df = [1, 2, 3]")
    downstream = session.insert_cell("total = sum(df)", after=upstream)

    session.run_cell(downstream)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert CellMark.OUT_OF_ORDER in session.marks(downstream), (
        "a cell that read a name no cell has bound in this kernel ran out of written order"
    )
    reasons = [(read.name, read.definer, read.last_binder) for read in session.out_of_order_reads(downstream)]
    assert reasons == [("df", upstream, None)], (
        "the reason must name the graph's definer and say that the kernel names nobody"
    )
    assert session.marks(upstream) == frozenset({CellMark.NEVER_RUN}), "nothing was run on the person's behalf"


@needs_kernel
@pytest.mark.serial
def test_the_upstream_cell_running_afterwards_clears_the_downstream_mark_only_on_a_rerun(
    services: Callable[..., SessionService],
) -> None:
    """FR-022: running the upstream marks the downstream stale; it does not un-mark it.

    The out-of-order mark records what *already happened*, so nothing the
    upstream cell does afterwards can make the downstream run have been in order. The
    downstream cell keeps both marks until it runs again.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    upstream = session.cells()[0].cell_id
    assert upstream is not None
    session.set_cell_source(upstream, "df = [1, 2, 3]")
    downstream = session.insert_cell("total = sum(df)", after=upstream)

    session.run_cell(downstream)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    session.run_cell(upstream)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert session.marks(downstream) == frozenset({CellMark.OUT_OF_ORDER, CellMark.STALE})

    session.run_cell(downstream)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(downstream) == frozenset(), "an in-order re-run clears both marks"


# ---------------------------------------------------------------------------
# Spec §4.4: the six-cell fixture, through a kernel and a queue
# ---------------------------------------------------------------------------

#: The six-cell notebook of User Story 2, in names a kernel started from the
#: bundled interpreter can bind without pandas or scipy: a load, a filter, an
#: in-place mutation, a peak finder, the ``head()`` the person left in, and the
#: output declaration. The shape is the one
#: ``tests/explore/test_dependency_analysis.py::STORY_TWO`` analyses statically
#: — cell 3 mutates in place, so only the *observation* makes it a definer, and
#: cell 5 reads and binds nothing, so it is never in the slice.
SIX_CELLS: tuple[str, ...] = (
    "rows = [1, 2, 3, 4, 5]",
    "rows = [value for value in rows if value > 2]",
    "rows.pop()",
    "peaks = max(rows)",
    "rows[:1]",
    "scistudio.output(peaks=peaks, table=rows)",
)


@pytest.fixture
def six_cell_session(
    services: Callable[..., SessionService],
) -> tuple[ExploreSession, tuple[str, ...]]:
    """The six-cell fixture in a real session, every cell run once in written order."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, SIX_CELLS[0])
    ids = [first]
    for source in SIX_CELLS[1:]:
        ids.append(session.insert_cell(source, after=ids[-1]))

    for cell_id in ids:
        session.run_cell(cell_id)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.questionable_cells() == (), "the fixture runs in written order, so nothing is marked"
    return session, tuple(ids)


@needs_kernel
@pytest.mark.serial
def test_the_six_cell_slice_excludes_the_cell_that_binds_nothing(
    six_cell_session: tuple[ExploreSession, tuple[str, ...]],
) -> None:
    """US2 scenario 1 through a live session, not through the static analysis alone.

    ``test_dependency_analysis.py`` proves this slice by *handing* the graph the
    observation ``{"c3": {"df"}}``. Here the observation is the one the kernel
    produced, so the assertion covers the fingerprint comparison and the
    last-bound-by bookkeeping as well as the slice.
    """
    session, ids = six_cell_session
    c1, c2, c3, c4, c5, c6 = ids

    assert session.graph.backward_slice([c6]).cells == (c1, c2, c3, c4, c6)
    assert c5 not in session.graph.backward_slice([c6]).cells, "the head() cell binds nothing, so nothing needs it"
    assert "rows" in session.graph.changed_set(c3), "the observation made the in-place cell a definer"
    assert session.graph.definer_for(c4, "rows") == c3
    assert session.last_bound_by["rows"] == c3


@needs_kernel
@pytest.mark.serial
def test_re_running_the_filter_marks_the_rest_and_enqueues_nothing(
    six_cell_session: tuple[ExploreSession, tuple[str, ...]],
) -> None:
    """FR-022 on the six-cell fixture, counted at the queue.

    Re-running cell 2 reads a ``rows`` cell 3 last bound, so cell 2 is out of
    order; everything below it is stale, including the ``head()`` cell, which
    reads ``rows`` even though nothing reads it. Not one of them is enqueued.
    """
    session, ids = six_cell_session
    c1, c2, c3, c4, c5, c6 = ids

    submitted: list[str] = []
    original = session.queue.submit_cell

    def watch(cell_id: str, **kwargs: object) -> object:
        submitted.append(cell_id)
        return original(cell_id, **kwargs)  # type: ignore[arg-type]

    session.queue.submit_cell = watch  # type: ignore[method-assign]
    try:
        session.run_cell(c2)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    finally:
        session.queue.submit_cell = original  # type: ignore[method-assign]

    assert submitted == [c2], f"the service enqueued cells nobody asked for: {submitted}"
    assert CellMark.OUT_OF_ORDER in session.marks(c2), "cell 2 read a rows that cell 3 last bound"
    assert session.stale_cells() == (c3, c4, c5, c6)
    assert session.marks(c1) == frozenset(), "nothing above the re-run is questionable"


@needs_kernel
@pytest.mark.serial
def test_run_with_upstream_on_the_output_cell_never_enqueues_the_head_cell(
    six_cell_session: tuple[ExploreSession, tuple[str, ...]],
) -> None:
    """FR-024 on the six-cell fixture: the slice, in written order, and only the slice.

    Cell 5 is stale after the re-run and it reads ``rows``, so a skip rule that
    walked the *downstream* set instead of the backward slice, or that seeded
    itself from the stale set, would run it here. It is not in the backward
    slice of the declared outputs and it must not run.
    """
    session, ids = six_cell_session
    c1, c2, c3, c4, c5, c6 = ids
    session.run_cell(c2)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    enqueued = _enqueued(lambda: session.run_with_upstream(c6))

    assert c5 not in enqueued, f"run-with-upstream ran the head() cell: {enqueued}"
    assert enqueued == [c1, c2, c3, c4, c6], f"run-with-upstream enqueued {enqueued}"
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(c6) == frozenset(), "the output cell is clean once its slice has re-run in order"


@needs_kernel
@pytest.mark.serial
def test_run_stale_on_the_six_cell_fixture_runs_the_head_cell_because_it_is_stale(
    six_cell_session: tuple[ExploreSession, tuple[str, ...]],
) -> None:
    """FR-024's two controls are not the same set, and this fixture is where they differ.

    Run-with-upstream is bounded by the backward slice and never touches cell 5.
    Run-stale is bounded by the marks, and cell 5 *is* stale, so it runs. A
    reading of the spec that made the two controls share one set would pass on
    the A, B, C fixture and fail here.
    """
    session, ids = six_cell_session
    _c1, c2, c3, c4, c5, c6 = ids
    session.run_cell(c2)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    enqueued = _enqueued(session.run_stale)

    assert enqueued == [c3, c4, c5, c6], f"run-stale enqueued {enqueued}"
    assert c2 not in enqueued, "cell 2 is out of order, not stale, and run-stale runs the stale set"


# ---------------------------------------------------------------------------
# FR-013 to FR-015: the kernel under adversity, through the session
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_the_interrupt_through_the_session_ends_a_hung_cell_and_keeps_the_namespace(
    services: Callable[..., SessionService],
    tmp_path: Path,
) -> None:
    """SC-005 and US2 scenario 6 against the object the API calls.

    ``tests/explore/test_kernel_session.py`` proves the interrupt on
    :class:`~scistudio.explore.kernel.KernelHandle`. The API never touches a
    handle: it calls :meth:`ExploreSession.interrupt`, which runs while the
    queue's worker thread is blocked inside ``handle.execute``. That is a
    different claim — that the interrupt is reachable from a thread the session
    is not holding a lock against — and the cell is a bare ``while True: pass``
    so that a kernel which merely *accepts* the interrupt cannot pass.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "survivor = 'alive'")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    status = session.kernel_status()
    assert status is not None
    pid = status.pid

    marker = tmp_path / "session-hung-cell"
    hung = session.insert_cell(_spin_after_marker(marker), after=first)
    session.run_cell(hung)
    _wait_for_marker(marker)

    started = time.monotonic()
    session.interrupt()
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT), "the interrupted cell never ended"
    elapsed = time.monotonic() - started

    assert elapsed < _IDLE_TIMEOUT, "the cell ended because it was interrupted, not because we gave up"
    after_status = session.kernel_status()
    assert after_status is not None
    assert after_status.pid == pid, "an interrupt is not a restart"
    assert not session.needs_restart, "an interrupt does not retire the kernel"
    assert session.last_bound_by.get("survivor") == first, "the namespace survived the interrupt"

    after = session.insert_cell("recovered = survivor", after=hung)
    session.run_cell(after)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.last_bound_by.get("recovered") == after, "the session still runs cells after an interrupt"


@needs_kernel
@pytest.mark.serial
def test_a_branch_switch_while_a_cell_is_running_leaves_no_process_behind(
    services: Callable[..., SessionService],
    tmp_path: Path,
) -> None:
    """FR-014 against the case a branch switch actually meets: a cell in flight.

    ``test_a_branch_change_retires_every_kernel`` retires idle kernels. A person
    switching branches while a cell spins is the case that can strand a process:
    the queue's worker is blocked inside ``execute`` on the very handle
    ``retire_kernels`` is stopping. The claim is that the process is gone, the
    session says it needs a restart, and the queue is still usable afterwards.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    marker = tmp_path / "retire-mid-cell"
    session.set_cell_source(first, _spin_after_marker(marker))

    session.run_cell(first)
    _wait_for_marker(marker)
    status = session.kernel_status()
    assert status is not None and status.pid is not None
    pid = status.pid

    retired = service.retire_kernels()

    assert session.session_id in retired
    assert _process_gone(pid), "a branch switch left a kernel running with no session to attribute it to"
    assert session.needs_restart, "the session must report that its kernel was retired underneath it"
    assert service.kernels() == (), "the kernel list must not report a process that is gone"
    assert session.queue.is_started, "the queue survives the kernel it was running on"

    session.set_cell_source(first, "recovered = 1")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT), "the session must run again after a retirement"
    assert session.last_bound_by.get("recovered") == first
    assert not session.needs_restart


@needs_kernel
@pytest.mark.serial
def test_two_sessions_hold_independent_kernels_and_ending_one_leaves_the_other(
    services: Callable[..., SessionService],
) -> None:
    """FR-016 and US7 scenario 2 with more than one kernel in the list.

    One session is the case where "end the kernel" cannot be told apart from
    "end every kernel". Two sessions bind the *same* name to different values,
    so a shared namespace would be caught as well as a shared process.
    """
    service = services()
    left = service.open_over_file("data/raw/left.csv")
    right = service.open_over_file("data/raw/right.csv")
    for session, value in ((left, "left"), (right, "right")):
        cell = session.cells()[0].cell_id
        assert cell is not None
        session.set_cell_source(cell, f"which = {value!r}")
        session.run_cell(cell)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    listings = {listing.session_id: listing for listing in service.kernels()}
    assert set(listings) == {left.session_id, right.session_id}
    pids = {listing.session_id: listing.status.pid for listing in listings.values()}
    assert pids[left.session_id] != pids[right.session_id], "two sessions must not share one process"
    assert all(listing.status.memory_bytes for listing in listings.values()), "each kernel reports its memory"

    left_pid = pids[left.session_id]
    assert left_pid is not None
    service.end_kernel(left.relative_path)

    assert _process_gone(left_pid)
    assert not left.has_kernel
    assert right.has_kernel, "ending one kernel must not end the other"
    assert [listing.session_id for listing in service.kernels()] == [right.session_id]

    cell = right.cells()[0].cell_id
    assert cell is not None
    still = right.insert_cell("still_here = which", after=cell)
    right.run_cell(still)
    assert right.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert right.last_bound_by.get("still_here") == still, "the surviving kernel kept its namespace"


@needs_kernel
@pytest.mark.serial
def test_a_kernel_that_never_starts_fails_the_run_and_leaves_the_session_usable(
    services: Callable[..., SessionService],
    tmp_path: Path,
) -> None:
    """FR-015's neighbour: the kernel that never came up in the first place.

    A run whose kernel cannot launch must end as a failed request rather than
    hanging the queue, must leave nothing in the kernel list, and must still
    have written the notebook — FR-027 puts that write *before* execution
    precisely so a start that never happened loses nothing typed.
    """
    service = services(python_executable=tmp_path / "no-such-interpreter")
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "value = 1")

    request = session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT), "a kernel that cannot start must not hang the queue"

    assert request.state.value == "failed", f"the request ended as {request.state}"
    assert request.error is not None
    assert type(request.error).__name__ == "KernelLaunchError"
    assert not session.has_kernel
    assert service.kernels() == (), "a kernel that never started must not appear in the list"
    assert "value = 1" in session.notebook_path.read_text(encoding="utf-8"), (
        "FR-027 writes the notebook before the run, so a failed start loses nothing typed"
    )
    assert session.marks(first) == frozenset({CellMark.NEVER_RUN}), "a run that never happened is not a run"
    assert session.queue.is_started, "the queue survives a kernel that could not start"


# ---------------------------------------------------------------------------
# FR-025: the freeze, at the session rather than at the queue
# ---------------------------------------------------------------------------


def _busy_cell(marker: Path, name: str = "df", seconds: float = 4.0) -> str:
    """A cell that announces itself, waits, and then binds *name*."""
    return (
        "import pathlib\n"
        "import time\n"
        f"pathlib.Path({str(marker.as_posix())!r}).write_text('running', encoding='utf-8')\n"
        f"time.sleep({seconds})\n"
        f"{name} = [1, 2, 3]\n"
    )


@needs_kernel
@pytest.mark.serial
def test_a_frozen_panel_is_refused_before_a_cell_is_inserted(
    services: Callable[..., SessionService],
    tmp_path: Path,
) -> None:
    """FR-025 and US3 scenario 4 through :meth:`ExploreSession.emit_snippet`.

    The delivered suite proves the freeze on :class:`ExecutionQueue`, which
    refuses at *submission* — by which point ``emit_snippet`` has already
    inserted the cell and has to take it out again in an exception handler. The
    session's own pre-insert guard exists so that never happens, and removing it
    left every test in ``tests/explore`` green.

    The event stream is what tells the two apart: FR-018 says no cell is
    inserted, and an ``analysis_updated`` event announcing ``cell_inserted``
    for a cell that is gone by the time the client reads it is a cell having
    been inserted.
    """
    from scistudio.explore.queue import PanelFrozenError
    from scistudio.explore.session import SessionEvent, SessionEventType

    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    marker = tmp_path / "freeze-running"
    session.set_cell_source(first, _busy_cell(marker))
    session.set_current_cell(first)
    cells_before = len(session.cells())

    events: list[SessionEvent] = []
    service.subscribe(events.append)

    session.run_cell(first)
    _wait_for_marker(marker)
    assert "df" in session.queue.running_changed_names, "the freeze is armed from the analysis, not from the run"

    with pytest.raises(PanelFrozenError) as refused:
        session.emit_snippet("df = df[:1]", panel="table:df", bound_names={"df"})

    assert refused.value.panel == "table:df"
    assert "df" in refused.value.names
    assert len(session.cells()) == cells_before, "a refused emission inserted a cell"
    inserted = [
        event
        for event in events
        if event.type is SessionEventType.ANALYSIS_UPDATED and event.payload.get("reason") == "cell_inserted"
    ]
    assert inserted == [], "a refused emission announced a cell insertion to every subscriber"

    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)


@needs_kernel
@pytest.mark.serial
def test_a_panel_bound_to_another_name_may_emit_while_a_cell_runs(
    services: Callable[..., SessionService],
    tmp_path: Path,
) -> None:
    """FR-025's other half at the session: only the names the run may change freeze.

    The emitted cell is queued behind the running one and runs when it ends, so
    the assertion is that the emission was *accepted* and that the notebook holds
    the cell afterwards — not merely that no exception was raised.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    marker = tmp_path / "other-panel-running"
    session.set_cell_source(first, _busy_cell(marker))
    session.set_current_cell(first)

    session.run_cell(first)
    _wait_for_marker(marker)

    cell_id, request = session.emit_snippet("elsewhere = 7", panel="table:elsewhere", bound_names={"elsewhere"})

    assert request.cell_id == cell_id
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.cell_source(cell_id) == "elsewhere = 7"
    assert session.last_bound_by.get("elsewhere") == cell_id, "the accepted emission ran once the cell ended"


# ---------------------------------------------------------------------------
# FR-028 to FR-030 and §4.1: what a run leaves in the repository
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


def _git(repository: GitEngine, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(repository.project_path),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@needs_kernel
@pytest.mark.serial
def test_many_runs_leave_the_branch_the_index_and_the_working_tree_alone(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """SC-006 for *several* runs rather than one, and against git rather than the service.

    One run cannot tell a per-run leak from a first-run leak, and the ref's
    commit count cannot tell whether the person's own staged work survived. This
    runs five cells and then reads the branch, the index, and the status the
    person would see.
    """
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "counter = 0")

    branch_head = _git(repository, "rev-parse", "HEAD").strip()
    branch_log = _git(repository, "log", "--format=%H", "HEAD").splitlines()
    # The person has staged work of their own; a commit path that touched the
    # branch index would sweep it up or drop it.
    (repository.project_path / "notes.txt").write_text("mine\n", encoding="utf-8")
    _git(repository, "add", "notes.txt")
    staged_before = _git(repository, "diff", "--cached", "--name-only")
    assert staged_before.split() == ["notes.txt"]

    for index in range(5):
        session.set_cell_source(first, f"counter = {index}")
        session.run_cell(first)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    ref = _explore_session_ref(session.session_id)
    assert _git(repository, "rev-list", "--count", ref).strip() == "5", "one commit per run, no more and no fewer"
    assert _git(repository, "rev-parse", "HEAD").strip() == branch_head, "the branch did not move"
    assert _git(repository, "log", "--format=%H", "HEAD").splitlines() == branch_log, "the branch log gained a commit"
    assert _git(repository, "diff", "--cached", "--name-only").split() == ["notes.txt"], (
        "the person's staged work was disturbed"
    )
    assert session.relative_path not in _git(repository, "ls-files", "--stage"), (
        "an explore commit staged the notebook in the branch's index"
    )
    status = _git(repository, "status", "--porcelain")
    assert f"?? {session.relative_path.split('/')[0]}/" in status or f"?? {session.relative_path}" in status, (
        f"the notebook should be an ordinary untracked file; status was {status!r}"
    )
    tracked_changes = [line for line in status.splitlines() if not line.startswith("??") and "notes.txt" not in line]
    assert tracked_changes == [], f"an explore commit changed tracked files: {tracked_changes}"


@needs_kernel
@pytest.mark.serial
def test_an_edit_after_execution_cannot_change_what_the_commit_carries(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """§4.1 and FR-028: the commit carries the notebook *as captured at execution time*.

    Two windows, both closed by the same one line. The edit is made from a
    subscriber, which the service calls **on the worker thread**, in the moment
    between the cell finishing and the commit being queued — so a run that
    re-read its own document at that point would record a notebook that never
    ran. The commit writer's git call is then held until afterwards, which
    closes the second window: between queueing and writing.

    Both matter because they fail differently. A capture taken at queue time
    passes any test that edits after ``wait_until_idle``; only an edit inside
    the run catches it.
    """
    from scistudio.explore.session import SessionEvent, SessionEventType

    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "executed = 'the source that ran'")

    edited = threading.Event()

    def edit_between_execution_and_commit(event: SessionEvent) -> None:
        if edited.is_set() or event.type is not SessionEventType.ANALYSIS_UPDATED:
            return
        if event.payload.get("reason") != "cell_ran":
            return
        edited.set()
        session.set_cell_source(first, "executed = 'an edit made after the run'")

    released = threading.Event()
    original = repository.commit_entries_to_ref

    def hold_until_edited(*args: object, **kwargs: object) -> str:
        assert edited.wait(timeout=_IDLE_TIMEOUT), "the test never made its edit"
        released.set()
        return original(*args, **kwargs)  # type: ignore[arg-type]

    service.subscribe(edit_between_execution_and_commit)
    repository.commit_entries_to_ref = hold_until_edited  # type: ignore[method-assign]
    try:
        session.run_cell(first)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
        assert edited.is_set(), "the run never reported that the cell had run"
        assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)
    finally:
        repository.commit_entries_to_ref = original  # type: ignore[method-assign]

    assert released.is_set(), "the commit was written without passing through the hold"
    ref = _explore_session_ref(session.session_id)
    committed = _git(repository, "show", f"{ref}:{session.relative_path}")
    assert "the source that ran" in committed, "the commit did not carry the notebook as captured at execution time"
    assert "an edit made after the run" not in committed, (
        "an edit made afterwards reached a commit that had already happened"
    )


@needs_kernel
@pytest.mark.serial
def test_two_runs_commit_in_order_on_one_parent_chain(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """FR-028 and FR-029: the session ref is a chain, not a series of overwrites.

    Two runs whose commits are written back to back must both survive: the
    second is parented on the first, so a compare-and-swap that lost the race
    would show up as a ref one commit deep rather than two.
    """
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None

    session.set_cell_source(first, "step = 1")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    session.set_cell_source(first, "step = 2")
    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    ref = _explore_session_ref(session.session_id)
    shas = _git(repository, "rev-list", ref).split()
    assert len(shas) == 2, f"the session ref holds {len(shas)} commits, not one per run"
    assert _git(repository, "rev-parse", f"{ref}~1").strip() == shas[1], (
        "the second commit is not parented on the first"
    )
    assert "step = 2" in _git(repository, "show", f"{ref}:{session.relative_path}")
    assert "step = 1" in _git(repository, "show", f"{ref}~1:{session.relative_path}")
    assert session.notebook_commit == shas[0], "FR-035: the session reports its latest commit"


# ---------------------------------------------------------------------------
# FR-027: the notebook reaches disk before the cell reaches the kernel
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_the_notebook_is_written_to_disk_by_the_run_itself(
    services: Callable[..., SessionService],
) -> None:
    """FR-027: "The service MUST write the notebook before each run".

    Every edit path also writes, so the pre-run write is invisible unless the
    file is taken away underneath the session — which is what a kernel death
    loses nothing typed is about. Deleting the file and running a cell is the
    only way to ask whether the *run* writes, and removing that write left every
    test in ``tests/explore`` green.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "typed = 'not lost'")

    session.notebook_path.unlink()
    assert not session.notebook_path.exists()

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert session.notebook_path.exists(), "the run did not write the notebook before executing"
    assert "typed = 'not lost'" in session.notebook_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# FR-051 to FR-055: the lineage half of the spec, at the seam
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
@pytest.mark.xfail(
    reason=(
        "#2240: scistudio.explore.lineage.ExploreLineage is never constructed by any production "
        "path, so no explore_sessions row is written when a session opens (FR-052, US6 scenario 4)."
    ),
    strict=False,
)
def test_opening_a_session_writes_its_explore_sessions_row(
    services: Callable[..., SessionService],
) -> None:
    """US6 scenario 4 and FR-052, asked of the service rather than of the recorder.

    ``tests/explore/test_explore_lineage.py`` proves that
    :class:`~scistudio.explore.lineage.ExploreLineage` writes the row when it is
    called. Nothing calls it: no module outside that one constructs it, and a
    :class:`SessionService` given a lineage store uses it only to resolve a
    block's output ports. So the anchor every cell-run and block-call record
    hangs off is never written for a real session.
    """
    from scistudio.core.lineage.store import LineageStore

    store = LineageStore(":memory:")
    try:
        service = services(lineage_store=store)
        session = service.open_over_file("data/raw/signal.csv")

        rows = store.list_explore_sessions()
        assert [row["session_id"] for row in rows] == [session.session_id]
        assert rows[0]["notebook_path"] == session.relative_path
        assert rows[0]["status"] == "running"
    finally:
        store.close()


@needs_kernel
@pytest.mark.serial
@pytest.mark.xfail(
    reason="#2240: no production path records a cell run against its session (FR-053).",
    strict=False,
)
def test_a_cell_run_writes_a_record_against_its_session(
    services: Callable[..., SessionService],
) -> None:
    """FR-053: "Every cell run MUST write a record carrying the session, the notebook commit, the cell id"."""
    from scistudio.core.lineage.store import LineageStore

    store = LineageStore(":memory:")
    try:
        service = services(lineage_store=store)
        session = service.open_over_file("data/raw/signal.csv")
        first = session.cells()[0].cell_id
        assert first is not None
        session.set_cell_source(first, "k = 1")
        session.run_cell(first)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

        executions = store.list_session_block_executions(session.session_id)
        assert executions, "a cell run left no record against the session"
        assert any(row.get("block_id") == first for row in executions)
    finally:
        store.close()


@needs_kernel
@pytest.mark.serial
@pytest.mark.xfail(
    reason=(
        "#2240: with no explore_sessions row, sessions_in_progress() is always empty and the "
        "retention guard that FR-055 relies on never fires."
    ),
    strict=False,
)
def test_retention_will_not_sweep_while_a_session_is_open(
    services: Callable[..., SessionService],
) -> None:
    """FR-055's protection, read from the store the planner actually consults.

    ``scistudio.core.lineage.retention`` refuses to sweep while
    ``sessions_in_progress()`` is non-empty. Nothing writes the rows that method
    reads, so the guard is inert in a live project and a session's objects are
    reclaimable while the person is still exploring. This is the consequence of
    the unwired anchor above, and it is the one that costs data rather than
    provenance.
    """
    from scistudio.core.lineage.store import LineageStore

    store = LineageStore(":memory:")
    try:
        service = services(lineage_store=store)
        service.open_over_file("data/raw/signal.csv")

        assert store.sessions_in_progress(), "retention was not told that a session is open"
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Spec §2 edge case: the same name declared as an output twice
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "#2240: _build_ports uses setdefault, so the *first* declaration wins and no duplicate "
        "is reported; the spec's edge case says the second one wins and the duplicate is reported."
    ),
    strict=False,
)
def test_a_name_declared_as_an_output_twice_takes_the_second_declaration() -> None:
    """The spec's edge case: the declaration written second in order wins,
    and packaging reports the duplicate."

    Both halves fail. ``_build_ports`` merges the declarations with
    ``setdefault``, so the port is wired to the variable the *earlier* call
    named — the one the notebook's own execution order says was superseded — and
    :class:`~scistudio.explore.packaging.PackagingProblemKind` has no member for
    a duplicate, so nothing tells the person the two declarations disagree.

    The consequence is silent: a person who refines an output by writing a
    second ``scistudio.output(table=better)`` further down gets a block whose
    port carries ``worse``, with the type of ``worse``, and no message.
    """
    from scistudio.explore.notebook import new_code_cell, new_notebook
    from scistudio.explore.packaging import check_packaging

    document = new_notebook(
        [
            new_code_cell("import scistudio\nearly = 'first'"),
            new_code_cell("scistudio.output(table=early)"),
            new_code_cell("late = 'second'"),
            new_code_cell("scistudio.output(table=late)"),
        ]
    )

    plan = check_packaging(document, bindings={"early": "Text", "late": "Text"})

    ports = {port.name: port.bound_name for port in plan.outputs}
    assert ports.get("table") == "late", f"the earlier declaration won: {ports}"
    assert any("twice" in problem.message or "duplicate" in problem.message for problem in plan.problems), (
        f"the duplicate declaration was not reported: {[problem.message for problem in plan.problems]}"
    )


def test_a_name_declared_as_an_output_twice_is_wired_to_the_earlier_declaration_today() -> None:
    """The behaviour as delivered, pinned so the fix above is visible when it lands.

    Written as an assertion of what happens rather than of what should, because
    an undocumented behaviour that nothing pins is one that changes without
    anybody deciding to change it.
    """
    from scistudio.explore.notebook import new_code_cell, new_notebook
    from scistudio.explore.packaging import check_packaging

    document = new_notebook(
        [
            new_code_cell("import scistudio\nearly = 'first'"),
            new_code_cell("scistudio.output(table=early)"),
            new_code_cell("late = 'second'"),
            new_code_cell("scistudio.output(table=late)"),
        ]
    )

    plan = check_packaging(document, bindings={"early": "Text", "late": "Text"})

    assert [(port.name, port.bound_name) for port in plan.outputs] == [("table", "early")]
    assert plan.is_packageable, "the notebook is packaged, silently, against the superseded name"


# ---------------------------------------------------------------------------
# FR-035: the commit a session reports
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "#2240: ExploreSession.note_branch_commit keeps the first sha it is given "
        "(``self._last_commit_sha or sha``), so a second branch commit does not update FR-035's answer."
    ),
    strict=False,
)
@pytest.mark.serial
def test_the_reported_commit_follows_the_second_branch_commit(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """FR-035: "A session MUST report its current notebook commit".

    ``note_explore_commit`` overwrites; ``note_branch_commit`` keeps whatever is
    already there. The hybrid means a session whose only commits are branch
    commits reports the first one for ever — a commit whose tree no longer holds
    the notebook. Either rule alone would be defensible; the property's own
    docstring says it reports "the commit of the last cell run on the session's
    ref", which the ``or`` contradicts in the other direction by accepting a
    branch commit at all.
    """
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None

    service.commit_to_branch(session)
    session.set_cell_source(first, "changed = True")
    second = service.commit_to_branch(session)

    assert session.notebook_commit == second, "the session reports a commit that predates its notebook"


@pytest.mark.serial
def test_the_reported_commit_keeps_the_first_branch_commit_today(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """The behaviour as delivered, pinned. See the xfail above for why it is wrong."""
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None

    initial = service.commit_to_branch(session)
    session.set_cell_source(first, "changed = True")
    second = service.commit_to_branch(session)

    assert initial != second
    assert session.notebook_commit == initial


# ---------------------------------------------------------------------------
# FR-027 and FR-028: the outputs a notebook keeps, and the ones a commit drops
# ---------------------------------------------------------------------------


def _give_the_first_cell_an_output(session: ExploreSession) -> None:
    """Put a real output into the notebook on disk and make the session reload it.

    Every assertion that a commit is "stripped of outputs" is vacuous unless the
    document being committed had an output to lose. The session never records
    one (see the xfail below), so a test that needs one has to supply it the way
    an outside editor would: by writing the file and letting FR-005's reload
    pick it up.
    """
    document = json.loads(session.notebook_path.read_text(encoding="utf-8"))
    for cell in document["cells"]:
        if cell.get("cell_type") == "code":
            cell["outputs"] = [
                {"output_type": "stream", "name": "stdout", "text": ["a rendered output the person can see\n"]}
            ]
            cell["execution_count"] = 7
            break
    session.notebook_path.write_text(json.dumps(document, indent=1), encoding="utf-8")
    assert session.reload_if_changed(), "the session did not pick up the edited notebook"
    assert any(cell.outputs for cell in session.cells()), "the fixture failed to give a cell an output"


@needs_kernel
@pytest.mark.serial
def test_the_explore_commit_strips_outputs_that_were_really_there(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """FR-028 and SC-006, against a notebook that actually carries an output.

    The delivered assertion for this is ``'"outputs": []' in committed``, which
    holds for a notebook that never had an output — and the session never puts
    one there, so the check cannot fail. Given a document with a rendered output
    in it, this asks the same question with something at stake: the commit must
    drop it and the file on disk must keep it.
    """
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 1")
    _give_the_first_cell_an_output(session)

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    ref = _explore_session_ref(session.session_id)
    committed = json.loads(_git(repository, "show", f"{ref}:{session.relative_path}"))
    assert all(cell.get("outputs", []) == [] for cell in committed["cells"]), "the commit carried a cell output"
    assert all(cell.get("execution_count") is None for cell in committed["cells"]), (
        "the commit carried an execution count"
    )

    on_disk = json.loads(session.notebook_path.read_text(encoding="utf-8"))
    assert any(cell.get("outputs") for cell in on_disk["cells"]), (
        "FR-027: the file on disk keeps its outputs; only the commit is stripped"
    )


@pytest.mark.serial
def test_the_branch_commit_strips_outputs_that_were_really_there(
    services: Callable[..., SessionService],
    repository: GitEngine,
) -> None:
    """FR-036, asked the same way as FR-028 above and for the same reason."""
    service = services(repository.project_path, git_engine=repository)
    session = service.open_over_file("data/raw/signal.csv")
    _give_the_first_cell_an_output(session)

    sha = service.commit_to_branch(session)
    assert sha is not None

    committed = json.loads(_git(repository, "show", f"{sha}:{session.relative_path}"))
    assert all(cell.get("outputs", []) == [] for cell in committed["cells"])
    assert any(cell.get("outputs") for cell in json.loads(session.notebook_path.read_text(encoding="utf-8"))["cells"])


@needs_kernel
@pytest.mark.serial
@pytest.mark.xfail(
    reason=(
        "#2240: no production path writes a run's outputs back into the notebook, so FR-027's "
        "'the notebook on disk MUST keep its cell outputs' has nothing to keep."
    ),
    strict=False,
)
def test_a_cell_run_leaves_its_output_in_the_notebook_on_disk(
    services: Callable[..., SessionService],
) -> None:
    """FR-027, first sentence: "The notebook on disk MUST keep its cell outputs".

    The run's outputs reach the frontend as a ``cell_output`` event and are then
    dropped: nothing writes them into :class:`NotebookDocument`, which has no
    setter for them at all. The notebook a person reopens, or opens in
    JupyterLab, shows every cell as never having run.

    This is also why the delivered "outputs stripped" assertions cannot fail —
    a mutation that made the explore commit carry the whole document, outputs
    and all, survived the entire ``tests/explore`` run.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "print('a rendered output the person can see')")

    session.run_cell(first)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    on_disk = json.loads(session.notebook_path.read_text(encoding="utf-8"))
    outputs = [output for cell in on_disk["cells"] for output in cell.get("outputs", [])]
    assert outputs, "the run's output did not reach the notebook on disk"


def _still_running(pid: int) -> bool:
    """Whether *pid* is a live process **right now**, with no waiting.

    The delivered lifecycle tests all poll for up to ten seconds, which is right
    for "the process eventually goes" and wrong for "the call that ended it did
    not return early". Removing the handle's own wait-for-exit left every one of
    them green.
    """
    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return False
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


@needs_kernel
@pytest.mark.serial
def test_ending_a_kernel_returns_only_once_its_process_has_gone(
    services: Callable[..., SessionService],
) -> None:
    """FR-016 and US7 scenario 2 with no polling: the *call* is the guarantee.

    ``KernelHandle.stop`` promises it "always ends with no kernel process left
    behind", and a caller that has to poll afterwards does not have that
    promise. It matters at a branch switch: the next thing that happens is a
    checkout, and on Windows a kernel that is still up holds the old branch's
    files open.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    session.start_kernel()
    status = session.kernel_status()
    assert status is not None and status.pid is not None
    pid = status.pid
    assert _still_running(pid), "the fixture never started a kernel"

    service.end_kernel(session.relative_path)

    assert not _still_running(pid), "end_kernel returned while its kernel process was still alive"


@needs_kernel
@pytest.mark.serial
def test_retiring_kernels_returns_only_once_every_process_has_gone(
    services: Callable[..., SessionService],
) -> None:
    """FR-014 with the same discipline, over more than one kernel.

    A branch switch retires every kernel and then proceeds. If ``retire_kernels``
    can return while a process is still up, the checkout that follows races it,
    and the failure surfaces as a file-lock error a long way from here.
    """
    service = services()
    sessions = [service.open_over_file(f"data/raw/{name}.csv") for name in ("one", "two")]
    for session in sessions:
        session.start_kernel()
    pids = []
    for session in sessions:
        status = session.kernel_status()
        assert status is not None and status.pid is not None
        pids.append(status.pid)
    assert all(_still_running(pid) for pid in pids)

    service.retire_kernels()

    still_up = [pid for pid in pids if _still_running(pid)]
    assert still_up == [], f"a branch switch returned with kernels still running: {still_up}"


# ---------------------------------------------------------------------------
# FR-038: the type a packaged port gets, from the bridge a real session holds
# ---------------------------------------------------------------------------


def _packageable_session(service: SessionService) -> ExploreSession:
    """A session whose notebook declares one output and has run clean."""
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "import scistudio\nvalue = 'a result worth keeping'")
    declare = session.insert_cell("scistudio.output(table=value)", after=first)
    for cell_id in (first, declare):
        session.run_cell(cell_id)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.questionable_cells() == ()
    return session


@needs_kernel
@pytest.mark.serial
@pytest.mark.xfail(
    reason=(
        "#2240: KernelBridge reports type(value).__name__, so binding_types() yields 'str' where "
        "FR-038 needs 'Text'; packaging a real session refuses every port it cannot name."
    ),
    strict=False,
)
def test_packaging_a_real_session_can_type_its_declared_port(
    services: Callable[..., SessionService],
) -> None:
    """FR-038 and SC-007 with the bindings a real session actually reports.

    Every packaging test in the delivered suite supplies its own bindings, and
    the API harness's fake bridge translates ``str`` to ``Text`` under a comment
    saying "the real bridge does this translation because it is the only side
    holding the object". It does not: ``KernelBridge`` reports
    ``type(value).__name__``, and :meth:`ExploreSession.binding_types` passes it
    straight through, so ``check_packaging`` gets ``'str'`` and
    ``default_port_extension`` has no entry for it.

    The refusal is ``untyped_port``, which reads as "nothing is bound to that
    name" — so the person is told their variable is missing when what is
    missing is the translation. Only a type whose Python class name happens to
    equal a SciStudio type name (``DataFrame``, ``Series``) packages at all.
    """
    from scistudio.explore.packaging import check_packaging

    service = services()
    session = _packageable_session(service)

    plan = check_packaging(
        session.document,
        marks=session.cell_marks(),
        bindings=session.binding_types(),
        observations=session.observations,
    )

    assert plan.is_packageable, f"packaging a clean real session refused it: {[p.message for p in plan.problems]}"
    assert [(port.name, port.data_type) for port in plan.outputs] == [("table", "Text")]


@needs_kernel
@pytest.mark.serial
def test_the_bridge_reports_the_native_type_name_today(
    services: Callable[..., SessionService],
) -> None:
    """The behaviour as delivered, pinned so the fix above is visible when it lands.

    ``binding_types`` documents this as the bridge's job; nothing in the bridge
    does it. Pinned here rather than left implicit, because the API harness's
    fake bridge asserts the opposite in a comment and there is nothing else in
    the suite that would notice.
    """
    from scistudio.explore.packaging import check_packaging

    service = services()
    session = _packageable_session(service)

    assert session.binding_types().get("value") == "str", "the bridge began translating; update the xfail above"

    plan = check_packaging(
        session.document,
        marks=session.cell_marks(),
        bindings=session.binding_types(),
        observations=session.observations,
    )
    assert not plan.is_packageable
    assert [problem.kind.value for problem in plan.problems] == ["untyped_port"]


# ---------------------------------------------------------------------------
# FR-039: what packaging sees while the queue is still moving
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_editing_a_cell_that_has_run_leaves_it_carrying_no_mark(
    services: Callable[..., SessionService],
) -> None:
    """The behaviour as delivered, pinned: an edited cell is neither stale nor never-run.

    FR-023's three marks are never-run, stale, and out-of-order, and an edit
    produces none of them: the cell "has run", so its never-run mark was
    cleared, and nothing above it re-ran, so it is not stale. The analysis does
    drop the cell's observation once its source hash moves (analysis FR-027), so
    the graph falls back to the static estimate — but packaging reads the
    *marks*, and by them the cell is clean.

    The consequence is that FR-039's list of refusals does not cover a slice
    whose source is not the source that ran. Whether it should is a question for
    the spec rather than for this test, which only makes the behaviour visible.
    """
    service = services()
    session = _packageable_session(service)
    first = session.cells()[0].cell_id
    assert first is not None

    session.set_cell_source(first, "import scistudio\nvalue = 'edited and never run as written'")

    assert session.marks(first) == frozenset(), "an edited cell carries no mark"
    assert session.questionable_cells() == (), "packaging is given three empty sets for an edited notebook"
    assert first not in session.observations, "the analysis did drop the observation, as analysis FR-027 requires"


@needs_kernel
@pytest.mark.serial
def test_a_branch_switch_writes_the_notebook_itself_rather_than_relying_on_an_earlier_write(
    services: Callable[..., SessionService],
) -> None:
    """FR-014: "MUST retire every kernel **after writing every open notebook to disk**".

    The delivered test for this sentence edits a cell and then asserts the edit
    is on disk — but every edit path writes as it goes, so the assertion holds
    whether or not the retirement writes anything, and removing the write left
    it green. Taking the file away first is what makes the question real, and it
    is also the state that matters: the retirement is the last chance to put a
    session's notebook somewhere before the checkout that follows.
    """
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "unsaved = 'typed just now'")

    session.notebook_path.unlink()
    assert not session.notebook_path.exists()

    service.retire_kernels()

    assert session.notebook_path.exists(), "a branch switch retired the kernels without writing the notebook"
    assert "unsaved = 'typed just now'" in session.notebook_path.read_text(encoding="utf-8")


@needs_kernel
@pytest.mark.serial
def test_closing_a_session_writes_the_notebook_itself(
    services: Callable[..., SessionService],
) -> None:
    """FR-006, asked the same way: close writes the notebook, not merely the edits before it."""
    service = services()
    session = service.open_over_file("data/raw/one.csv")
    session.start_kernel()
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "unsaved = 'typed just now'")
    path = session.notebook_path
    path.unlink()

    service.close(session)

    assert path.exists(), "closing a session did not write its notebook"
    assert "unsaved = 'typed just now'" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# FR-059: the half of the bundled-runtime blocker a test can reach
# ---------------------------------------------------------------------------


def test_the_kernel_dependencies_are_core_rather_than_optional() -> None:
    """FR-059, and the only part of SC-015 a checkout can answer.

    SC-015 is measured "by starting a session from the packaged application",
    which no test in this repository can do. What a test *can* hold is the
    condition that makes the rebuild carry them:
    ``desktop/scripts/build-python-runtime.ps1`` installs the repository root
    into the bundled interpreter, so ``[project].dependencies`` is what reaches
    it. Moved into an optional extra — the ordinary way a heavy dependency
    drifts out of a build — they would still import in every developer's
    environment and be absent from every shipped one, and nothing would say so
    until a person opened a session in the desktop app.

    The rebuild itself stays a release-checklist obligation (spec §4.5); this
    only keeps the input to it honest.
    """
    import tomllib

    repo_root = Path(__file__).resolve().parents[2]
    manifest = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = manifest["project"]["dependencies"]
    names = {requirement.split(">=")[0].split("==")[0].split("[")[0].strip().lower() for requirement in declared}

    assert "ipykernel" in names, "ipykernel left the core dependencies; the bundled runtime will not carry it"
    assert "jupyter_client" in names or "jupyter-client" in names, (
        "jupyter_client left the core dependencies; the bundled runtime will not carry it"
    )


@needs_kernel
@pytest.mark.serial
def test_a_freshly_opened_session_inserts_a_panel_emission_after_its_first_cell(
    services: Callable[..., SessionService],
) -> None:
    """FR-018 and US3 scenario 1 without the test first telling the session where it is.

    A session opens on its generated first cell, and that is what "the session's
    current cell" means before the person has moved. Every delivered test that
    reaches the emission path sets the current cell itself, so the service
    setting it on open is unasserted — and removing it left the whole
    ``tests/explore`` run green, because a one-cell notebook puts "after the
    first cell" and "at the end" in the same place.

    Two cells put them in different places. Without the current cell the
    emission appends, and the person watching a panel sees their edit land at
    the bottom of a notebook they were working in the middle of.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    last = session.insert_cell("tail = 'the cell at the bottom'", after=first)
    assert session.current_cell == first, "a session opens on its first cell"

    cell_id, _request = session.emit_snippet("df = [1]", panel="table:df", bound_names={"df"})
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    ids = [cell.cell_id for cell in session.cells()]
    assert ids == [first, cell_id, last], f"the emission did not land after the current cell: {ids}"


@needs_kernel
@pytest.mark.serial
def test_two_separate_failing_runs_report_the_failure_once(
    services: Callable[..., SessionService],
    repository: GitEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-030's "reported once", over two runs that really are two runs.

    The delivered test for this submits the same cell twice in a row and counts
    the reports. Two submissions of a cell that is still queued **coalesce**
    (FR-017), so that test runs the cell once, queues one commit, and would read
    "once" however the reporting were written — removing the de-duplication
    entirely left it green. Draining the queue between the two submissions is
    what makes them two runs, and counting the writer's own attempts is what
    proves it rather than assuming it.
    """
    from scistudio.explore.session import SessionEventType

    service = services(repository.project_path, git_engine=repository)
    reports: list[dict[str, Any]] = []
    service.subscribe(
        lambda event: reports.append(dict(event.payload)) if event.type is SessionEventType.COMMIT_RECORDED else None
    )
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None

    attempts: list[str] = []

    def refuse(ref: str, *args: object, **kwargs: object) -> str:
        attempts.append(ref)
        raise RuntimeError("the repository is locked")

    monkeypatch.setattr(repository, "commit_entries_to_ref", refuse)

    for source in ("k = 1", "k = 2"):
        session.set_cell_source(first, source)
        session.run_cell(first)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT), "a failing commit must not block the queue"
    assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    assert len(attempts) >= 2, f"the two runs did not queue two commits: {len(attempts)} attempt(s)"
    failures = [report for report in reports if report.get("error")]
    assert len(failures) == 1, f"the failure must be reported once, not per run: {failures}"
    assert "locked" in failures[0]["error"]


@needs_kernel
@pytest.mark.serial
def test_a_failure_after_a_recovery_is_never_reported_again(
    services: Callable[..., SessionService],
    repository: GitEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The behaviour as delivered, pinned: "once" is once per session, for ever.

    ``SessionService._reported_commit_failure`` is a set of session ids that is
    never cleared, so the first failure is the only one a session will ever
    report. A repository that was locked this morning, recovered, and is locked
    again this afternoon costs the person their afternoon's commits in silence.

    FR-030 says "a run whose commit could not be written MUST be reported once",
    which reads as once per run rather than once per session; the two readings
    differ only after a recovery, which is exactly when it matters. Pinned here
    rather than argued: the behaviour should be visible either way.
    """
    from scistudio.explore.session import SessionEventType

    service = services(repository.project_path, git_engine=repository)
    reports: list[dict[str, Any]] = []
    service.subscribe(
        lambda event: reports.append(dict(event.payload)) if event.type is SessionEventType.COMMIT_RECORDED else None
    )
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    working = repository.commit_entries_to_ref

    def refuse(*args: object, **kwargs: object) -> str:
        raise RuntimeError("the repository is locked")

    def run(source: str) -> None:
        session.set_cell_source(first, source)
        session.run_cell(first)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
        assert service.wait_for_commits(timeout=_IDLE_TIMEOUT)

    monkeypatch.setattr(repository, "commit_entries_to_ref", refuse)
    run("k = 1")
    assert len([report for report in reports if report.get("error")]) == 1

    monkeypatch.setattr(repository, "commit_entries_to_ref", working)
    run("k = 2")
    assert [report for report in reports if report.get("sha")], "the recovered commit was written"

    monkeypatch.setattr(repository, "commit_entries_to_ref", refuse)
    run("k = 3")

    assert len([report for report in reports if report.get("error")]) == 1, (
        "the second outage was reported; update this pin and the finding it records"
    )


# ---------------------------------------------------------------------------
# Spec section 2 edge case: an output declaration in a disabled cell
# ---------------------------------------------------------------------------


def test_an_output_declared_in_a_disabled_cell_is_not_an_output() -> None:
    """The spec's edge case: "It is not an output; the analysis builds over enabled cells only".

    No delivered test disables a cell that declares an output, so the filter
    that implements this — ``_output_cell_ids`` intersecting the declarations
    with the graph's cells — could be removed without anything noticing. A
    notebook whose only declaration is disabled has nothing to package, and
    saying so is the refusal FR-039 already has for a notebook that declares no
    output at all.
    """
    from scistudio.explore.notebook import new_code_cell, new_notebook
    from scistudio.explore.packaging import PackagingProblemKind, check_packaging

    document = new_notebook(
        [
            new_code_cell("import scistudio\nvalue = 'a result'"),
            new_code_cell("scistudio.output(table=value)"),
        ]
    )
    declaring = document.cells[1].cell_id
    assert declaring is not None
    document.set_cell_enabled(declaring, enabled=False)

    plan = check_packaging(document, bindings={"value": "Text"})

    assert not plan.is_packageable
    assert [problem.kind for problem in plan.problems] == [PackagingProblemKind.NO_DECLARED_OUTPUT]
    assert plan.outputs == ()


def test_disabling_one_of_two_declarations_leaves_the_other_a_port() -> None:
    """The same rule where it has to discriminate rather than refuse everything."""
    from scistudio.explore.notebook import new_code_cell, new_notebook
    from scistudio.explore.packaging import check_packaging

    document = new_notebook(
        [
            new_code_cell("import scistudio\nkept = 'one'\ndropped = 'two'"),
            new_code_cell("scistudio.output(kept=kept)"),
            new_code_cell("scistudio.output(dropped=dropped)"),
        ]
    )
    disabled = document.cells[2].cell_id
    assert disabled is not None
    document.set_cell_enabled(disabled, enabled=False)

    plan = check_packaging(document, bindings={"kept": "Text", "dropped": "Text"})

    assert plan.is_packageable, [problem.message for problem in plan.problems]
    assert [port.name for port in plan.outputs] == ["kept"]
    assert disabled not in plan.cells, "a disabled cell is not in the slice a packaged block runs"


# ---------------------------------------------------------------------------
# FR-038: the load line a file-opened session's packaging rewrites, and only it
# ---------------------------------------------------------------------------


def test_the_load_rewrite_leaves_a_named_variable_that_is_not_a_load_alone() -> None:
    """FR-038 rewrites ``x = scistudio.load(...)``, not every assignment to ``x``.

    The delivered test for this checks a variable the port mapping does not
    name, which the ``ports.get`` lookup already rejects. The other half — a
    variable the mapping *does* name, bound by something that is not a load —
    is what ``_is_load_call`` is for, and making that function answer ``True``
    for everything left the whole ``tests/explore`` run green.

    It matters because the rewrite is silent and destructive: the packaged copy
    would read a port where the person wrote their preprocessing, and the block
    would produce a different answer from the session it came from with nothing
    to show why.
    """
    from scistudio.explore.packaging import rewrite_load_to_input

    source = 'raw = scistudio.load("data/raw.csv")\nspectra = preprocess(raw)\n'

    rewritten = rewrite_load_to_input(source, {"spectra": "spectra"})

    assert rewritten == source, "the rewrite replaced a line that was not a load"


def test_the_load_rewrite_leaves_a_load_that_is_not_the_whole_expression_alone() -> None:
    """A load wrapped in another call is not the load line FR-038 names.

    ``x = normalise(scistudio.load(...))`` binds the *normalised* object;
    replacing the line with a port read would drop the normalisation, and the
    port would carry data the notebook never worked with.
    """
    from scistudio.explore.packaging import rewrite_load_to_input

    source = 'spectra = normalise(scistudio.load("data/raw.csv"))\n'

    assert rewrite_load_to_input(source, {"spectra": "spectra"}) == source


def test_the_load_rewrite_replaces_the_line_it_does_name() -> None:
    """The positive case beside the two negatives, so the pair cannot both be vacuous."""
    from scistudio.explore.packaging import rewrite_load_to_input

    source = 'raw = scistudio.load("data/raw.csv")\nspectra = preprocess(raw)\n'

    rewritten = rewrite_load_to_input(source, {"raw": "signal"})

    assert rewritten == 'raw = scistudio.input("signal")\nspectra = preprocess(raw)\n'
