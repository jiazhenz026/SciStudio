"""The queue, the admission whitelist, and the marks (ADR-054 T-007, T-008).

FR-017 to FR-026 of ``docs/specs/adr-054-explore-session.md`` (#2240).

The claim spec §4.1 makes is that **marks are bookkeeping, not execution**. Every
assertion about the marks in this module therefore comes in two halves: what was
marked, and what was enqueued. The second half is the one that matters, and it is
almost always *nothing*. A test that asserted only "B is marked out of order"
would pass just as happily against a service that then re-ran half the notebook.

The mark tests run against a **real ipykernel process**. Marks are a function of
what a run was observed to change, and an observation is a comparison of real
fingerprints over a real namespace; a substituted kernel would let a test pass
that asserts the design rather than the behaviour. The queue and the whitelist
have no kernel in them at all, so those tests do not spawn one.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psutil
import pytest

from scistudio.explore.dependency_analysis import source_hash
from scistudio.explore.fingerprint import Fingerprint, fingerprint
from scistudio.explore.queue import (
    ExecutionQueue,
    ExecutionRequest,
    Observation,
    PanelFrozenError,
    RequestKind,
    RequestState,
    SnippetRefusedError,
    admit_snippet,
    observe_namespaces,
)
from scistudio.explore.session import CellMark, ExploreSession, SessionError, SessionService

# ---------------------------------------------------------------------------
# FR-018: the admission whitelist. Refused, not sanitised.
# ---------------------------------------------------------------------------


ACCEPTED = [
    pytest.param("df = df.drop(index=[3, 7])", id="assignment-to-a-plain-name"),
    pytest.param("a, b = split(df)", id="tuple-unpacking-of-plain-names"),
    pytest.param("[a, b] = split(df)", id="list-unpacking-of-plain-names"),
    pytest.param("head, *rest = rows", id="star-unpacking-of-plain-names"),
    pytest.param("a = b = df.copy()", id="chained-assignment-to-plain-names"),
    pytest.param("import numpy", id="import"),
    pytest.param("import numpy as np", id="import-as"),
    pytest.param("from numpy import array", id="from-import"),
    pytest.param("scistudio.output(table=df)", id="scistudio-output-call"),
    pytest.param("df = df.dropna()\nscistudio.output(table=df)", id="several-admitted-statements"),
    pytest.param("f = lambda row: row * 2", id="lambda-bound-to-a-plain-name"),
]

REFUSED = [
    pytest.param("df.drop(index=[3, 7], inplace=True)", "a bare expression", id="bare-method-call"),
    pytest.param("print(df)", "a bare expression", id="bare-function-call"),
    pytest.param("df", "a bare expression", id="bare-name"),
    pytest.param("scistudio.input('signal')", "a bare expression", id="a-call-that-is-not-output"),
    pytest.param("df['a'] = 1", "an assignment to a subscript", id="subscript-assignment"),
    pytest.param("df.name = 'x'", "an assignment to an attribute", id="attribute-assignment"),
    pytest.param("a, df['x'] = 1, 2", "an assignment to a subscript", id="unpacking-onto-a-subscript"),
    pytest.param("df += 1", "an augmented assignment", id="augmented-assignment"),
    pytest.param("df: list = []", "an annotated assignment", id="annotated-assignment"),
    pytest.param("del df", "a del statement", id="del"),
    pytest.param("for row in df:\n    pass", "a for loop", id="for-loop"),
    pytest.param("while True:\n    break", "a while loop", id="while-loop"),
    pytest.param("if df:\n    x = 1", "an if statement", id="if-statement"),
    pytest.param("with open('f') as fh:\n    x = 1", "a with statement", id="with-statement"),
    pytest.param("try:\n    x = 1\nexcept Exception:\n    pass", "a try statement", id="try-statement"),
    pytest.param("def f():\n    return 1", "a function definition", id="function-def"),
    pytest.param("class C:\n    pass", "a class definition", id="class-def"),
    pytest.param("raise ValueError('no')", "a raise statement", id="raise"),
    pytest.param("assert df", "an assert statement", id="assert"),
    pytest.param("global df", "a global statement", id="global"),
    pytest.param("pass", "a pass statement", id="pass"),
    pytest.param("%pip install numpy", "not valid Python", id="a-magic-line"),
    pytest.param("df = ", "not valid Python", id="a-syntax-error"),
    pytest.param("", "emitted no statement", id="an-empty-emission"),
    pytest.param("   \n\n", "emitted no statement", id="whitespace-only"),
]


@pytest.mark.parametrize("source", ACCEPTED)
def test_the_whitelist_admits_what_a_panel_may_emit(source: str) -> None:
    """FR-018: an assignment to plain names, an import, or scistudio.output."""
    assert admit_snippet(source, panel="table:df") is not None


@pytest.mark.parametrize(("source", "expected_phrase"), REFUSED)
def test_the_whitelist_refuses_every_other_statement_form(source: str, expected_phrase: str) -> None:
    """FR-018: anything else is refused, naming the panel and the statement."""
    with pytest.raises(SnippetRefusedError) as raised:
        admit_snippet(source, panel="table:df")
    message = str(raised.value)
    assert "table:df" in message, "the refusal must name the panel"
    assert expected_phrase in message, f"the refusal must say what it refused; got {message!r}"
    assert raised.value.panel == "table:df"


def test_a_refusal_names_the_offending_statement_not_the_whole_snippet() -> None:
    """FR-018: the message names *the statement*, so a person can find it."""
    with pytest.raises(SnippetRefusedError) as raised:
        admit_snippet("df = df.dropna()\ndf.sort_values('a', inplace=True)", panel="table:df")
    assert raised.value.statement == "df.sort_values('a', inplace=True)"
    assert "df = df.dropna()" not in raised.value.statement


def test_a_snippet_is_refused_whole_when_one_statement_is_outside_the_whitelist() -> None:
    """FR-018: no partial admission — a rewritten snippet is one nobody wrote."""
    with pytest.raises(SnippetRefusedError):
        admit_snippet("a = 1\nb['x'] = 2\nc = 3", panel="table:df")


def test_a_fully_qualified_output_call_is_admitted() -> None:
    """The whitelist resolves ``scistudio.output`` the way the analysis does."""
    assert admit_snippet("a.scistudio.output(table=df)", panel="p") is not None


# ---------------------------------------------------------------------------
# FR-021, analysis FR-026 and FR-029: the observation around a run
# ---------------------------------------------------------------------------


def test_observation_reports_what_moved_appeared_and_disappeared() -> None:
    before = {"df": fingerprint([1, 2, 3]), "gone": fingerprint(1), "same": fingerprint("x")}
    after = {"df": fingerprint([1, 2]), "same": fingerprint("x"), "new": fingerprint(7)}
    observed = observe_namespaces(before, after, cell_id="c1", source_hash="h")
    assert observed.differing == {"df"}
    assert observed.appeared == {"new"}
    assert observed.disappeared == {"gone"}
    assert observed.changed_names == {"df", "new", "gone"}
    assert "same" not in observed.changed_names


def test_an_unobservable_name_that_did_not_move_is_reported_not_guessed_at() -> None:
    """Analysis FR-029: equality proves nothing about it, so it is surfaced.

    It must **not** join the changed set: calling every module and function in
    the namespace "changed" on every run would make the last-bound-by map claim
    each cell rebinds all of them, and every cell below would be stale for ever.
    """
    opaque = Fingerprint(digest="id:123", observable=False, type_name="module")
    observed = observe_namespaces({"np": opaque}, {"np": opaque}, cell_id="c1", source_hash="h")
    assert observed.unobservable == {"np"}
    assert observed.changed_names == frozenset()


def test_an_unobservable_name_that_moved_is_still_a_change() -> None:
    """A rebinding moves the identity digest, and that is a real observation."""
    before = Fingerprint(digest="id:1", observable=False, type_name="module")
    after = Fingerprint(digest="id:2", observable=False, type_name="module")
    observed = observe_namespaces({"m": before}, {"m": after}, cell_id="c1", source_hash="h")
    assert observed.changed_names == {"m"}
    assert observed.unobservable == frozenset()


def test_an_observation_is_what_build_graph_accepts() -> None:
    """The handoff of FR-021: the analysis reads ``changed_names`` and nothing else."""
    from scistudio.explore.dependency_analysis import analyse_cells, build_graph

    facts = analyse_cells([("c1", "run()"), ("c2", "print(df)")])
    observation = Observation(cell_id="c1", source_hash=source_hash("run()"), appeared=frozenset({"df"}))
    graph = build_graph(facts, observations={"c1": observation})
    assert graph.changed_set("c1") == {"df"}
    assert graph.definer_for("c2", "df") == "c1"


# ---------------------------------------------------------------------------
# FR-017, FR-025: the queue itself. No kernel is involved in any of these.
# ---------------------------------------------------------------------------


class _Recorder:
    """A runner that records what it was given and can be held mid-request."""

    def __init__(self) -> None:
        self.ran: list[str] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.hold: str | None = None

    def __call__(self, request: ExecutionRequest) -> None:
        if self.hold is not None and request.cell_id == self.hold:
            self.started.set()
            assert self.release.wait(timeout=30), "the test never released the held request"
        self.ran.append(request.cell_id)


@pytest.fixture
def recorder() -> _Recorder:
    return _Recorder()


@pytest.fixture
def execution_queue(recorder: _Recorder) -> Iterator[Callable[..., ExecutionQueue]]:
    """Hand out queues and stop every one of them, however the test ended."""
    made: list[ExecutionQueue] = []

    def make(**kwargs: object) -> ExecutionQueue:
        queue = ExecutionQueue(recorder, **kwargs)  # type: ignore[arg-type]
        made.append(queue)
        queue.start()
        return queue

    try:
        yield make
    finally:
        for queue in made:
            recorder.release.set()
            with contextlib.suppress(Exception):
                queue.stop(timeout=10)


def test_the_queue_runs_requests_in_submission_order(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-017: one at a time, in submission order."""
    queue = execution_queue()
    for cell_id in ("c1", "c2", "c3"):
        queue.submit_cell(cell_id)
    assert queue.wait_until_idle(timeout=30)
    assert recorder.ran == ["c1", "c2", "c3"]


def test_a_duplicate_submission_of_a_queued_cell_runs_once(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-017 and US2 scenario 5: a person leaning on the button runs the cell once."""
    recorder.hold = "blocker"
    recorder.release.clear()
    queue = execution_queue()
    queue.submit_cell("blocker")
    assert recorder.started.wait(timeout=30)

    first = queue.submit_cell("c2")
    second = queue.submit_cell("c2")
    third = queue.submit_cell("c2")
    assert first is second is third, "the same queued request must be returned"
    assert first.coalesced == 2

    recorder.release.set()
    assert queue.wait_until_idle(timeout=30)
    assert recorder.ran == ["blocker", "c2"], "c2 ran once"


def test_a_submission_of_the_running_cell_is_not_coalesced_with_it(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-017 coalesces a cell 'already queued and not yet started', not a running one."""
    recorder.hold = "c1"
    recorder.release.clear()
    queue = execution_queue()
    running = queue.submit_cell("c1")
    assert recorder.started.wait(timeout=30)

    recorder.hold = None
    again = queue.submit_cell("c1")
    assert again is not running

    recorder.release.set()
    assert queue.wait_until_idle(timeout=30)
    assert recorder.ran == ["c1", "c1"]


def test_a_panel_bound_to_a_changing_name_cannot_emit_while_the_run_holds_it(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-025 and US3 scenario 4: the submission is refused, and only until the run ends."""
    recorder.hold = "c1"
    recorder.release.clear()
    queue = execution_queue(changed_names_of=lambda request: frozenset({"df"}))
    queue.submit_cell("c1")
    assert recorder.started.wait(timeout=30)

    with pytest.raises(PanelFrozenError) as raised:
        queue.submit_cell("emitted", kind=RequestKind.SNIPPET, panel="table:df", bound_names={"df"})
    assert raised.value.names == {"df"}
    assert "table:df" in str(raised.value)

    recorder.release.set()
    assert queue.wait_until_idle(timeout=30)
    accepted = queue.submit_cell("emitted", kind=RequestKind.SNIPPET, panel="table:df", bound_names={"df"})
    assert accepted.state in {RequestState.QUEUED, RequestState.RUNNING, RequestState.DONE}
    assert queue.wait_until_idle(timeout=30)
    assert "emitted" in recorder.ran


def test_a_panel_bound_to_another_name_may_emit_while_a_run_is_in_flight(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-025: submissions from other panels are accepted."""
    recorder.hold = "c1"
    recorder.release.clear()
    queue = execution_queue(changed_names_of=lambda request: frozenset({"df"}))
    queue.submit_cell("c1")
    assert recorder.started.wait(timeout=30)

    queue.submit_cell("emitted", kind=RequestKind.SNIPPET, panel="plot:signal", bound_names={"signal"})
    recorder.release.set()
    assert queue.wait_until_idle(timeout=30)
    assert recorder.ran == ["c1", "emitted"]


def test_a_cell_the_person_ran_is_never_frozen(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-025 freezes *panel submissions*, not the person's own run."""
    recorder.hold = "c1"
    recorder.release.clear()
    queue = execution_queue(changed_names_of=lambda request: frozenset({"df"}))
    queue.submit_cell("c1")
    assert recorder.started.wait(timeout=30)
    queue.submit_cell("c2")  # no bound names: the person, not a panel
    recorder.release.set()
    assert queue.wait_until_idle(timeout=30)
    assert recorder.ran == ["c1", "c2"]


def test_the_freeze_is_armed_before_the_request_is_visible_as_running(recorder: _Recorder) -> None:
    """FR-025 has no window: a request is never published as running with an empty frozen set.

    Read the changed set late enough and a panel slips an emission in between the
    request going to ``running`` and its names arriving. This drives that window
    directly: the callback blocks, and a panel that emits while it is blocked
    must still be refused.
    """
    asked = threading.Event()
    proceed = threading.Event()

    def changed_names_of(request: ExecutionRequest) -> frozenset[str]:
        asked.set()
        assert proceed.wait(timeout=30)
        return frozenset({"df"})

    recorder.hold = "c1"
    recorder.release.clear()
    queue = ExecutionQueue(recorder, changed_names_of=changed_names_of)
    queue.start()
    try:
        queue.submit_cell("c1")
        assert asked.wait(timeout=30), "the queue never asked for the changed set"
        # The request is mid-take: not yet published as running.
        assert queue.running is None
        proceed.set()
        assert recorder.started.wait(timeout=30)
        with pytest.raises(PanelFrozenError):
            queue.submit_cell("emitted", kind=RequestKind.SNIPPET, panel="table:df", bound_names={"df"})
    finally:
        proceed.set()
        recorder.release.set()
        queue.stop(timeout=10)


def test_stopping_cancels_what_is_queued_and_never_the_running_request(
    execution_queue: Callable[..., ExecutionQueue], recorder: _Recorder
) -> None:
    """FR-017: a running request is not cancelled except by an explicit interrupt."""
    recorder.hold = "c1"
    recorder.release.clear()
    queue = execution_queue()
    queue.submit_cell("c1")
    assert recorder.started.wait(timeout=30)
    queued = queue.submit_cell("c2")

    stopper = threading.Thread(target=lambda: queue.stop(timeout=30))
    stopper.start()
    time.sleep(0.1)
    recorder.release.set()
    stopper.join(timeout=30)

    assert queued.state is RequestState.CANCELLED
    assert recorder.ran == ["c1"], "the running request completed; the queued one did not start"


def test_a_runner_that_raises_leaves_the_queue_alive(execution_queue: Callable[..., ExecutionQueue]) -> None:
    """A dead kernel must not take the queue with it."""
    seen: list[str] = []

    def runner(request: ExecutionRequest) -> None:
        seen.append(request.cell_id)
        if request.cell_id == "boom":
            raise RuntimeError("the kernel died")

    queue = ExecutionQueue(runner)
    queue.start()
    try:
        failing = queue.submit_cell("boom")
        queue.submit_cell("after")
        assert queue.wait_until_idle(timeout=30)
        assert failing.state is RequestState.FAILED
        assert isinstance(failing.error, RuntimeError)
        assert seen == ["boom", "after"]
    finally:
        queue.stop(timeout=10)


# ---------------------------------------------------------------------------
# FR-019 to FR-024: the marks, on the A, B, C fixture of User Story 2.
#
# These run a real ipykernel. See the module docstring for why. They are skipped
# rather than substituted where the dependency is absent, and they carry the
# serial marker because they spawn processes (#1867).
# ---------------------------------------------------------------------------


needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

#: Long enough that a loaded machine does not flake starting a kernel, and
#: short enough that it fires before the suite's 60s per-test wall-clock kill,
#: so a stuck queue fails with this assertion rather than with a timeout.
_IDLE_TIMEOUT = 40.0

#: The A, B, C fixture of User Story 2: three cells that each bind ``df``, the
#: second and third reading the one above. Plain lists, so the fingerprints are
#: content fingerprints and no third-party package has to be importable in the
#: kernel for the observation to be real.
STORY_TWO_CELLS = (
    "df = [1, 2, 3, 4]",
    "df = df[:3]",
    "df = df[:2]",
)


@pytest.fixture
def project_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``scistudio`` importable from a kernel started in the project directory.

    A source checkout reaches the interpreter through a *relative*
    ``PYTHONPATH=./src``, which stops resolving the moment a process starts
    somewhere else — and the session deliberately starts its kernel in the
    project, because that is where a notebook's relative paths are read from. An
    installed SciStudio needs none of this; a checkout does.
    """
    import scistudio

    root = Path(scistudio.__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    entries = [str(root), *(entry for entry in existing.split(os.pathsep) if entry)]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(entries))


@pytest.fixture
def services(tmp_path: Path, project_pythonpath: None) -> Iterator[Callable[..., SessionService]]:
    """Hand out session services and guarantee every kernel they started is gone.

    Cleanup records each pid *before* shutting down, so a session that has
    already forgotten its process is still reaped, and kills anything that
    outlives a polite shutdown. It runs on the failure path as well.
    """
    made: list[SessionService] = []

    def make(**kwargs: object) -> SessionService:
        service = SessionService(tmp_path, **kwargs)  # type: ignore[arg-type]
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


@pytest.fixture
def abc_session(services: Callable[..., SessionService]) -> tuple[ExploreSession, tuple[str, str, str]]:
    """A session holding the A, B, C fixture, with all three cells run in order.

    At the end of this fixture the notebook is in the state User Story 2 opens
    with: everything has run, in order, and nothing carries a mark.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, STORY_TWO_CELLS[0])
    cell_b = session.insert_cell(STORY_TWO_CELLS[1], after=first)
    cell_c = session.insert_cell(STORY_TWO_CELLS[2], after=cell_b)

    for cell_id in (first, cell_b, cell_c):
        session.run_cell(cell_id)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    return session, (first, cell_b, cell_c)


def _enqueued(action: Callable[[], object]) -> list[str]:
    """Every cell *action* enqueued, in the order it enqueued them.

    Reads the requests the control returned rather than watching the queue
    drain, so a control that enqueued a cell which then coalesced away is still
    counted honestly.
    """
    requests = action()
    if isinstance(requests, ExecutionRequest):
        requests = (requests,)
    return [request.cell_id for request in requests]  # type: ignore[union-attr]


@needs_kernel
@pytest.mark.serial
def test_the_abc_fixture_starts_clean_with_nothing_marked(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """Running A, B, C in order leaves nothing questionable and ``df`` bound by C."""
    session, (cell_a, cell_b, cell_c) = abc_session
    assert session.marks(cell_a) == frozenset()
    assert session.marks(cell_b) == frozenset()
    assert session.marks(cell_c) == frozenset()
    assert session.last_bound_by["df"] == cell_c


@needs_kernel
@pytest.mark.serial
def test_rerunning_b_marks_it_out_of_order_marks_c_stale_and_runs_nothing(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """US2 scenarios 1 and 2, and FR-022's 'MUST NOT enqueue any cell on its own account'.

    B reads C's ``df``, as it would in Jupyter. It is marked out of order, C is
    marked stale, and **nothing else runs** — the second half is the claim the
    whole design rests on.
    """
    session, (cell_a, cell_b, cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:3]  # edited")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert CellMark.OUT_OF_ORDER in session.marks(cell_b)
    reads = session.out_of_order_reads(cell_b)
    assert [(read.name, read.definer, read.last_binder) for read in reads] == [("df", cell_a, cell_c)]
    assert CellMark.STALE in session.marks(cell_c)
    assert session.marks(cell_a) == frozenset(), "A was not touched"

    assert session.queue.pending == (), "marking enqueued nothing"
    assert session.queue.running is None


@needs_kernel
@pytest.mark.serial
def test_marking_alone_enqueues_nothing_at_all(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """Spec §4.1: neither the before-run comparison nor the after-run propagation enqueues.

    Counted at the queue rather than inferred from the marks: every request that
    reached the queue over the whole re-run must be the one cell the person named.
    """
    session, (_cell_a, cell_b, _cell_c) = abc_session
    submitted: list[str] = []
    original = session.queue.submit_cell

    def watch(cell_id: str, **kwargs: object) -> object:
        submitted.append(cell_id)
        return original(cell_id, **kwargs)  # type: ignore[arg-type]

    session.queue.submit_cell = watch  # type: ignore[method-assign]
    try:
        session.set_cell_source(cell_b, "df = df[:3]  # edited")
        session.run_cell(cell_b)
        assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    finally:
        session.queue.submit_cell = original  # type: ignore[method-assign]

    assert submitted == [cell_b], f"the service enqueued cells nobody asked for: {submitted}"


@needs_kernel
@pytest.mark.serial
def test_run_with_upstream_runs_a_then_b_and_nothing_else(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """US2 scenario 3 and FR-024: the exact set, in written order.

    A is re-run because ``df`` is no longer last bound by A — the second clause
    of the skip rule. C is not in B's backward slice and is not touched.
    """
    session, (cell_a, cell_b, cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:3]  # edited")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    enqueued = _enqueued(lambda: session.run_with_upstream(cell_b))
    assert enqueued == [cell_a, cell_b], f"run-with-upstream enqueued {enqueued}"
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert session.marks(cell_b) == frozenset(), "B's marks clear once it reads A's df in order"
    assert CellMark.STALE in session.marks(cell_c), "C still reads a df B has since rebound"


@needs_kernel
@pytest.mark.serial
def test_run_stale_runs_the_stale_set_and_nothing_else(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """US2 scenario 4 and FR-024: the stale cells in written order, and nothing else."""
    session, (_cell_a, cell_b, cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:3]  # edited")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    session.run_with_upstream(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert session.stale_cells() == (cell_c,)
    enqueued = _enqueued(session.run_stale)
    assert enqueued == [cell_c], f"run-stale enqueued {enqueued}"
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(cell_c) == frozenset()


@needs_kernel
@pytest.mark.serial
def test_run_stale_does_not_run_an_out_of_order_cell(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """FR-024: run-stale enqueues *the stale cells*, not everything questionable.

    B is out of order and not stale. A control called run-stale that also ran B
    would be the service choosing a cell the person did not name.
    """
    session, (_cell_a, cell_b, cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:3]  # edited")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert CellMark.OUT_OF_ORDER in session.marks(cell_b)
    assert CellMark.STALE not in session.marks(cell_b)
    assert _enqueued(session.run_stale) == [cell_c]


@needs_kernel
@pytest.mark.serial
def test_run_with_upstream_skips_an_undisturbed_upstream_cell(
    services: Callable[..., SessionService],
) -> None:
    """FR-024's skip rule, on the input where it would otherwise run a cell nobody named.

    ``setup`` binds ``k``, which nothing has disturbed since: it carries no mark
    and ``k`` is still last bound by it. The person asks to run the cell below
    with its upstream, and only that cell runs — the whole point of the rule.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 2")
    user = session.insert_cell("scaled = k * 10", after=first)
    session.run_cell(first)
    session.run_cell(user)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(first) == frozenset()
    assert session.last_bound_by["k"] == first

    enqueued = _enqueued(lambda: session.run_with_upstream(user))
    assert enqueued == [user], f"the undisturbed upstream cell was re-run: {enqueued}"


@needs_kernel
@pytest.mark.serial
def test_run_with_upstream_runs_a_never_run_upstream_cell(
    services: Callable[..., SessionService],
) -> None:
    """FR-024's second clause carries a never-run cell.

    A never-run cell is neither stale nor out of order, so the first clause alone
    would skip it and the cell below would fail with a NameError. It runs because
    the name it changes is bound by nothing in the kernel.
    """
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 2")
    user = session.insert_cell("scaled = k * 10", after=first)

    assert CellMark.NEVER_RUN in session.marks(first)
    enqueued = _enqueued(lambda: session.run_with_upstream(user))
    assert enqueued == [first, user]
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert session.marks(first) == frozenset()
    assert session.last_bound_by["scaled"] == user


@needs_kernel
@pytest.mark.serial
def test_an_out_of_order_rerun_still_runs_the_cell(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """FR-019: 'The cell MUST run regardless.' The graph marks; it does not gate."""
    session, (_cell_a, cell_b, _cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:1]")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)
    assert CellMark.OUT_OF_ORDER in session.marks(cell_b)
    assert session.last_bound_by["df"] == cell_b
    assert session.observations[cell_b].changed_names == {"df"}


@needs_kernel
@pytest.mark.serial
def test_a_kernel_restart_resets_every_cell_to_never_run(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """FR-023: the marks are session state and the namespace is gone."""
    session, cells = abc_session
    session.restart_kernel()
    for cell_id in cells:
        assert session.marks(cell_id) == {CellMark.NEVER_RUN}
    assert session.last_bound_by == {}


@needs_kernel
@pytest.mark.serial
def test_an_emitted_snippet_lands_after_the_current_cell_and_runs(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """US3 scenario 1: an admitted emission becomes a cell after the current one."""
    session, (cell_a, cell_b, cell_c) = abc_session
    session.set_current_cell(cell_b)
    cell_id, _request = session.emit_snippet("df = df + [99]", panel="table:df", bound_names={"df"})
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    assert [cell.cell_id for cell in session.cells()] == [cell_a, cell_b, cell_id, cell_c]
    assert session.last_bound_by["df"] == cell_id


@needs_kernel
@pytest.mark.serial
def test_a_refused_emission_inserts_no_cell(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """US3 scenario 2: refused before it is queued, and the notebook is untouched."""
    session, cells = abc_session
    session.set_current_cell(cells[1])
    before = [cell.cell_id for cell in session.cells()]
    with pytest.raises(SnippetRefusedError):
        session.emit_snippet("df.drop(index=[3], inplace=True)", panel="table:df", bound_names={"df"})
    assert [cell.cell_id for cell in session.cells()] == before
    assert session.queue.pending == ()


@needs_kernel
@pytest.mark.serial
def test_the_cell_marks_seam_hands_packaging_three_sets(
    abc_session: tuple[ExploreSession, tuple[str, str, str]],
) -> None:
    """Packaging takes the marks as an argument and never reaches into the session."""
    session, (_cell_a, cell_b, cell_c) = abc_session
    session.set_cell_source(cell_b, "df = df[:3]  # edited")
    session.run_cell(cell_b)
    assert session.wait_until_idle(timeout=_IDLE_TIMEOUT)

    marks = session.cell_marks()
    assert marks.stale == {cell_c}
    assert marks.out_of_order == {cell_b}
    assert marks.never_run == frozenset()


@needs_kernel
@pytest.mark.serial
def test_a_disabled_cell_is_refused_rather_than_run(
    services: Callable[..., SessionService],
) -> None:
    """The analysis builds over enabled cells only, so a disabled cell has no graph row."""
    service = services()
    session = service.open_over_file("data/raw/signal.csv")
    first = session.cells()[0].cell_id
    assert first is not None
    session.set_cell_source(first, "k = 2")
    session.set_cell_enabled(first, enabled=False)
    with pytest.raises(SessionError, match="disabled"):
        session.run_cell(first)
    assert session.queue.pending == ()
