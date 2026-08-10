"""The completion-condition vocabulary, its parser, and its evaluator.

ADR-053 Learning Center spec, FR-045 … FR-055
(``docs/specs/adr-053-learning-center.md``).

The vocabulary is **core-owned** (FR-045). Tutorials reference terms; they do
not define them. It is the sixteen terms FR-047 requires, plus ``config_matches``
(see :func:`_eval_config_matches` for the gap it closes — FR-047 sets a floor
rather than a ceiling, and §4.5 records that core extends the vocabulary as
tutorials find it short), plus the ``all`` and ``any`` combinators of FR-048.

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

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
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
    "LIBRARY_KINDS",
    "READING_TERMS",
    "TERM_SPECS",
    "UI_EVENT_NAMES",
    "UNSATISFIABLE_LIBRARY_KINDS",
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
        name="config_matches",
        judges="a node's configuration key matches a glob, compared as a path",
        required=("key", "pattern"),
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
"""Every term, each with the arguments it accepts: FR-047's sixteen plus
``config_matches``."""

VOCABULARY: frozenset[str] = frozenset(TERM_SPECS)
"""FR-045: the core-owned term set. This is the single declaration of it.

The published manifest schema deliberately does not restate the names — a
second copy is a second thing to keep in step — and defers to this module,
which :mod:`scistudio.tutorials.manifest` calls during validation (FR-049).
"""

COMBINATORS: frozenset[str] = frozenset({"all", "any"})
"""FR-048. Negation is not here and is not an omission; see the module docstring."""

UI_EVENT_NAMES: frozenset[str] = frozenset({"preview_expanded", "block_source_viewed"})
"""The closed set of frontend events a ``ui_event`` condition may name (FR-052).

Both members are FR-052's own motivating case: real product actions that leave
no backend state behind, which is the entire reason that requirement exists.
Everything else a tutorial waits on is a backend fact and belongs to one of the
other fifteen terms.

The set is closed for the reason FR-049 gives about terms. A free-form event
name is a typo that fails the *user* on step nine — the step simply never
advances, and nothing tells anyone why — instead of failing the author at
validation. So an unlisted name is rejected while the tutorial is being listed.

It grows by core change, not by a manifest author inventing a name: a new
member is only meaningful once the frontend reports it, so adding one requires
a matching frontend change in the same breath.
"""

READING_TERMS: frozenset[str] = frozenset({"page_reached"})
"""Terms whose truth is the reader turning a page, not the user doing anything.

Every other term judges a product fact — a registered block, a succeeded run, a
branch, a file. ``page_reached`` judges only that someone read on, which is what
makes it the one term a tutorial can be built entirely out of and still be
reading rather than doing.

This is what :attr:`~scistudio.tutorials.manifest.TutorialManifest.is_reading_only`
tests a manifest against, so the Learning Center can list reading tutorials
apart from hands-on ones **without a declared kind field**. The manifest module
records why there is no such field: the step actions already say what each step
does, and a second classification could contradict them. Deriving the answer
from ``done_when`` keeps that true — a tutorial cannot claim to be reading while
waiting on a run to succeed, because the claim is the conditions themselves.
"""

LIBRARY_KINDS: frozenset[str] = frozenset({"block", "type", "previewer"})
"""The three kinds ``library_contains`` is specified to judge (FR-047).

``previewer`` is **specified but not yet satisfiable**, and is kept here on
purpose. Deleting it would leave the next reader to "add" it back without
knowing it was ever considered; see :data:`UNSATISFIABLE_LIBRARY_KINDS` for
what happens to it at validation and why.
"""

UNSATISFIABLE_LIBRARY_KINDS: Mapping[str, str] = MappingProxyType(
    {
        "previewer": (
            "the tutorial-scoped library has no previewer tier yet — "
            "scoped_library_dirs() creates blocks/ and types/ only, and the previewer "
            "registry does not scan the library at all, so the condition can never "
            "become true. The user previewer tier is out of scope per spec assumption "
            "A-006 and is tracked at #2017; this term will accept the kind once it exists"
        ),
    }
)
"""Library kinds the vocabulary declares but the product cannot yet satisfy.

FR-047 names "block, type, or previewer", so accepting the kind in the
vocabulary is not a mistake — it is written against a product that does not
exist yet. But a tutorial declaring it today would leave the reader on a step
that can never complete and never says why, which is the failure FR-049 exists
to prevent by rejecting at validation rather than at step nine. So the kind is
declared, and rejected with its reason and its tracking issue, rather than
silently accepted or silently removed.
"""

_CLOSED_ARG_VALUES: Mapping[tuple[str, str], frozenset[str]] = MappingProxyType(
    {
        ("library_contains", "kind"): LIBRARY_KINDS,
        ("ui_event", "name"): UI_EVENT_NAMES,
    }
)
"""Term arguments whose value set is itself closed, checked at validation.

One table rather than a branch per term, so a third one cannot be added as a
special case that forgets to say what it accepts.
"""

_UNSATISFIABLE_ARG_VALUES: Mapping[tuple[str, str], Mapping[str, str]] = MappingProxyType(
    {
        ("library_contains", "kind"): UNSATISFIABLE_LIBRARY_KINDS,
    }
)
"""Argument values inside a closed set that the product cannot yet make true.

Checked after membership, so an author who writes an unsatisfiable value is
told *why* it cannot work rather than being told it is not a valid value —
those are different messages and only one of them is true.
"""


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
    for (term, argument), accepted in _CLOSED_ARG_VALUES.items():
        if spec.name == term and args.get(argument) not in accepted:
            raise ConditionValidationError(
                f"{field_name}.{term}.{argument}: {args.get(argument)!r} is not accepted; "
                f"the accepted values are {', '.join(sorted(accepted))}"
            )
    for (term, argument), unsatisfiable in _UNSATISFIABLE_ARG_VALUES.items():
        reason = unsatisfiable.get(str(args.get(argument))) if spec.name == term else None
        if reason is not None:
            raise ConditionValidationError(
                f"{field_name}.{term}.{argument}: {args.get(argument)!r} cannot be satisfied yet — {reason}"
            )
    if spec.name == "config_matches":
        pattern = args.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConditionValidationError(f"{field_name}: config_matches pattern must be a non-empty string")


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


def _addressed_config_values(args: Mapping[str, Any], state: ProductState) -> Iterator[Any]:
    """Yield the value of ``args['key']`` on every node the condition addresses.

    ``config_equals`` and ``config_matches`` differ only in how they compare a
    value once they have it. *Finding* it is one idea — no open workflow means
    no match, then the ``node_id``/``block_type`` selection FR-047 gives both
    terms, then the key being present on that node at all — and is written
    once, so a change to which nodes a config term addresses reaches both terms
    together.

    A node that does not carry the key yields nothing rather than yielding
    ``None``: absent and present-but-null are different, and only the caller
    knows whether that difference matters to its comparison.
    """
    workflow = state.workflow()
    if workflow is None:
        return
    key = args["key"]
    for node in workflow.nodes:
        if not _node_matches(node, block_type=args.get("block_type"), node_id=args.get("node_id")):
            continue
        if key in node.config:
            yield node.config[key]


def _eval_config_equals(args: Mapping[str, Any], state: ProductState) -> bool:
    expected = args["value"]
    return any(value == expected for value in _addressed_config_values(args, state))


def _as_posix(value: str) -> str:
    """Normalise separators so one manifest judges the same on every platform."""
    return value.replace("\\", "/")


def _eval_config_matches(args: Mapping[str, Any], state: ProductState) -> bool:
    """Does a node's configuration key match a glob, compared as a path?

    ``config_equals`` is exact string equality, which cannot judge a value the
    user produced through a file browser: the browser yields an **absolute**
    path, while a manifest can only ever declare a project-relative one, so the
    two never compare equal. The reader points the block at the right file, the
    step does not advance, and nothing tells them why — worse than a stuck step,
    because it looks like they did something wrong.

    The retired frontend predicate handled this by normalising separators and
    accepting a trailing-suffix match, and that capability was lost when judging
    moved to the backend (FR-046). This term restores it as a first-class part
    of the vocabulary rather than as a special case hidden inside
    ``config_equals``, so a manifest that means "matches" says "matches" and a
    term named "equals" always means equality.

    Two properties do the work, both from :meth:`pathlib.PurePath.match`:

    * a **relative pattern is matched from the right**, so
      ``data/raw/cells.csv`` is satisfied by
      ``/Users/someone/SciStudio Tutorials/proj/data/raw/cells.csv``. An
      absolute pattern anchors at the root instead, for the rare manifest that
      wants that.
    * separators are normalised on both sides first, so a manifest written with
      ``/`` judges a Windows configuration value containing ``\\`` correctly.

    Plain relative patterns already match at any depth, so ``**`` is not needed
    and is not recommended: ``PurePath.match`` treats it as a single ``*``.
    """
    pattern = _as_posix(str(args["pattern"]))
    for value in _addressed_config_values(args, state):
        if not isinstance(value, str) or not value:
            continue
        try:
            if PurePosixPath(_as_posix(value)).match(pattern):
                return True
        except ValueError:
            # An unusable pattern is a false condition, never a crashed session.
            continue
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
        "config_matches": _eval_config_matches,
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
        WORKFLOW_CHANGED: frozenset({"node_exists", "edge_exists", "config_equals", "config_matches"}),
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
