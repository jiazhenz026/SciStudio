"""The session's one execution queue, its admission whitelist, and its observation.

ADR-054 spec 3 task T-007, FR-017, FR-018, FR-021, FR-025.

ipykernel executes one request at a time, so the single queue ADR-054 §6.3 asks
for is really the kernel's own. What this module adds is everything that has to
sit *between* a person and that kernel:

**Admission** (FR-018). A cell the person wrote is theirs and runs as typed. A
snippet a *panel* emitted is machine-written code arriving from the UI, and it
is admitted only if every statement is an assignment to plain names, an import,
or a call to ``scistudio.output``. Anything else is **refused before it is
queued** and no cell is inserted. It is refused rather than sanitised because a
rewritten statement is a statement nobody wrote: the person would read one thing
in the notebook and the kernel would have run another.

**Ordering and coalescing** (FR-017). One worker thread takes one request at a
time in submission order. Submitting a cell that is already queued and has not
started coalesces with the queued request, so a person leaning on a button runs
the cell once.

**The freeze** (FR-025). While a request runs, a panel bound to a name that
request may change cannot emit. Reads are not blocked — a window request queues
behind the running cell in the kernel and completes when the cell does, which is
the shallow freeze ADR-054 §6.3 accepts. Only *submissions* are refused, and
only from panels whose name the run is about to move underneath them.

**The observation** (FR-021, analysis spec FR-026 and FR-029).
:func:`observe_namespaces` compares the namespace fingerprints taken before and
after a run and reports what the cell changed. :class:`Observation` exposes
``changed_names``, which is exactly the shape
:func:`scistudio.explore.dependency_analysis.build_graph` accepts, so the
observation is handed to the analysis without either module importing the other's
runtime.

Nothing here decides *which* cells to run: that is the session's, and the marks
never enqueue anything (spec §4.1, "Marks are bookkeeping, not execution").
"""

from __future__ import annotations

import ast
import itertools
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from scistudio.explore.dependency_analysis import OUTPUT_CALL_PATH
from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from scistudio.explore.fingerprint import Fingerprint

__all__ = [
    "ExecutionQueue",
    "ExecutionRequest",
    "Observation",
    "PanelFrozenError",
    "RequestKind",
    "RequestState",
    "SnippetRefusedError",
    "admit_snippet",
    "observe_namespaces",
]

_LOG = logging.getLogger(__name__)

#: How long the worker waits on the condition before looping, so that a stop
#: requested while the queue is empty is noticed promptly on every platform.
_WORKER_POLL_SECONDS: Final[float] = 0.05

#: What a panel is told it may emit. Written once, quoted in every refusal, so
#: the rule the code enforces and the rule the message states cannot drift.
_WHITELIST_SUMMARY: Final[str] = (
    "a panel may emit only an assignment whose every target is a plain name "
    "(including tuple and star unpacking), an import, or a call to scistudio.output"
)


@provisional(since="0.3.4")
class RequestKind(StrEnum):
    """What produced a request (FR-017)."""

    CELL = "cell"
    """A cell the person ran."""

    SNIPPET = "snippet"
    """A cell inserted from a snippet a panel emitted (FR-018)."""


@provisional(since="0.3.4")
class RequestState(StrEnum):
    """Where a request is in its life."""

    QUEUED = "queued"
    """Waiting. Only a queued request coalesces (FR-017)."""

    RUNNING = "running"
    """Handed to the kernel. Ends only by finishing or by an interrupt."""

    DONE = "done"
    """The runner returned. Says nothing about whether the cell raised — a cell
    that raised is a completed request whose result carries the error."""

    FAILED = "failed"
    """The runner itself raised, e.g. the kernel died mid-request."""

    CANCELLED = "cancelled"
    """The queue was stopped before this request started."""


@provisional(since="0.3.4")
@dataclass(eq=False)
class ExecutionRequest:
    """One unit of work on the queue (FR-017).

    Identity is the object, not the fields: two submissions of the same cell
    that were *not* coalesced are two requests, and a caller holding one can
    watch its own.
    """

    cell_id: str
    """The cell to run. A snippet is inserted as a cell before it is submitted,
    so every request names a cell by the time it reaches the queue."""

    kind: RequestKind = RequestKind.CELL
    """Whether the person ran a cell or a panel emitted one."""

    panel: str | None = None
    """The panel that emitted the snippet, for :class:`RequestKind.SNIPPET`."""

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """Stable id for this request, for events and logs."""

    submitted_at: float = field(default_factory=time.time)
    """``time.time()`` when the request was accepted."""

    state: RequestState = RequestState.QUEUED
    """Current state. Written by the queue under its lock."""

    coalesced: int = 0
    """How many further submissions were folded into this one (FR-017)."""

    error: BaseException | None = None
    """The exception the runner raised, when :attr:`state` is
    :attr:`RequestState.FAILED`."""

    def __repr__(self) -> str:
        return f"ExecutionRequest(cell_id={self.cell_id!r}, kind={self.kind.value!r}, state={self.state.value!r})"


@provisional(since="0.3.4")
class SnippetRefusedError(ValueError):
    """A panel emitted code outside the admission whitelist (FR-018).

    Carries the panel and the offending statement so the message the person
    sees names both, and so a caller can render them without parsing the text.
    """

    def __init__(self, message: str, *, panel: str, statement: str) -> None:
        super().__init__(message)
        self.panel = panel
        """The panel the emission came from."""
        self.statement = statement
        """The statement that was refused, as source."""


@provisional(since="0.3.4")
class PanelFrozenError(RuntimeError):
    """A panel tried to emit while a run may move a name it is bound to (FR-025).

    Reads are unaffected; only the submission is refused, and only until the
    running request ends.
    """

    def __init__(self, message: str, *, panel: str, names: frozenset[str]) -> None:
        super().__init__(message)
        self.panel = panel
        """The panel whose submission was refused."""
        self.names = names
        """The bound names the running request may change."""


# ---------------------------------------------------------------------------
# Admission (FR-018)
# ---------------------------------------------------------------------------


def _dotted_path(node: ast.expr) -> tuple[str, ...] | None:
    """The dotted path of ``a.b.c``, or ``None`` when the base is not a plain name.

    The same resolution
    :func:`scistudio.explore.dependency_analysis.analyse_cell` uses, so a call
    this whitelist admits as ``scistudio.output`` is a call the analysis records
    as an output declaration.
    """
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def _is_output_call(node: ast.stmt) -> bool:
    """Whether *node* is an expression statement calling ``scistudio.output``."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    path = _dotted_path(node.value.func)
    if path is None:
        return False
    return len(path) >= len(OUTPUT_CALL_PATH) and path[-len(OUTPUT_CALL_PATH) :] == OUTPUT_CALL_PATH


def _plain_name_target(target: ast.expr) -> bool:
    """Whether *target* binds plain names only.

    ``x``, ``a, b``, ``[a, b]``, and ``a, *rest`` are plain. ``d["k"]`` and
    ``obj.attr`` are not: FR-018 refuses them because they mutate the object the
    name holds rather than rebinding the name, and a panel that mutates an
    object leaves the notebook's source no longer describing what the kernel
    holds.
    """
    if isinstance(target, ast.Name):
        return True
    if isinstance(target, ast.Starred):
        return _plain_name_target(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        return all(_plain_name_target(element) for element in target.elts)
    return False


#: How each refused statement form is named in a message a person reads. A
#: person fixing a panel needs to be told what was refused in the words they
#: would use for it, not the name of an ``ast`` class.
_STATEMENT_NAMES: Final[dict[type[ast.stmt], str]] = {
    ast.AugAssign: "an augmented assignment",
    ast.AnnAssign: "an annotated assignment",
    ast.Delete: "a del statement",
    ast.For: "a for loop",
    ast.AsyncFor: "an async for loop",
    ast.While: "a while loop",
    ast.If: "an if statement",
    ast.With: "a with statement",
    ast.AsyncWith: "an async with statement",
    ast.Try: "a try statement",
    ast.Match: "a match statement",
    ast.FunctionDef: "a function definition",
    ast.AsyncFunctionDef: "an async function definition",
    ast.ClassDef: "a class definition",
    ast.Return: "a return statement",
    ast.Raise: "a raise statement",
    ast.Assert: "an assert statement",
    ast.Global: "a global statement",
    ast.Nonlocal: "a nonlocal statement",
    ast.Pass: "a pass statement",
    ast.Break: "a break statement",
    ast.Continue: "a continue statement",
}


def _target_description(target: ast.expr) -> str | None:
    """Name what an assignment target is, when it is not a plain name.

    Descends into tuple and list targets, so ``a, df["x"] = 1, 2`` is named for
    the subscript inside it rather than for the tuple around it.
    """
    if isinstance(target, ast.Subscript):
        return "an assignment to a subscript"
    if isinstance(target, ast.Attribute):
        return "an assignment to an attribute"
    if isinstance(target, ast.Starred):
        return _target_description(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            described = _target_description(element)
            if described is not None:
                return described
        return None
    if isinstance(target, ast.Name):
        return None
    return "an assignment to something other than a plain name"


def _describe(node: ast.stmt) -> str:
    """Name the statement form in the words a refusal message uses."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            described = _target_description(target)
            if described is not None:
                return described
        return "an assignment to something other than a plain name"  # pragma: no cover - admitted above
    if isinstance(node, ast.Expr):
        return "a bare expression"
    named = _STATEMENT_NAMES.get(type(node))
    if named is not None:
        return named
    article = "an" if type(node).__name__[0].lower() in "aeiou" else "a"
    return f"{article} {type(node).__name__} statement"


def _statement_source(node: ast.stmt, source: str) -> str:
    """The refused statement as source, preferring the person's own text."""
    segment = ast.get_source_segment(source, node)
    if segment:
        return segment.strip()
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse handles every node ast builds
        return f"<{type(node).__name__}>"


@provisional(since="0.3.4")
def admit_snippet(source: str, *, panel: str) -> ast.Module:
    """Parse and admit a snippet a panel emitted, or refuse it (FR-018).

    Called **before** anything is inserted or queued, which is the whole point:
    a refused emission leaves the notebook exactly as it was.

    Admitted:

    * an assignment whose every target is a plain name, including chained
      assignment and tuple or star unpacking of plain names;
    * an ``import`` or ``from ... import``;
    * an expression statement calling ``scistudio.output``.

    Everything else is refused, including an augmented assignment (``df += 1``
    runs ``__iadd__``, which mutates in place for the containers a panel binds
    to) and an annotated assignment (its annotation is a claim about the name
    that the panel has no way to keep true). A snippet with no statement at all
    is refused too: it would insert an empty cell and run it for no effect.

    Args:
        source: The emitted code.
        panel: The panel that emitted it, named in every refusal.

    Returns:
        The parsed module, so a caller need not parse it twice.

    Raises:
        SnippetRefusedError: The snippet does not parse, holds no statement, or
            holds a statement outside the whitelist.

    Example:
        >>> _ = admit_snippet("df = df.drop(index=[3, 7])", panel="table:df")
        >>> admit_snippet("df.drop(index=[3], inplace=True)", panel="table:df")
        Traceback (most recent call last):
        ...
        scistudio.explore.queue.SnippetRefusedError: ...
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        message = (
            f"Panel {panel!r} emitted code that is not valid Python "
            f"({error.msg} on line {error.lineno}); {_WHITELIST_SUMMARY}."
        )
        raise SnippetRefusedError(message, panel=panel, statement=source.strip()) from error

    if not tree.body:
        message = f"Panel {panel!r} emitted no statement; {_WHITELIST_SUMMARY}."
        raise SnippetRefusedError(message, panel=panel, statement=source.strip())

    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Assign) and all(_plain_name_target(target) for target in node.targets):
            continue
        if _is_output_call(node):
            continue
        statement = _statement_source(node, source)
        message = (
            f"Panel {panel!r} emitted {_describe(node)} on line {node.lineno}, which a session will not run: "
            f"{statement!r}. It is refused rather than rewritten, because a rewritten statement is one nobody "
            f"wrote. Please note that {_WHITELIST_SUMMARY}."
        )
        raise SnippetRefusedError(message, panel=panel, statement=statement)

    return tree


# ---------------------------------------------------------------------------
# The observation around a run (FR-021)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Observation:
    """What one run was observed to change (FR-021, analysis FR-026 to FR-030).

    Keyed to the hash of the cell's source at the time of the run, so the
    analysis discards it when the source changes and the static estimate alone
    governs until the cell runs again (analysis FR-027).

    Handed straight to
    :func:`~scistudio.explore.dependency_analysis.build_graph` as an
    observation: it exposes ``changed_names``, which is the attribute that
    function reads.
    """

    cell_id: str
    """The cell that ran."""

    source_hash: str
    """:func:`~scistudio.explore.dependency_analysis.source_hash` of the source
    that ran."""

    differing: frozenset[str] = frozenset()
    """Names bound before and after whose fingerprint moved."""

    appeared: frozenset[str] = frozenset()
    """Names the run bound that were not bound before."""

    disappeared: frozenset[str] = frozenset()
    """Names the run unbound."""

    unobservable: frozenset[str] = frozenset()
    """Names whose fingerprint fell back to identity and did not move
    (analysis FR-029).

    Equality proves nothing about these, so they are reported rather than
    guessed at. They are deliberately **not** in :attr:`changed_names`: calling
    every module, function, and figure in the namespace "changed" on every run
    would make the last-bound-by map claim each cell rebinds all of them, and
    every cell below would be stale for ever.
    """

    @property
    def changed_names(self) -> frozenset[str]:
        """The observed changed set (analysis FR-026).

        The union of what moved, what appeared, and what was unbound. This is
        the attribute :func:`build_graph` reads, and per analysis FR-030 it only
        ever *adds* to a cell's changed set.
        """
        return self.differing | self.appeared | self.disappeared


@provisional(since="0.3.4")
def observe_namespaces(
    before: Mapping[str, Fingerprint],
    after: Mapping[str, Fingerprint],
    *,
    cell_id: str,
    source_hash: str,
) -> Observation:
    """Compare two namespace fingerprints and report what the run changed.

    Args:
        before: Fingerprints of every top-level name before the run.
        after: Fingerprints of every top-level name after it.
        cell_id: The cell that ran.
        source_hash: Hash of the source that ran, which keys the observation.

    Returns:
        The :class:`Observation`.

    Example:
        >>> from scistudio.explore.fingerprint import fingerprint
        >>> before = {"df": fingerprint([1, 2])}
        >>> after = {"df": fingerprint([1]), "n": fingerprint(1)}
        >>> sorted(observe_namespaces(before, after, cell_id="c1", source_hash="h").changed_names)
        ['df', 'n']
    """
    before_names = set(before)
    after_names = set(after)
    shared = before_names & after_names

    differing = {name for name in shared if before[name].digest != after[name].digest}
    unobservable = {name for name in shared - differing if not before[name].observable or not after[name].observable}
    return Observation(
        cell_id=cell_id,
        source_hash=source_hash,
        differing=frozenset(differing),
        appeared=frozenset(after_names - before_names),
        disappeared=frozenset(before_names - after_names),
        unobservable=frozenset(unobservable),
    )


# ---------------------------------------------------------------------------
# The queue itself (FR-017, FR-025)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class ExecutionQueue:
    """One session's execution queue: one request at a time, in submission order.

    A worker thread takes requests and hands each to *runner*. The runner is the
    session's: it writes the notebook, fingerprints, executes, observes, and
    marks. The queue knows none of that; it knows order, coalescing, and the
    freeze.

    Threading contract: :meth:`submit_cell`, :meth:`pending`, :meth:`running`,
    and :meth:`wait_until_idle` are safe to call from any thread while a request
    is running — a panel emitting while a cell runs is the case FR-025 exists
    for. The runner runs on the worker thread and nothing else runs there.

    Args:
        runner: Called with each request, on the worker thread. An exception it
            raises marks the request failed and is logged; the queue keeps
            running, because one cell that killed a kernel must not silently
            take the queue with it.
        changed_names_of: Asked, once per request as it starts, for the names
            that request may change — the union the analysis reports (FR-025).
            Defaults to a session with no analysis, where nothing is frozen.
        thread_name: Worker thread name, for a stack dump that has to be read.

    Example::

        queue = ExecutionQueue(runner=session._run)
        queue.start()
        queue.submit_cell("c1")
        queue.wait_until_idle(timeout=30)
        queue.stop()
    """

    def __init__(
        self,
        runner: Callable[[ExecutionRequest], None],
        *,
        changed_names_of: Callable[[ExecutionRequest], frozenset[str]] | None = None,
        thread_name: str = "scistudio-explore-queue",
    ) -> None:
        self._runner = runner
        self._changed_names_of = changed_names_of
        self._thread_name = thread_name

        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._pending: list[ExecutionRequest] = []
        self._running: ExecutionRequest | None = None
        self._running_names: frozenset[str] = frozenset()
        self._worker: threading.Thread | None = None
        self._stopping = False
        self._counter = itertools.count()

    # -- state ------------------------------------------------------------

    @property
    def running(self) -> ExecutionRequest | None:
        """The request the kernel is executing, or ``None``."""
        with self._lock:
            return self._running

    @property
    def running_changed_names(self) -> frozenset[str]:
        """The names the running request may change; empty when idle (FR-025)."""
        with self._lock:
            return self._running_names

    @property
    def pending(self) -> tuple[ExecutionRequest, ...]:
        """The queued requests, in submission order."""
        with self._lock:
            return tuple(self._pending)

    @property
    def is_idle(self) -> bool:
        """Whether nothing is running and nothing is queued."""
        with self._lock:
            return self._running is None and not self._pending

    @property
    def is_started(self) -> bool:
        """Whether the worker thread is alive."""
        worker = self._worker
        return worker is not None and worker.is_alive()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Start the worker thread. Idempotent."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stopping = False
            self._worker = threading.Thread(target=self._loop, name=self._thread_name, daemon=True)
            self._worker.start()

    def stop(self, *, timeout: float | None = 30.0) -> None:
        """Stop the worker after the running request ends, cancelling the rest.

        A running request is never cancelled from here (FR-017): the only thing
        that ends a running cell early is an explicit interrupt, which reaches
        the kernel rather than the queue.

        Args:
            timeout: Seconds to wait for the worker to exit. ``None`` waits.
        """
        with self._lock:
            self._stopping = True
            for request in self._pending:
                request.state = RequestState.CANCELLED
            self._pending.clear()
            worker = self._worker
            self._wake.notify_all()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=timeout)
        with self._lock:
            if self._worker is worker:
                self._worker = None

    # -- submission -------------------------------------------------------

    def submit_cell(
        self,
        cell_id: str,
        *,
        kind: RequestKind = RequestKind.CELL,
        panel: str | None = None,
        bound_names: Iterable[str] = (),
    ) -> ExecutionRequest:
        """Queue *cell_id*, coalescing with a queued submission of the same cell.

        Args:
            cell_id: The cell to run.
            kind: Whether the person ran a cell or a panel emitted one.
            panel: The emitting panel, for a snippet.
            bound_names: The names the emitting panel is bound to. Checked
                against the running request's changed set (FR-025); an empty set
                is never frozen, which is what makes a cell the person ran
                submittable while another runs.

        Returns:
            The queued request — the *existing* one when the submission
            coalesced, with its :attr:`~ExecutionRequest.coalesced` count raised.

        Raises:
            PanelFrozenError: A panel bound to a name the running request may
                change tried to emit (FR-025).
            RuntimeError: The queue is stopping.
        """
        names = frozenset(bound_names)
        with self._lock:
            if self._stopping:
                raise RuntimeError("The execution queue is stopping; it accepts no further requests.")
            if names and self._running is not None:
                clash = names & self._running_names
                if clash:
                    message = (
                        f"Panel {panel!r} cannot emit while the cell {self._running.cell_id!r} is running: "
                        f"it may change {', '.join(sorted(clash))}. The panel keeps reading; try again when "
                        f"the run ends."
                    )
                    raise PanelFrozenError(message, panel=panel or "", names=frozenset(clash))
            for queued in self._pending:
                if queued.cell_id == cell_id and queued.state is RequestState.QUEUED:
                    queued.coalesced += 1
                    return queued
            request = ExecutionRequest(cell_id=cell_id, kind=kind, panel=panel)
            self._pending.append(request)
            self._wake.notify_all()
            return request

    def submit_cells(self, cell_ids: Sequence[str]) -> tuple[ExecutionRequest, ...]:
        """Queue several cells in the order given, coalescing each.

        This is how run-stale and run-with-upstream reach the kernel: the
        session decides the cells and their order, the queue only keeps it.
        """
        return tuple(self.submit_cell(cell_id) for cell_id in cell_ids)

    # -- waiting ----------------------------------------------------------

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is running or queued.

        Packaging waits on this before it checks the marks, because the slice's
        marks are not final until the queue has drained (spec §2, edge cases).

        Args:
            timeout: Seconds to wait, or ``None`` to wait as long as it takes.

        Returns:
            ``True`` when the queue went idle, ``False`` when *timeout* elapsed.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            while self._running is not None or self._pending:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._wake.wait(timeout=remaining if remaining is not None else _WORKER_POLL_SECONDS)
            return True

    # -- the worker -------------------------------------------------------

    def _loop(self) -> None:
        while True:
            request = self._take()
            if request is None:
                return
            try:
                self._runner(request)
            except BaseException as error:  # a dead kernel must not take the queue with it
                request.state = RequestState.FAILED
                request.error = error
                _LOG.exception("Explore execution request %s failed", request.request_id)
            else:
                request.state = RequestState.DONE
            finally:
                with self._lock:
                    self._running = None
                    self._running_names = frozenset()
                    self._wake.notify_all()

    def _take(self) -> ExecutionRequest | None:
        """Block until there is a request to run, or the queue is stopping.

        The changed set is read *before* the request is published as running, so
        there is no window in which a panel sees a running request with an empty
        frozen set and slips an emission past FR-025. Reading it outside the lock
        keeps a submission arriving meanwhile from waiting on the analysis; the
        worker is the only thread that pops, so the head cannot move underneath
        this — only :meth:`stop` can clear it, which the identity re-check
        catches.
        """
        while True:
            with self._lock:
                while not self._pending:
                    if self._stopping:
                        return None
                    self._wake.wait(timeout=_WORKER_POLL_SECONDS)
                request = self._pending[0]
            names = self._frozen_names_for(request)
            with self._lock:
                if not self._pending or self._pending[0] is not request:
                    continue  # stop() cleared the queue while we were asking
                self._pending.pop(0)
                request.state = RequestState.RUNNING
                self._running = request
                self._running_names = names
                self._wake.notify_all()
                return request

    def _frozen_names_for(self, request: ExecutionRequest) -> frozenset[str]:
        """The names *request* may change, for the freeze of FR-025."""
        if self._changed_names_of is None:
            return frozenset()
        try:
            return frozenset(self._changed_names_of(request))
        except Exception:  # an unanalysed cell freezes nothing rather than failing the run
            _LOG.debug("Could not read the changed set of %s", request.cell_id, exc_info=True)
            return frozenset()

    def __repr__(self) -> str:
        with self._lock:
            return f"ExecutionQueue(running={self._running!r}, pending={len(self._pending)}, started={self.is_started})"
