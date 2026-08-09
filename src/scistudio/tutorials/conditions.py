"""The completion-condition vocabulary, its parser, and its evaluator.

ADR-053 Learning Center spec, FR-045 … FR-055
(``docs/specs/adr-053-learning-center.md``).

The vocabulary is **core-owned** (FR-045). Tutorials reference terms; they do
not define them. It is exactly the sixteen terms of FR-047 plus the ``all`` and
``any`` combinators of FR-048.

**Negation is deliberately absent.** FR-048's reason, kept here because the
next reader will otherwise assume it was an oversight: a step that advances
when something is *absent* advances by the user doing nothing, which teaches
nothing and is indistinguishable from a stuck step.

Everything is judged on the backend against product truth (FR-046), read
through the single injected :class:`ProductState` port. ``ui_event`` is the one
term whose truth originates in the frontend (FR-052), and it still arrives here
as backend state: the frontend reports the event and the API layer records it
into the state object.

Evaluation is side-effect free (FR-055). Every method on :class:`ProductState`
is a pure read, ``file_exists`` only stats, and nothing here creates a file,
mutates a registry, or triggers a run.

An unknown term is rejected at **manifest validation**, not at evaluation
(FR-049): :mod:`scistudio.tutorials.manifest` calls :func:`parse_condition`
while validating, so a typo fails the tutorial's author rather than failing a
user on step nine. ``manifest -> conditions`` is the only direction the module
boundary allows (checklist §6.1.2); this module imports nothing else from
:mod:`scistudio.tutorials`, and never imports ``scistudio.api``.

No polling (FR-051)
-------------------

This module creates no timer and no loop. Re-evaluation is caused by a mapped
engine event (:data:`EVENT_TERM_MAP` / :func:`build_event_term_map`), by an
explicit request (FR-053), or by entry into a step. A condition already true
when its step is entered satisfies it immediately (FR-054) — which is simply
what "entry evaluates" means, since these are statements about state and not
about the user having just acted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    GIT_HEAD_CHANGED,
    INTERACTIVE_COMPLETE,
    WORKFLOW_CHANGED,
    WORKFLOW_COMPLETED,
)

if TYPE_CHECKING:
    from scistudio.workflow.definition import WorkflowDefinition

__all__ = [
    "BLOCKS_RELOADED_TERMS",
    "COMBINATORS",
    "EVENT_TERM_MAP",
    "FILE_CHANGED_TERMS",
    "TERM_SPECS",
    "VOCABULARY",
    "Condition",
    "ConditionValidationError",
    "ExternalEventNames",
    "ProductState",
    "RunSummary",
    "TermSpec",
    "build_event_term_map",
    "evaluate",
    "event_types_for_condition",
    "parse_condition",
    "terms_for_event",
]


class ConditionValidationError(ValueError):
    """A ``done_when`` was rejected at manifest validation (FR-049).

    Raised for an unknown term, a malformed shape, or missing term arguments.
    :mod:`scistudio.tutorials.manifest` re-raises it as a
    ``ManifestValidationError`` naming the file.
    """


# ---------------------------------------------------------------------------
# The vocabulary (FR-047) and each term's arguments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TermSpec:
    """What one vocabulary term judges and which arguments it takes."""

    name: str
    judges: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    one_of: tuple[tuple[str, ...], ...] = ()
    """Groups from which at least one key must be present."""


_SPECS: tuple[TermSpec, ...] = (
    TermSpec(
        name="node_exists",
        judges="a node of a given block type is present in the workflow",
        required=("block_type",),
        optional=("node_id",),
    ),
    TermSpec(
        name="edge_exists",
        judges="an edge connects two given block types or node ids",
        optional=("source_block_type", "source_node_id", "target_block_type", "target_node_id"),
        one_of=(("source_block_type", "source_node_id"), ("target_block_type", "target_node_id")),
    ),
    TermSpec(
        name="config_equals",
        judges="a node's configuration key holds a given value",
        required=("key", "value"),
        optional=("node_id", "block_type"),
        one_of=(("node_id", "block_type"),),
    ),
    TermSpec(
        name="run_succeeded",
        judges="a run of the workflow, or of a given node, completed successfully",
        optional=("workflow_id", "node_id"),
    ),
    TermSpec(
        name="port_has_output",
        judges="a given output port holds data",
        required=("node_id", "port"),
    ),
    TermSpec(
        name="block_registered",
        judges="a block type is present in the registry",
        required=("block_type",),
    ),
    TermSpec(
        name="type_registered",
        judges="a data type is present in the type registry",
        required=("type_name",),
    ),
    TermSpec(
        name="previewer_registered",
        judges="a previewer is registered for a given type",
        required=("type_name",),
    ),
    TermSpec(
        name="plot_exists",
        judges="a plot exists, optionally bound to a given block's output",
        optional=("plot_id", "node_id", "port"),
    ),
    TermSpec(
        name="file_exists",
        judges="a project-relative path exists",
        required=("path",),
    ),
    TermSpec(
        name="git_branch_exists",
        judges="a branch exists in the project repository",
        required=("branch",),
    ),
    TermSpec(
        name="git_current_branch",
        judges="the checked-out branch is a given name",
        required=("branch",),
    ),
    TermSpec(
        name="library_contains",
        judges="the tutorial-scoped library holds a named block, type, or previewer",
        required=("kind", "name"),
    ),
    TermSpec(
        name="interaction_completed",
        judges="an interactive block's panel was submitted",
        required=("node_id",),
    ),
    TermSpec(
        name="page_reached",
        judges="a reading step reached a given page",
        required=("page",),
    ),
    TermSpec(
        name="ui_event",
        judges="a named frontend event was reported",
        required=("name",),
    ),
)

TERM_SPECS: Mapping[str, TermSpec] = MappingProxyType({spec.name: spec for spec in _SPECS})
"""The sixteen terms of FR-047, each with the arguments it accepts."""

VOCABULARY: frozenset[str] = frozenset(TERM_SPECS)
"""FR-045: the core-owned term set. This is the single declaration of it.

The published manifest schema deliberately does not restate the names — a
second copy is a second thing to keep in step — and defers to this module,
which :mod:`scistudio.tutorials.manifest` calls during validation (FR-049).
"""

COMBINATORS: frozenset[str] = frozenset({"all", "any"})
"""FR-048. Negation is not here and is not an omission; see the module docstring."""

_LIBRARY_KINDS: frozenset[str] = frozenset({"block", "type", "previewer"})


# ---------------------------------------------------------------------------
# The parsed condition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """A parsed ``done_when``: one vocabulary term, or an ``all``/``any`` of them."""

    term: str
    """A name from :data:`VOCABULARY`, or ``"all"`` / ``"any"``."""
    args: Mapping[str, Any] = field(default_factory=dict)
    """Term arguments. Empty for a combinator."""
    operands: tuple[Condition, ...] = ()
    """Sub-conditions. Empty for a term."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", MappingProxyType(dict(self.args)))

    @property
    def is_combinator(self) -> bool:
        """True when this node is an ``all`` or an ``any``."""
        return self.term in COMBINATORS

    def terms(self) -> frozenset[str]:
        """Every vocabulary term this condition uses, recursively.

        The session layer uses this to decide which events can change the
        answer, without re-walking the tree itself.
        """
        if not self.is_combinator:
            return frozenset({self.term})
        found: set[str] = set()
        for operand in self.operands:
            found |= operand.terms()
        return frozenset(found)


def _check_args(spec: TermSpec, args: Mapping[str, Any], *, field_name: str) -> None:
    allowed = set(spec.required) | set(spec.optional)
    unknown = set(args) - allowed
    if unknown:
        raise ConditionValidationError(
            f"{field_name}: {spec.name} does not accept {', '.join(sorted(unknown))}; "
            f"it accepts {', '.join(sorted(allowed)) or 'no arguments'}"
        )
    missing = [key for key in spec.required if key not in args]
    if missing:
        raise ConditionValidationError(f"{field_name}: {spec.name} requires {', '.join(missing)}")
    for group in spec.one_of:
        if not any(key in args for key in group):
            raise ConditionValidationError(f"{field_name}: {spec.name} requires one of {', '.join(group)}")
    if spec.name == "library_contains":
        kind = args.get("kind")
        if kind not in _LIBRARY_KINDS:
            raise ConditionValidationError(
                f"{field_name}: library_contains kind must be one of {', '.join(sorted(_LIBRARY_KINDS))}"
            )


def parse_condition(raw: Any, *, field_name: str = "done_when") -> Condition:
    """Parse a ``done_when`` mapping, rejecting anything outside the vocabulary.

    The accepted shape is a single-key mapping: ``{term: {args}}`` for a term,
    ``{all: [condition, ...]}`` or ``{any: [...]}`` for a combinator. Called at
    manifest validation (FR-049), never at evaluation.
    """
    if not isinstance(raw, Mapping):
        raise ConditionValidationError(f"{field_name}: expected a mapping, got {type(raw).__name__}")
    if len(raw) != 1:
        raise ConditionValidationError(
            f"{field_name}: a condition must declare exactly one term; got {len(raw)} keys "
            f"({', '.join(sorted(str(key) for key in raw))})"
        )
    term, body = next(iter(raw.items()))
    term = str(term)
    if term in COMBINATORS:
        if not isinstance(body, Sequence) or isinstance(body, str) or not body:
            raise ConditionValidationError(f"{field_name}.{term}: expected a non-empty list of conditions")
        operands = tuple(
            parse_condition(item, field_name=f"{field_name}.{term}[{index}]") for index, item in enumerate(body)
        )
        return Condition(term=term, operands=operands)
    if term not in TERM_SPECS:
        raise ConditionValidationError(
            f"{field_name}: unknown completion condition {term!r}; "
            f"the vocabulary is {', '.join(sorted(VOCABULARY | COMBINATORS))}"
        )
    if body is None:
        body = {}
    if not isinstance(body, Mapping):
        raise ConditionValidationError(f"{field_name}.{term}: expected a mapping of arguments")
    args = {str(key): value for key, value in body.items()}
    _check_args(TERM_SPECS[term], args, field_name=field_name)
    return Condition(term=term, args=args)


# ---------------------------------------------------------------------------
# The product-state port (checklist §6.1.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunSummary:
    """The read-only view of one recorded run that ``run_succeeded`` needs.

    Deliberately not ``scistudio.core.lineage.record.RunRecord``: this module
    must not depend on the lineage schema, and the only facts a condition can
    ask about are which workflow the run belonged to, whether it succeeded, and
    which nodes within it succeeded. The layer that satisfies
    :class:`ProductState` projects the lineage rows into this.
    """

    run_id: str
    workflow_id: str
    succeeded: bool
    succeeded_node_ids: frozenset[str] = frozenset()


@runtime_checkable
class ProductState(Protocol):
    """The one injected port through which conditions read product truth.

    FR-046: judging is a backend concern, evaluated against the registries, the
    workflow definition, the run records, git, and the filesystem. This module
    reaches all of that through this protocol rather than by importing the API
    runtime, which keeps ``api -> tutorials`` a one-way edge and keeps the
    package testable without a FastAPI app (checklist §6.1.2, §6.1.3).

    Every member is a pure read (FR-055).
    """

    project_dir: Path | None
    tutorial_library_dir: Path | None

    def workflow(self) -> WorkflowDefinition | None:
        """The active workflow definition, or ``None`` when none is open."""
        ...

    def block_type_names(self) -> frozenset[str]: ...

    def data_type_names(self) -> frozenset[str]: ...

    def previewer_type_ids(self) -> frozenset[str]: ...

    def plot_bindings(self) -> tuple[tuple[str, str, str], ...]:
        """``(plot_id, node_id, output_port)`` for every plot that exists."""
        ...

    def run_records(self) -> tuple[RunSummary, ...]: ...

    def port_has_output(self, node_id: str, port: str) -> bool: ...

    def git_branches(self) -> frozenset[str]: ...

    def git_current_branch(self) -> str | None: ...

    def library_entries(self) -> frozenset[tuple[str, str]]:
        """``(kind, name)`` for every entry in the tutorial-scoped library."""
        ...

    def interactions_completed(self) -> frozenset[str]: ...

    def pages_reached(self) -> frozenset[str]: ...

    def ui_events(self) -> frozenset[str]: ...


# ---------------------------------------------------------------------------
# Evaluation (FR-046, FR-054, FR-055)
# ---------------------------------------------------------------------------


def _node_matches(node: Any, *, block_type: str | None, node_id: str | None) -> bool:
    if block_type is not None and node.block_type != block_type:
        return False
    return not (node_id is not None and node.id != node_id)


def _endpoint_matches(endpoint: str, nodes: Mapping[str, Any], *, block_type: Any, node_id: Any) -> bool:
    endpoint_node = endpoint.split(":", 1)[0]
    if node_id is not None and endpoint_node != node_id:
        return False
    if block_type is not None:
        node = nodes.get(endpoint_node)
        if node is None or node.block_type != block_type:
            return False
    return True


def _eval_node_exists(args: Mapping[str, Any], state: ProductState) -> bool:
    workflow = state.workflow()
    if workflow is None:
        return False
    return any(
        _node_matches(node, block_type=args.get("block_type"), node_id=args.get("node_id")) for node in workflow.nodes
    )


def _eval_edge_exists(args: Mapping[str, Any], state: ProductState) -> bool:
    workflow = state.workflow()
    if workflow is None:
        return False
    nodes = {node.id: node for node in workflow.nodes}
    for edge in workflow.edges:
        source_ok = _endpoint_matches(
            edge.source, nodes, block_type=args.get("source_block_type"), node_id=args.get("source_node_id")
        )
        target_ok = _endpoint_matches(
            edge.target, nodes, block_type=args.get("target_block_type"), node_id=args.get("target_node_id")
        )
        if source_ok and target_ok:
            return True
    return False


def _eval_config_equals(args: Mapping[str, Any], state: ProductState) -> bool:
    workflow = state.workflow()
    if workflow is None:
        return False
    key = args["key"]
    expected = args["value"]
    for node in workflow.nodes:
        if not _node_matches(node, block_type=args.get("block_type"), node_id=args.get("node_id")):
            continue
        if key in node.config and node.config[key] == expected:
            return True
    return False


def _eval_run_succeeded(args: Mapping[str, Any], state: ProductState) -> bool:
    workflow_id = args.get("workflow_id")
    node_id = args.get("node_id")
    for record in state.run_records():
        if workflow_id is not None and record.workflow_id != workflow_id:
            continue
        if node_id is not None:
            if node_id in record.succeeded_node_ids:
                return True
            continue
        if record.succeeded:
            return True
    return False


def _eval_plot_exists(args: Mapping[str, Any], state: ProductState) -> bool:
    plot_id = args.get("plot_id")
    node_id = args.get("node_id")
    port = args.get("port")
    for bound_plot_id, bound_node_id, bound_port in state.plot_bindings():
        if plot_id is not None and bound_plot_id != plot_id:
            continue
        if node_id is not None and bound_node_id != node_id:
            continue
        if port is not None and bound_port != port:
            continue
        return True
    return False


def _eval_file_exists(args: Mapping[str, Any], state: ProductState) -> bool:
    """Does a project-relative path exist?

    FR-053 is a requirement rather than a convenience *because of this term*.
    The ``file.changed`` watcher event is filtered to ``ADR036_FILE_ALLOWLIST``
    (``.py .r .txt .md .yaml .yml .json .csv .log``), so a ``file_exists``
    condition on a TIFF, a Zarr store, or any other data file is never
    event-driven and can only be re-checked through the explicit evaluate
    request. A step whose completion turns on such a file must not be written
    expecting the event map to reach it.

    Reading the filesystem is a pure read; nothing is created (FR-055).
    """
    project_dir = state.project_dir
    if project_dir is None:
        return False
    relative = str(args["path"])
    candidate = project_dir / relative
    try:
        return candidate.exists()
    except OSError:
        return False


_SIMPLE_EVALUATORS: Mapping[str, Any] = MappingProxyType(
    {
        "node_exists": _eval_node_exists,
        "edge_exists": _eval_edge_exists,
        "config_equals": _eval_config_equals,
        "run_succeeded": _eval_run_succeeded,
        "port_has_output": lambda args, state: state.port_has_output(str(args["node_id"]), str(args["port"])),
        "block_registered": lambda args, state: str(args["block_type"]) in state.block_type_names(),
        "type_registered": lambda args, state: str(args["type_name"]) in state.data_type_names(),
        "previewer_registered": lambda args, state: str(args["type_name"]) in state.previewer_type_ids(),
        "plot_exists": _eval_plot_exists,
        "file_exists": _eval_file_exists,
        "git_branch_exists": lambda args, state: str(args["branch"]) in state.git_branches(),
        "git_current_branch": lambda args, state: state.git_current_branch() == str(args["branch"]),
        "library_contains": lambda args, state: (str(args["kind"]), str(args["name"])) in state.library_entries(),
        "interaction_completed": lambda args, state: str(args["node_id"]) in state.interactions_completed(),
        "page_reached": lambda args, state: str(args["page"]) in state.pages_reached(),
        "ui_event": lambda args, state: str(args["name"]) in state.ui_events(),
    }
)


def evaluate(condition: Condition, state: ProductState) -> bool:
    """Judge ``condition`` against ``state``.

    Side-effect free (FR-055): no file is created, no registry is mutated, no
    run is triggered. Called on step entry (FR-054), on a mapped event
    (FR-050), and on an explicit request (FR-053) — never on a timer (FR-051).
    """
    if condition.term == "all":
        return all(evaluate(operand, state) for operand in condition.operands)
    if condition.term == "any":
        return any(evaluate(operand, state) for operand in condition.operands)
    evaluator = _SIMPLE_EVALUATORS.get(condition.term)
    if evaluator is None:  # pragma: no cover - parse_condition rejects this first
        raise ConditionValidationError(f"unknown completion condition {condition.term!r}")
    return bool(evaluator(condition.args, state))


# ---------------------------------------------------------------------------
# The event map (FR-050) — constants, never literals
# ---------------------------------------------------------------------------

BLOCKS_RELOADED_TERMS: frozenset[str] = frozenset(
    {"block_registered", "type_registered", "previewer_registered", "library_contains"}
)
"""Terms re-evaluated when the registries reload.

The event's own name is ``BLOCKS_RELOADED`` in ``scistudio.api.ws``. This
package may not import ``scistudio.api`` (checklist §6.1.2), and FR-050
requires the runtime to subscribe using the *declared constant* rather than a
string literal, so the name is not written down here at all: the API layer
passes it in through :class:`ExternalEventNames` at wiring time. That is why
this constant names only the terms.
"""

FILE_CHANGED_TERMS: frozenset[str] = frozenset({"file_exists"})
"""Terms re-evaluated on a watcher file event.

Same arrangement as :data:`BLOCKS_RELOADED_TERMS`: the event name is
``FILE_CHANGED_EVENT_TYPE`` in ``scistudio.api.file_contracts`` and is supplied
through :class:`ExternalEventNames`. See :func:`_eval_file_exists` for why this
mapping does not cover every case FR-053 has to.
"""

EVENT_TERM_MAP: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        WORKFLOW_CHANGED: frozenset({"node_exists", "edge_exists", "config_equals"}),
        WORKFLOW_COMPLETED: frozenset({"run_succeeded", "port_has_output"}),
        BLOCK_DONE: frozenset({"run_succeeded", "port_has_output"}),
        BLOCK_ERROR: frozenset({"run_succeeded", "port_has_output"}),
        GIT_HEAD_CHANGED: frozenset({"git_branch_exists", "git_current_branch"}),
        INTERACTIVE_COMPLETE: frozenset({"interaction_completed"}),
    }
)
"""FR-050's mapping, for the six events declared in ``scistudio.engine.events``.

Keyed by the imported constants, so the table cannot drift from the bus without
the import failing. The two events that live outside ``engine/events.py`` —
``blocks.reloaded`` and ``file.changed``, both under ``scistudio.api``, which
this package may not import — are not keyed here; see
:func:`build_event_term_map`.
"""


@dataclass(frozen=True)
class ExternalEventNames:
    """The two FR-050 event names that live under ``scistudio.api``.

    ``engine/events.py`` is frozen by the ADR-035/036 hard-scope rules, so
    ``BLOCKS_RELOADED`` and ``FILE_CHANGED_EVENT_TYPE`` were declared at the
    API and watcher layer instead. This package may not import that layer, and
    FR-050 forbids subscribing by string literal, so the API layer constructs
    this object from *its* constants and hands it in when it wires the
    subscription:

        ExternalEventNames(blocks_reloaded=BLOCKS_RELOADED,
                           file_changed=FILE_CHANGED_EVENT_TYPE)

    The result is that neither event name appears as a literal anywhere inside
    :mod:`scistudio.tutorials`, which a test asserts.
    """

    blocks_reloaded: str
    file_changed: str


def build_event_term_map(external: ExternalEventNames) -> Mapping[str, frozenset[str]]:
    """Return FR-050's full mapping, with the two API-layer events filled in."""
    complete = dict(EVENT_TERM_MAP)
    complete[external.blocks_reloaded] = BLOCKS_RELOADED_TERMS
    complete[external.file_changed] = FILE_CHANGED_TERMS
    return MappingProxyType(complete)


def terms_for_event(event_type: str, external: ExternalEventNames | None = None) -> frozenset[str]:
    """Which vocabulary terms an observed event can change the answer for."""
    mapping = EVENT_TERM_MAP if external is None else build_event_term_map(external)
    return mapping.get(event_type, frozenset())


def event_types_for_condition(condition: Condition, external: ExternalEventNames | None = None) -> frozenset[str]:
    """Which event types can change ``condition``'s answer.

    A term reached by no event — ``page_reached`` and ``ui_event``, whose truth
    is reported directly, and ``file_exists`` for a path the watcher filters out
    — contributes nothing here, which is exactly the gap FR-053's explicit
    evaluate request exists to cover.
    """
    mapping = EVENT_TERM_MAP if external is None else build_event_term_map(external)
    used = condition.terms()
    return frozenset(event for event, terms in mapping.items() if terms & used)
