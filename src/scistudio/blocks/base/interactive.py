"""The interaction capability for data-processing blocks.

An interactive block pauses mid-workflow, opens a block-owned window onto its
real input data, takes a data-dependent decision from the user, and computes its
outputs from that decision. Interaction is a *capability* any block category can
carry, not a category of its own: a block becomes interactive by mixing in
:class:`InteractiveMixin` and declaring ``execution_mode =
ExecutionMode.INTERACTIVE``. There is deliberately no ``InteractiveBlock`` base
class — interactivity is layered onto an existing category (for example
:class:`~scistudio.blocks.process.process_block.ProcessBlock`).

The capability gives a block three things:

* :attr:`InteractiveMixin.interactive_panel` — a
  :class:`~scistudio.core.panels.PanelManifest` naming the panel the block
  opens. A block-declared panel must declare the producing capability
  (:class:`~scistudio.core.panels.PanelCapability`, imported from the contract
  module), which is what the manifest defaults to and what the registry
  checks when the block is discovered (ADR-054 spec 1 FR-050).
* :meth:`InteractiveMixin.prepare_prompt` — turns the real input data into the
  JSON-safe, window-sized view the panel renders, plus optional heavy
  intermediate work carried forward as storage references (never in memory).
* ``run`` — inherited from the block's category; on the compute phase it reads
  the user's decision from ``config["interactive_response"]`` and produces the
  block's outputs.

A producing panel has one outbound path, the emission of code (ADR-054 spec 1
FR-012), and ADR-054 §3.6 says the meaning of an emission is settled by the
context it is mounted in. This module owns the interactive-block half of that:
:func:`settle_interactive_response` turns the snippet the host committed into
the decision dict ``run`` reads. The other half — appending an emission as a
notebook cell and queuing it, with the §3.6 statement whitelist that governs
*that* context — belongs to the explore session and is deliberately not here.

The registry binds the capability and the execution mode together when it scans
blocks: a block that declares one without the other, omits ``prepare_prompt``,
or omits a valid :class:`PanelManifest` is rejected at load time.

The two halves run in two worker subprocesses on either side of an engine-held
pause: the prompt phase builds the view and exits, the engine holds the pause
with nothing resident, then a fresh compute phase runs ``run`` with the decision
injected. This module only defines the contract; the two-phase orchestration
lives in the engine scheduler and runners.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from scistudio.core.meta._display_name import resolve_display_name

# ADR-054 spec 1, FR-001 / D-009: the manifest, the capability declaration and
# the API version constant live in the core layer, and this module imports them
# rather than defining its own. The block layer sits below the panel subsystem
# and below the API layer, all three read the same manifest, and no layer above
# core may be imported by the others — so a manifest defined here would force
# the panel subsystem to import upward, and the pressure to relieve that is what
# produced two manifest types and two version constants in the first place.
from scistudio.core.panels import PANEL_API_VERSION, PanelManifest
from scistudio.core.storage.ref import StorageReference
from scistudio.stability import provisional

if TYPE_CHECKING:
    from scistudio.blocks.base.config import BlockConfig

# Config keys the engine threads into the compute phase. The response key
# carries the user's decision and is recorded in lineage; the intermediate key
# carries engine-held storage references for reuse and is excluded from lineage.
INTERACTIVE_RESPONSE_KEY = "interactive_response"
"""Config key under which an interactive block's run reads the user's decision.

On the compute phase the engine places the value the user chose in the panel at
``config[INTERACTIVE_RESPONSE_KEY]``. This decision is recorded in the run's
lineage.
"""
INTERACTIVE_INTERMEDIATE_KEY = "interactive_intermediate"

# ADR-051 interaction memory: a block config may carry a remembered decision so
# future runs skip the dialog and compute directly. The record is
# ``{"enabled": bool, "decision": <interactive_response>, "signature": <input
# signature>}``; the frontend writes it on confirm (when the user opts in) and
# the engine reads it on dispatch. Stored in node config (frontend owns the
# workflow definition); the engine never writes it back.
INTERACTIVE_MEMORY_KEY = "interactive_memory"


@provisional(since="0.3.1")
@dataclass(frozen=True)
class InteractivePrompt:
    """What :meth:`InteractiveMixin.prepare_prompt` returns to drive the panel.

    Bundles the window-sized view the panel renders together with any heavy
    intermediate results the block wants to reuse afterwards, without putting those
    heavy results in memory or on the wire.

    Example:
        >>> prompt = InteractivePrompt(panel_payload={"items": ["a", "b"]})
    """

    panel_payload: dict[str, Any]
    """JSON-safe, window-sized view of the data the panel renders.

    Reducing the data to something a person can look at (a downsampled trace, a
    summary table, a list of selectable items) is the block's responsibility; the runtime
    rejects a payload that is not plain JSON.
    """

    intermediate: tuple[StorageReference, ...] = ()
    """Storage references to heavy intermediate work to reuse in the compute phase.

    Carried by the engine across the pause, never sent to the browser, and
    excluded from lineage. Leave empty when the compute phase rebuilds entirely
    from the inputs, config, and the user's decision.
    """


@provisional(since="0.3.1")
class InteractiveMixin:
    """Mix-in that makes a block interactive.

    Inherit this alongside a block category and declare ``execution_mode =
    ExecutionMode.INTERACTIVE`` to turn an ordinary block into one that pauses to
    ask the user a question. The registry rejects a block that declares one of
    these without the other. A subclass MUST set the :attr:`interactive_panel`
    class attribute and SHOULD override :meth:`prepare_prompt` (the default
    raises). The block's own ``run`` — inherited from its category — consumes the
    user's decision on the compute phase.

    Example:
        >>> from scistudio.blocks.base import (
        ...     ExecutionMode,
        ...     InteractiveMixin,
        ...     PanelManifest,
        ... )
        >>> class PickOne(InteractiveMixin):  # doctest: +SKIP
        ...     execution_mode = ExecutionMode.INTERACTIVE
        ...     interactive_panel = PanelManifest(panel_id="core.interactive.data_router")
        ...     def prepare_prompt(self, inputs, config):
        ...         return {"items": [str(i) for i in inputs]}
    """

    interactive_panel: ClassVar[PanelManifest]
    """The window this block opens. A subclass MUST set it to a :class:`PanelManifest`."""

    @provisional(since="0.3.1")
    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt | dict[str, Any]:
        """Turn the real input data into what the window should show.

        Runs in an isolated worker subprocess. Receives the block's full input
        collections (one interaction spans the whole input) and the resolved
        config, and returns what the panel needs.

        Args:
            inputs: The block's input collections, keyed by input-port name.
            config: The block's resolved configuration.

        Returns:
            An :class:`InteractivePrompt` carrying the JSON-safe
            ``panel_payload`` and any intermediate storage references. A bare
            ``dict`` is accepted as shorthand for a payload with no intermediate.

        Raises:
            NotImplementedError: If the subclass does not override this method.
        """
        raise NotImplementedError(
            f"{type(self).__name__} declares execution_mode=INTERACTIVE and "
            f"InteractiveMixin but does not implement prepare_prompt()."
        )

    @provisional(since="0.3.1")
    def remap_saved_decision(
        self,
        saved_decision: dict[str, Any],
        saved_signature: dict[str, list[str]],
        current_signature: dict[str, list[str]],
    ) -> dict[str, Any] | None:
        """Re-resolve a remembered decision against the current inputs.

        Interaction memory lets a block skip its dialog on a re-run by replaying
        the user's earlier decision. The engine calls this on dispatch with the
        decision the user saved, the input fingerprint captured when they saved
        it, and the fingerprint of the current inputs.

        The default policy reuses the saved decision only when the input
        fingerprint is unchanged (same items, same order per port) — safe for a
        plain re-run, and it never replays a stale decision. Override it to remap
        a decision by item identity so it survives reordering or partial input
        changes.

        Args:
            saved_decision: The decision (an ``interactive_response``) the user
                saved earlier.
            saved_signature: Input fingerprint captured when the decision was
                saved, mapping each port name to its ordered item labels.
            current_signature: Fingerprint of the current inputs, in the same
                shape.

        Returns:
            The ``interactive_response`` to apply automatically (skipping the
            pause and the panel), or ``None`` to fall back to opening the panel.
        """
        if saved_signature == current_signature:
            return saved_decision
        return None


@runtime_checkable
class SupportsInteraction(Protocol):
    """Structural protocol used to validate the interaction capability.

    A block satisfies it when it carries an :attr:`interactive_panel` manifest
    and a ``prepare_prompt`` method. The registry uses
    :class:`InteractiveMixin` inheritance for the hard biconditional check and
    this protocol for duck-typed validation of the required members (FR-002).

    Internal (ADR-052 §4.8): registry-validation protocol, not author surface.
    """

    interactive_panel: PanelManifest

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> Any: ...


def coerce_prompt(result: InteractivePrompt | dict[str, Any]) -> InteractivePrompt:
    """Normalize a ``prepare_prompt`` return to an :class:`InteractivePrompt`.

    A block may return a bare ``dict`` (the panel payload, no intermediate) or a
    full :class:`InteractivePrompt`. Used by the worker prompt phase so block
    authors are not forced to import the dataclass for the simple case.

    Internal (ADR-052 §4.8): worker prompt-phase normalizer, not author surface.
    """
    if isinstance(result, InteractivePrompt):
        return result
    if isinstance(result, dict):
        return InteractivePrompt(panel_payload=result)
    raise TypeError(
        "prepare_prompt must return an InteractivePrompt or a dict panel payload, "
        f"got {type(result).__name__} (ADR-051)."
    )


# ---------------------------------------------------------------------------
# ADR-054 spec 1 FR-012, second half: settling a produced value in the
# interactive-block context.
# ---------------------------------------------------------------------------

INTERACTIVE_EMISSION_KEY = "code"
"""The key a producing panel's emission arrives under on ``interactive_complete``.

FR-012 gives a producing panel exactly one outbound path — the emission of code
— so the host (``InteractivePanelHost``) commits the panel's most recent ``emit``
by sending ``{"code": "<the emitted snippet>"}``. This module turns that snippet
into the decision dict the block's ``run`` reads from
``config[INTERACTIVE_RESPONSE_KEY]``.

Internal (ADR-052 §4.8): wire key, not author surface.
"""

#: The filename a traceback from an emitted snippet carries. Not a real path:
#: it exists so a syntax error names something a reader recognises.
_EMISSION_FILENAME = "<panel emission>"


class InteractiveEmissionError(ValueError):
    """A producing panel's emission could not be settled into a decision (FR-012).

    Every refusal names the block and the panel, because those are the two
    things a person looking at a paused block can act on. The engine surfaces
    one of these exactly as it surfaces a rejected (non-JSON-safe) interactive
    response: the block goes to ``ERROR`` and the message reaches the reader.
    Clicking Confirm and getting nothing is the failure mode this class exists
    to prevent.

    Args:
        message: What went wrong, without the block/panel prefix.
        block_name: The block the panel was opened for.
        panel_id: The panel that emitted.
    """

    def __init__(self, message: str, *, block_name: str, panel_id: str) -> None:
        super().__init__(f"{block_name} (panel {panel_id!r}): {message}")
        self.block_name = block_name
        self.panel_id = panel_id
        self.reason = message


def _emission_namespace(
    record: list[dict[str, Any]],
    *,
    block_name: str,
    panel_id: str,
) -> Any:
    """Build the one object an emitted snippet may reach: ``scistudio``.

    Its only attribute is ``output``, which records the keyword arguments it was
    called with. Nothing else — no module, no host object, no block — is
    reachable through it.
    """

    def _output(*args: Any, **kwargs: Any) -> None:
        if args:
            raise InteractiveEmissionError(
                "emitted code called scistudio.output() with a positional argument; "
                "the decision is named keyword arguments only, "
                "for example scistudio.output(assignments=assignments)",
                block_name=block_name,
                panel_id=panel_id,
            )
        record.append(dict(kwargs))

    class _Scistudio:
        """The ``scistudio`` name inside a panel emission. One attribute only."""

        __slots__ = ()

        output = staticmethod(_output)

    return _Scistudio()


def _refuse_dunder_reach(tree: ast.AST, *, block_name: str, panel_id: str) -> None:
    """Refuse any identifier beginning with ``__`` anywhere in the emission.

    This is a restriction on the *namespace*, not on the statement forms. An
    emission runs with no builtins, and the documented way out of a
    no-builtins namespace is a dunder walk — ``().__class__.__bases__[0]
    .__subclasses__()`` and from there some class whose ``__init__.__globals__``
    still carries a live ``__builtins__``. Nothing a decision needs to say
    contains a dunder, so refusing the whole family closes that walk at the one
    point every emission passes, and does it before anything executes.

    It is deliberately NOT the ADR-054 §3.6 statement whitelist, which admits
    only rebinding assignments, imports and ``scistudio.output`` calls: that
    whitelist belongs where an emission is *queued* (the explore session), and
    the spec's ``scope.out`` keeps it out of this one. Statement forms are
    unrestricted here; reachable names are not.
    """
    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.keyword | ast.arg):
            name = node.arg
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            name = node.name
        elif isinstance(node, ast.alias):
            name = node.asname or node.name
        elif isinstance(node, ast.Global | ast.Nonlocal):
            name = next((each for each in node.names if each.startswith("__")), None)
        if name is not None and name.startswith("__"):
            raise InteractiveEmissionError(
                f"emitted code reaches {name!r}; a panel's decision runs in a namespace whose "
                "only name is scistudio, and names beginning with '__' are refused because they "
                "are how that namespace is escaped",
                block_name=block_name,
                panel_id=panel_id,
            )


def settle_panel_emission(code: str, *, block_name: str, panel_id: str) -> dict[str, Any]:
    """Run a producing panel's emitted code and return the decision it output.

    **Which half of FR-012 this is.** FR-012 gives a producing panel one
    outbound path, the emission of code, and says the meaning of what it emits
    is settled by the context it runs in — never by the panel loading
    machinery. ADR-054 §3.6 names two such contexts. In a session with a
    notebook open, the emission is appended as a cell and queued; that half is
    the explore session's and is out of this spec. This is the other half: an
    interactive block's pause, where the emission *is* the user's decision, and
    settling it means running it and taking what it handed back.

    **The namespace.** The snippet arrived over a WebSocket, so it executes with
    ``__builtins__`` set to an empty mapping and exactly one name bound:
    ``scistudio``, an object whose only attribute is ``output``. There is no
    ``open``, no ``__import__`` (so an ``import`` statement fails), no ``eval``,
    no ``getattr``, no module, and no host object. Identifiers beginning with
    ``__`` are refused before execution by :func:`_refuse_dunder_reach`.

    **What is not restricted.** Statement forms. The ADR-054 §3.6 whitelist that
    admits only rebinding assignments, imports and ``scistudio.output`` calls
    sits where an emission is queued, and the spec's ``scope.out`` keeps it out
    of here. Both built-in producing panels emit exactly two statements — an
    assignment to a plain name and one ``scistudio.output`` call — but this
    function admits any statement the namespace can execute.

    **What the namespace does not bound: time.** An emission that does not
    terminate — ``while True: pass`` — is not refused, and this runs on the
    scheduler's event loop, so it would wedge the whole engine rather than one
    block. Nothing here can interrupt it: a bound would need a worker thread or
    a subprocess, and how long to wait and what to do with the thread that
    outlives the wait are decisions this function is not the place to take. The
    exposure is the same one an installed block already has (a panel document is
    installed the way a block is), which is why it is recorded here rather than
    guessed at.

    Args:
        code: The snippet the panel emitted.
        block_name: The block whose pause this settles, for the diagnostic.
        panel_id: The panel that emitted, for the diagnostic.

    Returns:
        The keyword arguments of the snippet's single ``scistudio.output`` call,
        which the engine places at ``config[INTERACTIVE_RESPONSE_KEY]``. It is
        *not* checked for JSON-safety here: the engine applies the same
        ``json.dumps(..., allow_nan=False)`` gate it applies to every
        interactive response, and one gate is better than two.

    Raises:
        InteractiveEmissionError: If the snippet is empty, does not parse,
            reaches a refused name, raises while running, never calls
            ``scistudio.output``, or calls it more than once. Every message
            names the block and the panel.
    """
    if not isinstance(code, str) or not code.strip():
        raise InteractiveEmissionError(
            "the panel emitted no code, so there is no decision to settle",
            block_name=block_name,
            panel_id=panel_id,
        )

    try:
        tree = ast.parse(code, filename=_EMISSION_FILENAME, mode="exec")
    except SyntaxError as exc:
        raise InteractiveEmissionError(
            f"the emitted code does not parse as Python: {exc.msg} (line {exc.lineno})",
            block_name=block_name,
            panel_id=panel_id,
        ) from exc

    _refuse_dunder_reach(tree, block_name=block_name, panel_id=panel_id)

    record: list[dict[str, Any]] = []
    namespace: dict[str, Any] = {
        "__builtins__": {},
        "scistudio": _emission_namespace(record, block_name=block_name, panel_id=panel_id),
    }
    try:
        exec(compile(tree, filename=_EMISSION_FILENAME, mode="exec"), namespace)
    except InteractiveEmissionError:
        raise
    except BaseException as exc:  # every failure becomes one legible refusal
        raise InteractiveEmissionError(
            f"the emitted code raised while running: {type(exc).__name__}: {exc}",
            block_name=block_name,
            panel_id=panel_id,
        ) from exc

    if not record:
        raise InteractiveEmissionError(
            "the emitted code ran but never called scistudio.output(), so it handed back no "
            "decision; a producing panel commits by calling it once with the whole decision",
            block_name=block_name,
            panel_id=panel_id,
        )
    if len(record) > 1:
        raise InteractiveEmissionError(
            f"the emitted code called scistudio.output() {len(record)} times; exactly one call "
            "carries the decision, because the host commits one emission and the block reads one "
            "response",
            block_name=block_name,
            panel_id=panel_id,
        )
    return record[0]


def is_panel_emission(payload: Any) -> bool:
    """Return whether *payload* is a producing panel's emission rather than a decision.

    The two shapes that reach the boundary are told apart structurally: an
    emission is a mapping whose *only* key is ``code`` and whose value is a
    ``str``. Anything else — any other key, any extra key, a non-string value,
    a non-mapping — is a decision dict and passes through untouched, which is
    what keeps a programmatic driver, a test, and a decision remembered before
    this migration working exactly as they did.

    A decision that happened to be exactly ``{"code": "<some string>"}`` would be
    read as an emission. No block in the tree has such a decision (``DataRouter``
    reads ``assignments``, ``PairEditor`` reads ``reorder``), and the
    misclassification is loud rather than silent: the string would be run and,
    calling no ``scistudio.output``, would raise
    :class:`InteractiveEmissionError` naming the block and the panel.
    """
    return (
        isinstance(payload, dict)
        and set(payload) == {INTERACTIVE_EMISSION_KEY}
        and isinstance(payload[INTERACTIVE_EMISSION_KEY], str)
    )


def settle_interactive_response(payload: Any, *, block_name: str, panel_id: str) -> Any:
    """Turn what came back from the panel into the decision the block's ``run`` reads.

    The boundary the engine calls at the moment an ``interactive_complete``
    resolves a paused block, before the JSON-safety gate. A producing panel's
    emission (FR-012) is executed by :func:`settle_panel_emission`; anything
    else is already a decision and is returned unchanged.

    Args:
        payload: What the frontend sent, or what a remembered decision replayed.
        block_name: The block whose pause this settles, for the diagnostic.
        panel_id: The panel the block declared, for the diagnostic.

    Returns:
        The decision dict for ``config[INTERACTIVE_RESPONSE_KEY]``.

    Raises:
        InteractiveEmissionError: When *payload* is an emission that cannot be
            settled. The engine turns it into the block's error, exactly as it
            does a response that is not JSON-safe.
    """
    if not is_panel_emission(payload):
        return payload
    return settle_panel_emission(
        payload[INTERACTIVE_EMISSION_KEY],
        block_name=block_name,
        panel_id=panel_id,
    )


def interactive_item_label(item: Any, index: int) -> str:
    """Best-effort human label for one input item shown in an interactive panel.

    Interactive panels (DataRouter, PairEditor) list a block's input items for
    the user to route or reorder. A generic ``item_<index>`` is meaningless when
    the user is matching items by which file they came from, so this delegates
    to :func:`scistudio.core.meta._display_name.resolve_display_name` — the
    single canonical precedence authority shared with the panel/API path
    (#1812) — and supplies ``item_<index>`` as the last-resort fallback.
    """
    return resolve_display_name(item, fallback=f"item_{index}")


def interactive_input_signature(inputs: dict[str, Any]) -> dict[str, list[str]]:
    """A stable, JSON-safe identity fingerprint of an interactive block's inputs.

    Maps each input port to the ordered list of its items' labels (the source
    filename via :func:`interactive_item_label`). Two runs whose inputs carry
    the same files in the same order per port produce equal signatures — the
    basis for reusing a remembered decision and skipping the dialog (ADR-051
    interaction memory). Computed generically for every interactive block, so a
    package-provided block inherits the behaviour without extra code.
    """
    from scistudio.core.types.collection import Collection

    signature: dict[str, list[str]] = {}
    for port, value in inputs.items():
        if isinstance(value, Collection):
            signature[port] = [interactive_item_label(item, i) for i, item in enumerate(value)]
        else:
            signature[port] = [interactive_item_label(value, 0)]
    return signature


def load_interactive_memory(config: Any) -> dict[str, Any] | None:
    """Read an enabled remembered-decision record from a block config.

    Looks in ``config[INTERACTIVE_MEMORY_KEY]`` and
    ``config['params'][INTERACTIVE_MEMORY_KEY]`` (block configs carry user
    fields in either place). Returns the record dict
    (``{enabled, decision, signature}``) or ``None`` when memory is absent or
    disabled.
    """
    record: Any = None
    if isinstance(config, dict):
        record = config.get(INTERACTIVE_MEMORY_KEY)
        if record is None and isinstance(config.get("params"), dict):
            record = config["params"].get(INTERACTIVE_MEMORY_KEY)
    if not isinstance(record, dict) or not record.get("enabled"):
        return None
    return record


def serialise_storage_ref(ref: StorageReference) -> dict[str, Any]:
    """Serialize a :class:`StorageReference` to a JSON-safe dict (intermediate channel)."""
    return {
        "backend": ref.backend,
        "path": ref.path,
        "format": ref.format,
        "metadata": ref.metadata,
    }


def deserialise_storage_ref(data: dict[str, Any]) -> StorageReference:
    """Reconstruct a :class:`StorageReference` from its serialized dict."""
    return StorageReference(
        backend=data["backend"],
        path=data["path"],
        format=data.get("format"),
        metadata=data.get("metadata"),
    )


@provisional(since="0.3.1")
def load_intermediate(config: BlockConfig | dict[str, Any]) -> tuple[StorageReference, ...]:
    """Return the intermediate storage references the engine carried across the pause.

    Convenience for an interactive block's ``run`` (the compute phase) to read
    back the references its :meth:`InteractiveMixin.prepare_prompt` stored,
    without re-deriving the wire shape by hand.

    Args:
        config: The block's config — a :class:`BlockConfig` or a plain dict.

    Returns:
        The stored storage references as a tuple, empty when the block produced
        no intermediate.
    """
    raw: Any
    if isinstance(config, dict):
        raw = config.get(INTERACTIVE_INTERMEDIATE_KEY)
    else:
        raw = config.get(INTERACTIVE_INTERMEDIATE_KEY) if hasattr(config, "get") else None
    if not raw:
        return ()
    refs: list[StorageReference] = []
    for item in raw:
        if isinstance(item, StorageReference):
            refs.append(item)
        elif isinstance(item, dict):
            refs.append(deserialise_storage_ref(item))
    return tuple(refs)


# Public author surface (ADR-052 §4.8). All provisional. The kept symbols are
# re-exported from the ``scistudio.blocks.base`` root (the canonical path).
# Demoted to internal (deep-path importable, out of ``__all__``):
# ``SupportsInteraction``, ``coerce_prompt``, ``serialise_storage_ref``,
# ``deserialise_storage_ref``, ``INTERACTIVE_INTERMEDIATE_KEY``, and the FR-012
# emission-settling group (``INTERACTIVE_EMISSION_KEY``,
# ``InteractiveEmissionError``, ``is_panel_emission``,
# ``settle_panel_emission``, ``settle_interactive_response``) — engine-facing,
# called from ``scistudio.engine.scheduler._dispatch``.
__all__ = [
    "INTERACTIVE_RESPONSE_KEY",
    "PANEL_API_VERSION",
    "InteractiveMixin",
    "InteractivePrompt",
    "PanelManifest",
    "load_intermediate",
]
