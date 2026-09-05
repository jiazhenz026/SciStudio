"""Category (h) MCP tools — the explore session (7 tools, ADR-054 spec 5).

Read-class (3): ``read_notebook``, ``get_bindings``, ``check_packaging``.
Write-class (4): ``open_explore_session``, ``append_cell``, ``run_cell``,
``package_notebook``. ``check_packaging`` is read-class although it waits for
the queue, because it writes nothing; ``open_explore_session`` is write-class
although it moves nothing the person can see, because it creates a notebook file
in their project.

**These tools are thin, and FR-024 is why.** Each one is a call to the session
API with the focus resolved first. None of them touches the kernel, the notebook
file, or the execution queue, because the whole point of the session service is
that every execution passes through it — a tool that reached past it would be a
second door into the person's kernel, and an appended cell would appear in their
notebook by a route their own edits never take. What this module imports is the
enforcement of that claim, and
``tests/ai/test_mcp_tools_explore.py::test_no_session_tool_module_reaches_past_the_session_api``
walks the package's whole import graph — module scope and function bodies alike —
to assert it, because a shortcut would be written as a lazy import inside a
function, not at the top of a file.

**The focus, and the one tool that must not move it.** Every tool but
``open_explore_session`` acts on the focused session by default, accepts an
explicit ``session_path`` instead, and otherwise refuses through
:func:`scistudio.ai.agent.mcp._focus.resolve_session_path` with a message that
names how to open one (FR-005). ``open_explore_session`` is the exception in both
directions: it needs no focus because it creates a session, and FR-019 forbids it
from *changing* the focus. The person's focus is the person's — the frontend
reports where they are, and a tool that moved them would be the agent deciding
what they are looking at.

**A refusal is a result, not an exception.** ``run_cell`` returns the queue's
refusal on :attr:`~._models.RunCellResult.refused`, and ``package_notebook``
returns the packaging report on :attr:`~._models.PackageNotebookResult.packaged`
being false. Both are answers the agent has to read and act on, and raising them
would flatten a structured report into a string the agent has to parse back.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from scistudio.ai.agent.mcp._context import get_optional_context
from scistudio.ai.agent.mcp._focus import effective_focus, resolve_session_path
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_explore._models import (
    OUTPUT_TEXT_LIMIT,
    AppendCellResult,
    BindingModel,
    BoundRunModel,
    BoundRunPortModel,
    CellModel,
    CellOutputModel,
    CheckPackagingResult,
    DeclaredOutputModel,
    GetBindingsResult,
    GraphEdgeModel,
    NotebookGraphModel,
    OpenExploreSessionResult,
    PackagedPortModel,
    PackageNotebookResult,
    PackagingProblemModel,
    ReadNotebookResult,
    RunCellResult,
    UnresolvedReadModel,
)
from scistudio.ai.agent.mcp.tools_explore._service import SessionToolError, session_for, session_service

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scistudio.explore.session import ExploreSession

logger = logging.getLogger(__name__)

#: How long a tool waits for the session's queue to drain before answering that
#: it did not. Shorter than the HTTP packaging route's fifteen minutes on
#: purpose: a person watching a progress bar can wait, and an agent blocked
#: inside a tool call it cannot interrupt cannot. The refusal says to retry, and
#: the run it was waiting on carries on regardless.
QUEUE_DRAIN_TIMEOUT: float = 300.0

#: The MIME type whose text an agent can actually read. Every other payload an
#: output carries is reported by name rather than by value.
_TEXT_MIME = "text/plain"


# ---------------------------------------------------------------------------
# Rendering the session API's answers into the agent's shapes
# ---------------------------------------------------------------------------


def _bounded(text: str) -> tuple[str, bool]:
    """Return *text* cut to :data:`~._models.OUTPUT_TEXT_LIMIT`, and whether it was."""
    if len(text) <= OUTPUT_TEXT_LIMIT:
        return text, False
    return text[:OUTPUT_TEXT_LIMIT], True


def _join(value: Any) -> str:
    """nbformat writes text as a string or a list of lines. Read both."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return "" if value is None else str(value)


def _output_model(raw: Any) -> CellOutputModel:
    """Render one nbformat output into something bounded and readable.

    The bytes of an image, a widget, or an HTML table are deliberately dropped
    and their MIME types reported instead: an agent cannot look at a PNG, and
    handing it several megabytes of base64 costs it the context it needs for the
    notebook itself.
    """
    output_type = str(raw.get("output_type", "")) if hasattr(raw, "get") else ""
    if output_type == "error":
        traceback = _join(raw.get("traceback"))
        text, truncated = _bounded(traceback)
        return CellOutputModel(
            output_type="error",
            text=text,
            truncated=truncated,
            ename=str(raw.get("ename")) if raw.get("ename") is not None else None,
            evalue=str(raw.get("evalue")) if raw.get("evalue") is not None else None,
        )
    if output_type == "stream":
        text, truncated = _bounded(_join(raw.get("text")))
        return CellOutputModel(
            output_type="stream",
            name=str(raw.get("name")) if raw.get("name") is not None else None,
            text=text,
            truncated=truncated,
        )
    data = raw.get("data")
    bundle = data if isinstance(data, dict) else {}
    text, truncated = _bounded(_join(bundle.get(_TEXT_MIME)))
    execution_count = raw.get("execution_count")
    return CellOutputModel(
        output_type=output_type or "display_data",
        text=text,
        truncated=truncated,
        mime_types=sorted(str(key) for key in bundle),
        execution_count=execution_count
        if isinstance(execution_count, int) and not isinstance(execution_count, bool)
        else None,
    )


def _cell_models(session: ExploreSession) -> list[CellModel]:
    """Every cell with its source, enabled flag, marks and outputs (FR-020)."""
    marks = session.marks_by_cell
    models: list[CellModel] = []
    for cell in session.cells():
        cell_id = cell.cell_id or ""
        models.append(
            CellModel(
                cell_id=cell_id,
                cell_type=cell.cell_type,
                source=cell.source,
                enabled=cell.enabled,
                marks=sorted(mark.value for mark in marks.get(cell_id, frozenset())),
                outputs=[_output_model(output) for output in cell.outputs],
                execution_count=cell.execution_count,
            )
        )
    return models


def _binding_models(session: ExploreSession) -> list[BindingModel]:
    """Every name the notebook binds or would bind, and whether it is live.

    The union the session API's own bindings call reports (FR-056): what the
    kernel holds now, plus what the analysis says the cells change or declare as
    outputs. A name the notebook produces but the kernel has not bound yet comes
    back with ``exists_in_kernel=False`` rather than being missing from the
    answer, which is the difference between "there is no such name" and "it has
    not run yet".
    """
    bound = {binding.name: binding for binding in session.bindings()}
    known: set[str] = set(bound)
    for changed in session.graph.changed_sets.values():
        known.update(changed)
    for fact in session.facts:
        for declaration in fact.outputs:
            known.update(declaration.keywords)
            known.update(declaration.arguments)
    last_bound_by = session.last_bound_by
    models: list[BindingModel] = []
    for name in sorted(known):
        binding = bound.get(name)
        models.append(
            BindingModel(
                name=name,
                exists_in_kernel=binding is not None,
                type_name=binding.type_name if binding is not None else None,
                native_type_name=binding.native_type_name if binding is not None else None,
                type_module=binding.type_module if binding is not None else None,
                summary=binding.summary if binding is not None else None,
                last_bound_by=last_bound_by.get(name),
            )
        )
    return models


def _declared_output_models(session: ExploreSession) -> list[DeclaredOutputModel]:
    """The ``scistudio.output(...)`` declarations, per cell (FR-020)."""
    models: list[DeclaredOutputModel] = []
    for fact in session.facts:
        for declaration in fact.outputs:
            models.append(
                DeclaredOutputModel(
                    cell_id=fact.cell_id,
                    names=list(declaration.keywords),
                    arguments=list(declaration.arguments),
                )
            )
    return models


def _graph_model(session: ExploreSession) -> NotebookGraphModel:
    """The dependency graph over the enabled code cells (FR-020)."""
    graph = session.graph
    return NotebookGraphModel(
        cells=list(graph.cells),
        edges=[
            GraphEdgeModel(reader=edge.reader, definer=edge.definer, name=edge.name, origin=str(edge.origin))
            for edge in graph.edges
        ],
        unresolved_reads=[UnresolvedReadModel(cell_id=read.cell_id, name=read.name) for read in graph.unresolved_reads],
        unknown_binding_cells=list(graph.unknown_binding_cells),
        changed_sets={cell_id: sorted(names) for cell_id, names in graph.changed_sets.items()},
    )


def _bound_run_model(session: ExploreSession) -> BoundRunModel | None:
    bound = session.bound_run
    if bound is None:
        return None
    return BoundRunModel(
        run_id=bound.run_id,
        block_id=bound.block_id,
        opened_over=bound.opened_over,
        ports=[
            BoundRunPortModel(
                name=port.name,
                type_name=port.type_name,
                backend=port.backend,
                path=port.path,
                format=port.format,
            )
            for port in bound.ports
        ],
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
            refuses=bool(problem.refuses),
        )
        for problem in problems
    ]


def _outputs_of(session: ExploreSession, cell_id: str) -> list[CellOutputModel]:
    for cell in session.cells():
        if cell.cell_id == cell_id:
            return [_output_model(output) for output in cell.outputs]
    return []


# ---------------------------------------------------------------------------
# (h.1) open_explore_session  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="open_explore_session", tags={"category:session", "write"})
async def open_explore_session(
    source: Annotated[
        str,
        Field(description="'block_outputs' to explore what a block produced, or 'file' to explore a file."),
    ],
    block_id: Annotated[
        str,
        Field(description="For source='block_outputs': the block whose outputs to load. Its latest run by default."),
    ] = "",
    path: Annotated[
        str,
        Field(description="For source='file': a file in the project's data tree, project-relative or absolute."),
    ] = "",
    run_id: Annotated[
        str,
        Field(description="For source='block_outputs': bind to this run rather than the block's most recent one."),
    ] = "",
    name: Annotated[
        str,
        Field(description="Notebook file stem. Defaults to the block id or the file's stem."),
    ] = "",
) -> OpenExploreSessionResult:
    """Open an explore session over a block's outputs or a file, and return its path.

    Use when:
      - You need to look at real data before writing a block: open a session
        over the block that produced it and read the objects themselves.
      - The person asked for work in a notebook and none is open, or the session
        tools refused because no session is focused.

    Do NOT use to:
      - Move the person somewhere. **This does not change their focus** (FR-019)
        — it opens a session; where they are looking stays theirs. Every later
        call must pass the returned ``session_path``, unless the person is
        already focused on that same notebook.
      - Re-open a notebook you already have: a notebook has one session, so
        calling this twice over the same source makes a second notebook.

    The session opens with no kernel. The first ``run_cell`` starts one.

    Returns:
        The session path — the handle every other session tool takes — with the
        notebook as it was opened and the run it is bound to.
    """
    chosen = (source or "").strip().lower()
    if chosen not in {"block_outputs", "file"}:
        raise SessionToolError(
            f"source must be 'block_outputs' or 'file', not {source!r}. Pass source='block_outputs' with block_id "
            f"set to the block whose outputs you want, or source='file' with path set to a file in the project."
        )
    if chosen == "block_outputs" and not block_id.strip():
        raise SessionToolError("source='block_outputs' needs block_id. Call list_blocks to see what has run.")
    if chosen == "file" and not path.strip():
        raise SessionToolError("source='file' needs path. Call list_data to see what is in the project's data tree.")

    service = session_service()
    stem = name.strip() or None

    def _open() -> Any:
        if chosen == "block_outputs":
            return service.open_over_block_outputs(
                block_id.strip(),
                run_id=run_id.strip() or None,
                name=stem,
            )
        return service.open_over_file(path.strip(), name=stem)

    session = await asyncio.to_thread(_open)

    # FR-019: the focus is read, never written. It is reported so the agent can
    # see for itself that opening a session did not move the person, and knows
    # whether later calls need session_path passed explicitly.
    focus = effective_focus(get_optional_context())
    return OpenExploreSessionResult(
        session_path=session.relative_path,
        session_id=session.session_id,
        opened_over="block_outputs" if chosen == "block_outputs" else "file",
        bound_run=_bound_run_model(session),
        has_kernel=session.has_kernel,
        cells=_cell_models(session),
        focus_unchanged=True,
        focused_session_path=focus.session_path,
    )


# ---------------------------------------------------------------------------
# (h.2) read_notebook  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="read_notebook", tags={"category:session", "read"})
async def read_notebook(
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
) -> ReadNotebookResult:
    """Read an explore session whole: cells, bindings, declared outputs, graph.

    Use when:
      - You are about to write or change a cell and need to see what is there.
      - A run went wrong and you need the marks and the graph to say which cells
        the session no longer trusts.

    Do NOT use to:
      - Poll for a run to finish — ``run_cell`` already waits and returns the
        outputs.
      - Ask only what is bound; ``get_bindings`` is the cheaper question.

    Each cell carries its source, its enabled flag, its marks, and its outputs.
    An output's bytes are not returned: a figure is reported by its MIME type,
    and text is bounded.

    Returns:
        The whole session: the cells, the bindings with their types and whether
        each is live, the ``scistudio.output`` declarations, and the dependency
        graph.
    """
    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)
    bindings = await asyncio.to_thread(_binding_models, session)
    return ReadNotebookResult(
        session_path=session.relative_path,
        session_id=session.session_id,
        has_kernel=session.has_kernel,
        needs_restart=session.needs_restart,
        current_cell=session.current_cell,
        notebook_commit=session.notebook_commit,
        bound_run=_bound_run_model(session),
        cells=_cell_models(session),
        bindings=bindings,
        declared_outputs=_declared_output_models(session),
        graph=_graph_model(session),
    )


# ---------------------------------------------------------------------------
# (h.3) append_cell  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="append_cell", tags={"category:session", "write"})
async def append_cell(
    source: Annotated[str, Field(description="The Python source for the new cell.")],
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
) -> AppendCellResult:
    """Insert a code cell after the session's current cell and return its id.

    Use when:
      - You want to try something in the person's notebook. The cell lands where
        their cursor is, which is where a cell they typed would land.

    Do NOT use to:
      - Rewrite an existing cell — this only inserts.
      - Run it. The cell is inserted, not submitted; call ``run_cell`` next.

    The cell goes in directly after the session's current cell (FR-021), and at
    the end of the notebook when the session has no current cell. It appears in
    the person's notebook through the same events their own edits produce.

    Returns:
        The new cell's id, and the cell it was inserted after.
    """
    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)
    after = session.current_cell
    cell_id = await asyncio.to_thread(lambda: session.insert_cell(source, after=after))
    return AppendCellResult(
        session_path=session.relative_path,
        cell_id=cell_id,
        after=after,
        source=source,
    )


# ---------------------------------------------------------------------------
# (h.4) run_cell  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_cell", tags={"category:session", "write"})
async def run_cell(
    cell_id: Annotated[str, Field(description="The cell to run, as read_notebook or append_cell reported it.")],
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait for the queue to drain before answering that the run is still going."),
    ] = QUEUE_DRAIN_TIMEOUT,
) -> RunCellResult:
    """Submit one cell to the session's queue and return its outputs and changed names.

    Use when:
      - You appended a cell and need to see what it produced.
      - You changed a cell and want the session to re-observe what it binds.

    Do NOT use to:
      - Run the whole notebook. This runs the cell you named and nothing else,
        which is what the session guarantees.
      - Work around a refusal. A disabled cell refuses on purpose; enable it in
        the GUI, or write a new cell.

    Starts the session's kernel if none is running. Waits for the queue to
    drain, so what comes back is the run's own outputs rather than a promise.

    **A refusal is a result.** When the queue declines the submission — the cell
    is disabled, it is not a code cell, no cell carries that id, or the queue is
    shutting down — this returns ``refused=true`` with the reason, not an error.

    Returns:
        The outputs, the names the run was observed to change, whether the cell
        raised, and the cell's marks afterwards — or the queue's refusal.
    """
    from scistudio.explore.session import SessionError

    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)

    try:
        request = await asyncio.to_thread(lambda: session.run_cell(cell_id))
    except KeyError:
        return RunCellResult(
            session_path=session.relative_path,
            cell_id=cell_id,
            refused=True,
            refusal_kind="unknown_cell",
            refusal=(
                f"No cell carries the id {cell_id!r} in this session. Call read_notebook to see the cells "
                f"this notebook actually has."
            ),
            next_step="Call read_notebook and run one of the cell ids it reports.",
        )
    except SessionError as refusal:
        return RunCellResult(
            session_path=session.relative_path,
            cell_id=cell_id,
            refused=True,
            refusal_kind="not_runnable",
            refusal=str(refusal),
            next_step="Fix what the refusal names — enable the cell, or write a code cell — and submit again.",
        )
    except RuntimeError as refusal:
        return RunCellResult(
            session_path=session.relative_path,
            cell_id=cell_id,
            refused=True,
            refusal_kind="queue_unavailable",
            refusal=str(refusal),
            next_step="The session is shutting down; open a session again before running anything.",
        )

    completed = await asyncio.to_thread(lambda: session.wait_until_idle(timeout_seconds))
    outputs = _outputs_of(session, cell_id)
    observation = session.observations.get(cell_id)
    changed = sorted(observation.changed_names) if observation is not None else []
    errored = any(output.output_type == "error" for output in outputs)
    return RunCellResult(
        session_path=session.relative_path,
        cell_id=cell_id,
        completed=completed,
        request_id=getattr(request, "request_id", None),
        state=str(getattr(request, "state", "")) or None,
        outputs=outputs,
        changed_names=changed,
        errored=errored,
        marks=sorted(mark.value for mark in session.marks(cell_id)),
        next_step=(
            "Read `outputs` and `changed_names`. Call get_bindings to see what the run left in the kernel."
            if completed
            else "The run is still going. Call read_notebook again in a moment for its final outputs."
        ),
    )


# ---------------------------------------------------------------------------
# (h.5) get_bindings  (read)
# ---------------------------------------------------------------------------


@mcp.tool(name="get_bindings", tags={"category:session", "read"})
async def get_bindings(
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
) -> GetBindingsResult:
    """Return what the session's notebook binds, and whether each name is live.

    Use when:
      - You are about to write a cell and need to know what already exists,
        which is the common case this tool exists for (FR-022).
      - You are about to package and need the type of each name a declared
        output carries.

    Do NOT use to:
      - Read a value. This says what a name is, not what is in it; a windowed
        read of a variable is the GUI's, not a tool's.

    The set of names is the union of what the kernel holds now and what the
    notebook's cells change or declare — so a name the notebook produces but has
    not run yet comes back with ``exists_in_kernel=false``.

    Returns:
        Every name with its SciStudio type, its native type, a short summary,
        the cell that last bound it, and whether it exists in the kernel.
    """
    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)
    bindings = await asyncio.to_thread(_binding_models, session)
    return GetBindingsResult(
        session_path=session.relative_path,
        has_kernel=session.has_kernel,
        bindings=bindings,
        count=len(bindings),
    )


# ---------------------------------------------------------------------------
# (h.6) check_packaging  (read)
# ---------------------------------------------------------------------------


async def _drain(session: ExploreSession, timeout_seconds: float) -> bool:
    """Wait for the queue, because packaging's marks are not final until it has.

    FR-039's last sentence. A check answered mid-run can call a notebook
    packageable whose slice the running cell is about to make stale.
    """
    return await asyncio.to_thread(lambda: session.wait_until_idle(timeout_seconds))


def _not_drained_problem(timeout_seconds: float) -> PackagingProblemModel:
    return PackagingProblemModel(
        kind="queue_not_drained",
        message=(
            f"This session is still running cells after {timeout_seconds:g}s, and packaging waits for the queue "
            f"to drain because the slice's marks are not final until it has (FR-039). Let the run finish, or "
            f"interrupt the kernel from the GUI, and try again."
        ),
        cell_ids=[],
        names=[],
        refuses=True,
    )


@mcp.tool(name="check_packaging", tags={"category:session", "read"})
async def check_packaging(
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
    file_ports: Annotated[
        dict[str, str] | None,
        Field(description="For a file-opened session: port name -> the notebook variable the load line binds."),
    ] = None,
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait for the queue to drain before refusing to answer from stale marks."),
    ] = QUEUE_DRAIN_TIMEOUT,
) -> CheckPackagingResult:
    """Answer whether this notebook can be packaged, and what block it would make.

    Use when:
      - Before ``package_notebook``, always. It writes nothing and collects
        every reason rather than stopping at the first.
      - The person asked "can this be a block yet?".

    Do NOT use to:
      - Discover the notebook's outputs — ``read_notebook`` reports the
        declarations without waiting for the queue.

    Waits for the queue to drain first: a cell still running can make the slice
    stale, so an answer given before it finishes describes a notebook that no
    longer exists by the time the agent acts on it (FR-039).

    Returns:
        Whether it is packageable, the slice the block would run, the ports it
        would declare, and every problem — the ones that refuse and the ones
        that only report.
    """
    from scistudio.explore.packaging import check_packaging as _check

    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)
    if not await _drain(session, timeout_seconds):
        return CheckPackagingResult(
            session_path=session.relative_path,
            is_packageable=False,
            problems=[_not_drained_problem(timeout_seconds)],
            notebook_commit=session.notebook_commit,
        )

    def _plan() -> Any:
        return _check(
            session.document,
            marks=session.cell_marks(),
            bindings=session.binding_types(),
            observations=session.observations,
            file_ports=file_ports,
        )

    plan = await asyncio.to_thread(_plan)
    return CheckPackagingResult(
        session_path=session.relative_path,
        is_packageable=plan.is_packageable,
        cells=list(plan.cells),
        inputs=_port_models(plan.inputs),
        outputs=_port_models(plan.outputs),
        problems=_problem_models(plan.problems),
        notebook_commit=session.notebook_commit,
    )


# ---------------------------------------------------------------------------
# (h.7) package_notebook  (write)
# ---------------------------------------------------------------------------


@mcp.tool(name="package_notebook", tags={"category:session", "write"})
async def package_notebook(
    block_name: Annotated[
        str, Field(description="What to call the block. Becomes the file stem and the display name.")
    ],
    session_path: Annotated[
        str,
        Field(description="The session's notebook path. Defaults to the session the person is focused on."),
    ] = "",
    on_new_input: Annotated[
        str,
        Field(description="'replay' (re-run on changed input) or 'ask' (pause and ask the person first)."),
    ] = "replay",
    file_ports: Annotated[
        dict[str, str] | None,
        Field(description="For a file-opened session: port name -> the notebook variable the load line binds."),
    ] = None,
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait for the queue to drain before refusing to package from stale marks."),
    ] = QUEUE_DRAIN_TIMEOUT,
) -> PackageNotebookResult:
    """Package the notebook's declared-output slice into a Code Block.

    Use when:
      - ``check_packaging`` says it is packageable and the person asked for a
        block.

    Do NOT use to:
      - Find out whether it would work — that is ``check_packaging``, which
        writes nothing.
      - Package a notebook nothing has run in. A block's version is the commit
        it was packaged from, so a notebook with no commit is refused.

    Writes two files into the project's blocks directory and nothing else: the
    generated declaration and a copy of the notebook beside it. The notebook
    this was packaged from is never touched.

    **A refusal is a result.** When packaging refuses, this returns
    ``packaged=false`` with the whole report on ``problems`` (FR-023) — nothing
    was written — rather than raising and leaving the agent to reconstruct why.

    Returns:
        The block id the registry will key the block by, the files written, and
        the ports — or the packaging report when it was refused.
    """
    from scistudio.explore.packaging import PackagingRefusedError
    from scistudio.explore.packaging import package_notebook as _package

    resolved = resolve_session_path(session_path or None)
    session = session_for(resolved)
    service = session_service()

    if not await _drain(session, timeout_seconds):
        return PackageNotebookResult(
            session_path=session.relative_path,
            packaged=False,
            problems=[_not_drained_problem(timeout_seconds)],
            refusal="The session's queue did not drain, and packaging must not read marks that are not final.",
        )

    commit = session.notebook_commit
    if not commit:
        message = (
            "This notebook has no commit yet, and a packaged block's version is the commit it was packaged "
            "from (FR-041). Run a cell first, then package."
        )
        return PackageNotebookResult(
            session_path=session.relative_path,
            packaged=False,
            problems=[
                PackagingProblemModel(kind="no_notebook_commit", message=message, cell_ids=[], names=[], refuses=True)
            ],
            refusal=message,
        )

    def _write() -> Any:
        return _package(
            session.document,
            project_dir=service.project_dir,
            block_name=block_name,
            notebook_commit=commit,
            marks=session.cell_marks(),
            bindings=session.binding_types(),
            observations=session.observations,
            file_ports=file_ports,
            on_new_input=on_new_input,
        )

    try:
        packaged = await asyncio.to_thread(_write)
    except PackagingRefusedError as refusal:
        return PackageNotebookResult(
            session_path=session.relative_path,
            packaged=False,
            problems=_problem_models(refusal.problems),
            refusal=str(refusal),
        )
    except ValueError as refusal:
        # A block name that yields no identifier, or an on_new_input that is
        # neither policy. The agent chose both, so this is its refusal to read.
        return PackageNotebookResult(
            session_path=session.relative_path,
            packaged=False,
            problems=[
                PackagingProblemModel(
                    kind="invalid_argument", message=str(refusal), cell_ids=[], names=[], refuses=True
                )
            ],
            refusal=str(refusal),
        )

    _publish_packaged(service, session, packaged)
    return PackageNotebookResult(
        session_path=session.relative_path,
        packaged=True,
        block_id=packaged.class_name,
        block_name=packaged.block_name,
        declaration_path=str(packaged.declaration_path),
        notebook_path=str(packaged.notebook_path),
        notebook_commit=packaged.notebook_commit,
        cells=list(packaged.cells),
        inputs=_port_models(packaged.inputs),
        outputs=_port_models(packaged.outputs),
        on_new_input=packaged.on_new_input,
        problems=_problem_models(packaged.problems),
    )


def _publish_packaged(service: Any, session: ExploreSession, packaged: Any) -> None:
    """Publish FR-057's ``packaged`` event, the way the HTTP route publishes it.

    Packaging is a module function rather than a method on the service, so the
    caller hands the event to the service rather than inventing a second
    channel — which is exactly what ``api/routes/explore.py`` does. Doing it
    here too is what makes a block the agent packaged appear to the person
    through the same event their own packaging produces.

    Best-effort: a block was written, and an event the hub could not take must
    not turn a completed package into a failure.
    """
    try:
        from scistudio.explore.session import SessionEvent, SessionEventType

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
    except Exception:  # pragma: no cover - the block is written either way
        logger.warning("session tools: the packaged event could not be published", exc_info=True)
