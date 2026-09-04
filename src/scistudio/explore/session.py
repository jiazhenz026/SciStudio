"""The Explore session: the notebook, the marks, and the service that owns both.

ADR-054 spec 3 tasks T-006, T-008, and T-016; FR-001 to FR-006, FR-014,
FR-016, FR-019 to FR-026, and FR-036.

A session is a notebook file in ``{project}/explore/`` plus an optional
ipykernel. :class:`SessionService` opens one over a block's outputs, over a file
in the data tree, or over the inputs of a run paused at an interactive block; it
lists them, closes them, commits them, and owns every kernel in the project.

**Marks are bookkeeping, not execution** (spec §4.1). This module keeps which
cell last bound each name in the kernel, updated from each run's observed
changed set. *Before* a run it asks the graph for the definer of each name the
cell reads and compares the two; a mismatch marks the run out of order, and the
cell runs anyway, because execution semantics are Jupyter's and nothing is
rebound or re-run on the graph's account. *After* a run it asks the graph for
the downstream set and marks it stale. **Neither step enqueues anything.**

:meth:`ExploreSession.run_with_upstream` is the one place the service chooses
cells on the person's behalf, and its skip rule is exact (FR-024): a cell in the
backward slice is skipped only if it is neither stale nor out of order *and*
every name it changes is still last bound by it in the kernel. On the A, B, C
case of User Story 2 that re-runs A and nothing else; on an undisturbed chain it
re-runs nothing upstream.

The subsystem's layering (FR-008): this module imports ``core`` for storage,
lineage, and versioning and the rest of ``explore``. It imports neither the API,
nor AI, nor the engine, and the engine never imports it —
``tests/architecture/test_layer_deps.py`` asserts both halves.
"""

from __future__ import annotations

import keyword
import logging
import queue as stdlib_queue
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final, Protocol

from scistudio.explore.dependency_analysis import (
    CellFacts,
    DependencyGraph,
    analyse_cells,
    build_graph,
    source_hash,
)
from scistudio.explore.notebook import (
    NotebookCell,
    NotebookDocument,
    NotebookStore,
    NotebookStoreError,
    new_code_cell,
    new_notebook,
)
from scistudio.explore.notebook_api import encode_artefact_reference
from scistudio.explore.queue import (
    ExecutionQueue,
    ExecutionRequest,
    Observation,
    PanelFrozenError,
    RequestKind,
    admit_snippet,
    observe_namespaces,
)
from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from scistudio.core.lineage.store import LineageStore
    from scistudio.core.versioning.git_engine import GitEngine
    from scistudio.explore.kernel import ExecutionResult, KernelHandle, KernelStatus
    from scistudio.explore.kernel_bridge import Binding, KernelBridge
    from scistudio.explore.packaging import CellMarks

__all__ = [
    "EXPLORE_DIR_NAME",
    "BlockOutputResolver",
    "BoundRun",
    "CellMark",
    "ExploreSession",
    "KernelListing",
    "LineageBlockOutputResolver",
    "NothingToExploreError",
    "OutOfOrderRead",
    "PortArtefact",
    "SessionError",
    "SessionEvent",
    "SessionEventType",
    "SessionListing",
    "SessionService",
    "UnknownSessionError",
]

_LOG = logging.getLogger(__name__)

#: The project directory a session's notebook lives in (FR-001, A-003).
#:
#: ``scistudio.api.project_layout`` creates this directory when a project is
#: scaffolded and spells the same name. It is spelled twice on purpose: the
#: explore subsystem must not import the API layer (FR-008), and
#: ``project_layout`` is a leaf module a fast ``scistudio init`` pays for, which
#: importing this module — and through it ``jupyter_client`` — would end.
#: ``tests/explore/test_explore_session.py`` pins the two spellings together, so
#: the folder a project offers and the folder a session opens in cannot drift.
EXPLORE_DIR_NAME: Final[str] = "explore"

#: Notebook-level metadata key holding the ref-safe session id (FR-001).
SESSION_ID_METADATA_KEY: Final[str] = "session_id"

#: What a session id may look like, so that a notebook path containing a
#: character git refuses in a ref name never reaches ``update-ref`` (FR-001).
#: Matches ``_commit_ops._SESSION_ID_RE``, which is the backstop this satisfies.
_SESSION_ID_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: How many times a failed explore commit is retried before it is reported once
#: (FR-030). Small: a commit that fails three times is failing for a reason a
#: fourth attempt will not fix, and the run it belongs to already returned.
_COMMIT_ATTEMPTS: Final[int] = 3

#: Seconds between explore-commit retries.
_COMMIT_RETRY_SECONDS: Final[float] = 0.2

#: Characters a port or file name may contribute to a Python identifier.
_NON_IDENTIFIER = re.compile(r"\W")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class SessionError(RuntimeError):
    """Base class for the session service's refusals."""


@provisional(since="0.3.4")
class NothingToExploreError(SessionError):
    """A session was requested over outputs that have never been produced (FR-002)."""


@provisional(since="0.3.4")
class UnknownSessionError(SessionError, KeyError):
    """No session is open at the given notebook path or session id."""

    def __str__(self) -> str:  # KeyError would render the message with quotes
        return str(self.args[0]) if self.args else ""


# ---------------------------------------------------------------------------
# The marks (FR-019, FR-020, FR-022, FR-023)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class CellMark(StrEnum):
    """What a session says about a cell (FR-023).

    Session state, not notebook state: a kernel restart resets every cell to
    :attr:`NEVER_RUN`, because the namespace the other two marks describe is
    gone. A cell carries a *set* of these — a cell can be stale and out of order
    at once, and they are cleared independently.
    """

    NEVER_RUN = "never_run"
    """The cell has not run in this kernel."""

    STALE = "stale"
    """A cell this one reads from ran after it did (FR-022)."""

    OUT_OF_ORDER = "out_of_order"
    """A name this cell read was last bound by a cell other than the one written
    order says defines it (FR-019)."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class OutOfOrderRead:
    """Why a cell was marked out of order: one name and the two cells (FR-019).

    The reason is kept rather than recomputed so the frontend can say *which*
    read was out of order and against which cell, which is the difference
    between a mark a person can act on and a mark they learn to ignore.
    """

    name: str
    """The name the cell read."""

    definer: str | None
    """The cell written order says defines it, or ``None`` when no cell above does."""

    last_binder: str | None
    """The cell that last bound it in the kernel, or ``None`` when nothing has."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PortArtefact:
    """One port of a bound run, and where its object lives (FR-003)."""

    name: str
    """The port name; also the variable the generated first cell binds."""

    type_name: str
    """The SciStudio type recorded for the artefact, e.g. ``"DataFrame"``."""

    backend: str
    """The storage backend that holds it."""

    path: str
    """The artefact's path within that backend."""

    format: str | None = None
    """The backend's format hint, when it has one."""

    def reference(self) -> str:
        """The ``scistudio+artefact:`` reference session-mode ``input`` returns."""
        return encode_artefact_reference(
            type_name=self.type_name,
            backend=self.backend,
            path=self.path,
            format=self.format,
        )


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BoundRun:
    """The run a session is bound to, and the ports it was opened over (FR-003)."""

    run_id: str
    """The run whose ports these are."""

    block_id: str
    """The block within that run."""

    opened_over: str
    """``"block_outputs"`` or ``"paused_run"``, as ``explore_sessions`` records it."""

    ports: tuple[PortArtefact, ...]
    """The ports, in the order the generated first cell binds them."""

    def inputs(self) -> dict[str, str]:
        """Port name to artefact reference, for ``KernelBridge.install``."""
        return {port.name: port.reference() for port in self.ports}


@provisional(since="0.3.4")
class BlockOutputResolver(Protocol):
    """Where a session's bound ports come from.

    A protocol rather than a concrete dependency so the session service does not
    have to know how a project records its runs.
    :class:`LineageBlockOutputResolver` is the implementation over the lineage
    store; the API layer may pass another.
    """

    def latest_block_outputs(self, block_id: str) -> BoundRun | None:
        """The outputs of the most recent completed run of *block_id* (FR-003)."""
        ...

    def run_block_outputs(self, run_id: str, block_id: str) -> BoundRun | None:
        """The outputs *block_id* wrote in *run_id*."""
        ...

    def paused_run_inputs(self, run_id: str, block_id: str) -> BoundRun | None:
        """The inputs *block_id* received in *run_id* (FR-002, a paused run)."""
        ...


@provisional(since="0.3.4")
@dataclass(frozen=True)
class KernelListing:
    """One row of the kernel list (FR-016)."""

    session_id: str
    """The session that owns the kernel."""

    notebook_path: str
    """The notebook, project-relative, which is how the API addresses it."""

    status: KernelStatus
    """The kernel's state, pid, and memory, read from outside the process."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class SessionListing:
    """One row of the session list (FR-006)."""

    notebook_path: str
    """Project-relative path of the notebook."""

    session_id: str | None
    """The id in the notebook's metadata, or ``None`` when it could not be read."""

    has_kernel: bool
    """Whether a kernel is alive for it right now."""

    is_open: bool
    """Whether the service holds a session for it."""

    readable: bool = True
    """``False`` when the file is on disk but is not a notebook this can parse."""


@provisional(since="0.3.4")
class SessionEventType(StrEnum):
    """The events the service publishes (FR-057).

    The transport is the caller's: :meth:`SessionService.subscribe` takes a
    callback, and the API layer adapts these onto the WebSocket hub.
    """

    SESSION_OPENED = "session_opened"
    SESSION_CLOSED = "session_closed"
    KERNEL_STATE = "kernel_state"
    CELL_STATE = "cell_state"
    CELL_OUTPUT = "cell_output"
    CHANGED_NAMES = "changed_names"
    ANALYSIS_UPDATED = "analysis_updated"
    COMMIT_RECORDED = "commit_recorded"
    PACKAGED = "packaged"


@provisional(since="0.3.4")
@dataclass(frozen=True)
class SessionEvent:
    """One message for the frontend (FR-057)."""

    type: SessionEventType
    """Which event this is."""

    session_id: str
    """The session it concerns."""

    payload: Mapping[str, Any] = field(default_factory=dict)
    """Event-specific fields."""


# ---------------------------------------------------------------------------
# The session (FR-001 to FR-006, FR-019 to FR-026)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class ExploreSession:
    """One notebook, its optional kernel, its queue, and its marks.

    Built by :class:`SessionService`; not constructed directly, because a
    session's notebook, its id, and its binding to a run are decided when it is
    opened and never afterwards.

    Threading: the queue runs each request on its own worker thread, and every
    read of the marks, the graph, or the document takes the session's state
    lock, so the API layer can ask what a cell's marks are while another cell is
    running. The kernel handle serialises execution on its own lock and
    deliberately does not lock
    :meth:`~scistudio.explore.kernel.KernelHandle.status`, which is what lets
    the kernel list of FR-016 answer while a cell is stuck.
    """

    def __init__(
        self,
        *,
        service: SessionService,
        session_id: str,
        notebook_path: Path,
        project_dir: Path,
        document: NotebookDocument,
        store: NotebookStore,
        bound_run: BoundRun | None = None,
    ) -> None:
        self._service = service
        self._session_id = session_id
        self._path = notebook_path
        self._project_dir = project_dir
        self._document = document
        self._store = store
        self._bound_run = bound_run

        self._state_lock = threading.RLock()
        self._facts: tuple[CellFacts, ...] = ()
        self._graph: DependencyGraph | None = None
        self._observations: dict[str, Observation] = {}
        self._marks: dict[str, set[CellMark]] = {}
        self._reasons: dict[str, tuple[OutOfOrderRead, ...]] = {}
        self._last_bound_by: dict[str, str] = {}
        self._current_cell: str | None = None
        self._needs_restart = False
        self._last_commit_sha: str | None = None
        self._branch_commit_digest: str | None = None
        self._closed = False

        self._handle: KernelHandle | None = None
        self._bridge: KernelBridge | None = None
        self._kernel_lock = threading.RLock()

        self._queue = ExecutionQueue(
            self._run_request,
            changed_names_of=self._changed_names_of,
            thread_name=f"scistudio-explore-{session_id}",
        )
        self._rebuild()
        self._queue.start()

    # -- identity ---------------------------------------------------------

    @property
    def session_id(self) -> str:
        """The ref-safe id in the notebook's metadata (FR-001)."""
        return self._session_id

    @property
    def notebook_path(self) -> Path:
        """The notebook file this session owns."""
        return self._path

    @property
    def relative_path(self) -> str:
        """The notebook's project-relative POSIX path, which addresses it (FR-001)."""
        return _relative_posix(self._path, self._project_dir)

    @property
    def bound_run(self) -> BoundRun | None:
        """The run this session was opened over, or ``None`` for a file (FR-003)."""
        return self._bound_run

    @property
    def queue(self) -> ExecutionQueue:
        """This session's one execution queue (FR-017)."""
        return self._queue

    @property
    def needs_restart(self) -> bool:
        """Whether the kernel was retired underneath the session (FR-014)."""
        with self._state_lock:
            return self._needs_restart

    @property
    def notebook_commit(self) -> str | None:
        """The commit of the last cell run on the session's ref (FR-035)."""
        with self._state_lock:
            return self._last_commit_sha

    # -- the notebook (FR-005, FR-027, FR-033) ----------------------------

    @property
    def document(self) -> NotebookDocument:
        """The notebook as the session holds it. Read it; write through the methods."""
        with self._state_lock:
            return self._document

    def cells(self) -> tuple[NotebookCell, ...]:
        """Every cell in written order, markdown included."""
        with self._state_lock:
            return self._document.cells

    def cell_source(self, cell_id: str) -> str:
        """The source of one cell.

        Raises:
            KeyError: No cell carries that id.
        """
        with self._state_lock:
            return self._document.cell(cell_id).source

    def set_cell_source(self, cell_id: str, source: str) -> None:
        """Persist an edit and re-run the analysis (FR-005).

        Raises:
            KeyError: No cell carries that id.
        """
        with self._state_lock:
            self._document.set_cell_source(cell_id, source)
            self._store.write(self._document)
            self._rebuild()
        self._emit(SessionEventType.ANALYSIS_UPDATED, {"reason": "cell_edited", "cell_id": cell_id})

    def set_cell_enabled(self, cell_id: str, *, enabled: bool) -> None:
        """Toggle a cell's enabled flag and re-run the analysis (FR-033).

        Raises:
            KeyError: No cell carries that id.
        """
        with self._state_lock:
            self._document.set_cell_enabled(cell_id, enabled=enabled)
            self._store.write(self._document)
            self._rebuild()
        self._emit(SessionEventType.ANALYSIS_UPDATED, {"reason": "cell_enabled", "cell_id": cell_id})

    def insert_cell(self, source: str = "", *, after: str | None = None) -> str:
        """Insert a code cell and return its id.

        Args:
            source: The cell's source.
            after: Insert directly after this cell; append when ``None``.

        Returns:
            The new cell's id.

        Raises:
            KeyError: ``after`` names no cell.
        """
        with self._state_lock:
            inserted = (
                self._document.insert_cell_after(after, new_code_cell(source))
                if after is not None
                else self._document.append_cell(new_code_cell(source))
            )
            cell_id = inserted.cell_id
            self._store.write(self._document)
            self._rebuild()
        if cell_id is None:  # pragma: no cover - new_code_cell always assigns one
            raise SessionError("The inserted cell carries no id, so it could be neither marked nor run.")
        self._emit(SessionEventType.ANALYSIS_UPDATED, {"reason": "cell_inserted", "cell_id": cell_id})
        return cell_id

    def reload_if_changed(self) -> bool:
        """Re-read the notebook when it changed on disk from outside (FR-005).

        Marks are kept by cell id where the id survives, and the kernel
        namespace is untouched — an edit in JupyterLab unbinds nothing.

        Returns:
            ``True`` when the file was reloaded.

        Raises:
            FileNotFoundError: The notebook has been deleted.
            NotebookStoreError: The file on disk is no longer a notebook.
        """
        with self._state_lock:
            reloaded = self._store.reload()
            if reloaded is None:
                return False
            self._document = reloaded
            self._rebuild()
        self._emit(SessionEventType.ANALYSIS_UPDATED, {"reason": "external_edit"})
        return True

    @property
    def current_cell(self) -> str | None:
        """The cell a panel emission is inserted after (FR-018)."""
        with self._state_lock:
            return self._current_cell

    def set_current_cell(self, cell_id: str | None) -> None:
        """Tell the session which cell the person is on.

        Raises:
            KeyError: No cell carries that id.
        """
        with self._state_lock:
            if cell_id is not None:
                self._document.cell(cell_id)
            self._current_cell = cell_id

    # -- the analysis and the marks (FR-019 to FR-024) --------------------

    @property
    def graph(self) -> DependencyGraph:
        """The dependency graph over the enabled code cells (FR-056)."""
        with self._state_lock:
            if self._graph is None:  # pragma: no cover - the constructor builds one
                self._rebuild()
            assert self._graph is not None
            return self._graph

    @property
    def facts(self) -> tuple[CellFacts, ...]:
        """The per-cell static facts, in written order."""
        with self._state_lock:
            return self._facts

    def marks(self, cell_id: str) -> frozenset[CellMark]:
        """The marks on one cell. Empty means nothing about it is questionable."""
        with self._state_lock:
            return frozenset(self._marks.get(cell_id, ()))

    @property
    def marks_by_cell(self) -> Mapping[str, frozenset[CellMark]]:
        """Every marked cell's marks, for the API's marks call (FR-056)."""
        with self._state_lock:
            return {cell_id: frozenset(marks) for cell_id, marks in self._marks.items() if marks}

    def out_of_order_reads(self, cell_id: str) -> tuple[OutOfOrderRead, ...]:
        """Why a cell is marked out of order (FR-019)."""
        with self._state_lock:
            return self._reasons.get(cell_id, ())

    @property
    def last_bound_by(self) -> Mapping[str, str]:
        """Which cell last bound each name in the kernel (FR-020)."""
        with self._state_lock:
            return dict(self._last_bound_by)

    @property
    def observations(self) -> Mapping[str, Observation]:
        """The observation recorded for each cell that has run (FR-021)."""
        with self._state_lock:
            return dict(self._observations)

    def stale_cells(self) -> tuple[str, ...]:
        """The stale cells in written order — the set run-stale runs (FR-024).

        This is also the value packaging is given. FR-039 refuses a notebook
        whose declared-output slice contains a stale cell, and this is the set
        it intersects that slice with, so packaging never reaches into the
        session's internals to find it.
        """
        return self._cells_marked(CellMark.STALE)

    def out_of_order_cells(self) -> tuple[str, ...]:
        """The out-of-order cells in written order (FR-039)."""
        return self._cells_marked(CellMark.OUT_OF_ORDER)

    def never_run_cells(self) -> tuple[str, ...]:
        """The cells that have not run in this kernel, in written order (FR-039)."""
        return self._cells_marked(CellMark.NEVER_RUN)

    def questionable_cells(self) -> tuple[str, ...]:
        """Every cell carrying any mark, in written order.

        The union packaging refuses on (FR-039): never-run, stale, or out of
        order.
        """
        with self._state_lock:
            return self._in_written_order({cell_id for cell_id, marks in self._marks.items() if marks})

    def cell_marks(self) -> CellMarks:
        """The marks as :mod:`scistudio.explore.packaging` takes them (FR-039).

        Packaging is a pure function of the notebook and the marks it is *given*;
        it never reaches into a session to find them. This is the seam: the
        session hands over its three sets and packaging decides what to refuse.

        The import is local because ``packaging`` pulls in the block registry
        and the Code Block, which a session that is only running cells should
        not pay for.
        """
        from scistudio.explore.packaging import CellMarks as _CellMarks

        with self._state_lock:
            return _CellMarks(
                never_run=self.never_run_cells(),
                stale=self.stale_cells(),
                out_of_order=self.out_of_order_cells(),
            )

    def binding_types(self) -> dict[str, str]:
        """Name to the type the kernel reports for it, for packaging's ports (FR-038).

        Packaging types each port by the object bound to that name at packaging
        time, and only the kernel knows what that is. What comes back is
        :attr:`~scistudio.explore.kernel_bridge.Binding.type_name`, which is
        ``type(value).__name__`` inside the kernel — the *native* type. Where the
        native and the SciStudio type names differ (a numpy array is ``ndarray``,
        not ``Array``), packaging cannot resolve the port and says so, naming the
        port; the translation belongs in the bridge, which is the only side that
        holds the object.

        Returns an empty mapping when no kernel is running: a session with no
        kernel binds nothing.
        """
        return {binding.name: binding.type_name for binding in self.bindings()}

    def _cells_marked(self, mark: CellMark) -> tuple[str, ...]:
        with self._state_lock:
            return self._in_written_order({cell_id for cell_id, marks in self._marks.items() if mark in marks})

    def _in_written_order(self, cell_ids: Iterable[str]) -> tuple[str, ...]:
        order = {fact.cell_id: index for index, fact in enumerate(self._facts)}
        return tuple(sorted(cell_ids, key=lambda cell_id: order.get(cell_id, len(order))))

    # -- running (FR-017, FR-018, FR-024) ---------------------------------

    def run_cell(self, cell_id: str) -> ExecutionRequest:
        """Enqueue one cell — the cell the person named, and nothing else.

        Args:
            cell_id: The cell to run.

        Returns:
            The queued request; the *same* request when this coalesced with a
            submission already waiting (FR-017).

        Raises:
            KeyError: No cell carries that id.
            SessionError: The cell is disabled, so it is not in the graph.
        """
        self._require_runnable(cell_id)
        return self._queue.submit_cell(cell_id)

    def run_stale(self) -> tuple[ExecutionRequest, ...]:
        """Enqueue the stale cells in written order and nothing else (FR-024).

        Not the out-of-order ones and not the never-run ones: FR-024 says the
        stale set, and a control that quietly ran more than its name would be
        the service choosing cells the person did not ask for.
        """
        return self._queue.submit_cells(self.stale_cells())

    def run_with_upstream(self, cell_id: str) -> tuple[ExecutionRequest, ...]:
        """Enqueue *cell_id* with the part of its backward slice that needs re-running.

        FR-024's skip rule, exactly: a cell in the slice is skipped only if it
        is neither stale nor out of order **and** every name it changes is still
        last bound by it in the kernel. Both clauses are needed — a cell that
        has never run carries neither mark, and it is the second clause that
        runs it.

        The cell the person named always runs. The skip rule governs the cells
        the service chooses *on their behalf* (spec §4.1); a control called "run
        this cell with its upstream" that ran nothing when the chain was clean
        would be a control that does not do what it says.

        Args:
            cell_id: The cell to run with its upstream.

        Returns:
            The queued requests, in written order.

        Raises:
            KeyError: No cell carries that id.
            SessionError: The cell is disabled, so it is not in the graph.
        """
        self._require_runnable(cell_id)
        with self._state_lock:
            graph = self.graph
            slice_result = graph.backward_slice([cell_id])
            selected = [
                candidate
                for candidate in slice_result.cells
                if candidate == cell_id or not self._is_undisturbed(candidate, graph)
            ]
        return self._queue.submit_cells(selected)

    def _is_undisturbed(self, cell_id: str, graph: DependencyGraph) -> bool:
        """FR-024's skip test for one upstream cell.

        Undisturbed means: no mark on it, and every name it changes is still
        last bound by it in the kernel.
        """
        if self._marks.get(cell_id):
            return False
        changed = graph.changed_set(cell_id)
        return all(self._last_bound_by.get(name) == cell_id for name in changed)

    def emit_snippet(
        self,
        source: str,
        *,
        panel: str,
        bound_names: Iterable[str] = (),
    ) -> tuple[str, ExecutionRequest]:
        """Admit a snippet a panel emitted, insert it, and enqueue it (FR-018).

        Admission happens **before** anything is inserted, so a refused emission
        leaves the notebook exactly as it was. The cell lands directly after the
        session's current cell.

        Args:
            source: The emitted code.
            panel: The emitting panel, named in every refusal.
            bound_names: The names that panel is bound to. Checked against the
                running request's changed set (FR-025).

        Returns:
            The new cell's id and its queued request.

        Raises:
            SnippetRefusedError: The snippet is outside the whitelist (FR-018).
            PanelFrozenError: A run may change a name this panel is bound to
                (FR-025).
        """
        admit_snippet(source, panel=panel)
        names = frozenset(bound_names)
        # The freeze is checked before the cell is inserted as well as at
        # submission, so a refused emission never leaves a cell behind.
        self._refuse_if_frozen(panel=panel, names=names)
        cell_id = self.insert_cell(source, after=self.current_cell)
        try:
            request = self._queue.submit_cell(
                cell_id,
                kind=RequestKind.SNIPPET,
                panel=panel,
                bound_names=names,
            )
        except PanelFrozenError:
            with self._state_lock:
                self._document.remove_cell(cell_id)
                self._store.write(self._document)
                self._rebuild()
            raise
        return cell_id, request

    def _refuse_if_frozen(self, *, panel: str, names: frozenset[str]) -> None:
        if not names:
            return
        running = self._queue.running
        if running is None:
            return
        clash = names & self._queue.running_changed_names
        if clash:
            message = (
                f"Panel {panel!r} cannot emit while the cell {running.cell_id!r} is running: "
                f"it may change {', '.join(sorted(clash))}. The panel keeps reading; try again when the run ends."
            )
            raise PanelFrozenError(message, panel=panel, names=frozenset(clash))

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until the queue has drained. Packaging waits on this."""
        return self._queue.wait_until_idle(timeout)

    def _require_runnable(self, cell_id: str) -> None:
        with self._state_lock:
            cell = self._document.cell(cell_id)
            if cell.cell_type != "code":
                raise SessionError(f"Cell {cell_id!r} is a {cell.cell_type} cell; only a code cell runs.")
            if not cell.enabled:
                raise SessionError(
                    f"Cell {cell_id!r} is disabled, so it is not in the graph and the session will not run it. "
                    f"Enable it first."
                )

    def _changed_names_of(self, request: ExecutionRequest) -> frozenset[str]:
        """The names a request may change — the union the analysis reports (FR-025)."""
        with self._state_lock:
            graph = self.graph
            try:
                return graph.changed_set(request.cell_id)
            except KeyError:
                return frozenset()

    # -- the kernel (FR-013 to FR-016) ------------------------------------

    @property
    def has_kernel(self) -> bool:
        """Whether a kernel process is alive for this session."""
        with self._kernel_lock:
            return self._handle is not None and self._handle.is_alive()

    @property
    def kernel(self) -> KernelHandle | None:
        """The kernel handle, or ``None`` before the first run."""
        with self._kernel_lock:
            return self._handle

    @property
    def bridge(self) -> KernelBridge | None:
        """The bridge over this session's kernel, or ``None`` before the first run."""
        with self._kernel_lock:
            return self._bridge

    def kernel_status(self) -> KernelStatus | None:
        """A reading of this session's kernel for the list of FR-016.

        Takes no execution lock, so it answers while a cell is stuck.
        """
        handle = self.kernel
        return handle.status() if handle is not None else None

    def start_kernel(self) -> KernelHandle:
        """Start the kernel if it is not running and install the bridge.

        A session opens with no kernel (US1 scenario 1); this is what the first
        run calls, and what the API calls when a person asks for one early.
        """
        with self._kernel_lock:
            if self._handle is not None and self._handle.is_alive():
                return self._handle
            handle = self._service.build_kernel(self)
            handle.start()
            self._handle = handle
            self._bridge = self._service.build_bridge(handle)
            self._install_bridge()
            with self._state_lock:
                self._needs_restart = False
        self._emit_kernel_state()
        return handle

    def _install_bridge(self) -> None:
        assert self._bridge is not None
        inputs = self._bound_run.inputs() if self._bound_run is not None else {}
        self._bridge.install(
            inputs=inputs,
            project_dir=str(self._project_dir),
            run_id=self._bound_run.run_id if self._bound_run is not None else None,
        )

    def interrupt(self) -> None:
        """Interrupt the running cell without ending the session (FR-013).

        Raises:
            KernelNotRunningError: There is no kernel to interrupt.
            SessionError: No kernel has ever been started.
        """
        handle = self.kernel
        if handle is None:
            raise SessionError("This session has no kernel; there is nothing to interrupt.")
        handle.interrupt()

    def restart_kernel(self) -> None:
        """Start a fresh kernel and reset every mark to never-run (FR-013, FR-023).

        The namespace is gone, so the last-bound-by map is cleared with it: no
        name is bound by any cell any more, which is what makes run-with-upstream
        re-run the chain rather than skip it. The observations survive, because
        they are facts about the source a cell ran, not about the process.
        """
        with self._kernel_lock:
            if self._handle is None:
                self.start_kernel()
            else:
                self._handle.restart()
                self._install_bridge()
        with self._state_lock:
            self._last_bound_by.clear()
            self._reasons.clear()
            self._reset_marks_to_never_run()
            self._needs_restart = False
        self._emit_kernel_state()
        self._emit(SessionEventType.CELL_STATE, {"reason": "kernel_restarted", "marks": self._marks_payload()})

    def report_kernel_died(self) -> None:
        """The kernel process died without being stopped by us (FR-015).

        Passed to the handle as its ``on_death`` callback, so a kernel killed
        from outside is noticed the first time anything reads its state — a
        status poll for the kernel list, or the request that was in flight. The
        marks reset to never-run because the namespace they describe is gone,
        and the session reports that it needs a restart. Nothing is re-run.
        """
        with self._state_lock:
            self._last_bound_by.clear()
            self._reasons.clear()
            self._reset_marks_to_never_run()
            self._needs_restart = True
        self._emit(SessionEventType.KERNEL_STATE, {"state": "dead", "needs_restart": True})

    def stop_kernel(self, *, needs_restart: bool = False) -> None:
        """Terminate the kernel process (FR-013, FR-014, FR-016).

        Args:
            needs_restart: Report that the session needs a restart afterwards.
                Set when the kernel was retired underneath the person by a
                branch change rather than ended by them.
        """
        with self._kernel_lock:
            handle = self._handle
            if handle is not None:
                handle.stop()
            self._handle = None
            self._bridge = None
        with self._state_lock:
            self._last_bound_by.clear()
            self._reasons.clear()
            self._reset_marks_to_never_run()
            self._needs_restart = needs_restart
        self._emit_kernel_state()

    def bindings(self) -> tuple[Binding, ...]:
        """The kernel's top-level bindings with their type names (FR-056).

        Returns an empty tuple when no kernel is running, because a session with
        no kernel binds nothing rather than being an error to ask about.
        """
        bridge = self.bridge
        return bridge.bindings() if bridge is not None else ()

    def window(
        self,
        name: str,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """A windowed read of one variable, through the bridge (FR-056).

        A read, not a submission: it queues behind a running cell in the kernel
        and completes when the cell does, which is the shallow freeze ADR-054
        §6.3 accepts.

        Raises:
            SessionError: No kernel is running, so no variable is bound.
        """
        bridge = self.bridge
        if bridge is None:
            raise SessionError("This session has no kernel; no variable is bound to window.")
        return bridge.window(name, query=query, project_dir=str(self._project_dir))

    # -- the run itself (FR-019 to FR-022, FR-027, FR-028) ----------------

    def _run_request(self, request: ExecutionRequest) -> None:
        """Run one request. Called on the queue's worker thread and nowhere else."""
        cell_id = request.cell_id
        with self._state_lock:
            source = self._document.cell(cell_id).source
            self._store.write(self._document)  # FR-027: nothing typed is lost to a death
            captured = self._document.without_outputs().to_bytes()
        digest = source_hash(source)

        self.start_kernel()
        bridge = self.bridge
        handle = self.kernel
        assert bridge is not None and handle is not None

        before = bridge.fingerprints()
        reads = self._mark_order_before_run(cell_id)
        self._emit(
            SessionEventType.CELL_STATE,
            {"cell_id": cell_id, "state": "running", "out_of_order": [read.name for read in reads]},
        )

        result = handle.execute(source)
        after = bridge.fingerprints()
        observation = observe_namespaces(before, after, cell_id=cell_id, source_hash=digest)

        self._apply_observation(cell_id, observation, in_order=not reads)
        self._emit_run_results(cell_id, result, observation)
        self._service.queue_explore_commit(self, cell_id=cell_id, notebook=captured)

    def _mark_order_before_run(self, cell_id: str) -> tuple[OutOfOrderRead, ...]:
        """FR-019: compare each read's definer with its last binder, and mark.

        The cell runs regardless — this marks, it does not gate.
        """
        with self._state_lock:
            graph = self.graph
            facts = {fact.cell_id: fact for fact in self._facts}
            fact = facts.get(cell_id)
            if fact is None:
                return ()
            disordered: list[OutOfOrderRead] = []
            for name in sorted(fact.read):
                try:
                    definer = graph.definer_for(cell_id, name)
                except KeyError:  # a disabled cell is not in the graph
                    return ()
                binder = self._last_bound_by.get(name)
                if definer != binder:
                    disordered.append(OutOfOrderRead(name=name, definer=definer, last_binder=binder))
            reads = tuple(disordered)
            if reads:
                self._add_mark(cell_id, CellMark.OUT_OF_ORDER)
                self._reasons[cell_id] = reads
            return reads

    def _apply_observation(self, cell_id: str, observation: Observation, *, in_order: bool) -> None:
        """FR-020 to FR-023: record what ran, and mark what that made questionable.

        Enqueues nothing. Marking is the whole of it.
        """
        with self._state_lock:
            self._observations[cell_id] = observation
            for name in observation.differing | observation.appeared:
                self._last_bound_by[name] = cell_id
            for name in observation.disappeared:
                self._last_bound_by.pop(name, None)
            self._rebuild(keep_marks=True)

            self._discard_mark(cell_id, CellMark.NEVER_RUN)
            if in_order:
                self._discard_mark(cell_id, CellMark.STALE)
                self._discard_mark(cell_id, CellMark.OUT_OF_ORDER)
                self._reasons.pop(cell_id, None)
            try:
                downstream = self.graph.downstream(cell_id)
            except KeyError:  # pragma: no cover - the cell just ran, so it is enabled
                downstream = ()
            for below in downstream:
                self._add_mark(below, CellMark.STALE)

    def _emit_run_results(self, cell_id: str, result: ExecutionResult, observation: Observation) -> None:
        self._emit(
            SessionEventType.CELL_OUTPUT,
            {
                "cell_id": cell_id,
                "status": result.status,
                "execution_count": result.execution_count,
                "outputs": [_output_payload(output) for output in result.outputs],
            },
        )
        self._emit(
            SessionEventType.CHANGED_NAMES,
            {
                "cell_id": cell_id,
                "changed": sorted(observation.changed_names),
                "unobservable": sorted(observation.unobservable),
            },
        )
        self._emit(
            SessionEventType.CELL_STATE,
            {"cell_id": cell_id, "state": "idle", "marks": self._marks_payload()},
        )
        self._emit(SessionEventType.ANALYSIS_UPDATED, {"reason": "cell_ran", "cell_id": cell_id})

    # -- analysis plumbing -------------------------------------------------

    def _rebuild(self, *, keep_marks: bool = True) -> None:
        """Re-run the analysis over the notebook as it stands (FR-005, FR-021).

        An observation is passed to the graph only while its source hash still
        matches the cell's source, so an edited cell falls back to its static
        estimate until it runs again (analysis FR-027).
        """
        cells: list[tuple[str, str]] = []
        enabled: dict[str, bool] = {}
        for cell in self._document.cells:
            cell_id = cell.cell_id
            if cell_id is None or cell.cell_type != "code":
                continue
            cells.append((cell_id, cell.source))
            enabled[cell_id] = cell.enabled

        self._facts = analyse_cells(cells)
        current = {fact.cell_id: fact.source_hash for fact in self._facts}
        self._observations = {
            cell_id: observation
            for cell_id, observation in self._observations.items()
            if current.get(cell_id) == observation.source_hash
        }
        self._graph = build_graph(self._facts, enabled=enabled, observations=dict(self._observations))

        known = set(current)
        if keep_marks:
            # FR-005: marks survive a reload by cell id; a cell that is gone
            # takes its marks with it, and a new cell has never run.
            for cell_id in list(self._marks):
                if cell_id not in known:
                    del self._marks[cell_id]
            for cell_id in list(self._reasons):
                if cell_id not in known:
                    del self._reasons[cell_id]
            for cell_id in known:
                if cell_id not in self._marks:
                    self._marks[cell_id] = {CellMark.NEVER_RUN}
        else:
            self._marks = {cell_id: {CellMark.NEVER_RUN} for cell_id in known}
            self._reasons = {}

    def _reset_marks_to_never_run(self) -> None:
        self._marks = {fact.cell_id: {CellMark.NEVER_RUN} for fact in self._facts}

    def _add_mark(self, cell_id: str, mark: CellMark) -> None:
        self._marks.setdefault(cell_id, set()).add(mark)

    def _discard_mark(self, cell_id: str, mark: CellMark) -> None:
        self._marks.get(cell_id, set()).discard(mark)

    def _marks_payload(self) -> dict[str, list[str]]:
        with self._state_lock:
            return {cell_id: sorted(mark.value for mark in marks) for cell_id, marks in self._marks.items() if marks}

    # -- writing and closing (FR-006, FR-036) ------------------------------

    def write(self) -> Path:
        """Write the notebook to disk, outputs and all (FR-027)."""
        with self._state_lock:
            return self._store.write(self._document)

    def stripped_notebook(self) -> bytes:
        """The notebook as it is committed: outputs stripped (FR-028, FR-036)."""
        with self._state_lock:
            return self._document.without_outputs().to_bytes()

    def has_uncommitted_changes(self) -> bool:
        """Whether the notebook changed since the last branch commit (FR-006)."""
        with self._state_lock:
            return _digest(self.stripped_notebook()) != self._branch_commit_digest

    def note_branch_commit(self, sha: str, payload: bytes) -> None:
        """Record that *payload* reached the branch as *sha* (FR-036)."""
        with self._state_lock:
            self._branch_commit_digest = _digest(payload)
            self._last_commit_sha = self._last_commit_sha or sha

    def note_explore_commit(self, sha: str) -> None:
        """Record the commit one cell run produced on the session's ref (FR-035)."""
        with self._state_lock:
            self._last_commit_sha = sha

    def _shutdown(self) -> None:
        """Stop the queue and the kernel. Called by the service on close."""
        with self._state_lock:
            self._closed = True
        self._queue.stop()
        self.stop_kernel()

    def _emit(self, event_type: SessionEventType, payload: Mapping[str, Any]) -> None:
        self._service.publish(SessionEvent(type=event_type, session_id=self._session_id, payload=dict(payload)))

    def _emit_kernel_state(self) -> None:
        status = self.kernel_status()
        self._emit(
            SessionEventType.KERNEL_STATE,
            {
                "state": status.state if status is not None else "not-started",
                "pid": status.pid if status is not None else None,
                "memory_bytes": status.memory_bytes if status is not None else None,
                "needs_restart": self.needs_restart,
            },
        )

    def __repr__(self) -> str:
        return f"ExploreSession(session_id={self._session_id!r}, notebook_path={str(self._path)!r})"


# ---------------------------------------------------------------------------
# The service (FR-001 to FR-006, FR-014, FR-016, FR-036)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class SessionService:
    """The owner of every session and every kernel in one project.

    It is the kernel's only client (FR-007) and the one place every execution
    passes through, which is what lets it admit, mark, observe, record, and
    commit. It sits beside the engine: it imports ``core`` for storage, lineage,
    and versioning, and it imports neither the API, nor AI, nor the engine
    (FR-008).

    Args:
        project_dir: The project root. ``{project}/explore/`` is created on
            demand.
        git_engine: The engine that writes the explore commits and the branch
            commit. Without one, a session runs and marks perfectly well and
            writes no history — which is what a test wants and what a project
            with no repository gets.
        block_outputs: Where a bound run's ports come from. Defaults to
            :class:`LineageBlockOutputResolver` over *lineage_store* when one is
            given, and to nothing otherwise, in which case only file sessions
            can be opened.
        lineage_store: The project's lineage store, for the default resolver.
        kernel_factory: Builds the :class:`~scistudio.explore.kernel.KernelHandle`
            for a session. The default launches ipykernel from the running
            interpreter — the bundled one in a packaged build (FR-007).
        bridge_factory: Builds the :class:`~scistudio.explore.kernel_bridge.KernelBridge`
            over a handle.
        python_executable: Override the interpreter kernels are launched from.

    Example::

        service = SessionService(project_dir)
        session = service.open_over_file("data/raw/signal.csv")
        session.run_cell(session.cells()[0].cell_id)
        session.wait_until_idle(timeout=60)
        service.close(session)
    """

    def __init__(
        self,
        project_dir: str | Path,
        *,
        git_engine: GitEngine | None = None,
        block_outputs: BlockOutputResolver | None = None,
        lineage_store: LineageStore | None = None,
        kernel_factory: Callable[[ExploreSession], KernelHandle] | None = None,
        bridge_factory: Callable[[KernelHandle], KernelBridge] | None = None,
        python_executable: str | Path | None = None,
    ) -> None:
        self._project_dir = Path(project_dir).resolve()
        self._git = git_engine
        self._python_executable = python_executable
        self._kernel_factory = kernel_factory
        self._bridge_factory = bridge_factory
        if block_outputs is None and lineage_store is not None:
            block_outputs = LineageBlockOutputResolver(lineage_store)
        self._block_outputs = block_outputs

        self._lock = threading.RLock()
        self._sessions: dict[str, ExploreSession] = {}
        self._listeners: list[Callable[[SessionEvent], None]] = []
        self._commits = _CommitWriter(self)
        self._reported_commit_failure: set[str] = set()

    # -- project layout ----------------------------------------------------

    @property
    def project_dir(self) -> Path:
        """The project root."""
        return self._project_dir

    @property
    def explore_dir(self) -> Path:
        """``{project}/explore/`` — where session notebooks live (FR-001)."""
        return self._project_dir / EXPLORE_DIR_NAME

    # -- events (FR-057) ---------------------------------------------------

    def subscribe(self, listener: Callable[[SessionEvent], None]) -> Callable[[], None]:
        """Receive every :class:`SessionEvent` the service publishes.

        Returns:
            A callable that unsubscribes.
        """
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: SessionEvent) -> None:
        """Publish an event. A listener that raises is logged, never propagated."""
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # a subscriber's bug must not fail a cell run
                _LOG.exception("An explore session listener raised on %s", event.type)

    # -- kernels the sessions borrow --------------------------------------

    def build_kernel(self, session: ExploreSession) -> KernelHandle:
        """Build the kernel handle for *session* (FR-007).

        ``jupyter_client`` is imported here rather than at module scope so that
        the session, its queue, and its marks are importable — and testable —
        without a kernel present. It is a core dependency (FR-059); the lazy
        import is about the *cost and reach* of importing this module, not about
        the dependency being optional.
        """
        if self._kernel_factory is not None:
            return self._kernel_factory(session)
        from scistudio.explore.kernel import KernelHandle as _KernelHandle
        from scistudio.explore.kernel_bridge import session_kernel_env

        return _KernelHandle(
            python_executable=self._python_executable,
            working_directory=self._project_dir,
            env=session_kernel_env(),
            kernel_id=session.session_id,
            on_death=session.report_kernel_died,
        )

    def build_bridge(self, handle: KernelHandle) -> KernelBridge:
        """Build the bridge over *handle* (FR-009)."""
        if self._bridge_factory is not None:
            return self._bridge_factory(handle)
        from scistudio.explore.kernel_bridge import KernelBridge as _KernelBridge

        return _KernelBridge(handle)

    # -- opening (FR-001 to FR-004) ---------------------------------------

    def open_over_block_outputs(
        self,
        block_id: str,
        *,
        run_id: str | None = None,
        name: str | None = None,
    ) -> ExploreSession:
        """Open a session over a block's outputs (FR-002, FR-003, FR-004).

        Binds to the most recent completed run of *block_id*, or to *run_id*
        when one is named.

        Args:
            block_id: The block to explore.
            run_id: Bind to this run rather than the most recent one.
            name: Notebook file stem; the block id by default.

        Returns:
            The open session. No kernel is started (US1 scenario 1).

        Raises:
            NothingToExploreError: The block's outputs have never been produced,
                or no resolver was configured to answer.
        """
        resolver = self._require_resolver(block_id)
        bound = (
            resolver.run_block_outputs(run_id, block_id)
            if run_id is not None
            else resolver.latest_block_outputs(block_id)
        )
        if bound is None or not bound.ports:
            where = f" in run {run_id}" if run_id else ""
            raise NothingToExploreError(
                f"The block {block_id!r} has produced no outputs{where}, so there is nothing to explore. Run it first."
            )
        return self._create(name or block_id, bound_run=bound)

    def open_over_paused_run(
        self,
        run_id: str,
        block_id: str,
        *,
        name: str | None = None,
    ) -> ExploreSession:
        """Open a session over the inputs of a run paused at a block (FR-002, FR-003).

        Raises:
            NothingToExploreError: The paused block received no inputs, or no
                resolver was configured to answer.
        """
        resolver = self._require_resolver(block_id)
        bound = resolver.paused_run_inputs(run_id, block_id)
        if bound is None or not bound.ports:
            raise NothingToExploreError(
                f"The block {block_id!r} in run {run_id!r} has no recorded inputs, so there is nothing to explore."
            )
        return self._create(name or block_id, bound_run=bound)

    def open_over_file(self, path: str | Path, *, name: str | None = None) -> ExploreSession:
        """Open a session over a file in the project's data tree (FR-002, FR-004).

        A missing file is **not** refused: the first cell fails with the
        loader's error and the session opens regardless, because the notebook is
        the person's (spec §2, edge cases).

        Args:
            path: The file, absolute or project-relative.
            name: Notebook file stem; the file's stem by default.
        """
        target = Path(path)
        relative = _relative_posix(target, self._project_dir) if target.is_absolute() else target.as_posix()
        return self._create(name or PurePosixPath(relative).stem, file_path=relative)

    def open_notebook(self, path: str | Path, *, bound_run: BoundRun | None = None) -> ExploreSession:
        """Open a session on an existing notebook, or return the open one (FR-001).

        A notebook has at most one kernel, so opening a session on a notebook
        that already has one returns the first session rather than a second.
        This is also how a packaged block's node reopens its notebook copy
        (FR-042); the caller passes the run it should bind to.

        Raises:
            FileNotFoundError: There is no notebook at *path*.
            NotebookStoreError: The file is not a notebook.
        """
        resolved = self._resolve(path)
        key = _relative_posix(resolved, self._project_dir)
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None:
                return existing
        store = NotebookStore(resolved)
        document = store.read()
        session_id = _session_id_of(document) or _new_session_id()
        if _session_id_of(document) != session_id:
            document.set_scistudio_metadata(SESSION_ID_METADATA_KEY, session_id)
            store.write(document)
        return self._register(
            ExploreSession(
                service=self,
                session_id=session_id,
                notebook_path=resolved,
                project_dir=self._project_dir,
                document=document,
                store=store,
                bound_run=bound_run,
            )
        )

    def _resolve(self, path: str | Path) -> Path:
        """A notebook path as an absolute path, project-relative paths included."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._project_dir / candidate
        return candidate.resolve()

    def _require_resolver(self, block_id: str) -> BlockOutputResolver:
        if self._block_outputs is None:
            raise NothingToExploreError(
                f"This session service was built without a way to resolve {block_id!r}'s ports, so it cannot "
                f"say what the block produced. Pass block_outputs or lineage_store."
            )
        return self._block_outputs

    def _create(
        self,
        stem: str,
        *,
        bound_run: BoundRun | None = None,
        file_path: str | None = None,
    ) -> ExploreSession:
        """Write a new notebook with its generated first cell and open it (FR-004)."""
        self.explore_dir.mkdir(parents=True, exist_ok=True)
        path = _unique_path(self.explore_dir, stem)
        session_id = _new_session_id()
        document = new_notebook([new_code_cell(first_cell_source(bound_run=bound_run, file_path=file_path))])
        document.set_scistudio_metadata(SESSION_ID_METADATA_KEY, session_id)
        store = NotebookStore(path)
        store.write(document)
        session = self._register(
            ExploreSession(
                service=self,
                session_id=session_id,
                notebook_path=path,
                project_dir=self._project_dir,
                document=document,
                store=store,
                bound_run=bound_run,
            )
        )
        first = session.cells()[0].cell_id
        if first is not None:
            session.set_current_cell(first)
        self.publish(
            SessionEvent(
                type=SessionEventType.SESSION_OPENED,
                session_id=session_id,
                payload={
                    "notebook_path": session.relative_path,
                    "opened_over": bound_run.opened_over if bound_run is not None else "file",
                    "run_id": bound_run.run_id if bound_run is not None else None,
                },
            )
        )
        return session

    def _register(self, session: ExploreSession) -> ExploreSession:
        with self._lock:
            self._sessions[session.relative_path] = session
        self._commits.start()
        return session

    # -- listing, closing, committing (FR-006, FR-036) --------------------

    def sessions(self) -> tuple[ExploreSession, ...]:
        """Every open session."""
        with self._lock:
            return tuple(self._sessions.values())

    def session_for(self, key: str | Path) -> ExploreSession:
        """The open session at a notebook path or with a session id.

        Raises:
            UnknownSessionError: Nothing open matches.
        """
        with self._lock:
            direct = self._sessions.get(str(key))
            if direct is not None:
                return direct
            for session in self._sessions.values():
                if session.session_id == str(key):
                    return session
                if session.notebook_path == Path(key):
                    return session
        raise UnknownSessionError(f"No open session at {str(key)!r}.")

    def list_sessions(self) -> tuple[SessionListing, ...]:
        """Every notebook in the explore directory, with whether it has a kernel (FR-006)."""
        open_by_path = {session.relative_path: session for session in self.sessions()}
        listings: list[SessionListing] = []
        seen: set[str] = set()
        explore = self.explore_dir
        paths = sorted(explore.glob("*.ipynb")) if explore.is_dir() else []
        for path in paths:
            relative = _relative_posix(path, self._project_dir)
            seen.add(relative)
            session = open_by_path.get(relative)
            if session is not None:
                listings.append(
                    SessionListing(
                        notebook_path=relative,
                        session_id=session.session_id,
                        has_kernel=session.has_kernel,
                        is_open=True,
                    )
                )
                continue
            try:
                document = NotebookStore(path).read()
            except (NotebookStoreError, OSError, UnicodeDecodeError):
                listings.append(
                    SessionListing(
                        notebook_path=relative, session_id=None, has_kernel=False, is_open=False, readable=False
                    )
                )
                continue
            listings.append(
                SessionListing(
                    notebook_path=relative,
                    session_id=_session_id_of(document),
                    has_kernel=False,
                    is_open=False,
                )
            )
        for relative, session in sorted(open_by_path.items()):
            if relative not in seen:
                listings.append(
                    SessionListing(
                        notebook_path=relative,
                        session_id=session.session_id,
                        has_kernel=session.has_kernel,
                        is_open=True,
                    )
                )
        return tuple(listings)

    def close(self, session: ExploreSession | str | Path, *, commit: bool = True) -> str | None:
        """End a session: kernel, notebook, and one branch commit (FR-006, FR-036).

        Args:
            session: The session, its notebook path, or its id.
            commit: Write the branch commit when the notebook changed since the
                last one. Set ``False`` to close without touching the branch.

        Returns:
            The branch commit's SHA when one was written, else ``None``.
        """
        target = session if isinstance(session, ExploreSession) else self.session_for(session)
        target.write()
        sha: str | None = None
        if commit and target.has_uncommitted_changes():
            sha = self.commit_to_branch(target)
        target._shutdown()
        with self._lock:
            self._sessions.pop(target.relative_path, None)
        self.publish(
            SessionEvent(
                type=SessionEventType.SESSION_CLOSED,
                session_id=target.session_id,
                payload={"notebook_path": target.relative_path, "branch_commit": sha},
            )
        )
        return sha

    def commit_to_branch(self, session: ExploreSession, *, message: str | None = None) -> str | None:
        """Write one commit of the notebook, outputs stripped, to the branch (FR-036).

        Returns:
            The commit SHA, or ``None`` when the service has no git engine.
        """
        if self._git is None:
            return None
        payload = session.stripped_notebook()
        sha = self._git.commit_entries_to_branch(
            {session.relative_path: payload},
            message or f"explore: {session.relative_path}",
        )
        session.note_branch_commit(sha, payload)
        self.publish(
            SessionEvent(
                type=SessionEventType.COMMIT_RECORDED,
                session_id=session.session_id,
                payload={"sha": sha, "ref": "branch", "notebook_path": session.relative_path},
            )
        )
        return sha

    # -- the kernel list and branch-switch retirement (T-016, FR-014, FR-016)

    def kernels(self) -> tuple[KernelListing, ...]:
        """Every live kernel in the project, with its session and its memory (FR-016).

        Reads each kernel's status from outside the process, so the list answers
        while every kernel in it is stuck in a long cell.
        """
        listings: list[KernelListing] = []
        for session in self.sessions():
            status = session.kernel_status()
            if status is None or status.pid is None or status.state not in {"starting", "idle", "busy"}:
                continue
            listings.append(
                KernelListing(
                    session_id=session.session_id,
                    notebook_path=session.relative_path,
                    status=status,
                )
            )
        return tuple(listings)

    def end_kernel(self, key: str | Path) -> None:
        """Terminate one session's kernel process, leaving the session open (FR-016)."""
        self.session_for(key).stop_kernel()

    def retire_kernels(self) -> tuple[str, ...]:
        """Retire every kernel after writing every open notebook (FR-014).

        This is what a branch change calls. Each notebook is written to disk
        *before* its kernel goes, so nothing typed is lost, and each session then
        reports that it needs a restart.

        Returns:
            The ids of the sessions whose kernels were retired.
        """
        retired: list[str] = []
        for session in self.sessions():
            session.write()
            had_kernel = session.has_kernel
            session.stop_kernel(needs_restart=True)
            if had_kernel:
                retired.append(session.session_id)
        return tuple(retired)

    # -- explore commits (FR-028 to FR-031) -------------------------------

    def queue_explore_commit(self, session: ExploreSession, *, cell_id: str, notebook: bytes) -> None:
        """Queue the commit for one cell run, off the execution path (FR-028, FR-030).

        The notebook committed is the one captured when the cell started, so a
        second run during the interval cannot change what this commit records.
        Nothing here blocks the run: the request has already returned.
        """
        if self._git is None:
            return
        self._commits.submit(_CommitJob(session=session, cell_id=cell_id, notebook=notebook))

    def wait_for_commits(self, timeout: float | None = None) -> bool:
        """Block until every queued explore commit has been written or given up on."""
        return self._commits.wait_until_idle(timeout)

    def _write_explore_commit(self, job: _CommitJob) -> None:
        """Write one explore commit. Called on the commit thread and nowhere else."""
        assert self._git is not None
        session = job.session
        ref = self._git.explore_session_ref(session.session_id)
        sha = self._git.commit_entries_to_ref(
            ref,
            {session.relative_path: job.notebook},
            f"explore({session.session_id}): {job.cell_id}",
        )
        session.note_explore_commit(sha)
        self.publish(
            SessionEvent(
                type=SessionEventType.COMMIT_RECORDED,
                session_id=session.session_id,
                payload={"sha": sha, "ref": ref, "cell_id": job.cell_id},
            )
        )

    def _report_commit_failure(self, job: _CommitJob, error: BaseException) -> None:
        """FR-030: a run whose commit could not be written is reported once."""
        session = job.session
        if session.session_id in self._reported_commit_failure:
            return
        self._reported_commit_failure.add(session.session_id)
        _LOG.error("Explore commit for session %s failed: %s", session.session_id, error)
        self.publish(
            SessionEvent(
                type=SessionEventType.COMMIT_RECORDED,
                session_id=session.session_id,
                payload={"sha": None, "cell_id": job.cell_id, "error": str(error)},
            )
        )

    # -- shutdown ----------------------------------------------------------

    def shutdown(self, *, commit: bool = False) -> None:
        """Close every session and stop the commit thread."""
        for session in self.sessions():
            try:
                self.close(session, commit=commit)
            except Exception:  # a session that cannot be closed must not strand the others
                _LOG.exception("Could not close explore session %s", session.session_id)
        self._commits.stop()

    def __repr__(self) -> str:
        return f"SessionService(project_dir={str(self._project_dir)!r}, sessions={len(self._sessions)})"


# ---------------------------------------------------------------------------
# The commit thread (FR-029, FR-030)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CommitJob:
    """One explore commit waiting to be written."""

    session: ExploreSession
    cell_id: str
    notebook: bytes


class _CommitWriter:
    """Writes explore commits on a thread of its own, retrying and never blocking.

    FR-030 is the whole reason this is a thread: a commit that fails is retried
    off the execution path and must never block a run, and a run whose commit
    could not be written is reported once.
    """

    def __init__(self, service: SessionService) -> None:
        self._service = service
        self._jobs: stdlib_queue.Queue[_CommitJob | None] = stdlib_queue.Queue()
        self._lock = threading.RLock()
        self._idle = threading.Condition(self._lock)
        self._outstanding = 0
        self._thread: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping = False
            self._thread = threading.Thread(target=self._loop, name="scistudio-explore-commits", daemon=True)
            self._thread.start()

    def stop(self, *, timeout: float | None = 10.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stopping = True
        self._jobs.put(None)
        thread.join(timeout=timeout)
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def submit(self, job: _CommitJob) -> None:
        self.start()
        with self._lock:
            self._outstanding += 1
        self._jobs.put(job)

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._idle:
            while self._outstanding:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._idle.wait(timeout=remaining if remaining is not None else 0.05)
            return True

    def _loop(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._attempt(job)
            finally:
                with self._idle:
                    self._outstanding -= 1
                    self._idle.notify_all()

    def _attempt(self, job: _CommitJob) -> None:
        last: BaseException | None = None
        for attempt in range(_COMMIT_ATTEMPTS):
            try:
                self._service._write_explore_commit(job)
                return
            except Exception as error:  # git busy, repository locked, a lost compare-and-swap
                last = error
                if attempt + 1 < _COMMIT_ATTEMPTS:
                    time.sleep(_COMMIT_RETRY_SECONDS)
        if last is not None:
            self._service._report_commit_failure(job, last)


# ---------------------------------------------------------------------------
# The lineage-backed resolver
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class LineageBlockOutputResolver:
    """Answers a session's port questions from the project's lineage store (FR-003).

    A block's outputs are recorded as ``block_io`` edges over ``data_objects``,
    which is where a session's bound ports come from. The queries are read-only
    and go through :meth:`~scistudio.core.lineage.store.LineageStore.execute_query`,
    which enforces that.

    One limit, stated rather than discovered: a port that carried several
    objects — a Collection port — binds its **first**, because FR-004's
    generated first cell is one ``scistudio.load(scistudio.input(...))`` line per
    port and ``scistudio.input`` returns one reference.
    """

    def __init__(self, store: LineageStore) -> None:
        self._store = store

    def latest_block_outputs(self, block_id: str) -> BoundRun | None:
        """The outputs of the most recent completed run of *block_id*."""
        rows = self._store.execute_query(
            """
            SELECT be.block_execution_id, be.run_id
            FROM block_executions be
            JOIN runs r ON be.run_id = r.run_id
            WHERE be.block_id = ? AND be.termination = 'completed'
            ORDER BY be.started_at DESC, be.rowid DESC
            LIMIT 1
            """,
            (block_id,),
        )
        if not rows:
            return None
        execution_id, run_id = str(rows[0][0]), str(rows[0][1])
        ports = self._ports(execution_id, "output")
        if not ports:
            return None
        return BoundRun(run_id=run_id, block_id=block_id, opened_over="block_outputs", ports=ports)

    def run_block_outputs(self, run_id: str, block_id: str) -> BoundRun | None:
        """The outputs *block_id* wrote in *run_id*."""
        return self._for_run(run_id, block_id, direction="output", opened_over="block_outputs")

    def paused_run_inputs(self, run_id: str, block_id: str) -> BoundRun | None:
        """The inputs *block_id* received in *run_id* (FR-002, a paused run)."""
        return self._for_run(run_id, block_id, direction="input", opened_over="paused_run")

    def _for_run(self, run_id: str, block_id: str, *, direction: str, opened_over: str) -> BoundRun | None:
        rows = self._store.execute_query(
            """
            SELECT be.block_execution_id
            FROM block_executions be
            WHERE be.run_id = ? AND be.block_id = ?
            ORDER BY be.started_at DESC, be.rowid DESC
            LIMIT 1
            """,
            (run_id, block_id),
        )
        if not rows:
            return None
        ports = self._ports(str(rows[0][0]), direction)
        if not ports:
            return None
        return BoundRun(run_id=run_id, block_id=block_id, opened_over=opened_over, ports=ports)

    def _ports(self, execution_id: str, direction: str) -> tuple[PortArtefact, ...]:
        rows = self._store.execute_query(
            """
            SELECT bio.port_name, bio.position, do.type_name, do.backend, do.storage_path, do.wire_payload
            FROM block_io bio
            JOIN data_objects do ON bio.object_id = do.object_id
            WHERE bio.block_execution_id = ? AND bio.direction = ?
            ORDER BY bio.port_name, bio.position
            """,
            (execution_id, direction),
        )
        ports: list[PortArtefact] = []
        seen: set[str] = set()
        for port_name, _position, type_name, backend, storage_path, wire_payload in rows:
            name = str(port_name)
            if name in seen:
                continue  # a Collection port binds its first object; see the class docstring
            if not backend or not storage_path:
                continue
            seen.add(name)
            ports.append(
                PortArtefact(
                    name=name,
                    type_name=str(type_name),
                    backend=str(backend),
                    path=str(storage_path),
                    format=_format_hint(wire_payload),
                )
            )
        return tuple(ports)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def first_cell_source(*, bound_run: BoundRun | None = None, file_path: str | None = None) -> str:
    """The generated first cell: the imports, then one load line per input (FR-004).

    ``import scistudio`` is not decoration and must not be tidied away. The
    kernel's bridge binds ``scistudio`` in the namespace, so a cell using it runs
    perfectly well without the import — but the dependency analysis reads the
    *source*, and a use with no import above it is an unresolved read, which
    makes packaging refuse the whole notebook (FR-039) at the very end, after an
    hour of the notebook working. The import is what makes the two worlds agree.
    ``tests/explore/test_explore_session.py`` pins it by running the generated
    notebook through the analysis and asserting no unresolved read.

    Args:
        bound_run: The run whose ports the first cell loads.
        file_path: The project-relative file a file session was opened over.

    Returns:
        The cell's source. It does not run automatically (FR-004).
    """
    lines = ["import scistudio", ""]
    if bound_run is not None:
        for port in bound_run.ports:
            variable = _identifier(port.name)
            lines.append(f'{variable} = scistudio.load(scistudio.input("{port.name}"))')
    elif file_path is not None:
        variable = _identifier(PurePosixPath(file_path).stem)
        lines.append(f'{variable} = scistudio.load("{file_path}")')
    return "\n".join(lines)


def _identifier(name: str) -> str:
    """A Python identifier derived from a port or file name."""
    candidate = _NON_IDENTIFIER.sub("_", name).strip("_") or "data"
    if candidate[0].isdigit() or keyword.iskeyword(candidate):
        candidate = f"_{candidate}"
    return candidate


def _new_session_id() -> str:
    """A ref-safe session id (FR-001)."""
    session_id = uuid.uuid4().hex
    assert _SESSION_ID_RE.match(session_id)  # a hex uuid always does; the assert states why
    return session_id


def _session_id_of(document: NotebookDocument) -> str | None:
    """The session id written into the notebook's metadata, when it is usable (FR-001)."""
    raw = document.scistudio_metadata.get(SESSION_ID_METADATA_KEY)
    if isinstance(raw, str) and _SESSION_ID_RE.match(raw) and ".." not in raw and not raw.endswith((".", ".lock")):
        return raw
    return None


def _unique_path(directory: Path, stem: str) -> Path:
    """``{directory}/{stem}.ipynb``, with a counter when that name is taken."""
    base = _identifier(stem)
    candidate = directory / f"{base}.ipynb"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base}-{counter}.ipynb"
        counter += 1
    return candidate


def _relative_posix(path: Path, project_dir: Path) -> str:
    """*path* relative to the project, as POSIX. Absolute when it is outside."""
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _digest(payload: bytes) -> str:
    from hashlib import sha256

    return sha256(payload).hexdigest()


def _format_hint(wire_payload: object) -> str | None:
    """The storage format recorded in a data object's wire payload, when there is one."""
    if isinstance(wire_payload, str):
        try:
            from json import loads

            wire_payload = loads(wire_payload)
        except ValueError:
            return None
    if isinstance(wire_payload, Mapping):
        value = wire_payload.get("format")
        return str(value) if isinstance(value, str) else None
    return None


def _output_payload(output: Any) -> dict[str, Any]:
    """One kernel output as a JSON-safe mapping for the cell-output event (FR-057)."""
    payload: dict[str, Any] = {"output_type": output.output_type}
    if output.name is not None:
        payload["name"] = output.name
    if output.text is not None:
        payload["text"] = output.text
    if output.data:
        payload["data"] = dict(output.data)
    if output.metadata:
        payload["metadata"] = dict(output.metadata)
    if output.error is not None:
        payload["ename"] = output.error.ename
        payload["evalue"] = output.error.evalue
        payload["traceback"] = list(output.error.traceback)
    return payload
