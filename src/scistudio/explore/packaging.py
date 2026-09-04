"""Packaging an exploration notebook into a Code Block (ADR-054 FR-037 to FR-043, FR-046).

A person explores in a notebook, and when the notebook is worth keeping they
package it. ADR-054 §4.1 says what that produces, and it is deliberately not a
new kind of node: *packaging produces a Code Block, because that is what it is*.
A Code Block already runs a ``.ipynb`` through ``nbconvert`` from the project
root with exchange folders for its ports, so packaging writes a block
declaration the tier-1 scan discovers — a Python file in the project's blocks
directory defining a :class:`~scistudio.blocks.code.code_block.CodeBlock`
subclass with the ports and the notebook as its script — and copies the notebook
beside it. The scan is not recursive, which is why the declaration sits directly
in the blocks directory rather than in a subdirectory of it.

What this module adds to that is four things and no more.

**The checks that refuse** (FR-039). A notebook is packaged from the backward
slice of its declared outputs, and a slice that would not reproduce what the
person saw must not become a block. Packaging refuses a notebook whose slice
contains a never-run, stale, or out-of-order cell, whose slice has an unresolved
read, whose slice calls an interactive block, or that declares no output at all
— and every refusal **names the cells**, because "packaging failed" is not
something a person can act on.

The three marks are the session's, not the analysis'. They arrive here as
:class:`CellMarks`, an argument rather than an import, so the check is a pure
function of the notebook and the marks the caller passes and so this module does
not reach into the session service to ask.

**The ports** (FR-038). The block's inputs are the notebook's
``scistudio.input`` declarations and its outputs the ``scistudio.output``
declarations, exactly as the dependency analysis reports them. Each port's type
is the SciStudio type of the object bound to that name at packaging — which the
caller supplies, because only the kernel knows it — and each port's extension is
the default the materialisation layer assigns to that type.

**The cell selection** (FR-040). A packaged block's run executes the slice and
nothing else. The declaration carries the slice's cell ids and the notebook
backend materialises exactly those cells, in written order, as the notebook
``nbconvert`` runs. The copy on disk stays whole, so reopening the block's
notebook (FR-042) shows the person the notebook they wrote rather than a
fragment of it.

**The ask pause** (FR-046). A packaged block set to ask is an interactive block
whose decision is a notebook commit and whose panel is the Explore tab. It
reuses the engine's existing interactive pause rather than getting one of its
own: its prompt names the notebook, the commit, and the run's inputs, and the
commit the person confirms is what the compute phase executes. A packaged block
left at its default, ``replay``, is an ordinary Code Block and never pauses.

What this module does **not** do is touch the notebook it packaged from
(FR-043). Everything it writes is under the project's blocks directory.
"""

from __future__ import annotations

import ast
import keyword
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    INTERACTIVE_RESPONSE_KEY,
    InteractionPolicy,
    InteractiveMixin,
    PanelManifest,
    interactive_input_signature,
)
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.code.backends.notebook import NOTEBOOK_CELL_SELECTION_KEY
from scistudio.blocks.code.code_block import CodeBlock

# ADR-054 FR-054: the opt-in marker that makes a block's own version — here a
# notebook commit — win over the ADR-038 §3.3 distribution stamping. It is
# imported from ``_spec`` because that is the module that reads it: ADR-047 §C9
# keeps every module-level registry helper there and leaves ``registry``'s
# ``__init__`` for the class alone, so there is no public re-export to reach for
# without widening the registry's surface, which this change does not do.
from scistudio.blocks.registry._spec import SELF_DECLARED_VERSION
from scistudio.explore.dependency_analysis import (
    AnalysisFlag,
    CellFacts,
    DependencyGraph,
    OutputDeclaration,
    analyse_cells,
    build_graph,
)
from scistudio.explore.notebook import NotebookDocument, write_notebook
from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scistudio.core.types.collection import Collection

#: Directory, relative to the project root, that the tier-1 scan reads.
#:
#: The scan is not recursive (``scistudio.blocks.registry._scan._scan_tier1``
#: globs ``*.py``), so both the declaration and the notebook copy sit directly
#: in it.
BLOCKS_DIRNAME = "blocks"

#: Panel id of the Explore tab a packaged block's ask pause opens.
#:
#: The tab itself is the explore-frontend spec's surface; this module only names
#: it, so that the prompt event the engine emits carries a manifest the frontend
#: can resolve without a hardcoded block-type branch.
EXPLORE_SESSION_PANEL_ID = "core.explore.session"

#: Key under which a confirmed decision carries the notebook commit to execute
#: (FR-047).
DECISION_COMMIT_KEY = "notebook_commit"

#: Subdirectory of the blocks directory holding notebooks materialised from a
#: commit other than the packaged one (FR-047).
#:
#: It is a subdirectory precisely because the tier-1 scan is not recursive: a
#: materialised notebook must never be mistaken for a declaration, and nothing
#: here is a ``.py`` file in the scanned directory.
MATERIALISED_DIRNAME = ".packaged"

#: Extension the materialisation layer assigns to each core type, used when no
#: block registry is available to answer.
#:
#: Mirrors ``scistudio.blocks.io.materialisation``: with a registry, the answer
#: is the first extension of the first saver registered for the type, which is
#: what ``materialise_to_file`` itself uses when it is given no extension. This
#: table is the same answer for the six core types, so a caller that has not
#: scanned a registry still gets ports the exchange layer can write.
CORE_TYPE_EXTENSIONS: Mapping[str, str] = {
    "DataFrame": ".csv",
    "Series": ".csv",
    "Array": ".npy",
    "Text": ".txt",
    "Artifact": ".bin",
    "CompositeData": ".zarr",
    "DataObject": ".bin",
}

_IDENTIFIER_RE = re.compile(r"[^0-9a-zA-Z_]+")


# ---------------------------------------------------------------------------
# What packaging refuses (FR-039)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class PackagingProblemKind(StrEnum):
    """The closed set of things packaging reports about a notebook (FR-039).

    All but one of these refuse. :attr:`DUPLICATE_OUTPUT_DECLARATION` is
    reported without refusing, because spec §2's edge case resolves it —
    "the later declaration in written order wins" — rather than rejecting it,
    and a resolved ambiguity the person is not told about is the failure that
    edge case is guarding against. :attr:`PackagingProblem.refuses` says which
    a given problem is.
    """

    NO_DECLARED_OUTPUT = "no_declared_output"
    """The notebook declares no ``scistudio.output``, so there is no slice to package."""

    NEVER_RUN_CELL = "never_run_cell"
    """A cell in the slice has never run, so nothing observed what it changes."""

    STALE_CELL = "stale_cell"
    """A cell in the slice is stale: something it depends on has re-run since it did."""

    OUT_OF_ORDER_CELL = "out_of_order_cell"
    """A cell in the slice read a name from a cell other than the one written order names."""

    UNRESOLVED_READ = "unresolved_read"
    """A cell in the slice reads a name no enabled cell above it changes."""

    INTERACTIVE_BLOCK_CALL = "interactive_block_call"
    """A cell in the slice calls an interactive block, which cannot run unattended (FR-050)."""

    UNKNOWN_BLOCK_CALL = "unknown_block_call"
    """A cell in the slice calls a block whose identifier is not a string literal.

    Refused with the interactive calls rather than allowed through: the block a
    run would reach cannot be named without running the cell, so packaging
    cannot show that it is not an interactive one.
    """

    DUPLICATE_OUTPUT_DECLARATION = "duplicate_output_declaration"
    """The same port name was declared as an output more than once.

    Spec §2's edge case: "The same name is declared as output twice. The later
    declaration in written order wins, and packaging reports the duplicate."
    This is the report, and it does not refuse — the second declaration is a
    person refining an output, and refusing would turn a resolved ambiguity
    into a dead end. What must not happen is the silent version: a second
    ``scistudio.output(table=better)`` that leaves the port wired to ``worse``,
    with ``worse``'s type, and says nothing.
    """

    UNTYPED_PORT = "untyped_port"
    """A declared port names something the caller reported no bound type for.

    FR-038 makes a port's type the SciStudio type of the object bound to that
    name at packaging. When nothing is bound there is no type to give the port,
    and a port with a guessed type would fail at the exchange layer instead of
    here, where the cell can still be named.
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PackagingProblem:
    """One thing packaging found, with the cells it is about.

    :attr:`cell_ids` is what makes a report actionable, and it is never empty
    except for :attr:`PackagingProblemKind.NO_DECLARED_OUTPUT`, which is about
    the notebook rather than about any cell in it.
    """

    kind: PackagingProblemKind
    """Which problem this is."""
    message: str
    """Human-readable text naming the cells and, where it has them, the names."""
    cell_ids: tuple[str, ...] = ()
    """The offending cells, in the notebook's written order."""
    names: tuple[str, ...] = ()
    """The names or block identifiers the problem is about, where it has any."""
    refuses: bool = True
    """Whether this problem stops the notebook being packaged.

    Every refusal of FR-039 sets this. The one problem that does not is the
    duplicate output declaration of spec §2, which packaging resolves and
    reports rather than rejects.
    """


@provisional(since="0.3.4")
class PackagingRefusedError(ValueError):
    """Packaging refused the notebook; :attr:`problems` says why (FR-039).

    Example:
        >>> try:
        ...     package_notebook(...)  # doctest: +SKIP
        ... except PackagingRefusedError as refusal:  # doctest: +SKIP
        ...     for problem in refusal.problems:
        ...         print(problem.message)
    """

    def __init__(self, problems: Sequence[PackagingProblem]) -> None:
        self.problems = tuple(problems)
        """Every reason the notebook was refused, in the order they were found."""
        super().__init__("This notebook cannot be packaged: " + " ".join(problem.message for problem in self.problems))


@provisional(since="0.3.4")
@dataclass(frozen=True)
class CellMarks:
    """The session's marks over a notebook's cells, as packaging needs them.

    The marks live in the session, not in the analysis and not here: the session
    is what watches cells run and propagates staleness. Packaging takes them as
    an argument so that the check is a pure function of the notebook and the
    marks, and so that this module never reaches into the session service.

    Every field is optional and defaults to empty, which is what a freshly
    replayed notebook looks like.

    Example:
        >>> marks = CellMarks(stale=["cell-b"])
        >>> "cell-b" in marks.stale
        True
    """

    never_run: frozenset[str] = field(default_factory=frozenset)
    """Cells that have not run in this session."""
    stale: frozenset[str] = field(default_factory=frozenset)
    """Cells something they depend on has re-run since."""
    out_of_order: frozenset[str] = field(default_factory=frozenset)
    """Cells that read a name from a cell other than the one written order names."""

    def __init__(
        self,
        never_run: Iterable[str] = (),
        stale: Iterable[str] = (),
        out_of_order: Iterable[str] = (),
    ) -> None:
        object.__setattr__(self, "never_run", frozenset(never_run))
        object.__setattr__(self, "stale", frozenset(stale))
        object.__setattr__(self, "out_of_order", frozenset(out_of_order))


# ---------------------------------------------------------------------------
# Ports and the plan (FR-038)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PackagedPort:
    """One port of the generated block, ready to be written into its declaration."""

    name: str
    """The port name, which is the declared name in the notebook."""
    direction: str
    """``"input"`` or ``"output"``."""
    data_type: str
    """The SciStudio type name of the object bound to the port's name at packaging."""
    extension: str
    """The file extension the materialisation layer assigns to :attr:`data_type`."""
    bound_name: str = ""
    """The notebook variable the port carries, when it differs from :attr:`name`."""

    def as_port_config(self) -> dict[str, str]:
        """Return this port as the ``PortFileConfig`` mapping a Code Block reads."""
        return {
            "name": self.name,
            "direction": self.direction,
            "data_type": self.data_type,
            "extension": self.extension,
        }


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PackagingPlan:
    """What packaging would produce, and every reason it would refuse.

    Returned by :func:`check_packaging` so the session API can answer "can this
    be packaged, and if not why not" without writing anything (FR-056).
    """

    cells: tuple[str, ...] = ()
    """The backward slice of the declared outputs, in written order."""
    inputs: tuple[PackagedPort, ...] = ()
    """The input ports the generated block would declare."""
    outputs: tuple[PackagedPort, ...] = ()
    """The output ports the generated block would declare."""
    problems: tuple[PackagingProblem, ...] = ()
    """Everything packaging found, refusals and reports alike.

    Empty when the notebook is clean. Not every entry refuses: see
    :attr:`PackagingProblem.refuses`, and
    :attr:`PackagingProblemKind.DUPLICATE_OUTPUT_DECLARATION` for the one that
    does not.
    """

    @property
    def is_packageable(self) -> bool:
        """``True`` when nothing *refuses* this notebook.

        A reported-but-resolved problem — the duplicate output declaration of
        spec §2 — leaves this ``True``: the last declaration wins, so there is
        a block to write, and the person is told about the duplicate rather
        than blocked by it.
        """
        return not any(problem.refuses for problem in self.problems)


# ---------------------------------------------------------------------------
# The check (FR-039)
# ---------------------------------------------------------------------------


def _code_cells(document: NotebookDocument) -> list[tuple[str, str]]:
    """Return the ``(cell_id, source)`` pairs the analysis is built over.

    Raises:
        ValueError: When a code cell has no nbformat 4.5 id. Marks, analysis
            records, and the cell selection are all keyed by that id, so a
            notebook without ids cannot be packaged at all.
    """
    pairs: list[tuple[str, str]] = []
    for index, cell in enumerate(document.cells):
        if cell.cell_type != "code":
            continue
        if cell.cell_id is None:
            raise ValueError(
                f"Code cell at position {index} has no id. Packaging keys the cell selection by "
                f"nbformat 4.5 cell ids, so a notebook written before 4.5 must be re-saved first."
            )
        pairs.append((cell.cell_id, cell.source))
    return pairs


def _enabled_flags(document: NotebookDocument) -> dict[str, bool]:
    return {cell.cell_id: cell.enabled for cell in document.cells if cell.cell_id is not None}


def _analyse(
    document: NotebookDocument,
    *,
    observations: Mapping[str, object] | None,
) -> tuple[tuple[CellFacts, ...], DependencyGraph]:
    facts = analyse_cells(_code_cells(document))
    graph = build_graph(facts, enabled=_enabled_flags(document), observations=observations)
    return facts, graph


@provisional(since="0.3.4")
def slice_for_outputs(
    document: NotebookDocument,
    *,
    observations: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return the backward slice of the notebook's declared outputs, in written order.

    The selection a packaged block runs (FR-040). Computed from the notebook
    alone, so the same notebook always yields the same slice — which is what
    lets a run reproduce the slice of a commit other than the packaged one
    (FR-047) without carrying a second copy of the answer.

    Args:
        document: The notebook to slice.
        observations: What each cell was observed to change when it ran, as
            :func:`~scistudio.explore.dependency_analysis.build_graph` takes it.

    Returns:
        The cell ids of the slice, in the notebook's written order. Empty when
        the notebook declares no output.
    """
    facts, graph = _analyse(document, observations=observations)
    output_cells = _output_cell_ids(facts, graph)
    if not output_cells:
        return ()
    return graph.backward_slice(output_cells).cells


def _output_cell_ids(facts: Sequence[CellFacts], graph: DependencyGraph) -> tuple[str, ...]:
    enabled = set(graph.cells)
    return tuple(cell.cell_id for cell in facts if cell.is_output_cell and cell.cell_id in enabled)


def _ordered(cell_ids: Iterable[str], order: Sequence[str]) -> tuple[str, ...]:
    position = {cell_id: index for index, cell_id in enumerate(order)}
    return tuple(sorted(set(cell_ids), key=lambda cell_id: position.get(cell_id, len(position))))


def _mark_problem(
    kind: PackagingProblemKind,
    marked: Iterable[str],
    slice_cells: Sequence[str],
    description: str,
) -> PackagingProblem | None:
    offending = _ordered(set(marked) & set(slice_cells), slice_cells)
    if not offending:
        return None
    return PackagingProblem(
        kind=kind,
        message=f"{len(offending)} cell(s) in the declared-output slice {description}: {', '.join(offending)}.",
        cell_ids=offending,
    )


def _port_pairs(declaration: OutputDeclaration) -> list[tuple[str, str]]:
    """Return ``(port name, bound name)`` pairs for one ``scistudio.output`` call.

    ``OutputDeclaration`` reports the keyword names in written order and the
    argument names as positionals first, then keyword values — each argument
    that is a plain name. So the positional arguments are whatever is left once
    the keyword values are accounted for, and a positional argument is its own
    port name. When a keyword's value is not a plain name the counts no longer
    line up; the port keeps its keyword as both its name and its bound name,
    which is the reading that makes ``scistudio.output(total=total)`` and
    ``scistudio.output(total=frame["total"].sum())`` agree.
    """
    keywords = list(declaration.keywords)
    arguments = list(declaration.arguments)
    positional_count = max(0, len(arguments) - len(keywords))
    positional = arguments[:positional_count]
    keyword_values = arguments[positional_count:]

    pairs = [(name, name) for name in positional]
    aligned = len(keyword_values) == len(keywords)
    for index, keyword_name in enumerate(keywords):
        bound = keyword_values[index] if aligned else keyword_name
        pairs.append((keyword_name, bound))
    return pairs


@provisional(since="0.3.4")
def default_port_extension(data_type: str, *, registry: Any | None = None) -> str:
    """Return the file extension the materialisation layer assigns to *data_type* (FR-038).

    With a registry, the answer is the first extension of the first saver
    registered for the type — the same answer
    ``scistudio.blocks.io.materialisation.materialise_to_file`` reaches for when
    it is given no extension. Without one, or when the registry has no saver for
    the type, :data:`CORE_TYPE_EXTENSIONS` answers for the core types.

    Args:
        data_type: A SciStudio type name, for example ``"DataFrame"``.
        registry: An optional scanned block registry.

    Returns:
        The extension, with its leading dot.

    Raises:
        LookupError: When neither the registry nor the core table can answer.
    """
    if registry is not None:
        resolved = _core_type(data_type)
        if resolved is not None:
            try:
                capability = registry.find_saver_capability(resolved)
            except Exception:  # a registry with no saver for the type is not an error here
                capability = None
            if capability is not None and capability.extensions:
                extension = str(capability.extensions[0])
                return extension if extension.startswith(".") else f".{extension}"
    try:
        return CORE_TYPE_EXTENSIONS[data_type]
    except KeyError:
        raise LookupError(
            f"No default file extension is known for the SciStudio type {data_type!r}. "
            f"Register a saver for it, or declare the port's extension explicitly."
        ) from None


def _core_type(data_type: str) -> type | None:
    from scistudio.core.types.array import Array
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.composite import CompositeData
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.core.types.series import Series
    from scistudio.core.types.text import Text

    table: dict[str, type] = {
        cls.__name__: cls for cls in (DataObject, Array, DataFrame, Series, Text, Artifact, CompositeData)
    }
    return table.get(data_type)


def _build_ports(
    facts: Sequence[CellFacts],
    slice_cells: Sequence[str],
    *,
    bindings: Mapping[str, str],
    registry: Any | None,
    extra_inputs: Mapping[str, str],
) -> tuple[tuple[PackagedPort, ...], tuple[PackagedPort, ...], list[PackagingProblem]]:
    """Turn the slice's declarations into ports, collecting the ones that cannot be typed.

    An input name read in two cells is one port and the first read names it:
    the port is the notebook's *read* of a name, and a second read of the same
    name is the same port. An **output** name declared twice is the opposite
    case — two declarations that disagree — and spec §2 resolves it to the
    last one in written order, which is also what
    :func:`scistudio.explore.notebook_api.output` does in the kernel. The two
    implementations of that one sentence must agree, so this pops the earlier
    entry rather than keeping it, which gives the winner its own *position*
    as well as its value.
    """
    by_id = {cell.cell_id: cell for cell in facts}
    problems: list[PackagingProblem] = []

    input_specs: dict[str, tuple[str, str]] = {}
    output_specs: dict[str, tuple[str, str]] = {}
    duplicated: dict[str, list[str]] = {}
    for cell_id in slice_cells:
        cell = by_id.get(cell_id)
        if cell is None:
            continue
        for name in cell.inputs:
            input_specs.setdefault(name, (name, cell_id))
        for declaration in cell.outputs:
            for port_name, bound_name in _port_pairs(declaration):
                if port_name in output_specs:
                    superseded = output_specs.pop(port_name)
                    duplicated.setdefault(port_name, [superseded[1]]).append(cell_id)
                output_specs[port_name] = (bound_name, cell_id)
    for port_name, bound_name in extra_inputs.items():
        input_specs.setdefault(port_name, (bound_name, ""))

    if duplicated:
        cells = _ordered({cell_id for cell_ids in duplicated.values() for cell_id in cell_ids}, slice_cells)
        problems.append(
            PackagingProblem(
                kind=PackagingProblemKind.DUPLICATE_OUTPUT_DECLARATION,
                message=(
                    "These output names carry a duplicate declaration; the later one in written order "
                    "wins, and the earlier one is not packaged: "
                    + ", ".join(
                        f"{port_name} in cells {', '.join(_ordered(cell_ids, slice_cells))}"
                        for port_name, cell_ids in sorted(duplicated.items())
                    )
                    + "."
                ),
                cell_ids=cells,
                names=tuple(sorted(duplicated)),
                refuses=False,
            )
        )

    def make(port_name: str, bound_name: str, cell_id: str, direction: str) -> PackagedPort | None:
        data_type = bindings.get(bound_name) or bindings.get(port_name)
        if not data_type:
            where = f" declared in cell {cell_id}" if cell_id else ""
            problems.append(
                PackagingProblem(
                    kind=PackagingProblemKind.UNTYPED_PORT,
                    message=(
                        f"The {direction} port {port_name!r}{where} names {bound_name!r}, "
                        f"which is bound to nothing in the kernel, so the port has no type."
                    ),
                    cell_ids=(cell_id,) if cell_id else (),
                    names=(bound_name,),
                )
            )
            return None
        try:
            extension = default_port_extension(data_type, registry=registry)
        except LookupError as exc:
            problems.append(
                PackagingProblem(
                    kind=PackagingProblemKind.UNTYPED_PORT,
                    message=f"The {direction} port {port_name!r} cannot be given a file extension: {exc}",
                    cell_ids=(cell_id,) if cell_id else (),
                    names=(bound_name,),
                )
            )
            return None
        return PackagedPort(
            name=port_name,
            direction=direction,
            data_type=data_type,
            extension=extension,
            bound_name=bound_name if bound_name != port_name else "",
        )

    inputs = tuple(
        port
        for port_name, (bound_name, cell_id) in input_specs.items()
        if (port := make(port_name, bound_name, cell_id, "input")) is not None
    )
    outputs = tuple(
        port
        for port_name, (bound_name, cell_id) in output_specs.items()
        if (port := make(port_name, bound_name, cell_id, "output")) is not None
    )
    return inputs, outputs, problems


@provisional(since="0.3.4")
def check_packaging(
    document: NotebookDocument,
    *,
    marks: CellMarks | None = None,
    bindings: Mapping[str, str] | None = None,
    is_interactive: Callable[[str], bool] | None = None,
    observations: Mapping[str, object] | None = None,
    registry: Any | None = None,
    file_ports: Mapping[str, str] | None = None,
) -> PackagingPlan:
    """Answer whether *document* can be packaged, and what it would produce (FR-039).

    Writes nothing. Every refusal reason is collected rather than raised on the
    first one, because a person fixing a notebook wants the whole list.

    The marks are the session's and arrive as an argument: this module never
    asks the session service for them.

    Args:
        document: The notebook to check.
        marks: The session's never-run, stale, and out-of-order marks. Absent
            marks are treated as no marks, which is what a fully replayed
            notebook looks like.
        bindings: Name to SciStudio type name for everything bound in the
            kernel, as the session reports it (FR-056). A declared port whose
            name is missing here cannot be typed and is refused.
        is_interactive: Answers whether a block identifier names an interactive
            block. Defaults to a lookup against a freshly scanned block
            registry, or against *registry* when one is given.
        observations: What each cell was observed to change when it ran.
        registry: An optional scanned block registry, used to resolve port
            extensions and, unless *is_interactive* is given, block identifiers.
        file_ports: Additional input ports contributed by rewriting a
            file-opened session's load line (FR-038), as port name to the
            notebook variable it binds.

    Returns:
        The :class:`PackagingPlan`: the slice, the ports, and the problems.
    """
    marks = marks or CellMarks()
    bindings = bindings or {}
    problems: list[PackagingProblem] = []

    facts, graph = _analyse(document, observations=observations)
    output_cells = _output_cell_ids(facts, graph)
    if not output_cells:
        problems.append(
            PackagingProblem(
                kind=PackagingProblemKind.NO_DECLARED_OUTPUT,
                message=(
                    "This notebook declares no scistudio.output, so there is nothing to package: "
                    "a block with no output ports would produce nothing for the workflow to use."
                ),
            )
        )
        return PackagingPlan(problems=tuple(problems))

    slice_result = graph.backward_slice(output_cells)
    slice_cells = slice_result.cells

    for kind, marked, description in (
        (PackagingProblemKind.NEVER_RUN_CELL, marks.never_run, "have never run"),
        (PackagingProblemKind.STALE_CELL, marks.stale, "are stale"),
        (PackagingProblemKind.OUT_OF_ORDER_CELL, marks.out_of_order, "ran out of written order"),
    ):
        problem = _mark_problem(kind, marked, slice_cells, description)
        if problem is not None:
            problems.append(problem)

    if slice_result.unresolved_reads:
        reads = slice_result.unresolved_reads
        problems.append(
            PackagingProblem(
                kind=PackagingProblemKind.UNRESOLVED_READ,
                message=(
                    "The declared-output slice reads names no enabled cell above them changes, so a "
                    "packaged run would fail with a NameError: "
                    + ", ".join(f"{read.name} in cell {read.cell_id}" for read in reads)
                    + "."
                ),
                cell_ids=_ordered({read.cell_id for read in reads}, slice_cells),
                names=tuple(dict.fromkeys(read.name for read in reads)),
            )
        )

    problems.extend(_block_call_problems(facts, slice_cells, is_interactive=is_interactive, registry=registry))

    inputs, outputs, port_problems = _build_ports(
        facts,
        slice_cells,
        bindings=bindings,
        registry=registry,
        extra_inputs=dict(file_ports or {}),
    )
    problems.extend(port_problems)

    return PackagingPlan(cells=slice_cells, inputs=inputs, outputs=outputs, problems=tuple(problems))


def _block_call_problems(
    facts: Sequence[CellFacts],
    slice_cells: Sequence[str],
    *,
    is_interactive: Callable[[str], bool] | None,
    registry: Any | None,
) -> list[PackagingProblem]:
    """Refuse a slice that calls an interactive block, or one that cannot be named (FR-039, FR-050)."""
    in_slice = set(slice_cells)
    unknown: list[str] = []
    interactive: list[tuple[str, str]] = []
    for cell in facts:
        if cell.cell_id not in in_slice:
            continue
        if cell.has_flag(AnalysisFlag.UNKNOWN_BLOCK_CALL):
            unknown.append(cell.cell_id)
        for call in cell.block_calls:
            if call.block_id is None:
                continue
            if _resolve_is_interactive(call.block_id, is_interactive=is_interactive, registry=registry):
                interactive.append((cell.cell_id, call.block_id))

    problems: list[PackagingProblem] = []
    if interactive:
        cells = _ordered({cell_id for cell_id, _ in interactive}, slice_cells)
        names = tuple(dict.fromkeys(block_id for _, block_id in interactive))
        problems.append(
            PackagingProblem(
                kind=PackagingProblemKind.INTERACTIVE_BLOCK_CALL,
                message=(
                    "The declared-output slice calls interactive blocks, which cannot run unattended "
                    "inside a packaged block: "
                    + ", ".join(f"{block_id} in cell {cell_id}" for cell_id, block_id in interactive)
                    + "."
                ),
                cell_ids=cells,
                names=names,
            )
        )
    if unknown:
        cells = _ordered(unknown, slice_cells)
        problems.append(
            PackagingProblem(
                kind=PackagingProblemKind.UNKNOWN_BLOCK_CALL,
                message=(
                    "The declared-output slice calls a block whose identifier is not a string literal, so "
                    "packaging cannot show that the block is not an interactive one: "
                    + ", ".join(f"cell {cell_id}" for cell_id in cells)
                    + "."
                ),
                cell_ids=cells,
            )
        )
    return problems


def _resolve_is_interactive(
    block_id: str,
    *,
    is_interactive: Callable[[str], bool] | None,
    registry: Any | None,
) -> bool:
    if is_interactive is not None:
        return bool(is_interactive(block_id))
    resolved = registry
    if resolved is None:
        from scistudio.blocks.registry import BlockRegistry

        resolved = BlockRegistry()
        resolved.scan()
    spec = resolved.get_spec(block_id)
    if spec is None:
        return False
    return str(getattr(spec, "execution_mode", "")) == "interactive"


# ---------------------------------------------------------------------------
# Rewriting a file-opened session's load line (FR-038)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def rewrite_load_to_input(source: str, ports: Mapping[str, str]) -> str:
    """Rewrite ``x = scistudio.load(...)`` into ``x = scistudio.input("port")``.

    A session opened over a file loads that file in its first cell. A block
    packaged from it must read a port instead, because a workflow supplies its
    input rather than the file the person happened to explore (FR-038).

    Args:
        source: One cell's source.
        ports: The notebook variable each load binds, mapped to the port name to
            read instead. A variable this mapping does not name is left alone.

    Returns:
        The rewritten source, or *source* unchanged when it holds no load
        assignment this mapping names or when it does not parse.
    """
    if "scistudio.load" not in source or not ports:
        return source
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not _is_load_call(node.value):
            continue
        port = ports.get(target.id)
        if port is None:
            continue
        end = node.end_lineno if node.end_lineno is not None else node.lineno
        indent = " " * node.col_offset
        replacements.append((node.lineno - 1, end, f'{indent}{target.id} = scistudio.input("{port}")\n'))

    if not replacements:
        return source
    for start, end, text in reversed(replacements):
        lines[start:end] = [text]
    return "".join(lines)


def _is_load_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "load"
        and isinstance(func.value, ast.Name)
        and func.value.id == "scistudio"
    )


# ---------------------------------------------------------------------------
# Packaging (FR-037, FR-041, FR-042, FR-043)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PackagedBlock:
    """What packaging wrote, and where."""

    block_name: str
    """The file stem of both written files, and the block's display name."""
    class_name: str
    """The generated class's name, which is what the registry keys the block by."""
    declaration_path: Path
    """The generated ``.py`` declaration in the project's blocks directory."""
    notebook_path: Path
    """The notebook copy beside it."""
    notebook_commit: str
    """The commit the notebook was packaged from; the block's version (FR-041)."""
    cells: tuple[str, ...] = ()
    """The slice the block runs, in written order."""
    inputs: tuple[PackagedPort, ...] = ()
    """The block's input ports."""
    outputs: tuple[PackagedPort, ...] = ()
    """The block's output ports."""
    on_new_input: str = "replay"
    """The generated block's ``on_new_input`` default (FR-044)."""
    problems: tuple[PackagingProblem, ...] = ()
    """What packaging resolved on the way past, empty for a clean notebook.

    Never a refusal — a refusal raises :class:`PackagingRefusedError` and
    writes nothing. This carries the problems whose
    :attr:`PackagingProblem.refuses` is ``False``, so a duplicate output
    declaration is still reported to the person who packaged rather than only
    to the person who ran the check first (spec §2, edge cases).
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class PackagedBlockSession:
    """Where a packaged block's node reopens its session (FR-042)."""

    block_name: str
    """The packaged block's name."""
    notebook_path: Path
    """The block's notebook copy, which the session opens rather than the exploration notebook."""
    declaration_path: Path
    """The generated declaration, which repackaging replaces in place."""
    notebook_commit: str
    """The commit the block was packaged from, as its declaration records it."""


@provisional(since="0.3.4")
def block_identifier(block_name: str) -> str:
    """Return the Python class name a packaged block's declaration defines.

    Args:
        block_name: The block's name, as a person typed it.

    Returns:
        A CamelCase Python identifier.

    Raises:
        ValueError: When *block_name* holds no identifier characters at all.

    Example:
        >>> block_identifier("peak fit v2")
        'PeakFitV2'
    """
    parts = [part for part in _IDENTIFIER_RE.split(block_name) if part]
    if not parts:
        raise ValueError(f"Block name {block_name!r} contains no letters or digits to build a class name from.")
    camel = "".join(part[:1].upper() + part[1:] for part in parts)
    if camel[0].isdigit() or keyword.iskeyword(camel):
        camel = f"Notebook{camel}"
    return camel


@provisional(since="0.3.4")
def block_file_stem(block_name: str) -> str:
    """Return the file stem both written files share.

    Args:
        block_name: The block's name, as a person typed it.

    Returns:
        A lowercase, underscore-separated stem. A leading underscore is stripped
        because the tier-1 scan skips files whose name starts with one.

    Raises:
        ValueError: When *block_name* holds no identifier characters at all.
    """
    parts = [part for part in _IDENTIFIER_RE.split(block_name) if part]
    if not parts:
        raise ValueError(f"Block name {block_name!r} contains no letters or digits to build a file name from.")
    stem = "_".join(part.lower() for part in parts).strip("_")
    if not stem or stem[0].isdigit():
        stem = f"notebook_{stem}".rstrip("_")
    return stem


@provisional(since="0.3.4")
def package_notebook(
    document: NotebookDocument,
    *,
    project_dir: str | Path,
    block_name: str,
    notebook_commit: str,
    marks: CellMarks | None = None,
    bindings: Mapping[str, str] | None = None,
    is_interactive: Callable[[str], bool] | None = None,
    observations: Mapping[str, object] | None = None,
    registry: Any | None = None,
    file_ports: Mapping[str, str] | None = None,
    on_new_input: str = "replay",
    blocks_dirname: str = BLOCKS_DIRNAME,
) -> PackagedBlock:
    """Package *document* into a Code Block in the project's blocks directory.

    Writes two files and no others: ``{project}/{blocks}/<name>.py``, the
    declaration the tier-1 scan discovers, and ``{project}/{blocks}/<name>.ipynb``,
    the copy of the notebook the declaration names as its script (FR-037).
    Packaging again with the same *block_name* replaces both in place (FR-042).
    The notebook this was packaged from is never touched (FR-043).

    Args:
        document: The session's notebook. Read only; the copy is written from a
            duplicate of it.
        project_dir: The project root.
        block_name: What the person called the block.
        notebook_commit: The notebook commit this is packaged from, which
            becomes the block's version and its remembered decision
            (FR-041, FR-046). The session reports it (FR-035).
        marks: The session's marks, as :func:`check_packaging` takes them.
        bindings: Name to SciStudio type name, as :func:`check_packaging` takes it.
        is_interactive: As :func:`check_packaging` takes it.
        observations: As :func:`check_packaging` takes it.
        registry: As :func:`check_packaging` takes it.
        file_ports: Port name to notebook variable for a session opened over a
            file, whose load line is rewritten to a port read in the copy.
        on_new_input: ``"replay"`` (the default a packaged notebook block
            declares, FR-044) or ``"ask"``, which additionally makes the
            generated block interactive so it pauses on a changed input
            signature (FR-046).
        blocks_dirname: The project's blocks directory name.

    Returns:
        The :class:`PackagedBlock` describing what was written.

    Raises:
        PackagingRefusedError: When any check of FR-039 refuses the notebook. Nothing
            is written in that case.
        ValueError: When *block_name* yields no usable identifier, when
            *notebook_commit* is empty, or when *on_new_input* is neither
            ``"replay"`` nor ``"ask"``.
    """
    if not notebook_commit or not notebook_commit.strip():
        raise ValueError(
            "Packaging needs the notebook commit it is packaging from: it is the block's version "
            "and its remembered decision (FR-041, FR-046)."
        )
    policy = on_new_input.strip().lower()
    if policy not in {"replay", "ask"}:
        raise ValueError(f"on_new_input must be 'replay' or 'ask', not {on_new_input!r}.")

    variable_to_port = {variable: port for port, variable in (file_ports or {}).items()}
    plan = check_packaging(
        document,
        marks=marks,
        bindings=bindings,
        is_interactive=is_interactive,
        observations=observations,
        registry=registry,
        file_ports=file_ports,
    )
    if not plan.is_packageable:
        raise PackagingRefusedError(plan.problems)

    class_name = block_identifier(block_name)
    stem = block_file_stem(block_name)
    root = Path(project_dir).resolve()
    blocks_dir = root / blocks_dirname
    blocks_dir.mkdir(parents=True, exist_ok=True)

    copy = document.copy()
    if variable_to_port:
        for cell in copy.cells:
            if cell.cell_type != "code" or cell.cell_id is None:
                continue
            rewritten = rewrite_load_to_input(cell.source, variable_to_port)
            if rewritten != cell.source:
                copy.set_cell_source(cell.cell_id, rewritten)

    notebook_path = blocks_dir / f"{stem}.ipynb"
    declaration_path = blocks_dir / f"{stem}.py"
    write_notebook(notebook_path, copy)
    declaration_path.write_text(
        _render_declaration(
            class_name=class_name,
            block_name=block_name,
            stem=stem,
            notebook_commit=notebook_commit.strip(),
            plan=plan,
            on_new_input=policy,
            blocks_dirname=blocks_dirname,
        ),
        encoding="utf-8",
    )

    return PackagedBlock(
        block_name=block_name,
        class_name=class_name,
        declaration_path=declaration_path,
        notebook_path=notebook_path,
        notebook_commit=notebook_commit.strip(),
        cells=plan.cells,
        inputs=plan.inputs,
        outputs=plan.outputs,
        on_new_input=policy,
        problems=plan.problems,
    )


@provisional(since="0.3.4")
def reopen_target(
    project_dir: str | Path,
    block_name: str,
    *,
    blocks_dirname: str = BLOCKS_DIRNAME,
) -> PackagedBlockSession:
    """Return where a packaged block's node reopens its session (FR-042).

    Double-clicking a packaged block's node opens a session on the **block's
    notebook copy**, not on the exploration notebook it was packaged from, and
    packaging again from that session replaces the copy and the declaration in
    place. This resolves those two paths and reads back the commit the
    declaration records; binding the session to the node's most recent run
    inputs is the caller's, because only the caller knows which run that was.

    Args:
        project_dir: The project root.
        block_name: The packaged block's name.
        blocks_dirname: The project's blocks directory name.

    Returns:
        The :class:`PackagedBlockSession`.

    Raises:
        FileNotFoundError: When the declaration or the notebook copy is missing.
    """
    root = Path(project_dir).resolve()
    stem = block_file_stem(block_name)
    declaration_path = root / blocks_dirname / f"{stem}.py"
    notebook_path = root / blocks_dirname / f"{stem}.ipynb"
    for path in (declaration_path, notebook_path):
        if not path.exists():
            raise FileNotFoundError(
                f"No packaged block named {block_name!r} in {root / blocks_dirname}: {path} is missing."
            )
    return PackagedBlockSession(
        block_name=block_name,
        notebook_path=notebook_path,
        declaration_path=declaration_path,
        notebook_commit=_declared_commit(declaration_path),
    )


def _declared_commit(declaration_path: Path) -> str:
    """Read ``notebook_commit`` back out of a generated declaration without importing it."""
    match = re.search(
        r"^\s*notebook_commit:\s*ClassVar\[str\]\s*=\s*(['\"])(?P<sha>[^'\"]*)\1",
        declaration_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group("sha") if match else ""


def _render_declaration(
    *,
    class_name: str,
    block_name: str,
    stem: str,
    notebook_commit: str,
    plan: PackagingPlan,
    on_new_input: str,
    blocks_dirname: str,
) -> str:
    """Render the generated block declaration the tier-1 scan discovers (FR-037)."""
    # The two generators diverge here, and the choice is deliberate (FR-044,
    # FR-046). §4.1 says "on new data the block replays; **set to ask**, it
    # pauses", so ``replay`` — the packaged default — generates a plain Code
    # Block that is not interactive at all and therefore cannot pause, and
    # ``ask`` generates the interactive subclass whose panel is the Explore tab.
    #
    # The alternative reading is that a packaged block is *always* interactive
    # and declares ``on_new_input = replay``. That reading needs one more thing
    # this dispatch cannot decide: the engine's dispatch pauses any interactive
    # block that carries no remembered decision in its **node** config, so
    # "replay without pausing" would require someone to write the packaging
    # commit into the node's ``interactive_memory`` when the node is created —
    # a frontend/node-creation contract, and an owner's call, not packaging's.
    base = "AskingPackagedNotebookBlock" if on_new_input == "ask" else "PackagedNotebookBlock"
    input_ports = ",\n        ".join(
        f"InputPort(name={port.name!r}, accepted_types=[{port.data_type}], description={_port_doc(port)!r})"
        for port in plan.inputs
    )
    output_ports = ",\n        ".join(
        f"OutputPort(name={port.name!r}, accepted_types=[{port.data_type}], description={_port_doc(port)!r})"
        for port in plan.outputs
    )
    used_types = sorted({port.data_type for port in (*plan.inputs, *plan.outputs)})
    type_imports = "\n".join(f"from {_type_module(name)} import {name}" for name in used_types)

    return f'''"""Generated by SciStudio from the exploration notebook {stem}.ipynb.

Packaged at notebook commit {notebook_commit} (ADR-054 FR-037, FR-041). Edit the
notebook beside this file and package again rather than editing this
declaration: packaging replaces both files in place.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.blocks.base.interactive import InteractionPolicy
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.explore.packaging import {base}
{type_imports}


class {class_name}({base}):
    """{block_name}, packaged from an exploration notebook."""

    name: ClassVar[str] = {block_name!r}
    description: ClassVar[str] = "Packaged from the exploration notebook {stem}.ipynb."
    version: ClassVar[str] = {notebook_commit!r}

    notebook_filename: ClassVar[str] = "{stem}.ipynb"
    notebook_commit: ClassVar[str] = {notebook_commit!r}
    blocks_dirname: ClassVar[str] = {blocks_dirname!r}
    slice_cells: ClassVar[tuple[str, ...]] = {plan.cells!r}
    packaged_inputs: ClassVar[tuple[dict[str, str], ...]] = {tuple(port.as_port_config() for port in plan.inputs)!r}
    packaged_outputs: ClassVar[tuple[dict[str, str], ...]] = {tuple(port.as_port_config() for port in plan.outputs)!r}
    on_new_input: ClassVar[InteractionPolicy | str] = {on_new_input!r}

    variadic_inputs: ClassVar[bool] = False
    variadic_outputs: ClassVar[bool] = False
    input_ports: ClassVar[list[InputPort]] = [
        {input_ports}
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        {output_ports}
    ]
'''


def _port_doc(port: PackagedPort) -> str:
    if port.bound_name:
        return f"Declared in the notebook as {port.name} ({port.bound_name})."
    return f"Declared in the notebook as {port.name}."


def _type_module(data_type: str) -> str:
    modules = {
        "DataObject": "scistudio.core.types.base",
        "Array": "scistudio.core.types.array",
        "DataFrame": "scistudio.core.types.dataframe",
        "Series": "scistudio.core.types.series",
        "Text": "scistudio.core.types.text",
        "Artifact": "scistudio.core.types.artifact",
        "CompositeData": "scistudio.core.types.composite",
    }
    return modules.get(data_type, "scistudio.core.types.base")


# ---------------------------------------------------------------------------
# The generated block's behaviour (FR-040, FR-046, FR-047)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def notebook_at_commit(project_dir: str | Path, repo_relative_path: str, commit: str) -> NotebookDocument:
    """Read a notebook out of the project repository at *commit* (FR-047).

    The commit a person confirms at a packaged block's ask pause may not be the
    one the block was packaged from, and FR-047 says the compute phase runs
    *that* commit's slice. Reading the blob rather than checking anything out
    keeps the working tree and ``HEAD`` where the person left them.

    The read goes through :class:`~scistudio.core.versioning.git_engine.GitEngine`
    because it is the only class in SciStudio that shells out to git, and it owns
    the bundled binary; reaching for ``subprocess`` here would use whatever git
    happens to be on the path.

    Args:
        project_dir: The project root, which is the repository root.
        repo_relative_path: The notebook's path inside the repository, with
            ``/`` separators.
        commit: The commit to read it at.

    Returns:
        The notebook as it was at that commit.

    Raises:
        FileNotFoundError: When the commit has no such file.
    """
    from scistudio.core.versioning.git_engine import GitEngine

    engine = GitEngine(Path(project_dir))
    proc = engine._run(["cat-file", "blob", f"{commit}:{repo_relative_path}"], check=False)
    if getattr(proc, "returncode", 1) != 0:
        raise FileNotFoundError(f"Commit {commit} has no file at {repo_relative_path} in {project_dir}.")
    return NotebookDocument.from_json(proc.stdout, source=f"{commit}:{repo_relative_path}")


#: Code Block settings packaging owns, so they are not fields a person edits.
_PACKAGED_HIDDEN_FIELDS = frozenset({"script_path", "language", "input_ports", "output_ports"})


def _packaged_config_schema() -> dict[str, Any]:
    """Return the Code Block's config schema minus the fields packaging supplies.

    ``script_path`` is the notebook copy beside the declaration and the ports
    are the notebook's declarations, so neither belongs in the node's settings
    form. Dropping ``script_path`` from ``required`` is what lets the engine's
    pre-dispatch validation pass a node that carries no script path of its own.
    """
    properties = {
        key: value
        for key, value in dict(CodeBlock.config_schema.get("properties", {})).items()
        if key not in _PACKAGED_HIDDEN_FIELDS
    }
    return {"type": "object", "properties": properties, "required": []}


@provisional(since="0.3.4")
class PackagedNotebookBlock(CodeBlock):
    """Base class of every generated packaged-notebook declaration (FR-037, FR-040).

    A packaged block is a Code Block whose script is the notebook copy beside its
    declaration and whose run executes the backward slice of the notebook's
    declared outputs. This class supplies the Code Block configuration the
    generated declaration would otherwise have to spell out — the script path,
    the port file configs, and the cell selection the notebook backend reads —
    so the generated file stays a declaration rather than a program.

    Its ``on_new_input`` default is ``replay`` (FR-044): a packaged block replays
    the notebook commit it was packaged from and does not pause.
    :class:`AskingPackagedNotebookBlock` is the same block set to ask.

    A subclass is what packaging writes; it is not written by hand.
    """

    notebook_filename: ClassVar[str] = ""
    """File name of the notebook copy inside the blocks directory."""
    notebook_commit: ClassVar[str] = ""
    """The commit the notebook was packaged from; the block's version (FR-041)."""
    version: ClassVar[str] = ""
    """Blank on the base, a notebook commit on every generated subclass (FR-041).

    Blank rather than inherited so that the base — which was packaged from no
    notebook — falls through to the ADR-038 §3.3 distribution version instead of
    stamping the ``Block.version`` default as if it were a commit.
    """
    block_version_source: ClassVar[str] = SELF_DECLARED_VERSION
    """FR-054: this block's version is its notebook commit, not its distribution's.

    ADR-038 §3.3 force-injects the distribution version onto every block spec,
    because a hand-written version drifts. A packaged block is the case that
    rule does not fit: its version is a commit sha, which is more reproducible
    than the distribution's and is the only thing that lets a run point back at
    the Explore session it came from. Declaring this attribute is the opt-in the
    registry reads (:data:`~scistudio.blocks.registry._spec.BLOCK_VERSION_SOURCE_ATTR`);
    it is not a rule about packaged blocks, and any block whose version is a
    content identity may declare it.

    The base class itself carries no commit, so it falls back to the injected
    default; only a generated subclass, which always sets ``version``, stamps a
    sha.
    """
    blocks_dirname: ClassVar[str] = BLOCKS_DIRNAME
    """The project's blocks directory, relative to the project root."""
    slice_cells: ClassVar[tuple[str, ...]] = ()
    """The cell ids of the slice this block runs, in written order (FR-040)."""
    packaged_inputs: ClassVar[tuple[Mapping[str, str], ...]] = ()
    """The input ports as ``PortFileConfig`` mappings."""
    packaged_outputs: ClassVar[tuple[Mapping[str, str], ...]] = ()
    """The output ports as ``PortFileConfig`` mappings."""
    on_new_input: ClassVar[InteractionPolicy | str] = InteractionPolicy.REPLAY.value
    """What this block does with its remembered decision when its input changes (FR-044)."""

    variadic_inputs: ClassVar[bool] = False
    """A packaged block's ports are the notebook's declarations, not the canvas'."""
    variadic_outputs: ClassVar[bool] = False
    """A packaged block's ports are the notebook's declarations, not the canvas'."""

    config_schema: ClassVar[dict[str, Any]] = _packaged_config_schema()
    """The Code Block's settings minus the ones packaging owns.

    ``script_path`` is the notebook copy, and the ports are the notebook's
    declarations, so neither is a field a person edits — and ``script_path``
    must not stay *required*, or the engine's pre-dispatch validation would
    refuse a node whose script the block supplies for itself.
    """

    def packaged_config(self, raw_config: Mapping[str, Any]) -> dict[str, Any]:
        """Return the Code Block parameters this packaged block runs under.

        Merges the notebook, its ports, and the cell selection into whatever the
        node supplied, so the runtime keys a node carries — ``project_dir``,
        ``block_id``, ``run_id``, the registry and its adapters — survive.

        Args:
            raw_config: The node's own parameters.

        Returns:
            The merged parameter mapping.
        """
        project_dir = Path(str(raw_config.get("project_dir") or Path.cwd()))
        script_path, cells = self.resolve_script(project_dir, raw_config)
        environment = dict(raw_config.get("environment") or {})
        environment[NOTEBOOK_CELL_SELECTION_KEY] = list(cells)

        merged = dict(raw_config)
        merged.update(
            {
                "script_path": script_path,
                "inputs": [dict(port) for port in self.packaged_inputs],
                "outputs": [dict(port) for port in self.packaged_outputs],
                "environment": environment,
            }
        )
        return merged

    def resolve_script(
        self,
        project_dir: Path,
        raw_config: Mapping[str, Any],
    ) -> tuple[str, tuple[str, ...]]:
        """Return the project-relative notebook to run and the cells to run from it.

        The packaged copy and :attr:`slice_cells` unless a confirmed decision
        names a different notebook commit (FR-047), in which case that commit's
        notebook is materialised under the blocks directory and its own slice is
        computed from it — the slice is a function of the notebook, so a
        different commit has a different one.

        Args:
            project_dir: The project root.
            raw_config: The node's own parameters, which carry a confirmed
                decision under ``interactive_response`` when there is one.

        Returns:
            The project-relative script path and the ordered cell ids to run.
        """
        packaged = f"{self.blocks_dirname}/{self.notebook_filename}"
        commit = _decision_commit(raw_config)
        if not commit or commit == self.notebook_commit:
            return packaged, tuple(self.slice_cells)

        document = notebook_at_commit(project_dir, packaged, commit)
        target_dir = Path(project_dir) / self.blocks_dirname / MATERIALISED_DIRNAME
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(self.notebook_filename).stem
        target = target_dir / f"{stem}-{commit[:12]}.ipynb"
        write_notebook(target, document)
        return (
            f"{self.blocks_dirname}/{MATERIALISED_DIRNAME}/{target.name}",
            slice_for_outputs(document),
        )

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Run the packaged notebook's slice and return its declared outputs.

        Args:
            inputs: The block's input collections, keyed by port name.
            config: The node's configuration.

        Returns:
            The declared output ports, as the Code Block reconstructs them.
        """
        raw = dict(config.params)
        raw.update(config.__pydantic_extra__ or {})
        return super().run(inputs, BlockConfig(params=self.packaged_config(raw)))


def _decision_commit(raw_config: Mapping[str, Any]) -> str:
    """Return the notebook commit a confirmed decision carries, or an empty string."""
    response = raw_config.get(INTERACTIVE_RESPONSE_KEY)
    if isinstance(response, Mapping):
        commit = response.get(DECISION_COMMIT_KEY)
        if isinstance(commit, str):
            return commit.strip()
    return ""


@provisional(since="0.3.4")
class AskingPackagedNotebookBlock(PackagedNotebookBlock, InteractiveMixin):
    """A packaged notebook block set to ask (FR-046, FR-047, FR-048).

    Asking reuses the pause that already exists rather than adding one: this is
    an interactive block whose panel is the Explore tab and whose decision is a
    notebook commit. The engine's interactive dispatch runs the prompt phase,
    holds a future while nothing of the block is resident, and runs the compute
    phase from the decision — the same three steps every interactive block goes
    through. The prompt names the notebook, the commit, and the run's inputs so
    the frontend can open a session over them; whatever session it opens belongs
    to the session service and the engine never waits on it (FR-048).

    Its ``on_new_input`` still defaults to ``replay``, which is the packaged
    default FR-044 states. Setting it to ``ask`` — on the class, as packaging
    writes it, or on the node — is what makes a changed input signature pause.
    """

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    """Interactive: the engine dispatches this block through its existing pause (FR-048)."""

    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id=EXPLORE_SESSION_PANEL_ID,
        response_schema={
            "type": "object",
            "properties": {DECISION_COMMIT_KEY: {"type": "string"}},
            "required": [DECISION_COMMIT_KEY],
        },
    )
    """The Explore tab, and the shape of the decision it returns: a notebook commit (FR-047)."""

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:
        """Name the notebook, the commit, and the run's inputs (FR-046).

        Args:
            inputs: The block's input collections, keyed by port name.
            config: The node's resolved configuration.

        Returns:
            The panel payload: enough for the Explore tab to open a session over
            this run's inputs, and nothing heavy.
        """
        return {
            "block_name": getattr(type(self), "name", type(self).__name__),
            "notebook": f"{self.blocks_dirname}/{self.notebook_filename}",
            "notebook_commit": self.notebook_commit,
            "inputs": interactive_input_signature(inputs),
        }

    def remap_saved_decision(
        self,
        saved_decision: dict[str, Any],
        saved_signature: dict[str, list[str]],
        current_signature: dict[str, list[str]],
    ) -> dict[str, Any] | None:
        """Replay the remembered notebook commit only while the inputs are unchanged.

        The default interactive policy, kept deliberately: under ``ask`` a
        changed input signature is exactly the case FR-046 asks the engine to
        pause on, and returning the decision here would skip that pause.

        Args:
            saved_decision: The decision the node remembers.
            saved_signature: The input fingerprint captured with it.
            current_signature: This run's input fingerprint.

        Returns:
            The remembered decision when the signatures match, else ``None``.
        """
        if saved_signature == current_signature:
            return saved_decision
        return None
