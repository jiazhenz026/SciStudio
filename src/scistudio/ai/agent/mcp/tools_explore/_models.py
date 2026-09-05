"""Result envelopes for the seven session tools (ADR-054 spec 5 FR-019 to FR-024).

These are the *agent's* view of an explore session — a notebook path it can pass
back as ``session_path``, a cell id it can run, a refusal it can read and act on
— not the session subsystem's own types. Keeping them here rather than in
:mod:`scistudio.explore` is the same choice the panel tools made for the same
reason: the session runtime must not carry a dependency on how one client
prefers to be told things.

**Why the cell outputs are rendered rather than passed through.** A notebook
output is an nbformat mapping, and a single ``display_data`` can carry a
multi-megabyte base64 PNG. Handing that to an agent verbatim would spend its
whole context on one figure it cannot look at anyway. :class:`CellOutputModel`
therefore keeps what an agent can act on — the stream text, the ``text/plain``
representation, the error name, value and traceback — bounded by
:data:`OUTPUT_TEXT_LIMIT`, and reports the other MIME types by name so the agent
knows a figure was produced without being sent its bytes. ``truncated`` says
when that happened, so the tool never quietly shortens something and calls it
whole.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = [
    "OUTPUT_TEXT_LIMIT",
    "AppendCellResult",
    "BindingModel",
    "BoundRunModel",
    "BoundRunPortModel",
    "CellModel",
    "CellOutputModel",
    "CheckPackagingResult",
    "DeclaredOutputModel",
    "GetBindingsResult",
    "GraphEdgeModel",
    "NotebookGraphModel",
    "OpenExploreSessionResult",
    "PackageNotebookResult",
    "PackagedPortModel",
    "PackagingProblemModel",
    "ReadNotebookResult",
    "RunCellResult",
    "UnresolvedReadModel",
]

#: How much text one rendered output may carry. Generous enough for a traceback
#: and a printed table, small enough that a notebook of them still fits in a
#: tool result the agent can read.
OUTPUT_TEXT_LIMIT = 4000


class CellOutputModel(BaseModel):
    """One notebook output, rendered to what an agent can act on."""

    output_type: str = Field(description="nbformat output type: 'stream', 'execute_result', 'display_data', 'error'.")
    name: str | None = Field(default=None, description="For a stream output: 'stdout' or 'stderr'.")
    text: str = Field(
        default="",
        description=(
            "The stream text, the text/plain representation, or the error's traceback — whichever this "
            "output carries. Bounded; see `truncated`."
        ),
    )
    mime_types: list[str] = Field(
        default_factory=list,
        description=(
            "Every MIME type this output carries, including the ones whose bytes were not returned "
            "(an image, a widget). A figure shows up here rather than as base64."
        ),
    )
    execution_count: int | None = Field(default=None, description="Execution count of an execute_result output.")
    ename: str | None = Field(default=None, description="Exception class name, for an error output.")
    evalue: str | None = Field(default=None, description="Exception message, for an error output.")
    truncated: bool = Field(default=False, description="True when `text` was cut to the output text limit.")


class CellModel(BaseModel):
    """One notebook cell, as FR-020 asks for it."""

    cell_id: str = Field(description="The cell's id. Pass this to run_cell.")
    cell_type: str = Field(description="'code', 'markdown', or 'raw'. Only a code cell runs.")
    source: str = Field(description="The cell's source, as one string.")
    enabled: bool = Field(
        description="Whether the dependency analysis builds the graph over this cell. A disabled cell will not run."
    )
    marks: list[str] = Field(
        default_factory=list,
        description=(
            "Why this cell is questionable: 'never_run', 'stale', 'out_of_order'. Empty means nothing about "
            "it is questionable. Packaging refuses a declared-output slice that contains a marked cell."
        ),
    )
    outputs: list[CellOutputModel] = Field(default_factory=list, description="The cell's outputs, rendered.")
    execution_count: int | None = Field(default=None, description="The cell's execution count, or None if never run.")


class BindingModel(BaseModel):
    """One name the notebook binds or would bind (FR-020, FR-022)."""

    name: str = Field(description="The name as it is bound in the kernel namespace.")
    exists_in_kernel: bool = Field(
        description=(
            "Whether the name is bound right now. False for a name the notebook's cells change but the "
            "kernel has not run yet — it is still worth knowing the notebook produces it."
        )
    )
    type_name: str | None = Field(
        default=None, description="The SciStudio type of the bound object, which is how packaging types a port."
    )
    native_type_name: str | None = Field(default=None, description="type(value).__name__ — the person's reading.")
    type_module: str | None = Field(default=None, description="The module the native type came from.")
    summary: str | None = Field(default=None, description="A short bounded description: a length, a shape, a repr.")
    last_bound_by: str | None = Field(default=None, description="The cell that last bound this name in the kernel.")


class DeclaredOutputModel(BaseModel):
    """One ``scistudio.output(...)`` call the notebook makes (FR-020)."""

    cell_id: str = Field(description="The cell that declares these outputs.")
    names: list[str] = Field(
        default_factory=list, description="The declared port names, in written order. These become the block's outputs."
    )
    arguments: list[str] = Field(
        default_factory=list, description="The notebook variables passed as the declaration's values."
    )


class GraphEdgeModel(BaseModel):
    """One dependency edge: *reader* reads *name*, which *definer* changes."""

    reader: str = Field(description="The cell that reads the name.")
    definer: str = Field(description="The nearest enabled cell above it that changes the name.")
    name: str = Field(description="The name carried across the edge.")
    origin: str = Field(
        description="Whether the definer's changed set was observed from a run or estimated statically."
    )


class UnresolvedReadModel(BaseModel):
    """A name a cell reads that no cell above it defines."""

    cell_id: str = Field(description="The reading cell.")
    name: str = Field(description="The unresolved name.")


class NotebookGraphModel(BaseModel):
    """The dependency graph over the enabled code cells (FR-020)."""

    cells: list[str] = Field(default_factory=list, description="The cells in the graph, in written order.")
    edges: list[GraphEdgeModel] = Field(default_factory=list, description="The dependency edges.")
    unresolved_reads: list[UnresolvedReadModel] = Field(
        default_factory=list, description="Names read with nothing above defining them — usually an import or a typo."
    )
    unknown_binding_cells: list[str] = Field(
        default_factory=list, description="Cells whose changed set is not yet known because they have never run."
    )
    changed_sets: dict[str, list[str]] = Field(
        default_factory=dict, description="What each cell changes, as the analysis currently reports it."
    )


class BoundRunPortModel(BaseModel):
    """One port of the run a session was opened over."""

    name: str = Field(description="The port name.")
    type_name: str = Field(description="The SciStudio type of the artefact.")
    backend: str = Field(default="", description="The storage backend the artefact lives in.")
    path: str = Field(default="", description="The artefact's path.")
    format: str | None = Field(default=None, description="The artefact's format hint, when the backend has one.")


class BoundRunModel(BaseModel):
    """The run a session is bound to, when it was opened over one."""

    run_id: str = Field(description="The run the session is bound to.")
    block_id: str = Field(description="The block whose ports the notebook loads.")
    opened_over: str = Field(description="What the session was opened over: 'block_outputs' or 'paused_run'.")
    ports: list[BoundRunPortModel] = Field(default_factory=list, description="The ports the first cell loads.")


class OpenExploreSessionResult(BaseModel):
    """Result envelope for ``open_explore_session`` (FR-019)."""

    session_path: str = Field(
        description=(
            "Project-relative POSIX path of the session's notebook. This is the handle: pass it as "
            "`session_path` to every other session tool."
        )
    )
    session_id: str = Field(description="The session's id.")
    opened_over: str = Field(description="'block_outputs' or 'file' — what this session was opened over.")
    bound_run: BoundRunModel | None = Field(default=None, description="The run the session is bound to, if any.")
    has_kernel: bool = Field(description="Whether a kernel is running. A fresh session has none until a cell runs.")
    cells: list[CellModel] = Field(default_factory=list, description="The notebook as it was opened.")
    focus_unchanged: bool = Field(
        default=True,
        description=(
            "Always true: FR-019 forbids this tool from moving the person's focus. Opening a session does "
            "not put the person in it, and `focused_session_path` says where they still are."
        ),
    )
    focused_session_path: str | None = Field(
        default=None,
        description=(
            "The notebook the person is still focused on, or None when they are not in a session. Unchanged "
            "by this call. When it differs from `session_path`, every other session tool needs `session_path` passed in."
        ),
    )
    next_step: str = Field(
        default=(
            "Call read_notebook with this session_path to see the cells, then append_cell and run_cell. "
            "The person's focus was not moved, so pass session_path to every call."
        ),
        description="Suggested next action.",
    )


class ReadNotebookResult(BaseModel):
    """Result envelope for ``read_notebook`` (FR-020)."""

    session_path: str = Field(description="The session this describes.")
    session_id: str = Field(description="The session's id.")
    has_kernel: bool = Field(description="Whether a kernel is running.")
    needs_restart: bool = Field(description="Whether the kernel died and the session needs a restart.")
    current_cell: str | None = Field(
        default=None, description="The cell append_cell inserts after, which is the cell the person is on."
    )
    notebook_commit: str | None = Field(
        default=None,
        description="The notebook's latest explore commit. Packaging needs one, so a notebook that has never run has None.",
    )
    bound_run: BoundRunModel | None = Field(default=None, description="The run the session is bound to, if any.")
    cells: list[CellModel] = Field(
        default_factory=list, description="Every cell with its source, flag, marks, outputs."
    )
    bindings: list[BindingModel] = Field(default_factory=list, description="Every name, and whether it is live.")
    declared_outputs: list[DeclaredOutputModel] = Field(
        default_factory=list, description="The scistudio.output declarations, which are the block's output ports."
    )
    graph: NotebookGraphModel = Field(
        default_factory=NotebookGraphModel, description="The dependency graph over the enabled code cells."
    )


class AppendCellResult(BaseModel):
    """Result envelope for ``append_cell`` (FR-021)."""

    session_path: str = Field(description="The session the cell was inserted into.")
    cell_id: str = Field(description="The new cell's id. Pass it to run_cell.")
    after: str | None = Field(
        default=None,
        description="The cell it was inserted after — the session's current cell, or None when it was appended at the end.",
    )
    source: str = Field(description="The source as it was written into the cell.")
    next_step: str = Field(
        default="Call run_cell with this cell_id to run it, and read its outputs and changed names from the result.",
        description="Suggested next action.",
    )


class RunCellResult(BaseModel):
    """Result envelope for ``run_cell`` (FR-021).

    A refusal is a **result**, not an exception: the queue declining a cell is
    an answer the agent has to read and act on, and an error would lose the
    shape of it.
    """

    session_path: str = Field(description="The session the cell belongs to.")
    cell_id: str = Field(description="The cell that was submitted.")
    refused: bool = Field(default=False, description="True when the session's queue declined the submission.")
    refusal: str | None = Field(default=None, description="Why the submission was declined, in words to act on.")
    refusal_kind: str | None = Field(
        default=None,
        description=(
            "Machine-readable refusal: 'unknown_cell' (no cell carries that id), 'not_runnable' (disabled, or "
            "not a code cell), or 'queue_unavailable' (the queue is stopping)."
        ),
    )
    completed: bool = Field(
        default=False,
        description=(
            "Whether the queue drained before the wait ran out. False means the run is still going: the cell "
            "was submitted and will finish, but the outputs below are not its final ones."
        ),
    )
    request_id: str | None = Field(default=None, description="The queued request's id, for correlating with events.")
    state: str | None = Field(
        default=None, description="The request's state: queued, running, done, failed, cancelled."
    )
    outputs: list[CellOutputModel] = Field(default_factory=list, description="The cell's outputs after the run.")
    changed_names: list[str] = Field(
        default_factory=list,
        description="The names the run was observed to change. Empty when the cell bound nothing new and moved nothing.",
    )
    errored: bool = Field(default=False, description="True when the cell raised. The traceback is in `outputs`.")
    marks: list[str] = Field(default_factory=list, description="The cell's marks after the run.")
    next_step: str = Field(
        default="Read `outputs` and `changed_names`. Call get_bindings to see what the run left in the kernel.",
        description="Suggested next action.",
    )


class GetBindingsResult(BaseModel):
    """Result envelope for ``get_bindings`` (FR-022)."""

    session_path: str = Field(description="The session this describes.")
    has_kernel: bool = Field(
        description="Whether a kernel is running. Without one nothing is bound, and every binding reads exists_in_kernel=false."
    )
    bindings: list[BindingModel] = Field(default_factory=list, description="Every name, with its type and liveness.")
    count: int = Field(description="How many bindings were returned.")


class PackagingProblemModel(BaseModel):
    """One thing packaging found."""

    kind: str = Field(description="The problem's kind, e.g. 'no-declared-output', 'questionable-cell'.")
    message: str = Field(description="What is wrong, in words to act on.")
    cell_ids: list[str] = Field(default_factory=list, description="The cells the problem is about.")
    names: list[str] = Field(default_factory=list, description="The names the problem is about.")
    refuses: bool = Field(
        description="Whether this problem blocks packaging. A reported-but-resolved problem leaves the notebook packageable."
    )


class PackagedPortModel(BaseModel):
    """One port the generated block would declare."""

    name: str = Field(description="The port name, which is the declared name in the notebook.")
    direction: str = Field(description="'input' or 'output'.")
    data_type: str = Field(description="The SciStudio type of the object bound to the port's name.")
    extension: str = Field(description="The file extension the materialisation layer assigns to that type.")
    bound_name: str = Field(default="", description="The notebook variable the port carries, when it differs.")


class CheckPackagingResult(BaseModel):
    """Result envelope for ``check_packaging`` (FR-023)."""

    session_path: str = Field(description="The session this describes.")
    is_packageable: bool = Field(description="Whether nothing refuses this notebook.")
    cells: list[str] = Field(
        default_factory=list, description="The backward slice of the declared outputs — what the block would run."
    )
    inputs: list[PackagedPortModel] = Field(
        default_factory=list, description="The input ports the block would declare."
    )
    outputs: list[PackagedPortModel] = Field(
        default_factory=list, description="The output ports the block would declare."
    )
    problems: list[PackagingProblemModel] = Field(
        default_factory=list, description="Everything packaging found, refusals and reports alike."
    )
    notebook_commit: str | None = Field(
        default=None,
        description=(
            "The commit packaging would record as the block's version. None means no cell has run yet, and "
            "package_notebook will refuse for that reason alone."
        ),
    )


class PackageNotebookResult(BaseModel):
    """Result envelope for ``package_notebook`` (FR-023).

    Refusal is a **result**: FR-023 says this tool returns the block id "or the
    report when packaging is refused", so a refused notebook comes back with
    ``packaged=False`` and every problem, not as an error the agent has to
    reconstruct the report from.
    """

    session_path: str = Field(description="The session that was packaged.")
    packaged: bool = Field(description="Whether a block was written. False means nothing was written at all.")
    block_id: str | None = Field(
        default=None,
        description=(
            "The generated class's name, which is what the block registry keys the block by and what a "
            "workflow node references. None when packaging was refused."
        ),
    )
    block_name: str | None = Field(
        default=None, description="The file stem of both written files, and the display name."
    )
    declaration_path: str | None = Field(default=None, description="Absolute path of the generated .py declaration.")
    notebook_path: str | None = Field(default=None, description="Absolute path of the notebook copy written beside it.")
    notebook_commit: str | None = Field(
        default=None, description="The commit the block was packaged from — its version."
    )
    cells: list[str] = Field(default_factory=list, description="The slice the block runs, in written order.")
    inputs: list[PackagedPortModel] = Field(default_factory=list, description="The block's input ports.")
    outputs: list[PackagedPortModel] = Field(default_factory=list, description="The block's output ports.")
    on_new_input: str | None = Field(
        default=None, description="'replay' or 'ask' — what the block does on changed input."
    )
    problems: list[PackagingProblemModel] = Field(
        default_factory=list,
        description="The packaging report. On a refusal this is why; on success it is what packaging resolved on the way past.",
    )
    refusal: str | None = Field(
        default=None, description="A one-line summary of the refusal, or None when it packaged."
    )
    next_step: str = Field(
        default=(
            "Call reload_blocks so the registry discovers the new block, then place it in a workflow. "
            "On a refusal, fix each problem that has refuses=true and call check_packaging again."
        ),
        description="Suggested next action.",
    )
