"""Static dependency analysis for explore notebooks (ADR-054 §6.1/§6.2).

One row per cell: what the cell reads is found statically with ``symtable``
(scoping) plus a single ``ast`` walk (declarations and block calls); what it
changes is the union of that static estimate and the runtime observation of
:mod:`scistudio.explore.fingerprint`, so an observation can only add (FR-002,
FR-030). From the cell table and the written order, the graph follows one rule:
a cell that reads a name depends on the nearest enabled cell above it whose
changed set contains that name (FR-015).

The analysis is pure (FR-004): source, cell order, enabled flags, and recorded
observations in; facts and graph out. It executes no code, holds no kernel,
and touches no filesystem. It depends on the standard library only (FR-003) —
magic and shell lines are stripped rather than transformed, so no IPython is
required (ADR-054 §6.2).

The module imports nothing from SciStudio beyond the stability markers and its
sibling :mod:`scistudio.explore.fingerprint` (FR-035).
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import symtable
from collections.abc import Collection, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from scistudio.explore.fingerprint import ObservedChange
from scistudio.stability import provisional

__all__ = [
    "ANALYSIS_VERSION",
    "METADATA_KEY",
    "AnalysisFlag",
    "AnalysisRecord",
    "BlockCall",
    "CellFacts",
    "DependencyGraph",
    "Edge",
    "EdgeOrigin",
    "FlagDetail",
    "OutputDeclaration",
    "SliceResult",
    "UnresolvedRead",
    "VersionEdge",
    "VersionNode",
    "analyze_cell",
    "build_graph",
    "hash_source",
    "load_cell",
    "read_cell_enabled",
    "read_cell_record",
    "read_notebook_analysis_version",
    "write_cell_record",
    "write_notebook_record",
]

#: Key under which the analysis record lives in a notebook's cell metadata and
#: in the notebook-level metadata (FR-031).
METADATA_KEY = "scistudio"

#: Version of the record layout written under :data:`METADATA_KEY`. A record
#: whose version differs is discarded and the cell re-analysed (FR-032).
ANALYSIS_VERSION = "1"

#: Python's builtins namespace: reads of these names draw no edge and are not
#: recorded as unresolved (FR-015).
_BUILTIN_NAMES = frozenset(dir(builtins))


@provisional(since="0.3.4")
class AnalysisFlag(Enum):
    """The closed enumeration of every flag the analysis can raise (FR-036).

    Each member carries a human-readable message template; details (the
    parser's message, the cell and name a diagnostic names) are interpolated
    with ``str.format``.
    """

    SYNTAX_ERROR = "syntax_error"
    OPAQUE_CELL_MAGIC = "opaque_cell_magic"
    UNKNOWN_BINDINGS = "unknown_bindings"
    UNKNOWN_BLOCK_CALL = "unknown_block_call"
    UNPREDICTED_CHANGE = "unpredicted_change"
    UNOBSERVABLE_NAME = "unobservable_name"
    UNRESOLVED_READ = "unresolved_read"

    @property
    def message(self) -> str:
        """The human-readable message template for this flag (FR-036)."""
        return _FLAG_MESSAGES[self]


_FLAG_MESSAGES = {
    AnalysisFlag.SYNTAX_ERROR: "the cell does not parse: {detail}",
    AnalysisFlag.OPAQUE_CELL_MAGIC: ("the cell begins with a cell magic and is opaque to static analysis"),
    AnalysisFlag.UNKNOWN_BINDINGS: ("the cell changes an unknown set of names (a star import or a %run line)"),
    AnalysisFlag.UNKNOWN_BLOCK_CALL: ("a block call's identifier is not a string literal"),
    AnalysisFlag.UNPREDICTED_CHANGE: ("cell {cell} changed '{name}' without an assignment showing it"),
    AnalysisFlag.UNOBSERVABLE_NAME: ("the observation does not cover '{name}': its type cannot be fingerprinted"),
    AnalysisFlag.UNRESOLVED_READ: ("cell {cell} reads '{name}', which no enabled cell above it changes"),
}


@provisional(since="0.3.4")
@dataclass(frozen=True)
class FlagDetail:
    """One raised flag with its interpolated human-readable message (FR-036)."""

    flag: AnalysisFlag
    message: str


@provisional(since="0.3.4")
@dataclass(frozen=True)
class OutputDeclaration:
    """One ``scistudio.output(...)`` call in a cell (FR-008).

    ``keywords`` are the keyword names of the call; ``arguments`` are the
    names (plain variables) passed to it, positionally or by keyword.
    """

    keywords: tuple[str, ...]
    arguments: tuple[str, ...]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BlockCall:
    """One block call in a cell (FR-010).

    ``identifier`` is the block identifier string literal, or ``None`` when
    the call's first argument is not a string literal — the cell then also
    carries :attr:`AnalysisFlag.UNKNOWN_BLOCK_CALL`.
    """

    identifier: str | None


@provisional(since="0.3.4")
@dataclass(frozen=True)
class CellFacts:
    """The static result for one cell (FR-005..FR-013).

    ``assigned_names`` is the estimate of what the cell changes before it has
    run; ``read_names`` are the names the cell reads at module scope, including
    names it also assigns (statement order is not modelled, FR-006).
    ``source_hash`` keys these facts to the exact source they were computed
    from. ``flag_details`` carries the raised flags with their messages;
    ``flags`` is the convenience view of just the enumeration members.
    """

    cell_id: str
    source_hash: str
    assigned_names: tuple[str, ...]
    read_names: tuple[str, ...]
    output_declarations: tuple[OutputDeclaration, ...]
    input_declarations: tuple[str, ...]
    block_calls: tuple[BlockCall, ...]
    flag_details: tuple[FlagDetail, ...]

    @property
    def flags(self) -> tuple[AnalysisFlag, ...]:
        """The raised flags, without their messages."""
        return tuple(detail.flag for detail in self.flag_details)

    @property
    def is_output_cell(self) -> bool:
        """Whether the cell calls ``scistudio.output`` (FR-008)."""
        return bool(self.output_declarations)

    @property
    def has_unknown_bindings(self) -> bool:
        """Whether the cell changes an unknown set of names (FR-013)."""
        return AnalysisFlag.UNKNOWN_BINDINGS in self.flags


@provisional(since="0.3.4")
def hash_source(source: str) -> str:
    """The content hash observations and records are keyed to (FR-027, FR-031)."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Per-cell static facts
# ---------------------------------------------------------------------------


def _strip_cell(source: str) -> tuple[str, bool, bool]:
    """Strip magic and shell lines (FR-011).

    Returns ``(stripped_source, is_opaque, has_run_magic)``. A cell whose first
    non-blank line begins with ``%%`` is opaque. A stripped line beginning with
    ``%run`` marks the cell as changing an unknown set of names (FR-013).
    """
    lines = source.splitlines()
    first = next((line for line in lines if line.strip()), None)
    if first is not None and first.lstrip().startswith("%%"):
        return "", True, False
    kept: list[str] = []
    has_run = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("%", "!")):
            if stripped == "%run" or stripped.startswith(("%run ", "%run\t")):
                has_run = True
            continue
        kept.append(line)
    return "\n".join(kept), False, has_run


def _module_names(table: symtable.SymbolTable) -> tuple[set[str], set[str]]:
    """Assigned and read names at the module (cell) scope."""
    assigned: set[str] = set()
    read: set[str] = set()
    for name in table.get_identifiers():
        symbol = table.lookup(name)
        if symbol.is_assigned() or symbol.is_imported():
            assigned.add(name)
        if symbol.is_referenced():
            read.add(name)
    return assigned, read


def _nested_module_names(table: symtable.SymbolTable) -> tuple[set[str], set[str]]:
    """Names nested scopes read from, or assign to, the module scope (FR-005/FR-006).

    ``symtable`` resolves Python's scoping rules — nested functions,
    comprehensions, and ``global`` declarations — so the analysis does not
    re-derive them. A name bound only inside a nested scope is not global and
    never counts here.
    """
    assigned: set[str] = set()
    read: set[str] = set()
    for child in table.get_children():
        for name in child.get_identifiers():
            symbol = child.lookup(name)
            if symbol.is_global():
                if symbol.is_assigned():
                    assigned.add(name)
                if symbol.is_referenced():
                    read.add(name)
        child_assigned, child_read = _nested_module_names(child)
        assigned |= child_assigned
        read |= child_read
    return assigned, read


def _dotted_path(node: ast.expr) -> str | None:
    """The dotted path of a Name/Attribute chain (``scistudio.output``), else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _call_name_arguments(call: ast.Call) -> tuple[str, ...]:
    """Names (plain variables) passed to a call, positionally or by keyword."""
    names: list[str] = []

    def collect(expr: ast.expr) -> None:
        if isinstance(expr, ast.Name) and expr.id not in names:
            names.append(expr.id)

    for arg in call.args:
        collect(arg)
    for keyword in call.keywords:
        collect(keyword.value)
    return tuple(names)


class _CellWalk(ast.NodeVisitor):
    """The single ``ast`` walk: declarations, block calls, and the symtable gaps.

    ``symtable`` does not report the target of an augmented assignment as read
    (``q += 1`` reads ``q``), and reports a ``del`` behind a ``global``
    declaration only inside the nested scope; both are supplemented here so the
    static estimate never omits a binding form the code shows (FR-002).
    """

    def __init__(self) -> None:
        self.output_declarations: list[OutputDeclaration] = []
        self.input_declarations: list[str] = []
        self.block_calls: list[BlockCall] = []
        self.unknown_block_call = False
        self.star_import = False
        self.aug_assign_reads: set[str] = set()
        self.global_deletes: set[str] = set()
        self._scope_globals: list[set[str]] = [set()]

    def _enter_scope(self, node: ast.AST) -> None:
        self._scope_globals.append(set())
        self.generic_visit(node)
        self._scope_globals.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_scope(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._enter_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter_scope(node)

    def visit_Global(self, node: ast.Global) -> None:
        self._scope_globals[-1].update(node.names)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in self._scope_globals[-1]:
                self.global_deletes.add(target.id)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            self.aug_assign_reads.add(node.target.id)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(alias.name == "*" for alias in node.names):
            self.star_import = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        path = _dotted_path(node.func)
        if path == "scistudio.output":
            keywords = tuple(keyword.arg for keyword in node.keywords if keyword.arg is not None)
            self.output_declarations.append(OutputDeclaration(keywords=keywords, arguments=_call_name_arguments(node)))
        elif path == "scistudio.input":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.input_declarations.append(node.args[0].value)
        elif path in ("blocks.run", "scistudio.blocks.run"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.block_calls.append(BlockCall(identifier=node.args[0].value))
            else:
                self.block_calls.append(BlockCall(identifier=None))
                self.unknown_block_call = True
        self.generic_visit(node)


@provisional(since="0.3.4")
def analyze_cell(cell_id: str, source: str) -> CellFacts:
    """Compute the static facts of one cell from its source (FR-005..FR-013).

    Magic and shell lines are stripped before parsing (FR-011); a cell that
    does not parse is flagged and assigns and reads nothing, without affecting
    any other cell (FR-012). Never raises on cell source.
    """
    source_hash = hash_source(source)
    stripped, opaque, has_run_magic = _strip_cell(source)
    if opaque:
        detail = FlagDetail(AnalysisFlag.OPAQUE_CELL_MAGIC, AnalysisFlag.OPAQUE_CELL_MAGIC.message)
        return CellFacts(cell_id, source_hash, (), (), (), (), (), (detail,))
    try:
        tree = ast.parse(stripped)
        table = symtable.symtable(stripped, "<cell>", "exec")
    except (SyntaxError, ValueError) as exc:
        lineno = getattr(exc, "lineno", None)
        offset = getattr(exc, "offset", None)
        detail = FlagDetail(
            AnalysisFlag.SYNTAX_ERROR,
            AnalysisFlag.SYNTAX_ERROR.message.format(detail=f"{exc} (line {lineno}, column {offset})"),
        )
        return CellFacts(cell_id, source_hash, (), (), (), (), (), (detail,))

    walk = _CellWalk()
    walk.visit(tree)
    assigned, read = _module_names(table)
    nested_assigned, nested_read = _nested_module_names(table)
    assigned |= nested_assigned | walk.global_deletes
    read |= nested_read | walk.aug_assign_reads

    flag_details: list[FlagDetail] = []
    if walk.star_import or has_run_magic:
        flag_details.append(FlagDetail(AnalysisFlag.UNKNOWN_BINDINGS, AnalysisFlag.UNKNOWN_BINDINGS.message))
    if walk.unknown_block_call:
        flag_details.append(FlagDetail(AnalysisFlag.UNKNOWN_BLOCK_CALL, AnalysisFlag.UNKNOWN_BLOCK_CALL.message))

    return CellFacts(
        cell_id=cell_id,
        source_hash=source_hash,
        assigned_names=tuple(sorted(assigned)),
        read_names=tuple(sorted(read)),
        output_declarations=tuple(walk.output_declarations),
        input_declarations=tuple(walk.input_declarations),
        block_calls=tuple(walk.block_calls),
        flag_details=tuple(flag_details),
    )


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class EdgeOrigin(Enum):
    """Why an edge exists (FR-019)."""

    STATIC = "static"
    OBSERVED = "observed"
    UNKNOWN_BINDING = "unknown_binding"


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Edge:
    """A dependency from a reading cell to a defining cell for one name."""

    reader: str
    definer: str
    name: str
    origin: EdgeOrigin


@provisional(since="0.3.4")
@dataclass(frozen=True)
class VersionNode:
    """One name changed by one cell; what the dependency view renders (FR-016)."""

    cell_id: str
    name: str


@provisional(since="0.3.4")
@dataclass(frozen=True)
class VersionEdge:
    """A dependency between two version nodes, derived from a cell edge (FR-016).

    ``upstream`` is the version read (the definer's), ``downstream`` a version
    the reading cell changes; ``read_name`` is the name the edge is about.
    """

    upstream: VersionNode
    downstream: VersionNode
    origin: EdgeOrigin


@provisional(since="0.3.4")
@dataclass(frozen=True)
class UnresolvedRead:
    """A read no enabled cell above the reader changes (FR-015, FR-021)."""

    reader: str
    name: str

    @property
    def flag(self) -> AnalysisFlag:
        """The flag this read carries: always :attr:`AnalysisFlag.UNRESOLVED_READ`."""
        return AnalysisFlag.UNRESOLVED_READ


@provisional(since="0.3.4")
@dataclass(frozen=True)
class SliceResult:
    """The answer to a backward-slice query (FR-021).

    ``cells`` are the slice in written order; ``unresolved_reads`` are the
    unresolved reads inside the slice, so packaging can refuse a notebook that
    would fail with a name error.
    """

    cells: tuple[str, ...]
    unresolved_reads: tuple[UnresolvedRead, ...]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class DependencyGraph:
    """The cell-level graph over enabled cells (FR-014..FR-019).

    A deterministic function of the cells' source, their order, their enabled
    flags, and their recorded observations (FR-017). ``changed_sets`` holds the
    union of each cell's static estimate and its valid observation (FR-002,
    FR-022, FR-030).
    """

    cells: tuple[str, ...]
    edges: tuple[Edge, ...]
    unresolved_reads: tuple[UnresolvedRead, ...]
    version_nodes: tuple[VersionNode, ...]
    version_edges: tuple[VersionEdge, ...]
    changed_sets: Mapping[str, frozenset[str]]

    def downstream(self, cell_id: str) -> tuple[str, ...]:
        """Enabled cells that transitively read a name *cell_id* changes (FR-020).

        This is the set the session marks stale after a re-run. Returned in
        written order; *cell_id* itself is never included.
        """
        readers: dict[str, list[str]] = {}
        for edge in self.edges:
            readers.setdefault(edge.definer, []).append(edge.reader)
        reached: set[str] = set()
        queue = list(readers.get(cell_id, ()))
        while queue:
            current = queue.pop()
            if current in reached:
                continue
            reached.add(current)
            queue.extend(readers.get(current, ()))
        return tuple(cell for cell in self.cells if cell in reached)

    def backward_slice(self, cell_ids: Iterable[str]) -> SliceResult:
        """*cell_ids* plus every enabled cell they transitively depend on (FR-021).

        Returned in written order, together with the unresolved reads inside
        the slice. Seeds that are disabled or unknown contribute nothing.
        """
        definers: dict[str, list[str]] = {}
        for edge in self.edges:
            definers.setdefault(edge.reader, []).append(edge.definer)
        cell_set = set(self.cells)
        reached = {cell for cell in cell_ids if cell in cell_set}
        queue = list(reached)
        while queue:
            current = queue.pop()
            for definer in definers.get(current, ()):
                if definer not in reached:
                    reached.add(definer)
                    queue.append(definer)
        return SliceResult(
            cells=tuple(cell for cell in self.cells if cell in reached),
            unresolved_reads=tuple(read for read in self.unresolved_reads if read.reader in reached),
        )

    def changed_set(self, cell_id: str) -> frozenset[str]:
        """The union of a cell's static estimate and its observation (FR-022).

        Empty for a disabled or unknown cell.
        """
        return self.changed_sets.get(cell_id, frozenset())

    def definer_of(self, cell_id: str, name: str) -> str | None:
        """The enabled cell the written order says defines *name* for *cell_id* (FR-023).

        Returns ``None`` when no enabled cell above defines the name — the
        session compares the answer against the cell that last bound the name
        in the kernel to mark an out-of-order re-run; the graph itself never
        acts on the comparison.
        """
        for edge in self.edges:
            if edge.reader == cell_id and edge.name == name:
                return edge.definer
        return None


@provisional(since="0.3.4")
def build_graph(
    cells: Sequence[CellFacts],
    *,
    enabled: Collection[str] | None = None,
    observations: Mapping[str, ObservedChange] | None = None,
) -> DependencyGraph:
    """Build the dependency graph over enabled cells (FR-014..FR-019).

    *cells* are the per-cell facts in written order; *enabled* restricts the
    graph to those cell ids (``None`` enables all); *observations* maps cell id
    to its recorded :class:`~scistudio.explore.fingerprint.ObservedChange`. An
    observation whose source hash no longer matches its cell is discarded
    (FR-027). One linear pass over cells and names (FR-018): a running map
    from name to its latest enabled definer.
    """
    observations = observations or {}
    active = [facts for facts in cells if enabled is None or facts.cell_id in enabled]

    changed_sets: dict[str, frozenset[str]] = {}
    for facts in active:
        names = set(facts.assigned_names)
        observation = observations.get(facts.cell_id)
        if observation is not None and observation.source_hash == facts.source_hash:
            names |= set(observation.changed_names)
        changed_sets[facts.cell_id] = frozenset(names)

    edges: list[Edge] = []
    unresolved: list[UnresolvedRead] = []
    version_nodes: list[VersionNode] = []
    latest_definer: dict[str, tuple[str, EdgeOrigin]] = {}
    nearest_unknown: str | None = None

    for facts in active:
        for name in sorted(facts.read_names):
            if name in _BUILTIN_NAMES:
                continue
            hit = latest_definer.get(name)
            if hit is not None:
                definer, origin = hit
                if definer != facts.cell_id:
                    edges.append(Edge(reader=facts.cell_id, definer=definer, name=name, origin=origin))
            elif nearest_unknown is not None:
                edges.append(
                    Edge(
                        reader=facts.cell_id,
                        definer=nearest_unknown,
                        name=name,
                        origin=EdgeOrigin.UNKNOWN_BINDING,
                    )
                )
            else:
                unresolved.append(UnresolvedRead(reader=facts.cell_id, name=name))
        for name in sorted(changed_sets[facts.cell_id]):
            origin = EdgeOrigin.STATIC if name in facts.assigned_names else EdgeOrigin.OBSERVED
            latest_definer[name] = (facts.cell_id, origin)
            version_nodes.append(VersionNode(cell_id=facts.cell_id, name=name))
        if facts.has_unknown_bindings:
            nearest_unknown = facts.cell_id

    version_node_set = set(version_nodes)
    version_edges: list[VersionEdge] = []
    for edge in edges:
        upstream = VersionNode(cell_id=edge.definer, name=edge.name)
        if upstream not in version_node_set:
            continue  # unknown-binding resolutions have no version node for the name
        for changed_name in sorted(changed_sets.get(edge.reader, ())):
            downstream = VersionNode(cell_id=edge.reader, name=changed_name)
            version_edges.append(VersionEdge(upstream=upstream, downstream=downstream, origin=edge.origin))

    return DependencyGraph(
        cells=tuple(facts.cell_id for facts in active),
        edges=tuple(edges),
        unresolved_reads=tuple(unresolved),
        version_nodes=tuple(version_nodes),
        version_edges=tuple(version_edges),
        changed_sets=changed_sets,
    )


# ---------------------------------------------------------------------------
# The cell-metadata record codec (FR-031..FR-034)
# ---------------------------------------------------------------------------


def _facts_to_json(facts: CellFacts) -> dict[str, Any]:
    return {
        "source_hash": facts.source_hash,
        "assigned_names": list(facts.assigned_names),
        "read_names": list(facts.read_names),
        "output_declarations": [
            {"keywords": list(decl.keywords), "arguments": list(decl.arguments)} for decl in facts.output_declarations
        ],
        "input_declarations": list(facts.input_declarations),
        "block_calls": [{"identifier": call.identifier} for call in facts.block_calls],
        "flags": [{"flag": detail.flag.value, "message": detail.message} for detail in facts.flag_details],
    }


def _facts_from_json(cell_id: str, data: Mapping[str, Any]) -> CellFacts:
    return CellFacts(
        cell_id=cell_id,
        source_hash=str(data["source_hash"]),
        assigned_names=tuple(str(name) for name in data.get("assigned_names", ())),
        read_names=tuple(str(name) for name in data.get("read_names", ())),
        output_declarations=tuple(
            OutputDeclaration(
                keywords=tuple(str(kw) for kw in decl.get("keywords", ())),
                arguments=tuple(str(arg) for arg in decl.get("arguments", ())),
            )
            for decl in data.get("output_declarations", ())
        ),
        input_declarations=tuple(str(value) for value in data.get("input_declarations", ())),
        block_calls=tuple(
            BlockCall(identifier=None if call.get("identifier") is None else str(call["identifier"]))
            for call in data.get("block_calls", ())
        ),
        flag_details=tuple(
            FlagDetail(flag=AnalysisFlag(str(detail["flag"])), message=str(detail["message"]))
            for detail in data.get("flags", ())
        ),
    )


def _observation_to_json(observation: ObservedChange) -> dict[str, Any]:
    return {
        "source_hash": observation.source_hash,
        "changed_names": list(observation.changed_names),
        "unobservable_names": list(observation.unobservable_names),
    }


def _observation_from_json(cell_id: str, data: Mapping[str, Any]) -> ObservedChange:
    return ObservedChange(
        cell_id=cell_id,
        changed_names=tuple(str(name) for name in data.get("changed_names", ())),
        unobservable_names=tuple(str(name) for name in data.get("unobservable_names", ())),
        source_hash=str(data["source_hash"]),
    )


@provisional(since="0.3.4")
@dataclass(frozen=True)
class AnalysisRecord:
    """The record stored under the ``scistudio`` key of a cell's metadata (FR-031).

    Holds the static facts with the source hash they were computed from, the
    observation with its own source hash, and the analysis version. The JSON
    shape uses only JSON-serialisable primitives (FR-033). Edges are never
    stored; the graph is recomputed on load (FR-032).
    """

    facts: CellFacts
    observation: ObservedChange | None
    analysis_version: str = ANALYSIS_VERSION

    def to_json(self) -> dict[str, Any]:
        """The JSON-serialisable record body for one cell (FR-033)."""
        body: dict[str, Any] = {
            "analysis_version": self.analysis_version,
            "analysis": _facts_to_json(self.facts),
        }
        if self.observation is not None:
            body["observation"] = _observation_to_json(self.observation)
        return body

    @classmethod
    def from_json(cls, cell_id: str, body: Mapping[str, Any]) -> AnalysisRecord:
        """Rebuild a record from its stored body, without hash validation.

        Use :func:`read_cell_record` for the validating read path (FR-032).
        """
        facts = _facts_from_json(cell_id, body["analysis"])
        observation_data = body.get("observation")
        observation = (
            _observation_from_json(cell_id, observation_data) if isinstance(observation_data, Mapping) else None
        )
        return cls(
            facts=facts,
            observation=observation,
            analysis_version=str(body.get("analysis_version", ANALYSIS_VERSION)),
        )


@provisional(since="0.3.4")
def write_cell_record(metadata: MutableMapping[str, Any], record: AnalysisRecord) -> None:
    """Write *record* under the ``scistudio`` key of a cell's metadata (FR-031).

    Keys the analysis does not recognise are preserved (FR-033): the existing
    sub-record is read, the analysis-owned keys are replaced, and everything
    else — another tool's metadata under the same key — survives the rewrite.
    """
    existing = metadata.get(METADATA_KEY)
    sub = dict(existing) if isinstance(existing, MutableMapping) else {}
    body = record.to_json()
    sub["analysis_version"] = body["analysis_version"]
    sub["analysis"] = body["analysis"]
    if "observation" in body:
        sub["observation"] = body["observation"]
    else:
        sub.pop("observation", None)
    metadata[METADATA_KEY] = sub


@provisional(since="0.3.4")
def read_cell_record(
    cell_id: str,
    metadata: Mapping[str, Any],
    source: str,
) -> AnalysisRecord | None:
    """Read and validate a cell's record (FR-032).

    Returns ``None`` when no usable record exists — absent, from another
    analysis version, or computed from a source hash that no longer matches
    the cell — so the caller re-analyses the cell. An observation whose own
    source hash no longer matches is discarded while facts that still match
    are kept (FR-027).
    """
    sub = metadata.get(METADATA_KEY)
    if not isinstance(sub, Mapping):
        return None
    if sub.get("analysis_version") != ANALYSIS_VERSION:
        return None
    analysis = sub.get("analysis")
    if not isinstance(analysis, Mapping):
        return None
    source_hash = hash_source(source)
    if analysis.get("source_hash") != source_hash:
        return None
    record = AnalysisRecord.from_json(cell_id, sub)
    observation = record.observation
    if observation is not None and observation.source_hash != source_hash:
        observation = None
    return AnalysisRecord(facts=record.facts, observation=observation, analysis_version=record.analysis_version)


@provisional(since="0.3.4")
def load_cell(
    cell_id: str,
    source: str,
    metadata: Mapping[str, Any],
) -> tuple[CellFacts, ObservedChange | None]:
    """The cell's facts and observation, from the record when valid, else fresh (FR-032).

    A record whose source hash does not match the cell's source is discarded
    and the cell is re-analysed from source.
    """
    record = read_cell_record(cell_id, metadata, source)
    if record is not None:
        return record.facts, record.observation
    return analyze_cell(cell_id, source), None


@provisional(since="0.3.4")
def write_notebook_record(metadata: MutableMapping[str, Any]) -> None:
    """Write the notebook-level record holding the analysis version (FR-031).

    Unknown keys under the ``scistudio`` key are preserved (FR-033).
    """
    existing = metadata.get(METADATA_KEY)
    sub = dict(existing) if isinstance(existing, MutableMapping) else {}
    sub["analysis_version"] = ANALYSIS_VERSION
    metadata[METADATA_KEY] = sub


@provisional(since="0.3.4")
def read_notebook_analysis_version(metadata: Mapping[str, Any]) -> str | None:
    """The analysis version recorded at notebook level, if any (FR-031)."""
    sub = metadata.get(METADATA_KEY)
    if not isinstance(sub, Mapping):
        return None
    version = sub.get("analysis_version")
    return str(version) if version is not None else None


@provisional(since="0.3.4")
def read_cell_enabled(metadata: Mapping[str, Any]) -> bool:
    """The cell's enabled flag from its metadata, defaulting to enabled (FR-014).

    The flag is owned by the notebook and written by the session when the
    control is toggled; the analysis reads it and never writes it. The flag
    lives under the same ``scistudio`` metadata key as the analysis record.
    """
    sub = metadata.get(METADATA_KEY)
    if not isinstance(sub, Mapping):
        return True
    return bool(sub.get("enabled", True))
