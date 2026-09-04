"""Call a SciStudio block from a notebook cell (ADR-054 §5.5, FR-049 to FR-051).

A cell in an Explore session may call a block by identifier::

    peaks = blocks.run("imaging.find_peaks", img=img, sigma=2.0)

:class:`BlockCallAdapter` is what stands behind that line. It performs, in the
kernel process, the work the workflow runner performs *around* a block —
resolve it from the registry, split the call's keyword arguments into ports and
config, wrap native objects into typed data objects, validate the ports, run
the block, validate and unwrap the outputs, and translate the block's
exceptions — and it hands the cell a native object back.

**Why in-process.** Routing the call through the real runner would spawn a
subprocess per call and produce a storage reference to load back, which is the
wrong latency for a surface whose whole purpose is rapid iteration (ADR-054
§5.5). The cost is that a block which crashes the interpreter takes the kernel
with it; the kernel is restartable and the notebook replays.

**The interactive case (FR-050).** An interactive block called from a cell
cannot open a panel through the notebook's display protocol, because the panel
is SciStudio's own surface. The adapter instead builds the block's prompt, hands
a :class:`PendingInteraction` to the session's :class:`InteractionChannel`, and
**blocks the calling thread on a** :class:`threading.Event` until the session
service submits a value, cancels, or the cell is interrupted. It does not poll:
:attr:`PendingInteraction.wait_count` is ``1`` after a call that blocked once,
and any polling implementation would leave it higher. A notebook containing
such a call is refused at packaging (FR-039), because run anywhere but inside
SciStudio the cell waits for a panel that will never appear.

**Lineage (FR-051).** The adapter *reports* what a
:class:`~scistudio.core.lineage.record.BlockExecutionRecord` and its
``block_io`` edges need — as :class:`BlockCallLineage` — and writes nothing.
The lineage store is the session lineage module's business, and it receives
these facts either as the ``lineage`` field of a :class:`BlockCallResult` or
through the ``on_call`` callback every call fires.

**Deferred imports.** Every ``scistudio.blocks`` and ``scistudio.core`` import
in this module is made lazily, inside :func:`_runtime` or the function that
needs it. Two reasons, both real. The adapter is constructed inside a kernel,
where importing the whole block registry (and numpy, and pyarrow) at module
import time is latency a person watching a cell run would feel. And the
architecture layer test's ``explore`` entry currently forbids the subsystem
those two packages outright; FR-008 and FR-060 name only ``api``, ``ai``, and
``engine``, and narrowing that list is T-001's task, so the deferred form is
what stays correct on both sides of that change.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping, Sequence

    from scistudio.blocks.registry import BlockRegistry


BLOCK_CALL_API_VERSION = "1"
"""Version of the contract between the adapter and a session's interaction channel.

Bumped when :class:`InteractionRequest`, :class:`PendingInteraction`, or the
:class:`InteractionChannel` protocol change incompatibly, so a session service
built against an older shape can refuse rather than misbehave.
"""

#: Default axis names by dimension count, used when a native array has to be
#: wrapped into an :class:`~scistudio.core.types.array.Array` and the caller
#: gave no axes. The vocabulary is the one ``Array`` documents (``t``, ``z``,
#: ``c``, ``y``, ``x``); a value with more dimensions than this table covers is
#: refused rather than guessed at.
_DEFAULT_AXES: dict[int, tuple[str, ...]] = {
    1: ("x",),
    2: ("y", "x"),
    3: ("z", "y", "x"),
    4: ("c", "z", "y", "x"),
    5: ("t", "c", "z", "y", "x"),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class BlockCallError(Exception):
    """Base class for every failure of a block call made from a cell.

    Catching this one type in a notebook catches every way the adapter can
    refuse or fail a call, without also catching the arbitrary exceptions a
    block's own code may raise (those arrive wrapped in
    :class:`BlockCallFailedError`).
    """


@provisional(since="0.3.4")
class BlockNotFoundError(BlockCallError, LookupError):
    """No block is registered under the identifier the cell named.

    The message always names the identifier that was asked for, and lists the
    closest registered names when there are any, because a mistyped block id is
    the single most common way this call fails.
    """


@provisional(since="0.3.4")
class BlockCallValidationError(BlockCallError, ValueError):
    """The call's arguments or the block's outputs do not satisfy the port contract.

    Raised for a missing required input, a value that cannot be wrapped into
    the type its port accepts, a failed port constraint, and a block that did
    not produce a required output port. The message names the port.
    """


@provisional(since="0.3.4")
class BlockCallFailedError(BlockCallError):
    """The block ran and raised.

    The original exception is kept as ``__cause__``, so a notebook traceback
    still shows where inside the block the failure happened; this wrapper only
    adds which block was being called.
    """


@provisional(since="0.3.4")
class BlockCallCancelledError(BlockCallError):
    """An interactive call ended without a value.

    Raised when the session service cancels the pending interaction (the person
    closed the panel, or the session went away) and when a bounded wait passed
    to :meth:`PendingInteraction.await_value` expires. A cell interrupted by the
    user raises :class:`KeyboardInterrupt` instead — see
    :meth:`BlockCallAdapter.call_detailed`.
    """


@provisional(since="0.3.4")
class InteractionUnavailableError(BlockCallError):
    """An interactive block was called with no interaction channel to open its panel on.

    This is the diagnosis for the failure mode ADR-054 §5.5 describes: a
    notebook that calls an interactive block only completes inside SciStudio,
    because the panel is rendered by SciStudio's own surface. Run elsewhere the
    cell would otherwise wait for a window that never appears, so the adapter
    refuses immediately and says why.
    """


# ---------------------------------------------------------------------------
# What a call reports for lineage (FR-051)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BlockCallEdge:
    """One port-to-object edge of a block call — the facts a ``block_io`` row needs.

    Each item of each input and output port is one edge, matching how the
    workflow lineage store records a run: a Collection port contributes one row
    per item with an incrementing :attr:`position`.
    """

    direction: str
    """``"input"`` or ``"output"``."""

    port_name: str
    """Name of the port the object flowed through."""

    object_id: str
    """The data object's identity, from its framework metadata."""

    position: int
    """Index within the port's Collection; ``0`` for a single-item port."""

    type_name: str
    """The data object's concrete type name, e.g. ``"Array"``."""

    data_object: Any
    """The data object itself, so the recorder can build its ``data_objects`` row.

    Carried by reference and never serialised here; the adapter does not write
    lineage (that is the session lineage module's task) and cannot know what
    the recorder needs off the object.
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BlockCallLineage:
    """Everything a block call made from a cell reports for lineage (FR-051).

    These are exactly the fields of a
    :class:`~scistudio.core.lineage.record.BlockExecutionRecord` that the caller
    cannot derive for itself, plus the ``block_io`` edges, plus the session the
    call belongs to. The adapter returns them; the session's lineage module
    assigns the ``block_execution_id`` and writes the rows.
    """

    session_id: str | None
    """The explore session the call was made in — the record's foreign key.

    ``None`` when the adapter was built without one, which happens in a test
    and in any caller that is not a session.
    """

    block_identifier: str
    """The identifier the cell passed, verbatim, before registry resolution."""

    block_type: str
    """The block's stable type name as the registry resolved it."""

    block_version: str
    """The version string of the block that ran."""

    block_config_resolved: dict[str, Any]
    """The configuration the adapter actually handed the block.

    For an interactive call this includes the user's decision under
    ``interactive_response``, exactly as a workflow run records it.
    """

    started_at: str
    """ISO-8601 UTC timestamp taken immediately before the block was dispatched."""

    finished_at: str
    """ISO-8601 UTC timestamp taken when the call reached its terminal state."""

    duration_ms: int
    """Wall-clock duration of the call in milliseconds."""

    termination: str
    """``"completed"``, ``"error"``, or ``"cancelled"`` — the record's ``termination``."""

    termination_detail: str = ""
    """Error message or cancellation reason; empty when the call completed."""

    edges: tuple[BlockCallEdge, ...] = ()
    """The input and output edges, in port order, inputs first."""

    interactive: bool = False
    """Whether the call opened a panel and waited for a decision."""

    interactive_response: Any | None = None
    """The decision the person took in the panel, or ``None`` for a plain call."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class BlockCallResult:
    """The full result of one block call: native values, typed values, and lineage.

    :meth:`BlockCallAdapter.call` returns only :attr:`value`, because that is
    what the notebook line ``peaks = blocks.run(...)`` wants.
    :meth:`BlockCallAdapter.call_detailed` returns this, for a caller that also
    needs the typed objects or the lineage facts.
    """

    outputs: dict[str, Any]
    """Unwrapped native values, keyed by output-port name."""

    collections: dict[str, Any] = field(default_factory=dict)
    """The typed :class:`~scistudio.core.types.collection.Collection` per output port.

    The wrapping the block actually produced, before unwrapping — what the same
    block would have handed a downstream node in a workflow.
    """

    lineage: BlockCallLineage | None = None
    """What this call reports for lineage (FR-051), or ``None`` for a failed call."""

    @property
    def value(self) -> Any:
        """The single output's native value, or the whole mapping when there are several.

        A block with exactly one output port is by far the common case in a
        notebook, and ``peaks = blocks.run(...)`` should bind the peaks rather
        than a one-key dict. A block with several outputs binds the mapping, so
        the cell can unpack the ports it wants by name.

        Returns:
            The one output value, or :attr:`outputs` when the block declared a
            number of outputs other than one.
        """
        if len(self.outputs) == 1:
            return next(iter(self.outputs.values()))
        return self.outputs


# ---------------------------------------------------------------------------
# The interactive-block call (FR-050)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class InteractionRequest:
    """What the session service needs in order to open an interactive block's panel.

    Built by the adapter from the block's own prompt phase and handed to the
    :class:`InteractionChannel` inside a :class:`PendingInteraction`. It is the
    same material the engine sends the frontend when it pauses an interactive
    node, so the Explore tab can render the panel with the code that already
    exists.
    """

    block_identifier: str
    """The identifier the cell passed."""

    block_type: str
    """The block's resolved type name."""

    panel: dict[str, Any]
    """The block's :class:`~scistudio.blocks.base.interactive.PanelManifest`, in wire form."""

    panel_payload: dict[str, Any]
    """The JSON-safe, window-sized view the panel renders, from ``prepare_prompt``."""

    input_signature: dict[str, list[str]]
    """Identity fingerprint of the call's inputs, per port, for interaction memory."""

    session_id: str | None = None
    """The explore session the call was made in, when the adapter knows it."""

    api_version: str = BLOCK_CALL_API_VERSION
    """The contract version this request was built against."""


@provisional(since="0.3.4")
class PendingInteraction:
    """One interactive call, blocked in the kernel, waiting for a decision.

    The adapter creates one, hands it to the session's
    :class:`InteractionChannel`, and then blocks the calling thread in
    :meth:`await_value`. The session service opens the panel, and later — from
    whatever thread its transport runs on — calls :meth:`submit` with the
    person's decision or :meth:`cancel` if the panel was dismissed. Both are
    safe to call from another thread, and both are idempotent-by-first-caller:
    the first to settle the interaction wins and later calls are ignored, so a
    cancel racing an arriving value cannot corrupt the result.

    The wait is a single blocking :meth:`threading.Event.wait`, not a poll —
    which is what FR-050 asks for, and what :attr:`wait_count` exists to make
    checkable.
    """

    def __init__(self, request: InteractionRequest) -> None:
        """Create a pending interaction for *request*.

        Args:
            request: What the session service needs to open the panel.
        """
        self.request = request
        """The panel-open request the session service acts on."""
        self.wait_count = 0
        """How many times a caller entered the blocking wait.

        FR-050 asks the cell to *block* until a value arrives, not to poll for
        one. A call that blocked once leaves this at ``1``; any implementation
        that woke up to re-check would leave it higher. It is here so that the
        difference is assertable, which a wall-clock measurement alone cannot
        establish.
        """
        self._settled = threading.Event()
        self._lock = threading.Lock()
        self._response: Any = None
        self._cancel_reason: str | None = None

    @property
    def settled(self) -> bool:
        """Whether a decision or a cancellation has arrived.

        Returns:
            ``True`` once :meth:`submit` or :meth:`cancel` has been called.
        """
        return self._settled.is_set()

    @provisional(since="0.3.4")
    def submit(self, response: Any) -> bool:
        """Deliver the person's decision and release the blocked cell.

        Args:
            response: The ``interactive_response`` the panel produced. It is
                handed to the block's ``run`` under
                :data:`~scistudio.blocks.base.interactive.INTERACTIVE_RESPONSE_KEY`,
                exactly as the engine hands it to a paused workflow node.

        Returns:
            ``True`` when this call settled the interaction, ``False`` when it
            had already been settled by an earlier submit or cancel.
        """
        with self._lock:
            if self._settled.is_set():
                return False
            self._response = response
        self._settled.set()
        return True

    @provisional(since="0.3.4")
    def cancel(self, reason: str = "the interaction was cancelled") -> bool:
        """Abandon the interaction and release the blocked cell with an error.

        Args:
            reason: Why the interaction ended; carried into the
                :class:`BlockCallCancelledError` the cell sees and into the
                call's ``termination_detail``.

        Returns:
            ``True`` when this call settled the interaction, ``False`` when it
            had already been settled.
        """
        with self._lock:
            if self._settled.is_set():
                return False
            self._cancel_reason = reason
        self._settled.set()
        return True

    @provisional(since="0.3.4")
    def await_value(self, timeout: float | None = None) -> Any:
        """Block the calling thread until a decision arrives, and return it.

        This is the whole of FR-050's "blocks the cell until the value
        arrives": one :meth:`threading.Event.wait`, which parks the thread in
        the OS rather than spinning. A :class:`KeyboardInterrupt` — which is
        how the kernel interrupts a running cell — breaks the wait and
        propagates, leaving the interaction unsettled for the caller to cancel.

        Args:
            timeout: Optional bound in seconds. ``None``, the notebook's case,
                waits indefinitely. A caller that must not block forever passes
                a number and gets :class:`BlockCallCancelledError` when it
                elapses.

        Returns:
            The ``interactive_response`` passed to :meth:`submit`.

        Raises:
            BlockCallCancelledError: If :meth:`cancel` was called, or *timeout*
                elapsed first.
        """
        self.wait_count += 1
        arrived = self._settled.wait(timeout)
        if not arrived:
            self.cancel(f"no decision arrived within {timeout} seconds")
            raise BlockCallCancelledError(
                f"Interactive block '{self.request.block_identifier}' was not answered within {timeout} seconds."
            )
        if self._cancel_reason is not None:
            raise BlockCallCancelledError(f"Interactive block '{self.request.block_identifier}': {self._cancel_reason}")
        return self._response


@provisional(since="0.3.4")
@runtime_checkable
class InteractionChannel(Protocol):
    """How the adapter reaches the session service to open and close a panel.

    The session service implements this; the adapter only ever calls it. Both
    methods **must return promptly** — the adapter does its waiting on the
    :class:`PendingInteraction` it hands over, and a channel that blocked in
    :meth:`open` would block the cell before the panel had been announced.
    """

    def open(self, pending: PendingInteraction) -> None:
        """Announce the panel described by ``pending.request`` and return at once.

        The service is expected to settle *pending* afterwards, from another thread,
        with :meth:`PendingInteraction.submit` or
        :meth:`PendingInteraction.cancel`.

        Args:
            pending: The interaction to open a panel for and settle afterwards.
        """
        ...

    def close(self, pending: PendingInteraction) -> None:
        """Take the panel down, however the interaction ended.

        Called exactly once per :meth:`open`, including when the cell was
        interrupted or the block subsequently failed, so the Explore tab never
        keeps a panel for a call that is no longer waiting.

        Args:
            pending: The interaction whose panel should be closed.
        """
        ...


# ---------------------------------------------------------------------------
# Lazily imported machinery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Runtime:
    """The block and data-object machinery the adapter needs, imported once."""

    # Typed ``Any`` rather than ``type``: these are used as the second argument
    # to ``isinstance``/``issubclass``, and a checker that sees only ``type``
    # narrows the first argument to bare ``object`` and then loses every
    # attribute the branch exists to reach.
    Block: Any
    BlockConfig: Any
    Collection: Any
    DataObject: Any
    Array: Any
    DataFrame: Any
    Series: Any
    Text: Any
    ExecutionMode: Any
    InteractiveMixin: Any
    coerce_prompt: Any
    interactive_input_signature: Any
    response_key: str
    intermediate_key: str


@lru_cache(maxsize=1)
def _runtime() -> _Runtime:
    """Import the block and data-object machinery, once per process.

    Deferred rather than written at module level for the two reasons the module
    docstring gives: kernel import latency, and the architecture layer rule the
    explore subsystem currently carries. Cached, so the cost is paid on the
    first call and never again.

    Returns:
        The imported symbols, bundled.
    """
    from scistudio.blocks.base.block import Block
    from scistudio.blocks.base.config import BlockConfig
    from scistudio.blocks.base.interactive import (
        INTERACTIVE_INTERMEDIATE_KEY,
        INTERACTIVE_RESPONSE_KEY,
        InteractiveMixin,
        coerce_prompt,
        interactive_input_signature,
    )
    from scistudio.blocks.base.state import ExecutionMode
    from scistudio.core.types import Array, Collection, DataFrame, DataObject, Series, Text

    return _Runtime(
        Block=Block,
        BlockConfig=BlockConfig,
        Collection=Collection,
        DataObject=DataObject,
        Array=Array,
        DataFrame=DataFrame,
        Series=Series,
        Text=Text,
        ExecutionMode=ExecutionMode,
        InteractiveMixin=InteractiveMixin,
        coerce_prompt=coerce_prompt,
        interactive_input_signature=interactive_input_signature,
        response_key=INTERACTIVE_RESPONSE_KEY,
        intermediate_key=INTERACTIVE_INTERMEDIATE_KEY,
    )


def _scanned_registry() -> BlockRegistry:
    """Build and scan a fresh block registry.

    The fallback for an adapter constructed without one. A session always
    passes the registry it already maintains; this path exists for a bare
    ``blocks.run(...)`` in a kernel that has none yet, and it pays a full scan.

    Returns:
        A scanned :class:`~scistudio.blocks.registry.BlockRegistry`.
    """
    from scistudio.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    registry.scan()
    return registry


# ---------------------------------------------------------------------------
# Typed wrapping and unwrapping (FR-049)
# ---------------------------------------------------------------------------


def _native_family(value: Any) -> str:
    """Classify a native value into the data-object family that can hold it.

    Only the families the core types cover are recognised, and only through
    modules the calling process has already imported — an object cannot be a
    ``numpy.ndarray`` if numpy was never imported, so the check costs nothing
    in a kernel that has not touched it.

    Args:
        value: A native Python object.

    Returns:
        One of ``"array"``, ``"frame"``, ``"series"``, ``"text"``, or ``""``
        when no core family fits.
    """
    if isinstance(value, str):
        return "text"
    pandas = sys.modules.get("pandas")
    if pandas is not None:
        if isinstance(value, pandas.DataFrame):
            return "frame"
        if isinstance(value, pandas.Series):
            return "series"
    numpy = sys.modules.get("numpy")
    if numpy is not None and isinstance(value, numpy.ndarray):
        return "array"
    pyarrow = sys.modules.get("pyarrow")
    if pyarrow is not None and isinstance(value, pyarrow.Table):
        return "frame"
    return ""


def _family_of_type(target: type) -> str:
    """Return the native family a data-object class can be constructed from.

    Args:
        target: A :class:`~scistudio.core.types.base.DataObject` subclass.

    Returns:
        The family string :func:`_native_family` produces for values that class
        accepts, or ``""`` for a class with no native construction path.
    """
    rt = _runtime()
    if issubclass(target, rt.Array):
        return "array"
    if issubclass(target, rt.DataFrame):
        return "frame"
    if issubclass(target, rt.Series):
        return "series"
    if issubclass(target, rt.Text):
        return "text"
    return ""


def _construct(target: type, value: Any, family: str, port_name: str) -> Any:
    """Build a data object of *target* around the native *value*.

    Construction is "from data" in the ADR-054 §5.5 sense: the native object is
    handed to the type's own constructor as its transient in-memory data, so
    nothing is written to storage on the way into a block. Shape information is
    filled in from the value where the type declares a slot for it.

    Args:
        target: The data-object class to build.
        value: The native value to wrap.
        family: The family :func:`_native_family` reported for *value*.
        port_name: The port being wrapped, named in any error.

    Returns:
        A new instance of *target* carrying *value*.

    Raises:
        BlockCallValidationError: If *target* refuses the value — most often a
            subclass whose declared axes the value does not satisfy.
    """
    rt = _runtime()
    try:
        if family == "text":
            return target(content=value)
        if family == "array":
            shape = tuple(getattr(value, "shape", ()) or ())
            axes = _DEFAULT_AXES.get(len(shape))
            if axes is None:
                raise BlockCallValidationError(
                    f"Port '{port_name}': cannot name the axes of a {len(shape)}-dimensional array. "
                    f"Pass an {rt.Array.__name__} with explicit axes instead."
                )
            return target(axes=list(axes), shape=shape, dtype=getattr(value, "dtype", None), data=value)
        if family == "frame":
            # ``column_names`` first: on a pyarrow table ``columns`` holds the
            # arrays, not their names. A pandas ``Index`` is also not safely
            # truthy, so it is converted rather than tested.
            names = getattr(value, "column_names", None)
            if names is None:
                names = getattr(value, "columns", None)
            columns = [str(name) for name in names] if names is not None else None
            row_count = len(value) if hasattr(value, "__len__") else None
            return target(columns=columns, row_count=row_count, data=value)
        if family == "series":
            return target(
                value_name=getattr(value, "name", None),
                length=len(value) if hasattr(value, "__len__") else None,
                data=value,
            )
    except BlockCallValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise BlockCallValidationError(
            f"Port '{port_name}': cannot wrap a {type(value).__name__} into {target.__name__} ({exc})."
        ) from exc
    raise BlockCallValidationError(
        f"Port '{port_name}': no way to wrap a {type(value).__name__} into {target.__name__}. "
        f"Build the data object in the cell and pass that instead."
    )


def _wrap_one(value: Any, port: Any, port_name: str) -> Any:
    """Wrap one call argument into the Collection the block's port expects.

    The layers, in order: a Collection passes through; a data object becomes a
    length-one Collection; a list of data objects becomes a Collection of them;
    a native object is constructed into the type the port accepts and then
    wrapped. This is what FR-049 means by "wraps native objects into typed data
    objects on the way in", and it is the same transport contract the engine
    boundary enforces for a workflow (ADR-020 §3).

    Args:
        value: The value the cell passed for this port.
        port: The block's effective :class:`~scistudio.blocks.base.ports.InputPort`,
            or ``None`` when the block declares no port of that name.
        port_name: The port's name, used in errors.

    Returns:
        A Collection carrying the wrapped value.

    Raises:
        BlockCallValidationError: If the value cannot be wrapped for this port.
    """
    rt = _runtime()
    if isinstance(value, rt.Collection):
        return value
    if isinstance(value, rt.DataObject):
        return rt.Collection([value], item_type=type(value))
    if isinstance(value, (list, tuple)) and value and all(isinstance(item, rt.DataObject) for item in value):
        return rt.Collection(list(value), item_type=type(value[0]))

    family = _native_family(value)
    if not family:
        raise BlockCallValidationError(
            f"Port '{port_name}': a {type(value).__name__} is not a data object and has no "
            f"SciStudio type to wrap it into. Pass a data object, or a numpy array, "
            f"pandas frame or series, or a string."
        )

    accepted = list(getattr(port, "accepted_types", []) or []) if port is not None else []
    candidates = [target for target in accepted if _family_of_type(target) == family]
    if accepted and not candidates:
        names = [target.__name__ for target in accepted]
        raise BlockCallValidationError(
            f"Port '{port_name}': got a {type(value).__name__}, which cannot become any of {names}."
        )
    if not candidates:
        # An untyped port ("accepts any data object"): fall back to the core
        # type for the value's family.
        rt_by_family = {"array": rt.Array, "frame": rt.DataFrame, "series": rt.Series, "text": rt.Text}
        candidates = [rt_by_family[family]]
    return rt.Collection([_construct(candidates[0], value, family, port_name)], item_type=candidates[0])


def _to_native(obj: Any) -> Any:
    """Return the in-memory form of one data object, or the object itself.

    Unwrapping is the mirror of wrapping: the cell gets back the kind of thing
    it passed in. An object with neither a storage reference nor transient data
    has no in-memory form at all — a metadata-only result — and is returned
    unchanged so the cell still receives its metadata rather than an exception.

    Args:
        obj: The data object to read.

    Returns:
        The object's in-memory data, or the object when it holds none.
    """
    rt = _runtime()
    if isinstance(obj, rt.Text) and obj.content is not None:
        return obj.content
    try:
        return obj.to_memory()
    except (ValueError, NotImplementedError):
        # ADR-031 Addendum 2 declares ``_transient_data`` as the slot a
        # constructor's ``data=`` argument fills; ``Array.to_memory`` reads it
        # but the other core types only read storage, so an unflushed result
        # from an in-process run is found here or nowhere.
        transient = getattr(obj, "_transient_data", None)
        return transient if transient is not None else obj


@provisional(since="0.3.4")
def native_of(data_object: Any) -> Any:
    """The in-memory value a cell is handed for *data_object*.

    The same unwrapping :meth:`BlockCallAdapter.call` performs on its way out,
    exposed because FR-055 has to answer a question only this mapping can:
    ``blocks.run(...)`` hands the cell a **native** value, so the name a
    notebook later passes to ``scistudio.output`` is a ``str`` or an ``ndarray``
    with no object identity on it, while the object retention decides over is
    the ``DataObject`` the call produced. Unwrapping the edge's object the way
    the call did is what lets the two be recognised as the same thing.

    Args:
        data_object: The object a call's output edge carries.

    Returns:
        Its in-memory form, or the object itself when it has none.
    """
    return _to_native(data_object)


def _unwrap_one(value: Any) -> Any:
    """Unwrap one output port's Collection into what the cell should bind.

    Args:
        value: The value the block produced on this port, after normalisation.

    Returns:
        The single item's native form for a length-one Collection, a list of
        native forms for a longer one, and the value untouched when it is not a
        Collection at all.
    """
    rt = _runtime()
    if isinstance(value, rt.Collection):
        items = list(value)
        if len(items) == 1:
            return _to_native(items[0])
        return [_to_native(item) for item in items]
    if isinstance(value, rt.DataObject):
        return _to_native(value)
    return value


def _normalise_outputs(outputs: dict[str, Any], output_ports: Sequence[Any]) -> dict[str, Any]:
    """Wrap every declared output port's value into a Collection.

    The same transport normalisation the engine's worker performs at the block
    boundary (ADR-020 §3, #1811): a bare data object becomes a length-one
    Collection and a bare list of data objects becomes a Collection of them, on
    every declared port, unconditionally. Reimplemented here rather than
    imported because the explore subsystem must not import the engine (FR-008).

    Args:
        outputs: What the block's ``run`` returned.
        output_ports: The block's effective output ports.

    Returns:
        A new mapping with the declared ports normalised; undeclared keys pass
        through untouched.
    """
    rt = _runtime()
    declared = {port.name for port in output_ports}
    normalised: dict[str, Any] = {}
    for name, value in outputs.items():
        if name not in declared or isinstance(value, rt.Collection):
            normalised[name] = value
        elif isinstance(value, rt.DataObject):
            normalised[name] = rt.Collection([value], item_type=type(value))
        elif isinstance(value, list) and value and all(isinstance(item, rt.DataObject) for item in value):
            normalised[name] = rt.Collection(value, item_type=type(value[0]))
        else:
            normalised[name] = value
    return normalised


def _validate_outputs(outputs: Mapping[str, Any], output_ports: Sequence[Any], identifier: str) -> None:
    """Refuse a block that did not produce one of its required output ports.

    Args:
        outputs: The normalised outputs.
        output_ports: The block's effective output ports.
        identifier: The identifier the cell called, named in the error.

    Raises:
        BlockCallValidationError: On the first required port that is missing or
            ``None``.
    """
    for port in output_ports:
        if not getattr(port, "required", True):
            continue
        if outputs.get(port.name) is None:
            raise BlockCallValidationError(f"Block '{identifier}' did not produce required output port '{port.name}'.")


def _edges_for(direction: str, values: Mapping[str, Any]) -> list[BlockCallEdge]:
    """Build the ``block_io`` edge facts for one side of a call.

    Args:
        direction: ``"input"`` or ``"output"``.
        values: Port name to Collection (or bare value) mapping.

    Returns:
        One edge per item of each Collection port, in port order.
    """
    rt = _runtime()
    edges: list[BlockCallEdge] = []
    for port_name, value in values.items():
        items = list(value) if isinstance(value, rt.Collection) else [value]
        for position, item in enumerate(items):
            if not isinstance(item, rt.DataObject):
                continue
            edges.append(
                BlockCallEdge(
                    direction=direction,
                    port_name=port_name,
                    object_id=item.framework.object_id,
                    position=position,
                    type_name=type(item).__name__,
                    data_object=item,
                )
            )
    return edges


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string, matching lineage rows."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class BlockCallAdapter:
    """Runs a SciStudio block in-process on behalf of a notebook cell (FR-049).

    One adapter belongs to one session and is injected into its kernel by the
    bridge; the ``blocks.run(...)`` name a cell calls is bound to
    :meth:`call`.

    Example:
        >>> adapter = BlockCallAdapter(registry=registry)  # doctest: +SKIP
        >>> peaks = adapter.call("find_peaks", table=df, threshold=100)  # doctest: +SKIP
    """

    def __init__(
        self,
        *,
        registry: BlockRegistry | None = None,
        interaction: InteractionChannel | None = None,
        session_id: str | None = None,
        on_call: Callable[[BlockCallLineage], None] | None = None,
    ) -> None:
        """Create an adapter.

        Args:
            registry: The block registry to resolve identifiers against. When
                omitted, a fresh registry is built and scanned on first use —
                correct, but a session should pass the one it already has.
            interaction: The session's channel for opening an interactive
                block's panel. ``None`` makes every interactive call raise
                :class:`InteractionUnavailableError`, which is the right
                behaviour outside SciStudio (ADR-054 §5.5).
            session_id: The explore session these calls belong to, carried into
                every :class:`BlockCallLineage` as its foreign key (FR-051).
            on_call: Called with the lineage facts of every call that reached a
                terminal state, successful or not. This is how the session's
                lineage module receives what it must record; the adapter itself
                writes nothing.
        """
        self._registry = registry
        self._interaction = interaction
        self._session_id = session_id
        self._on_call = on_call

    @property
    @provisional(since="0.3.4")
    def registry(self) -> BlockRegistry:
        """The block registry this adapter resolves identifiers against.

        Builds and scans one on first access when none was injected.

        Returns:
            The registry.
        """
        if self._registry is None:
            self._registry = _scanned_registry()
        return self._registry

    @provisional(since="0.3.4")
    def call(self, identifier: str, /, **kwargs: Any) -> Any:
        """Run a block and return its result as a native object.

        This is the notebook-facing form. Keyword arguments are split by the
        block's own declared port names: a keyword matching an input port is an
        input, and everything else is configuration. So for a block with an
        ``img`` port and a ``sigma`` parameter::

            peaks = blocks.run("imaging.find_peaks", img=img, sigma=2.0)

        A variadic block declares its ports per instance rather than on the
        class, so nothing can be split by name until its config is known; the
        adapter therefore re-splits once the block is built, and a caller who
        wants no guessing at all can use :meth:`call_detailed`.

        Args:
            identifier: The block's display name or stable type name.
            **kwargs: The block's inputs and configuration, mixed.

        Returns:
            The single output port's native value, or a mapping of port name to
            native value when the block declares a number of outputs other than
            one.

        Raises:
            BlockNotFoundError: If no block is registered under *identifier*.
            BlockCallValidationError: If an input or output violates the port
                contract.
            BlockCallFailedError: If the block itself raised.
            BlockCallCancelledError: If an interactive call was cancelled.
            InteractionUnavailableError: If the block is interactive and the
                adapter has no interaction channel.
        """
        return self.call_detailed(identifier, **kwargs).value

    @provisional(since="0.3.4")
    def call_detailed(
        self,
        identifier: str,
        /,
        *,
        inputs: Mapping[str, Any] | None = None,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> BlockCallResult:
        """Run a block and return its native values, its typed values, and its lineage.

        The explicit form of :meth:`call`. Anything passed in *inputs* is an
        input port and anything in *config* is configuration, with no splitting
        by name; remaining keyword arguments are split exactly as :meth:`call`
        splits them and merged in.

        A cell interrupted while an interactive call is waiting raises
        :class:`KeyboardInterrupt`, unchanged, because that is what a notebook's
        interrupt means and what the person expects to see. The panel is closed
        and the call's lineage is reported as ``cancelled`` before it
        propagates.

        Args:
            identifier: The block's display name or stable type name.
            inputs: Values for input ports, by port name.
            config: Configuration values for the block.
            **kwargs: Further arguments, split by port name.

        Returns:
            The :class:`BlockCallResult` for this call.

        Raises:
            BlockNotFoundError: If no block is registered under *identifier*.
            BlockCallValidationError: If an input or output violates the port
                contract.
            BlockCallFailedError: If the block itself raised.
            BlockCallCancelledError: If an interactive call was cancelled.
            InteractionUnavailableError: If the block is interactive and the
                adapter has no interaction channel.
        """
        rt = _runtime()
        spec = self._resolve(identifier)
        declared_inputs = {port.name for port in (spec.input_ports or [])}
        call_inputs, call_config = self._split(kwargs, declared_inputs)
        call_inputs.update(inputs or {})
        call_config.update(config or {})

        block = self.registry.instantiate(spec.name, dict(call_config))
        effective_inputs = block.get_effective_input_ports()
        effective_names = {port.name for port in effective_inputs}
        if effective_names != declared_inputs:
            # A variadic block's real ports come from its config, so the first
            # split could not see them. Re-split now that the block exists, and
            # rebuild it so its config no longer carries the input values.
            call_inputs, call_config = self._split(kwargs, effective_names)
            call_inputs.update(inputs or {})
            call_config.update(config or {})
            block = self.registry.instantiate(spec.name, dict(call_config))
            effective_inputs = block.get_effective_input_ports()

        ports_by_name = {port.name: port for port in effective_inputs}
        wrapped = {name: _wrap_one(value, ports_by_name.get(name), name) for name, value in call_inputs.items()}

        # ``call_config`` is what lineage records; ``run_config`` is what the
        # block is handed. They differ for an interactive call by exactly the
        # intermediate storage references, which the engine also carries across
        # its pause and also keeps out of lineage.
        run_config = dict(call_config)

        started_at = _now()
        started_perf = time.perf_counter()
        pending: PendingInteraction | None = None
        response: Any = None
        interactive = self._is_interactive(block)

        def finish(termination: str, detail: str, outputs: Mapping[str, Any]) -> BlockCallLineage:
            lineage = BlockCallLineage(
                session_id=self._session_id,
                block_identifier=identifier,
                block_type=spec.type_name or spec.name,
                block_version=spec.version,
                block_config_resolved=dict(call_config),
                started_at=started_at,
                finished_at=_now(),
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
                termination=termination,
                termination_detail=detail,
                edges=tuple(_edges_for("input", wrapped) + _edges_for("output", outputs)),
                interactive=interactive,
                interactive_response=response,
            )
            if self._on_call is not None:
                self._on_call(lineage)
            return lineage

        try:
            block.validate(wrapped)
        except BlockCallValidationError:
            finish("error", "input validation failed", {})
            raise
        except ValueError as exc:
            finish("error", str(exc), {})
            raise BlockCallValidationError(f"Block '{identifier}': {exc}") from exc

        if interactive:
            try:
                pending, intermediate = self._open_panel(identifier, spec, block, wrapped)
            except BlockCallError as exc:
                # A refusal at the prompt phase — no channel, or a payload the
                # panel could never render — is as terminal as a failed run and
                # is reported the same way.
                finish("error", str(exc), {})
                raise
            try:
                response = pending.await_value()
            except BaseException as exc:
                # KeyboardInterrupt is the kernel interrupting the cell, and it
                # is re-raised unchanged: the notebook's own interrupt
                # semantics are what the person expects to see. Everything else
                # here is a BlockCallCancelledError. Either way the panel comes
                # down and the call is recorded as cancelled.
                pending.cancel("the cell was interrupted")
                self._close_panel(pending)
                finish("cancelled", str(exc) or type(exc).__name__, {})
                raise
            self._close_panel(pending)
            call_config = dict(call_config)
            call_config[rt.response_key] = response
            run_config = dict(call_config)
            if intermediate:
                run_config[rt.intermediate_key] = list(intermediate)
            block.config = rt.BlockConfig(**run_config)

        block_config = rt.BlockConfig(**run_config)
        try:
            raw_outputs = block.run(wrapped, block_config)
        except Exception as exc:
            finish("error", f"{type(exc).__name__}: {exc}", {})
            raise BlockCallFailedError(f"Block '{identifier}' failed: {exc}") from exc

        if not isinstance(raw_outputs, dict):
            finish("error", "run() did not return a mapping of output ports", {})
            raise BlockCallValidationError(
                f"Block '{identifier}' returned {type(raw_outputs).__name__} from run(); "
                f"a mapping of output-port name to value is required."
            )

        output_ports = block.get_effective_output_ports()
        outputs = _normalise_outputs(raw_outputs, output_ports)
        try:
            _validate_outputs(outputs, output_ports, identifier)
        except BlockCallValidationError as exc:
            finish("error", str(exc), outputs)
            raise

        lineage = finish("completed", "", outputs)
        return BlockCallResult(
            outputs={name: _unwrap_one(value) for name, value in outputs.items()},
            collections=dict(outputs),
            lineage=lineage,
        )

    # -- internals ---------------------------------------------------------

    def _resolve(self, identifier: str) -> Any:
        """Look up *identifier* in the registry, or fail naming it.

        Args:
            identifier: The block's display name or stable type name.

        Returns:
            The matching :class:`~scistudio.blocks.registry.BlockSpec`.

        Raises:
            BlockNotFoundError: If nothing is registered under *identifier*.
        """
        spec = self.registry.get_spec(identifier)
        if spec is not None:
            return spec
        known = sorted(self.registry.all_specs())
        lowered = identifier.lower()
        near = [name for name in known if lowered in name.lower() or name.lower() in lowered][:5]
        hint = f" Did you mean: {', '.join(near)}?" if near else ""
        raise BlockNotFoundError(f"No block is registered as '{identifier}'.{hint}")

    @staticmethod
    def _split(kwargs: Mapping[str, Any], port_names: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Split call keyword arguments into inputs and configuration.

        Args:
            kwargs: The keyword arguments the cell passed.
            port_names: Names of the block's input ports.

        Returns:
            The inputs and the configuration, as two new dicts.
        """
        call_inputs = {name: value for name, value in kwargs.items() if name in port_names}
        call_config = {name: value for name, value in kwargs.items() if name not in port_names}
        return call_inputs, call_config

    @staticmethod
    def _is_interactive(block: Any) -> bool:
        """Whether *block* pauses to ask the user a question.

        The registry already refuses a block that declares
        :class:`~scistudio.blocks.base.interactive.InteractiveMixin` without
        ``execution_mode = INTERACTIVE`` or the reverse, so either signal alone
        is enough; both are read so that a hand-built test double behaves the
        same way a scanned block does.

        Args:
            block: The instantiated block.

        Returns:
            ``True`` when the block is interactive.
        """
        rt = _runtime()
        mode = getattr(type(block), "execution_mode", None)
        if mode is rt.ExecutionMode.INTERACTIVE or getattr(mode, "value", None) == "interactive":
            return True
        return isinstance(block, rt.InteractiveMixin)

    def _open_panel(
        self,
        identifier: str,
        spec: Any,
        block: Any,
        wrapped: Mapping[str, Any],
    ) -> tuple[PendingInteraction, tuple[Any, ...]]:
        """Run the block's prompt phase and hand the panel to the session (FR-050).

        Args:
            identifier: The identifier the cell called.
            spec: The block's registry descriptor.
            block: The instantiated block.
            wrapped: The call's wrapped inputs.

        Returns:
            The pending interaction to block on, and the storage references the
            prompt phase produced for the compute phase to reuse.

        Raises:
            InteractionUnavailableError: If the adapter has no channel.
            BlockCallFailedError: If ``prepare_prompt`` raised or returned a
                payload that is not JSON.
        """
        rt = _runtime()
        if self._interaction is None:
            raise InteractionUnavailableError(
                f"Block '{identifier}' is interactive and opens a SciStudio panel, but this "
                f"notebook is not running in an Explore session. A cell that calls an "
                f"interactive block only completes inside SciStudio (ADR-054 §5.5)."
            )

        manifest = block.get_panel_manifest()
        try:
            prompt = rt.coerce_prompt(block.prepare_prompt(dict(wrapped), block.config))
        except Exception as exc:
            raise BlockCallFailedError(f"Block '{identifier}' failed preparing its panel: {exc}") from exc

        payload = prompt.panel_payload
        if not isinstance(payload, dict):
            raise BlockCallFailedError(
                f"Block '{identifier}' produced a panel payload of type "
                f"{type(payload).__name__}; a JSON object is required."
            )
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise BlockCallFailedError(
                f"Block '{identifier}' produced a panel payload that is not JSON: {exc}"
            ) from exc

        request = InteractionRequest(
            block_identifier=identifier,
            block_type=spec.type_name or spec.name,
            panel=manifest.to_dict() if manifest is not None else {},
            panel_payload=payload,
            input_signature=rt.interactive_input_signature(dict(wrapped)),
            session_id=self._session_id,
        )
        pending = PendingInteraction(request)
        self._interaction.open(pending)
        return pending, tuple(prompt.intermediate)

    def _close_panel(self, pending: PendingInteraction) -> None:
        """Take a panel down, swallowing a channel that fails on the way.

        A session that has already gone away must not turn a completed call
        into a failed one, so a raising ``close`` is ignored.

        Args:
            pending: The interaction whose panel to close.
        """
        if self._interaction is None:
            return
        with contextlib.suppress(Exception):
            self._interaction.close(pending)


__all__ = [
    "BLOCK_CALL_API_VERSION",
    "BlockCallAdapter",
    "BlockCallCancelledError",
    "BlockCallEdge",
    "BlockCallError",
    "BlockCallFailedError",
    "BlockCallLineage",
    "BlockCallResult",
    "BlockCallValidationError",
    "BlockNotFoundError",
    "InteractionChannel",
    "InteractionRequest",
    "InteractionUnavailableError",
    "PendingInteraction",
]
