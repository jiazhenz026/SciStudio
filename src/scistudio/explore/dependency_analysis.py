"""Per-cell static facts, the cell-level dependency graph, and the metadata codec.

This module implements FR-005 to FR-023, FR-028, and FR-031 to FR-036 of
``docs/specs/adr-054-notebook-dependency-analysis.md`` (ADR-054 §6.1, §6.2).

The unit of analysis is the **cell** (FR-001). For each cell the module records
what the source shows it binds and what it reads, and from the cells' written
order it builds a graph with one rule: *a cell that reads a name depends on the
nearest enabled cell above it whose changed set contains that name.*

Three standard-library tools do the work and nothing else is imported (FR-003):

* :mod:`symtable` answers the scoping question — which names the module scope of
  a cell assigns or imports, which it references, and which names a nested scope
  resolves to the module scope. It is used instead of re-deriving Python's
  scoping rules from the ``ast``.
* :mod:`ast` answers the shape question — the ``scistudio.output`` and
  ``scistudio.input`` declarations, the block calls, star imports, and the two
  forms :mod:`symtable` does not report as reads (augmented assignment and
  ``del``).
* :mod:`tokenize` answers the magic question — where a logical line begins, and
  therefore which ``%`` and ``!`` are IPython's and which are Python's modulo and
  inequality operators (FR-011). A kernel tokenises before it decides what a
  magic is, and so does this.

Nothing here executes code, holds a kernel, or touches the filesystem (FR-004).

**The one guarantee** (FR-002): the static estimate of what a cell changes never
omits an assignment the code shows, and may name one that execution would not
perform. Every consumer of the graph tolerates an extra edge; a missing edge is
the stale number ADR-054 §6.1 exists to remove. Where a rule's outcome is
uncertain, this module resolves toward the extra edge.

**What a cell changes is observed, not recognised** (FR-007). The static
estimate is *assignments only*: there is no list of mutating methods, no alias
tracking, and no analysis of a called function's body. When a cell runs, the
kernel fingerprints the namespace before and after and hands the observed
changed set to :func:`build_graph`, which unions it with the static estimate so
that an observation can only add a definer (FR-022, FR-030). The fingerprint and
the comparison live in :mod:`scistudio.explore.fingerprint`.

The graph never calls into that module: :func:`build_graph` reads an observation
through the two attributes it needs, so a caller may hand it an
:class:`~scistudio.explore.fingerprint.ObservedChange`, a plain set of names, or
anything else that answers to ``changed_names``. The codec is the one part that
must name the type, because decoding a stored record has to *build* one, and the
:class:`ObservedChange` import exists for that alone. Both modules stay inside
the FR-035 allowlist, which permits the standard library, the stability markers,
and ``scistudio.explore`` itself.
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import io
import re
import symtable
import tokenize
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from scistudio.explore.fingerprint import ObservedChange
from scistudio.stability import provisional

__all__ = [
    "ANALYSIS_VERSION",
    "BLOCK_CALL_PATHS",
    "BUILTIN_NAMES",
    "CELL_RECORD_KEY",
    "INPUT_CALL_PATH",
    "OUTPUT_CALL_PATH",
    "AnalysisFlag",
    "BlockCall",
    "CellFacts",
    "CellFlag",
    "DependencyGraph",
    "Edge",
    "EdgeOrigin",
    "LoadedCell",
    "OutputDeclaration",
    "SliceResult",
    "UnresolvedRead",
    "VersionEdge",
    "VersionNode",
    "analyse_cell",
    "analyse_cells",
    "build_graph",
    "decode_cell_record",
    "encode_cell_record",
    "encode_notebook_record",
    "notebook_record_version",
    "observation_flags",
    "source_hash",
]


#: The version of the analysis that produced a record. A stored record written
#: by an older version is re-analysed rather than trusted (FR-031).
ANALYSIS_VERSION: Final[int] = 1

#: The cell-metadata and notebook-metadata key the record is stored under
#: (FR-031). One key for both levels, so a notebook carries exactly one
#: SciStudio-owned entry per metadata dictionary and another tool's entries under
#: their own keys are untouched.
CELL_RECORD_KEY: Final[str] = "scistudio"

#: Names in Python's builtins namespace. A read of one of these draws no edge
#: and is *not* recorded as unresolved, so the unresolved list stays about names
#: a run would fail on (FR-015).
BUILTIN_NAMES: Final[frozenset[str]] = frozenset(dir(builtins))

#: The dotted call paths the analysis recognises. A call matches when its dotted
#: path *ends with* the tuple, so ``scistudio.output(...)`` and
#: ``blocks.run(...)`` match, and so do their fully qualified spellings.
OUTPUT_CALL_PATH: Final[tuple[str, ...]] = ("scistudio", "output")
INPUT_CALL_PATH: Final[tuple[str, ...]] = ("scistudio", "input")
BLOCK_CALL_PATHS: Final[tuple[tuple[str, ...], ...]] = (("blocks", "run"),)


# ---------------------------------------------------------------------------
# Flags (FR-036)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class AnalysisFlag(StrEnum):
    """The closed set of flags the analysis can raise (FR-036).

    Exactly seven members, no more: the spec names these and only these. Two of
    them — :attr:`UNPREDICTED_CHANGE` and :attr:`UNOBSERVABLE_NAME` — are raised
    by the runtime observation rather than by this module, and live here because
    FR-036 requires one enumeration for every flag the analysis can raise.
    """

    SYNTAX_ERROR = "syntax_error"
    OPAQUE_CELL_MAGIC = "opaque_cell_magic"
    UNKNOWN_BINDINGS = "unknown_bindings"
    UNKNOWN_BLOCK_CALL = "unknown_block_call"
    UNPREDICTED_CHANGE = "unpredicted_change"
    UNOBSERVABLE_NAME = "unobservable_name"
    UNRESOLVED_READ = "unresolved_read"

    @property
    def message_template(self) -> str:
        """The human-readable message template for this flag (FR-036)."""
        return _FLAG_MESSAGES[self]

    def message(self, **fields: object) -> str:
        """Render :attr:`message_template` with *fields*."""
        return self.message_template.format(**fields)


_FLAG_MESSAGES: Final[Mapping[AnalysisFlag, str]] = MappingProxyType(
    {
        AnalysisFlag.SYNTAX_ERROR: "Cell {cell_id} does not parse: {detail}",
        AnalysisFlag.OPAQUE_CELL_MAGIC: (
            "Cell {cell_id} begins with the cell magic {magic}, so its contents are opaque to the analysis."
        ),
        AnalysisFlag.UNKNOWN_BINDINGS: (
            "Cell {cell_id} binds an unknown set of names ({reason}), so a read below it that resolves to "
            "no other cell resolves here."
        ),
        AnalysisFlag.UNKNOWN_BLOCK_CALL: (
            "Cell {cell_id} calls a block whose identifier is not a string literal, so the block it runs "
            "cannot be named without running the cell."
        ),
        AnalysisFlag.UNPREDICTED_CHANGE: ("Cell {cell_id} changed {name} without an assignment showing it."),
        AnalysisFlag.UNOBSERVABLE_NAME: (
            "The fingerprint of {name} in cell {cell_id} fell back to identity, so the observation does not "
            "cover a change to its contents."
        ),
        AnalysisFlag.UNRESOLVED_READ: ("Cell {cell_id} reads {name}, which no enabled cell above it changes."),
    }
)


@provisional(since="0.3.4")
@dataclass(frozen=True)
class CellFlag:
    """One raised flag, with the rendered message and, where it has one, a position."""

    flag: AnalysisFlag
    message: str
    name: str | None = None
    lineno: int | None = None
    offset: int | None = None


@provisional(since="0.3.4")
class EdgeOrigin(StrEnum):
    """Why an edge exists (FR-019).

    The origin is what lets the dependency view and the diagnostics explain an
    edge rather than leaving the person to guess.
    """

    #: The definer's source assigns the name.
    STATIC_ASSIGNMENT = "static_assignment"
    #: The definer was observed to change the name when it ran, and its source
    #: does not show the assignment.
    OBSERVED_CHANGE = "observed_change"
    #: No cell above changes the name, and the definer binds an unknown set of
    #: names — a star import or a ``%run`` line (FR-013).
    UNKNOWN_BINDING = "unknown_binding"


# ---------------------------------------------------------------------------
# Per-cell static facts (FR-005 to FR-013)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class OutputDeclaration:
    """One ``scistudio.output(...)`` call in a cell (FR-008).

    ``keywords`` holds the keyword names in written order — the block's output
    port names once the notebook is packaged. ``arguments`` holds the names
    passed as values: the positional arguments first, then the keyword values,
    each in written order. An argument that is not a plain name contributes
    nothing to ``arguments``.
    """

    keywords: tuple[str, ...]
    arguments: tuple[str, ...]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BlockCall:
    """One block call in a cell (FR-010).

    ``block_id`` is the identifier when it was passed as a string literal, and
    ``None`` when it was not — in which case the cell also carries
    :attr:`AnalysisFlag.UNKNOWN_BLOCK_CALL`.
    """

    block_id: str | None
    lineno: int


@provisional(since="0.3.4")
@dataclass(frozen=True)
class CellFacts:
    """The static result for one cell.

    ``assigned`` is the *estimate* of what the cell changes, used until the cell
    has run (FR-005). ``read`` is what the cell reads at module scope (FR-006).
    Neither set makes a claim about statement order inside the cell.
    """

    cell_id: str
    source_hash: str
    assigned: frozenset[str]
    read: frozenset[str]
    outputs: tuple[OutputDeclaration, ...] = ()
    inputs: tuple[str, ...] = ()
    block_calls: tuple[BlockCall, ...] = ()
    flags: tuple[CellFlag, ...] = ()

    @property
    def flag_kinds(self) -> frozenset[AnalysisFlag]:
        """The distinct flags raised on this cell."""
        return frozenset(entry.flag for entry in self.flags)

    def has_flag(self, flag: AnalysisFlag) -> bool:
        """Return ``True`` when this cell carries *flag*."""
        return any(entry.flag is flag for entry in self.flags)

    @property
    def is_output_cell(self) -> bool:
        """``True`` when the cell calls ``scistudio.output`` (FR-008)."""
        return bool(self.outputs)

    @property
    def binds_unknown_names(self) -> bool:
        """``True`` when the cell binds an unknown set of names (FR-013)."""
        return self.has_flag(AnalysisFlag.UNKNOWN_BINDINGS)


# ---------------------------------------------------------------------------
# The graph (FR-014 to FR-023)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Edge:
    """A dependency from a reading cell to a defining cell, for one name."""

    reader: str
    definer: str
    name: str
    origin: EdgeOrigin


@provisional(since="0.3.4")
@dataclass(frozen=True)
class VersionNode:
    """One name changed by one cell (FR-016)."""

    cell_id: str
    name: str


@provisional(since="0.3.4")
@dataclass(frozen=True)
class VersionEdge:
    """An edge between version nodes, derived from the same facts as :class:`Edge`.

    ``source`` is the version that is read. ``target`` is the version the read
    contributes to, and is ``None`` when the reading cell changes nothing — a
    display cell is a sink in the version graph but must still appear in it, so
    the edge is kept with ``target_cell`` naming the reader.
    """

    source: VersionNode
    target_cell: str
    target: VersionNode | None
    origin: EdgeOrigin


@provisional(since="0.3.4")
@dataclass(frozen=True)
class UnresolvedRead:
    """A read no enabled cell above resolves (FR-015)."""

    cell_id: str
    name: str

    def as_flag(self) -> CellFlag:
        """Render this unresolved read as a :class:`CellFlag`."""
        return CellFlag(
            flag=AnalysisFlag.UNRESOLVED_READ,
            message=AnalysisFlag.UNRESOLVED_READ.message(cell_id=self.cell_id, name=self.name),
            name=self.name,
        )


@provisional(since="0.3.4")
@dataclass(frozen=True)
class SliceResult:
    """The answer to a backward-slice query (FR-021)."""

    cells: tuple[str, ...]
    unresolved_reads: tuple[UnresolvedRead, ...]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class DependencyGraph:
    """The cell-level graph over the enabled cells of a notebook.

    Built by :func:`build_graph`; a deterministic function of the cells' source,
    their order, their enabled flags, and their recorded observations (FR-017).
    """

    cells: tuple[str, ...]
    edges: tuple[Edge, ...]
    unresolved_reads: tuple[UnresolvedRead, ...]
    version_nodes: tuple[VersionNode, ...]
    version_edges: tuple[VersionEdge, ...]
    unknown_binding_cells: tuple[str, ...]
    changed_sets: Mapping[str, frozenset[str]]

    _order: Mapping[str, int] = field(init=False, repr=False, compare=False)
    _dependencies: Mapping[str, tuple[str, ...]] = field(init=False, repr=False, compare=False)
    _dependents: Mapping[str, tuple[str, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # The adjacency lists are de-duplicated through a parallel set rather
        # than by scanning the list, because the list is not short. FR-018 asks
        # for a cost linear in cells and names, and `x not in some_list` is
        # linear in that list's length -- which is fine only while every cell's
        # fan-in and fan-out stay small. They do not: a notebook's first cell
        # imports the libraries and reads the data, and every cell below it
        # reads those names, so that one cell's `dependents` entry grows to the
        # length of the notebook and the loop below turns quadratic against the
        # single most ordinary notebook shape there is. Measured on a 2000-cell
        # generated notebook whose first cell binds `base` and `scale`, the
        # list form spent 13 ms of a 36 ms build here; the set form spends
        # under 2 ms and the whole build is linear again. The lists are still
        # what is published, so first-seen order -- and therefore FR-017's
        # determinism -- is unchanged; the sets only answer the membership
        # question.
        order = {cell_id: index for index, cell_id in enumerate(self.cells)}
        dependencies: dict[str, list[str]] = {cell_id: [] for cell_id in self.cells}
        dependents: dict[str, list[str]] = {cell_id: [] for cell_id in self.cells}
        seen_dependencies: dict[str, set[str]] = {cell_id: set() for cell_id in self.cells}
        seen_dependents: dict[str, set[str]] = {cell_id: set() for cell_id in self.cells}
        for edge in self.edges:
            if edge.definer not in seen_dependencies[edge.reader]:
                seen_dependencies[edge.reader].add(edge.definer)
                dependencies[edge.reader].append(edge.definer)
            if edge.reader not in seen_dependents[edge.definer]:
                seen_dependents[edge.definer].add(edge.reader)
                dependents[edge.definer].append(edge.reader)
        object.__setattr__(self, "_order", MappingProxyType(order))
        object.__setattr__(
            self,
            "_dependencies",
            MappingProxyType({key: tuple(value) for key, value in dependencies.items()}),
        )
        object.__setattr__(
            self,
            "_dependents",
            MappingProxyType({key: tuple(value) for key, value in dependents.items()}),
        )

    # -- queries ----------------------------------------------------------

    def changed_set(self, cell_id: str) -> frozenset[str]:
        """FR-022: the union of the cell's static estimate and its observation.

        Answers for every analysed cell, enabled or not, because the panel layer
        and the session ask about a cell rather than about the graph's shape.
        """
        try:
            return self.changed_sets[cell_id]
        except KeyError:
            raise KeyError(f"no analysed cell {cell_id!r}") from None

    def downstream(self, cell_id: str) -> tuple[str, ...]:
        """FR-020: the enabled cells that transitively read a name this cell changes.

        Returned in written order. This is what the session marks stale after a
        re-run. The cell itself is never included: edges only ever point at a
        cell above, so the graph is acyclic.
        """
        start = self._require_enabled(cell_id)
        seen: set[str] = set()
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for reader in self._dependents[current]:
                if reader not in seen:
                    seen.add(reader)
                    frontier.append(reader)
        seen.discard(start)
        return self._in_written_order(seen)

    def backward_slice(self, cell_ids: Iterable[str]) -> SliceResult:
        """FR-021: *cell_ids* and every enabled cell they transitively depend on.

        Returned in written order, together with the unresolved reads inside the
        slice, so packaging can refuse a notebook whose slice would fail with a
        name error.
        """
        seen: set[str] = set()
        frontier = [self._require_enabled(cell_id) for cell_id in cell_ids]
        seen.update(frontier)
        while frontier:
            current = frontier.pop()
            for definer in self._dependencies[current]:
                if definer not in seen:
                    seen.add(definer)
                    frontier.append(definer)
        cells = self._in_written_order(seen)
        unresolved = tuple(read for read in self.unresolved_reads if read.cell_id in seen)
        return SliceResult(cells=cells, unresolved_reads=unresolved)

    def definer_for(self, cell_id: str, name: str) -> str | None:
        """FR-023: the enabled cell above *cell_id* that written order says defines *name*.

        ``None`` when no cell above defines it. The resolution is the same one
        the edges use: the nearest enabled cell above whose changed set contains
        the name, falling back to the nearest cell above that binds an unknown
        set of names (FR-013). The session compares the answer with the cell that
        last bound the name in the kernel; the graph itself does not act on the
        comparison.
        """
        index = self._order.get(cell_id)
        if index is None:
            raise KeyError(f"no enabled cell {cell_id!r} in the graph")
        for above in reversed(self.cells[:index]):
            if name in self.changed_sets[above]:
                return above
        unknown = set(self.unknown_binding_cells)
        for above in reversed(self.cells[:index]):
            if above in unknown:
                return above
        return None

    # -- helpers ----------------------------------------------------------

    def _require_enabled(self, cell_id: str) -> str:
        if cell_id not in self._order:
            raise KeyError(f"no enabled cell {cell_id!r} in the graph")
        return cell_id

    def _in_written_order(self, cell_ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted(cell_ids, key=lambda cell_id: self._order[cell_id]))


# ---------------------------------------------------------------------------
# Source hashing (FR-027, FR-031)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def source_hash(source: str) -> str:
    """The hash a per-cell record and an observation are keyed to.

    Encoded with ``surrogatepass``, as :mod:`scistudio.explore.fingerprint`
    encodes a string, because a notebook is JSON and JSON can carry a lone
    surrogate: ``json.loads('"\\\\ud800"')`` produces a ``str`` that strict UTF-8
    refuses. Hashing such a cell must not raise — FR-012 requires the cell to
    come back flagged and forbids it from stopping any other cell being
    analysed, and this hash is taken before the parse that raises the flag. Every
    string a strict encode accepts hashes to the same digest either way, so no
    stored record is invalidated by the choice.
    """
    return hashlib.sha256(source.encode("utf-8", "surrogatepass")).hexdigest()


# ---------------------------------------------------------------------------
# Magic and shell lines (FR-011, FR-013)
# ---------------------------------------------------------------------------

_MAGIC_LINE = re.compile(r"^[ \t]*[%!]")
_CELL_MAGIC_LINE = re.compile(r"^[ \t]*%%")
_RUN_MAGIC_LINE = re.compile(r"^[ \t]*%{1,2}run\b")
_CELL_MAGIC_NAME = re.compile(r"^[ \t]*(%%[A-Za-z_][A-Za-z0-9_]*)")


def _first_non_blank(source: str) -> str | None:
    for line in source.splitlines():
        if line.strip():
            return line
    return None


#: The two tokens that can open a magic line. ``!=`` and ``%=`` are single
#: tokens of their own and are never one of these, so a wrapped comparison is
#: safe by construction rather than by a second check.
_MAGIC_TOKENS: Final[frozenset[str]] = frozenset({"%", "!"})

#: Token types that say nothing about where a logical line begins. Ignoring them
#: is what lets an indented magic and a magic after a comment still be seen as
#: the first token of their logical line (FR-011).
_LOGICAL_LINE_IGNORED: Final[frozenset[int]] = frozenset({tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT})


def _source_lines(source: str) -> list[str]:
    """Split *source* the way the tokeniser's ``readline`` does.

    ``str.splitlines`` also breaks on a form feed, a vertical tab, and half a
    dozen other characters Python's tokeniser treats as ordinary whitespace, so
    using it here would shift every line number against the ones the tokeniser
    reports. Joining the result back with ``"\\n"`` reproduces *source* exactly.
    """
    return source.split("\n")


def _error_line(error: BaseException) -> int:
    """The 1-based line the tokeniser stopped on.

    :class:`SyntaxError` carries ``lineno``; :class:`tokenize.TokenError` carries
    a ``(row, column)`` pair as its second argument instead. Anything else is
    treated as a stop at the first line, which costs the older textual test over
    the whole cell and never less coverage than that.
    """
    lineno = getattr(error, "lineno", None)
    if isinstance(lineno, int):
        return lineno
    args: tuple[Any, ...] = error.args
    position = args[1] if len(args) >= 2 else None
    if isinstance(position, tuple) and position and isinstance(position[0], int):
        return position[0]
    return 1


def _textual_magic_lines(source: str, first: int) -> set[int]:
    """The lines from *first* on whose first non-blank character is ``%`` or ``!``."""
    return {
        number
        for number, line in enumerate(_source_lines(source), start=1)
        if number >= first and _MAGIC_LINE.match(line)
    }


def _magic_line_numbers(source: str) -> set[int]:
    """The 1-based physical lines the cell's magic and shell lines occupy (FR-011).

    A ``%`` or ``!`` opens a magic only as the first token of a *logical* line,
    which is what separates ``%matplotlib inline`` from the ``% count`` a
    formatter puts on the continuation line of a wrapped expression. The
    tokeniser draws that line for us, and the distinction the whole rule rests on
    is between its two newlines: ``NEWLINE`` ends a logical line, ``NL`` — what it
    emits inside an open bracket and after a blank or comment-only line — does
    not. Collapsing the two is exactly the reading that made ``    % count`` look
    like a magic, so ``NL`` is handled on its own and never sets the flag.

    Where the tokeniser stops on an error, every line from that one on is
    classified by the older textual test, so a magic in a cell that cannot be
    tokenised — ``!cat it's-a-file`` stops the tokeniser on the apostrophe — is
    still removed.
    """
    magic_lines: set[int] = set()
    at_logical_start = True
    in_magic = False
    error_line: int | None = None
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in _LOGICAL_LINE_IGNORED:
                continue
            if token.type == tokenize.NL:
                if in_magic:
                    magic_lines.update(range(token.start[0], token.end[0] + 1))
                continue
            if token.type == tokenize.NEWLINE:
                if in_magic:
                    magic_lines.add(token.start[0])
                    in_magic = False
                at_logical_start = True
                continue
            if token.type == tokenize.ENDMARKER:
                break
            if in_magic:
                magic_lines.update(range(token.start[0], token.end[0] + 1))
                continue
            if at_logical_start and token.string in _MAGIC_TOKENS:
                in_magic = True
                magic_lines.update(range(token.start[0], token.end[0] + 1))
            at_logical_start = False
    except (tokenize.TokenError, SyntaxError, ValueError) as error:
        # ValueError covers a source with a null byte, which the tokeniser
        # refuses before it reaches the first line. IndentationError is a
        # SyntaxError subclass and is covered with it.
        error_line = _error_line(error)

    if error_line is not None:
        magic_lines.update(_textual_magic_lines(source, error_line))
    return magic_lines


def _strip_magic_lines(source: str) -> tuple[str, bool]:
    """Remove the magic and shell lines, keeping the line count so positions survive.

    Returns the stripped source and whether any removed magic was a ``%run``,
    which binds an unknown set of names (FR-013). FR-011's definition of a magic
    line governs FR-013's ``%run`` too, so the ``%run`` test is applied to the
    first physical line of a line the lexical pass already called a magic, and
    never to a line that merely starts with the character.
    """
    magic_lines = _magic_line_numbers(source)
    saw_run = False
    kept: list[str] = []
    for number, line in enumerate(_source_lines(source), start=1):
        if number in magic_lines:
            if _RUN_MAGIC_LINE.match(line):
                saw_run = True
            kept.append("")
            continue
        kept.append(line)
    return "\n".join(kept), saw_run


# ---------------------------------------------------------------------------
# The ast walk (FR-008, FR-009, FR-010, FR-013)
# ---------------------------------------------------------------------------

_SCOPE_STATEMENTS: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass
class _AstScan:
    outputs: list[OutputDeclaration] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    block_calls: list[BlockCall] = field(default_factory=list)
    star_import_lines: list[int] = field(default_factory=list)
    comprehension_targets: set[str] = field(default_factory=set)
    explicit_bindings: set[str] = field(default_factory=set)
    walrus_targets: set[str] = field(default_factory=set)
    extra_reads: set[str] = field(default_factory=set)


def _dotted_path(node: ast.expr) -> tuple[str, ...] | None:
    """The dotted path of ``a.b.c``, or ``None`` when the base is not a plain name."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def _path_matches(path: tuple[str, ...], target: tuple[str, ...]) -> bool:
    return len(path) >= len(target) and path[-len(target) :] == target


def _alias_binding(alias: ast.alias) -> str:
    """The module-scope name an ``import`` alias binds."""
    if alias.asname:
        return alias.asname
    return alias.name.partition(".")[0]


def _iter_module_level(stmts: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield the statements that execute at module scope.

    Descends into ``if``/``for``/``while``/``with``/``try``/``match`` bodies and
    stops at a ``def`` or ``class``, whose body is a scope of its own (FR-001).
    """
    for node in stmts:
        if isinstance(node, _SCOPE_STATEMENTS):
            continue
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                yield from _iter_module_level([child])
            elif isinstance(child, ast.ExceptHandler | ast.match_case):
                yield from _iter_module_level(child.body)


def _collect_comprehension_targets(tree: ast.Module) -> tuple[set[str], set[int]]:
    """The names bound by comprehension targets, and the id() of each such node.

    A comprehension target binds a scope of its own in every supported Python
    version. PEP 709 inlines list, set, and dict comprehensions from CPython
    3.12, which makes :mod:`symtable` report their targets at module scope; on
    3.11 it does not. Collecting them here lets the facts stay a function of the
    source rather than of the interpreter (FR-017).
    """
    names: set[str] = set()
    node_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                    node_ids.add(id(sub))
    return names, node_ids


#: The nodes whose bodies are a scope of their own. A ``lambda`` joins the three
#: statement forms here because :func:`_collect_walrus_targets` walks expressions
#: as well as statements, and a walrus inside a lambda binds in the lambda.
_NESTED_SCOPES: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _collect_walrus_targets(tree: ast.Module, scan: _AstScan) -> None:
    """Record the ``:=`` targets that bind at module scope (FR-005).

    PEP 572 gives a walrus inside a comprehension to the scope *containing* the
    comprehension, and PEP 709 inlines list, set, and dict comprehensions from
    CPython 3.12. The two together defeat :mod:`symtable`: for
    ``vals = [y := i for i in range(3)]`` it reports ``y`` at module scope as
    neither assigned nor local nor referenced, so nothing in the symbol walk
    claims it, and ``assigned`` comes back as ``{"vals"}`` alone. ``exec`` binds
    both. A generator expression is still a real child scope, so
    :func:`_collect_nested_module_scope` already catches *its* walrus — which is
    why only the inlined forms went missing.

    A missing binding is the one direction FR-002 forbids: without ``y`` the cell
    is not a definer of it, ``downstream`` never marks the reader stale, the
    backward slice drops the cell, and FR-015 reports ``y`` as an unresolved read
    of a notebook that runs correctly.

    The walk descends from the module and stops at every :data:`_NESTED_SCOPES`
    node, so a walrus inside a ``def``, a ``class`` body, or a ``lambda`` — where
    it binds locally rather than at module scope — is not collected. Names the
    symbol walk already reports are simply re-added; this only ever unions.
    """

    def descend(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _NESTED_SCOPES):
                continue
            if isinstance(child, ast.NamedExpr) and isinstance(child.target, ast.Name):
                scan.walrus_targets.add(child.target.id)
            descend(child)

    descend(tree)


def _collect_bindings(tree: ast.Module, scan: _AstScan, comprehension_node_ids: set[int]) -> None:
    """Record every binding form the ``ast`` shows, at any depth.

    This over-approximates deliberately: it is only ever used to *keep* a name
    that :func:`_collect_comprehension_targets` would otherwise drop, so naming
    one binding too many is the safe direction (FR-002).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store | ast.Del) and id(node) not in comprehension_node_ids:
                scan.explicit_bindings.add(node.id)
        elif isinstance(node, ast.alias):
            scan.explicit_bindings.add(_alias_binding(node))
        elif isinstance(node, _SCOPE_STATEMENTS):
            scan.explicit_bindings.add(node.name)
        elif isinstance(node, ast.arg):
            scan.explicit_bindings.add(node.arg)
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            scan.explicit_bindings.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            scan.explicit_bindings.add(node.rest)


def _collect_calls(tree: ast.Module, scan: _AstScan) -> None:
    """Record output declarations, input declarations, and block calls (FR-008 to FR-010)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            scan.star_import_lines.append(node.lineno)
            continue
        if not isinstance(node, ast.Call):
            continue
        path = _dotted_path(node.func)
        if path is None:
            continue
        if _path_matches(path, OUTPUT_CALL_PATH):
            scan.outputs.append(_output_declaration(node))
        elif _path_matches(path, INPUT_CALL_PATH):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                scan.inputs.append(first.value)
        elif any(_path_matches(path, target) for target in BLOCK_CALL_PATHS):
            first = node.args[0] if node.args else None
            literal = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            scan.block_calls.append(BlockCall(block_id=literal, lineno=node.lineno))


def _output_declaration(node: ast.Call) -> OutputDeclaration:
    keywords = tuple(keyword.arg for keyword in node.keywords if keyword.arg is not None)
    arguments: list[str] = [arg.id for arg in node.args if isinstance(arg, ast.Name)]
    arguments.extend(
        keyword.value.id for keyword in node.keywords if keyword.arg is not None and isinstance(keyword.value, ast.Name)
    )
    return OutputDeclaration(keywords=keywords, arguments=tuple(arguments))


def _declared_global(body: Sequence[ast.stmt]) -> set[str]:
    """The names a scope declares ``global``.

    Read over the scope's own statements only. A ``global`` declaration governs
    the whole scope that makes it, including its nested blocks, but does not
    reach a ``def`` written inside it: that function has to repeat the
    declaration before it binds the module-scope name.
    """
    return {name for node in _iter_module_level(body) if isinstance(node, ast.Global) for name in node.names}


def _augmented_and_deleted_names(body: Sequence[ast.stmt]) -> Iterator[str]:
    """The names ``x += 1`` and ``del x`` read in *body*, excluding nested scopes."""
    for node in _iter_module_level(body):
        if isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                yield node.target.id
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id


def _collect_module_level_reads(tree: ast.Module, scan: _AstScan) -> None:
    """Record the two reads :mod:`symtable` does not report.

    ``x += 1`` and ``del x`` both require ``x`` to exist, and both are reported
    by :mod:`symtable` as bindings only. Without the read, a backward slice
    containing the cell would omit the cell that defines the name and fail with
    a ``NameError`` when the slice runs (FR-006, FR-021).

    Both forms count wherever they resolve to the module scope, which is what
    FR-006 asks for in full: at module level, and inside a ``def`` or a ``class``
    for a name that scope declares ``global``. ``counter += 1`` under
    ``global counter`` is the shape that matters — :mod:`symtable` reports the
    symbol as assigned and global but not as referenced, so the cell would
    otherwise be a definer of ``counter`` that reads nothing, and a slice through
    it would drop the cell that gave ``counter`` its initial value. A nested
    scope's own local stays its own and is not a module read.
    """
    scan.extra_reads.update(_augmented_and_deleted_names(tree.body))
    for node in ast.walk(tree):
        if not isinstance(node, _SCOPE_STATEMENTS):
            continue
        declared = _declared_global(node.body)
        if not declared:
            continue
        scan.extra_reads.update(name for name in _augmented_and_deleted_names(node.body) if name in declared)


def _scan_ast(tree: ast.Module) -> _AstScan:
    scan = _AstScan()
    comprehension_names, comprehension_node_ids = _collect_comprehension_targets(tree)
    scan.comprehension_targets = comprehension_names
    _collect_bindings(tree, scan, comprehension_node_ids)
    _collect_walrus_targets(tree, scan)
    _collect_calls(tree, scan)
    _collect_module_level_reads(tree, scan)
    return scan


# ---------------------------------------------------------------------------
# The symtable walk (FR-005, FR-006)
# ---------------------------------------------------------------------------


def _symtable_names(table: symtable.SymbolTable) -> tuple[set[str], set[str]]:
    """The module-scope assigned and read names of a parsed cell.

    ``is_imported()`` is unioned into the assigned set because :mod:`symtable`
    reports ``import os`` as imported and *not* as assigned, and FR-005 names
    imports as a binding form.
    """
    assigned: set[str] = set()
    read: set[str] = set()
    for sym in table.get_symbols():
        if sym.is_assigned() or sym.is_imported():
            assigned.add(sym.get_name())
        if sym.is_referenced():
            read.add(sym.get_name())
    _collect_nested_module_scope(table, assigned, read)
    return assigned, read


def _collect_nested_module_scope(table: symtable.SymbolTable, assigned: set[str], read: set[str]) -> None:
    """Add the names a nested scope resolves to the module scope.

    A name a nested scope only reads is a module-scope read (FR-006). A name a
    nested scope declares ``global`` and assigns is a module-scope binding the
    code shows, so FR-005's "bound only inside a nested scope" exclusion does
    not reach it. A *free* variable resolves to an enclosing function rather
    than to the module and is skipped.
    """
    for child in table.get_children():
        for sym in child.get_symbols():
            if not sym.is_global():
                continue
            if sym.is_referenced():
                read.add(sym.get_name())
            if sym.is_assigned() or sym.is_imported():
                assigned.add(sym.get_name())
        _collect_nested_module_scope(child, assigned, read)


# ---------------------------------------------------------------------------
# Analysing a cell (FR-005 to FR-013)
# ---------------------------------------------------------------------------


def _opaque_cell_facts(cell_id: str, source: str, digest: str) -> CellFacts:
    first = _first_non_blank(source) or ""
    match = _CELL_MAGIC_NAME.match(first)
    magic = match.group(1) if match else first.strip()
    flag = CellFlag(
        flag=AnalysisFlag.OPAQUE_CELL_MAGIC,
        message=AnalysisFlag.OPAQUE_CELL_MAGIC.message(cell_id=cell_id, magic=magic),
        lineno=1,
    )
    return CellFacts(
        cell_id=cell_id,
        source_hash=digest,
        assigned=frozenset(),
        read=frozenset(),
        flags=(flag,),
    )


def _syntax_error_facts(cell_id: str, digest: str, error: BaseException) -> CellFacts:
    detail = getattr(error, "msg", None) or str(error) or type(error).__name__
    flag = CellFlag(
        flag=AnalysisFlag.SYNTAX_ERROR,
        message=AnalysisFlag.SYNTAX_ERROR.message(cell_id=cell_id, detail=detail),
        lineno=getattr(error, "lineno", None),
        offset=getattr(error, "offset", None),
    )
    return CellFacts(
        cell_id=cell_id,
        source_hash=digest,
        assigned=frozenset(),
        read=frozenset(),
        flags=(flag,),
    )


@provisional(since="0.3.4")
def analyse_cell(cell_id: str, source: str) -> CellFacts:
    """Compute the static facts of one cell. Never raises.

    A cell that begins with a cell magic is opaque; a cell that does not parse
    carries the syntax-error flag; neither prevents any other cell from being
    analysed (FR-011, FR-012).
    """
    digest = source_hash(source)
    first = _first_non_blank(source)
    if first is not None and _CELL_MAGIC_LINE.match(first):
        return _opaque_cell_facts(cell_id, source, digest)

    stripped, saw_run_magic = _strip_magic_lines(source)
    filename = f"<cell {cell_id}>"
    try:
        tree = ast.parse(stripped, filename=filename)
        table = symtable.symtable(stripped, filename, "exec")
    except (SyntaxError, ValueError, RecursionError) as error:
        # ValueError covers a source with a null byte; RecursionError covers a
        # source nested past the parser's limit. FR-012 requires that neither
        # stops the notebook being analysed.
        return _syntax_error_facts(cell_id, digest, error)

    scan = _scan_ast(tree)
    assigned, read = _symtable_names(table)
    comprehension_only = scan.comprehension_targets - scan.explicit_bindings
    assigned -= comprehension_only
    # A walrus target the interpreter binds at module scope but symtable does not
    # report there. Added after the subtraction so an inlined comprehension's
    # ``:=`` survives it (FR-002, FR-005); see _collect_walrus_targets.
    assigned |= scan.walrus_targets
    read |= scan.extra_reads
    read -= comprehension_only

    flags: list[CellFlag] = []
    if scan.star_import_lines or saw_run_magic:
        reason = "a star import" if scan.star_import_lines else "a %run line"
        flags.append(
            CellFlag(
                flag=AnalysisFlag.UNKNOWN_BINDINGS,
                message=AnalysisFlag.UNKNOWN_BINDINGS.message(cell_id=cell_id, reason=reason),
                lineno=scan.star_import_lines[0] if scan.star_import_lines else None,
            )
        )
    flags.extend(
        CellFlag(
            flag=AnalysisFlag.UNKNOWN_BLOCK_CALL,
            message=AnalysisFlag.UNKNOWN_BLOCK_CALL.message(cell_id=cell_id),
            lineno=call.lineno,
        )
        for call in scan.block_calls
        if call.block_id is None
    )

    return CellFacts(
        cell_id=cell_id,
        source_hash=digest,
        assigned=frozenset(assigned),
        read=frozenset(read),
        outputs=tuple(scan.outputs),
        inputs=tuple(scan.inputs),
        block_calls=tuple(scan.block_calls),
        flags=tuple(flags),
    )


@provisional(since="0.3.4")
def analyse_cells(cells: Sequence[tuple[str, str]]) -> tuple[CellFacts, ...]:
    """Analyse ``(cell_id, source)`` pairs in written order."""
    return tuple(analyse_cell(cell_id, source) for cell_id, source in cells)


# ---------------------------------------------------------------------------
# Building the graph (FR-014 to FR-019)
# ---------------------------------------------------------------------------


def _observed_names(value: object) -> frozenset[str]:
    """Read an observed changed set out of *value*.

    Accepts either an iterable of names or an object exposing ``changed_names``,
    so the runtime observation record can be handed straight to
    :func:`build_graph` without this module importing it (FR-003, FR-035).
    """
    changed = getattr(value, "changed_names", None)
    if changed is None:
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise TypeError(
                f"an observation must be an iterable of names or expose changed_names, got {type(value).__name__}"
            )
        changed = value
    return frozenset(str(name) for name in changed)


def _observation_is_current(cell: CellFacts, observation: object) -> bool:
    """Return ``True`` when *observation* still describes *cell*'s source (FR-027).

    An observation is a statement about the version of the cell that ran. Once
    the source is edited the statement is about code that no longer exists, and
    keeping it would draw an edge for a change the edit may have removed — so it
    is discarded and the static estimate alone governs until the cell runs again.

    An observation that carries no ``source_hash`` at all — a bare set of names,
    which :func:`_observed_names` also accepts — is taken at face value, because
    the caller who built it without a key is the one vouching that it is current.
    """
    recorded = getattr(observation, "source_hash", None)
    return recorded is None or recorded == cell.source_hash


def _resolve_changed_sets(
    facts: Sequence[CellFacts],
    observations: Mapping[str, object] | None,
) -> dict[str, frozenset[str]]:
    """The changed set per cell: the union of the static estimate and the observation.

    FR-030 lives here, in one expression. ``cell.assigned | observed`` can only
    grow the static estimate; nothing in this module subtracts from it, so an
    observation that reports *fewer* names than the source shows — a conditional
    assignment on a branch that was not taken — leaves every static edge standing
    (FR-002, spec §4.1 "Why the changed set is a union").
    """
    changed: dict[str, frozenset[str]] = {}
    for cell in facts:
        recorded = observations.get(cell.cell_id) if observations else None
        observed = (
            _observed_names(recorded)
            if recorded is not None and _observation_is_current(cell, recorded)
            else frozenset()
        )
        changed[cell.cell_id] = cell.assigned | observed
    return changed


def _edge_origin(definer: CellFacts, name: str) -> EdgeOrigin:
    if name in definer.assigned:
        return EdgeOrigin.STATIC_ASSIGNMENT
    return EdgeOrigin.OBSERVED_CHANGE


def _version_edges(
    edges: Sequence[Edge],
    changed_sets: Mapping[str, frozenset[str]],
) -> tuple[VersionEdge, ...]:
    """Derive the version-level edges from the cell-level ones (FR-016)."""
    version_edges: list[VersionEdge] = []
    for edge in edges:
        source = VersionNode(cell_id=edge.definer, name=edge.name)
        reader_versions = sorted(changed_sets[edge.reader])
        if not reader_versions:
            version_edges.append(VersionEdge(source=source, target_cell=edge.reader, target=None, origin=edge.origin))
            continue
        version_edges.extend(
            VersionEdge(
                source=source,
                target_cell=edge.reader,
                target=VersionNode(cell_id=edge.reader, name=name),
                origin=edge.origin,
            )
            for name in reader_versions
        )
    return tuple(version_edges)


@provisional(since="0.3.4")
def build_graph(
    facts: Sequence[CellFacts],
    *,
    enabled: Mapping[str, bool] | None = None,
    observations: Mapping[str, object] | None = None,
) -> DependencyGraph:
    """Build the dependency graph over the enabled cells of a notebook.

    *facts* are the cells in written order. *enabled* is the notebook's own
    enabled flag per cell, defaulting to enabled; a disabled cell neither
    defines nor reads (FR-014) and the analysis never writes the flag.
    *observations* maps a cell id to what the cell was observed to change when
    it ran — either an iterable of names or an object exposing
    ``changed_names``. The changed set the graph uses is the union of the static
    estimate and the observation, so an observation can only add a definer
    (FR-002, FR-022, FR-030).

    One pass over the cells with a running map from name to latest enabled
    definer, so the cost is linear in cells and names (FR-018).
    """
    seen_ids: set[str] = set()
    for cell in facts:
        if cell.cell_id in seen_ids:
            raise ValueError(f"duplicate cell id {cell.cell_id!r}")
        seen_ids.add(cell.cell_id)

    changed_sets = _resolve_changed_sets(facts, observations)
    enabled_cells = [cell for cell in facts if (enabled is None or enabled.get(cell.cell_id, True))]

    by_id = {cell.cell_id: cell for cell in enabled_cells}
    latest_definer: dict[str, str] = {}
    latest_unknown: str | None = None
    edges: list[Edge] = []
    unresolved: list[UnresolvedRead] = []
    unknown_binding_cells: list[str] = []
    unknown_versions: dict[str, set[str]] = {}

    for cell in enabled_cells:
        for name in sorted(cell.read):
            definer = latest_definer.get(name)
            if definer is not None:
                edges.append(
                    Edge(
                        reader=cell.cell_id,
                        definer=definer,
                        name=name,
                        origin=_edge_origin(by_id[definer], name),
                    )
                )
                continue
            if latest_unknown is not None:
                # FR-013: a read that resolves to no enabled definer resolves to
                # the nearest cell above that binds an unknown set of names,
                # before it is recorded as unresolved. This runs ahead of the
                # builtins exemption because a star import genuinely shadows a
                # builtin, and FR-002 resolves the uncertainty toward the edge.
                edges.append(
                    Edge(
                        reader=cell.cell_id,
                        definer=latest_unknown,
                        name=name,
                        origin=EdgeOrigin.UNKNOWN_BINDING,
                    )
                )
                unknown_versions.setdefault(latest_unknown, set()).add(name)
                continue
            if name in BUILTIN_NAMES:
                continue
            if name in changed_sets[cell.cell_id]:
                # The cell binds the name itself, so in the ordinary case the
                # read is not one a run would fail on. FR-015 draws no edge here
                # because a cell must not depend on itself, and US2 scenario 5
                # scopes the unresolved list to "a name that no enabled cell
                # changes" -- which this is not.
                #
                # The justification is a cell that binds a name and then uses it,
                # which is how people write: ``import pandas as pd`` followed in
                # the same cell by ``df = pd.read_csv('f')`` reads ``pd``, and so
                # does ``total = 0`` followed by ``total += 1``, and
                # ``def f(n): return f(n - 1)``. Without the exception every one
                # of those would report its own name unresolved and packaging
                # would refuse the notebook. A *bare* ``import pandas as pd``
                # would not: symtable reports ``pd`` as imported and not
                # referenced, so the cell reads nothing and this branch is never
                # reached. That narrower claim stood in this comment until the
                # ADR-054 spec 2 audits measured it and found it false.
                #
                # TODO(#2243): FR-015 admits one exception -- a builtin -- and
                #   this is a second. The cost is a real false negative: a first
                #   cell that says ``df = df.dropna()`` raises NameError when it
                #   runs and is reported as resolved.
                #   Out of scope per the owner decision recorded on #2243:
                #   telling ``df = df.dropna()`` from ``total = 0; total += 1``
                #   needs the within-cell statement order FR-001 forbids the
                #   analysis to model, so the resolution is a spec change --
                #   either FR-015 gains this exception or FR-001 gains a narrow
                #   ordering rule -- and not an implementer's to invent.
                #   Followup: https://github.com/jiazhenz026/SciStudio/issues/2243
                continue
            unresolved.append(UnresolvedRead(cell_id=cell.cell_id, name=name))

        for name in changed_sets[cell.cell_id]:
            latest_definer[name] = cell.cell_id
        if cell.binds_unknown_names:
            latest_unknown = cell.cell_id
            unknown_binding_cells.append(cell.cell_id)

    # FR-016: one node per name in the cell's changed set, plus the names an
    # unknown-binding resolution says this cell produced. A star import binds an
    # unknown set, so its changed set is empty and the names it resolved would
    # otherwise be sources of version edges that point at nothing. Publishing the
    # node keeps the edge — a cell that reads ``arange`` after ``from numpy
    # import *`` really does depend on that cell (FR-013) — and FR-002 resolves
    # the uncertainty toward the extra node rather than toward a version view
    # that shows the reader unconnected.
    version_nodes = tuple(
        VersionNode(cell_id=cell.cell_id, name=name)
        for cell in enabled_cells
        for name in sorted(changed_sets[cell.cell_id] | unknown_versions.get(cell.cell_id, set()))
    )

    return DependencyGraph(
        cells=tuple(cell.cell_id for cell in enabled_cells),
        edges=tuple(edges),
        unresolved_reads=tuple(unresolved),
        version_nodes=version_nodes,
        version_edges=_version_edges(edges, changed_sets),
        unknown_binding_cells=tuple(unknown_binding_cells),
        changed_sets=MappingProxyType(changed_sets),
    )


# ---------------------------------------------------------------------------
# Observation diagnostics (FR-028, FR-029)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def observation_flags(facts: CellFacts, observation: ObservedChange | None) -> tuple[CellFlag, ...]:
    """The flags a cell's observation raises against its static estimate (FR-028, FR-029).

    Two of the seven flags in :class:`AnalysisFlag` can only be raised here,
    because only here are the observation and the static estimate both in hand:

    * :attr:`AnalysisFlag.UNPREDICTED_CHANGE`, one per name the cell was observed
      to change that its source does not assign. This is the ``normalise(df)``
      case of US3: the cell changed ``df`` and nothing in the code says so, and
      the person is entitled to be told which cell and which name. Where the
      message is shown is the explore-frontend spec's.
    * :attr:`AnalysisFlag.UNOBSERVABLE_NAME`, one per name whose fingerprint fell
      back to identity - reported once for that cell run (FR-029), so the person
      knows the observation does not cover it.

    Returns ``()`` for a cell with no observation and for one whose observation
    no longer matches its source (FR-027): a diagnostic about a run of code the
    person has since edited is noise, and the observation itself is discarded by
    :func:`build_graph` for the same reason.

    The flags are *returned*, not folded into :attr:`CellFacts.flags`, because
    ``CellFacts`` is the static result and stays a function of the source alone.
    A caller that wants both concatenates them.
    """
    if observation is None:
        return ()
    if observation.cell_id != facts.cell_id:
        raise ValueError(f"observation for cell {observation.cell_id!r} does not describe cell {facts.cell_id!r}")
    if not observation.applies_to(facts.source_hash):
        return ()

    flags: list[CellFlag] = [
        CellFlag(
            flag=AnalysisFlag.UNPREDICTED_CHANGE,
            message=AnalysisFlag.UNPREDICTED_CHANGE.message(cell_id=facts.cell_id, name=name),
            name=name,
        )
        for name in sorted(observation.changed_names - facts.assigned)
    ]
    flags.extend(
        CellFlag(
            flag=AnalysisFlag.UNOBSERVABLE_NAME,
            message=AnalysisFlag.UNOBSERVABLE_NAME.message(cell_id=facts.cell_id, name=name),
            name=name,
        )
        for name in sorted(observation.unobservable_names)
    )
    return tuple(flags)


# ---------------------------------------------------------------------------
# The metadata codec (FR-031 to FR-034)
# ---------------------------------------------------------------------------

#: Keys inside a per-cell record that this analysis owns. Every other key found
#: in the record is another tool's and is carried through a rewrite untouched
#: (FR-033).
_RECOGNISED_CELL_KEYS: Final[frozenset[str]] = frozenset(
    {"source_hash", "assigned", "read", "outputs", "inputs", "block_calls", "flags", "observation"}
)

#: Keys inside the notebook-level record that this analysis owns (FR-031).
_RECOGNISED_NOTEBOOK_KEYS: Final[frozenset[str]] = frozenset({"analysis_version"})


@provisional(since="0.3.4")
@dataclass(frozen=True)
class LoadedCell:
    """One cell's facts and observation, as :func:`decode_cell_record` recovered them.

    :attr:`facts` is always present and always describes the source that was
    passed in: a record that did not match is discarded and the cell re-analysed
    rather than returned as ``None`` for the caller to handle (FR-032).
    :attr:`reanalysed` says which of the two happened, so a session can tell a
    load that reused the stored facts from one that recomputed them, and so a
    test can assert the discard rather than infer it.
    """

    facts: CellFacts
    observation: ObservedChange | None
    reanalysed: bool


def _string_tuple(values: object) -> tuple[str, ...]:
    """Read a JSON array of strings, refusing anything else.

    A bare ``str`` is refused explicitly: iterating one yields characters, which
    would decode ``"df"`` as three names rather than failing, and a silently
    wrong record is worse than a discarded one.
    """
    if isinstance(values, str) or not isinstance(values, Iterable):
        raise TypeError(f"expected an array of strings, got {type(values).__name__}")
    items = tuple(values)
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"expected a string, got {type(item).__name__}")
    return items


def _require_str(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected {what} to be a string, got {type(value).__name__}")
    return value


def _optional_str(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"expected a string or null, got {type(value).__name__}")


def _require_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected {what} to be an integer, got {type(value).__name__}")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _require_int(value, "a position")


def _require_mapping(value: object, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected {what} to be an object, got {type(value).__name__}")
    return value


def _require_sequence(value: object, what: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"expected {what} to be an array, got {type(value).__name__}")
    return tuple(value)


def _encode_flag(flag: CellFlag) -> dict[str, Any]:
    return {
        "flag": flag.flag.value,
        "message": flag.message,
        "name": flag.name,
        "lineno": flag.lineno,
        "offset": flag.offset,
    }


def _decode_flag(payload: object) -> CellFlag:
    entry = _require_mapping(payload, "a flag")
    return CellFlag(
        # AnalysisFlag is closed (FR-036), so a value from outside it is a record
        # this version of the analysis cannot read: the ValueError reaches
        # decode_cell_record, which discards the record and re-analyses.
        flag=AnalysisFlag(entry["flag"]),
        message=_require_str(entry["message"], "a flag message"),
        name=_optional_str(entry.get("name")),
        lineno=_optional_int(entry.get("lineno")),
        offset=_optional_int(entry.get("offset")),
    )


def _encode_observation(observation: ObservedChange) -> dict[str, Any]:
    return {
        "changed_names": sorted(observation.changed_names),
        "unobservable_names": sorted(observation.unobservable_names),
        "source_hash": observation.source_hash,
    }


def _decode_observation(cell_id: str, digest: str, record: Mapping[str, Any]) -> ObservedChange | None:
    """Recover the observation, or ``None`` when it no longer describes the cell (FR-027)."""
    payload = record.get("observation")
    if payload is None:
        return None
    entry = _require_mapping(payload, "an observation")
    recorded = _require_str(entry["source_hash"], "an observation source hash")
    if recorded != digest:
        # The cell has been edited since the run. FR-027: the observation is
        # discarded and the static estimate alone governs until the cell runs
        # again. It is checked against the cell's *current* source rather than
        # against the record's own hash, so a record whose facts are stale for
        # one reason and whose observation is stale for another resolves each
        # independently.
        return None
    return ObservedChange(
        cell_id=cell_id,
        changed_names=frozenset(_string_tuple(entry.get("changed_names", ()))),
        unobservable_names=frozenset(_string_tuple(entry.get("unobservable_names", ()))),
        source_hash=recorded,
    )


def _decode_output(payload: object) -> OutputDeclaration:
    entry = _require_mapping(payload, "an output declaration")
    return OutputDeclaration(
        keywords=_string_tuple(entry["keywords"]),
        arguments=_string_tuple(entry["arguments"]),
    )


def _decode_block_call(payload: object) -> BlockCall:
    entry = _require_mapping(payload, "a block call")
    return BlockCall(
        block_id=_optional_str(entry.get("block_id")),
        lineno=_require_int(entry["lineno"], "a block call line number"),
    )


def _decode_facts(cell_id: str, digest: str, record: Mapping[str, Any]) -> CellFacts | None:
    """Recover the static facts, or ``None`` when the record is for other source (FR-032)."""
    if record.get("source_hash") != digest:
        return None
    return CellFacts(
        cell_id=cell_id,
        source_hash=digest,
        assigned=frozenset(_string_tuple(record.get("assigned", ()))),
        read=frozenset(_string_tuple(record.get("read", ()))),
        outputs=tuple(_decode_output(item) for item in _require_sequence(record.get("outputs", ()), "outputs")),
        inputs=_string_tuple(record.get("inputs", ())),
        block_calls=tuple(
            _decode_block_call(item) for item in _require_sequence(record.get("block_calls", ()), "block calls")
        ),
        flags=tuple(_decode_flag(item) for item in _require_sequence(record.get("flags", ()), "flags")),
    )


@provisional(since="0.3.4")
def encode_cell_record(
    facts: CellFacts,
    observation: ObservedChange | None = None,
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the per-cell record for the ``scistudio`` key of cell metadata (FR-031).

    The record holds the static facts, the flags, the source hash they were
    computed from, and the observation with its own source hash. It holds **no
    edges** (FR-032): the graph is a deterministic function of the sources, their
    order, the enabled flags, and the observations, all of which the notebook
    already carries, and a stored copy could only ever disagree with the
    recomputed one.

    Nor does it hold the cell id. The id belongs to the notebook cell the record
    is attached to; a second copy inside the record is one more value that can
    disagree with the cell it describes, for the same reason edges are not
    stored. :func:`decode_cell_record` takes the id from the caller.

    *existing* is the record currently under the key, if any. Keys this analysis
    does not recognise are carried through untouched, so another tool's metadata
    under the same key survives a rewrite (FR-033). The copy is shallow: an
    unknown value is passed through as the object it already was.

    Every value in the result is a JSON primitive - object, array, string,
    integer, or null - so the session's own :mod:`json` handling of the notebook
    is all that is needed to store it (FR-033, FR-034). Sets are written as
    sorted arrays, so the record is stable for a given input and a notebook does
    not churn in git on a re-save.
    """
    if observation is not None and observation.cell_id != facts.cell_id:
        raise ValueError(f"observation for cell {observation.cell_id!r} does not describe cell {facts.cell_id!r}")

    record: dict[str, Any] = {
        "source_hash": facts.source_hash,
        "assigned": sorted(facts.assigned),
        "read": sorted(facts.read),
        "outputs": [
            {"keywords": list(declaration.keywords), "arguments": list(declaration.arguments)}
            for declaration in facts.outputs
        ],
        "inputs": list(facts.inputs),
        "block_calls": [{"block_id": call.block_id, "lineno": call.lineno} for call in facts.block_calls],
        "flags": [_encode_flag(flag) for flag in facts.flags],
    }
    if observation is not None:
        record["observation"] = _encode_observation(observation)
    # Every recognised key is rewritten from the facts above, so one whose new
    # value is absent — an observation the source edit invalidated — is dropped
    # rather than left behind under a fresh source hash. Everything else in
    # *existing* is another tool's and survives (FR-033).
    record.update(
        {key: value for key, value in (existing or {}).items() if key not in _RECOGNISED_CELL_KEYS},
    )
    return record


@provisional(since="0.3.4")
def decode_cell_record(
    cell_id: str,
    source: str,
    record: Mapping[str, Any] | None,
    *,
    analysis_version: int | None = ANALYSIS_VERSION,
) -> LoadedCell:
    """Recover a cell's facts and observation from its stored record (FR-032).

    *record* is the value under the ``scistudio`` key of the cell's metadata, as
    the session's :mod:`json` load produced it, or ``None`` for a cell that has
    none. *analysis_version* is what :func:`notebook_record_version` read from
    the notebook-level record; ``None`` means the notebook carries no version.

    The record is **discarded and the cell re-analysed** when it is absent, when
    its source hash does not match *source*, when it was written by a different
    analysis version, or when any part of it fails to decode. That last case
    matters: a record lives in a file a person can edit and another tool can
    write, so a malformed one must cost a re-analysis and never an exception out
    of a notebook load. :attr:`LoadedCell.reanalysed` reports which happened.

    The observation is keyed to its own source hash and resolved independently:
    it survives only while it still describes the current source (FR-027).
    """
    digest = source_hash(source)
    facts: CellFacts | None = None
    observation: ObservedChange | None = None

    if record is not None and analysis_version == ANALYSIS_VERSION:
        try:
            entry = _require_mapping(record, "a cell record")
            facts = _decode_facts(cell_id, digest, entry)
            observation = _decode_observation(cell_id, digest, entry)
        except (TypeError, ValueError, KeyError, AttributeError):
            # Any malformed part discards the whole record: a half-read record
            # would produce facts that no source ever produced, and FR-002's one
            # guarantee is about facts the source shows.
            facts = None
            observation = None

    if facts is None:
        return LoadedCell(facts=analyse_cell(cell_id, source), observation=observation, reanalysed=True)
    return LoadedCell(facts=facts, observation=observation, reanalysed=False)


@provisional(since="0.3.4")
def encode_notebook_record(existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the notebook-level record for the ``scistudio`` key (FR-031).

    It holds the analysis version and nothing else: the version is what lets a
    newer release refuse records it cannot read, and everything else about a
    notebook is per-cell. Unknown keys in *existing* are preserved (FR-033).
    """
    record: dict[str, Any] = {"analysis_version": ANALYSIS_VERSION}
    record.update(
        {key: value for key, value in (existing or {}).items() if key not in _RECOGNISED_NOTEBOOK_KEYS},
    )
    return record


@provisional(since="0.3.4")
def notebook_record_version(record: Mapping[str, Any] | None) -> int | None:
    """The analysis version stored in the notebook-level record, or ``None``.

    ``None`` for a notebook that carries no record, one whose record is not an
    object, and one whose version is not an integer - all of which mean the same
    thing to :func:`decode_cell_record`: nothing here was written by an analysis
    this release can read, so every cell is re-analysed.
    """
    if not isinstance(record, Mapping):
        return None
    version = record.get("analysis_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    return version
