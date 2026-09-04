"""Tests for the block-call adapter (ADR-054 §5.5, T-012, FR-049 to FR-051).

Three properties carry the task and are asserted here directly rather than
inferred:

* **In-process, with typed wrapping (FR-049).** The block runs in the calling
  process — asserted on the process id the block itself observes, not on
  latency — and what reaches its ``run`` is the typed
  :class:`~scistudio.core.types.collection.Collection` its port declares, with
  the right ``item_type``, built from whatever native object the cell passed.
* **An interactive call blocks (FR-050).** The cell does not return before the
  decision arrives, and while it waits it neither spins nor wakes up to look:
  ``wait_count`` stays at ``1`` and the waiting thread burns no measurable CPU.
  Either assertion alone is satisfiable by an implementation that fails the
  other, which is why both are made.
* **The call reports lineage without writing it (FR-051).** Every fact a
  ``BlockExecutionRecord`` and its ``block_io`` edges need comes back to the
  caller; the adapter touches no store.

The blocks below are declared in this module and registered by hand, because
the registry resolves a spec to ``module_path`` + ``class_name`` at
instantiation time and this module is importable under exactly that name.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, ClassVar

import numpy as np
import pytest

from scistudio.blocks.base import (
    INTERACTIVE_RESPONSE_KEY,
    Block,
    BlockConfig,
    ExecutionMode,
    InputPort,
    InteractiveMixin,
    InteractivePrompt,
    OutputPort,
    PanelManifest,
    load_intermediate,
)
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types import Array, Collection, DataFrame, DataObject, StorageReference, Text
from scistudio.explore.block_call import (
    BlockCallAdapter,
    BlockCallCancelledError,
    BlockCallFailedError,
    BlockCallLineage,
    BlockCallValidationError,
    BlockNotFoundError,
    InteractionRequest,
    InteractionUnavailableError,
    PendingInteraction,
)

# What each block observed on its last run, so a test can assert on the shape
# that actually crossed the boundary rather than only on the return value.
OBSERVED: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Blocks under test
# ---------------------------------------------------------------------------


class ArrayDouble(Block):
    """Doubles an array, recording the process and the exact inputs it received."""

    name = "ArrayDouble"
    version = "2.1.0"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="img", accepted_types=[Array])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="doubled", accepted_types=[Array])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the input array multiplied by ``factor``."""
        OBSERVED["pid"] = os.getpid()
        OBSERVED["inputs"] = inputs
        OBSERVED["config"] = config
        item = inputs["img"][0]
        factor = config.get("factor", 2)
        return {"doubled": Array(axes=list(item.axes), data=item.to_memory() * factor)}


class PassThrough(Block):
    """Accepts anything on an untyped port and hands it straight back."""

    name = "PassThrough"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="value", accepted_types=[])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the incoming value on ``out``."""
        OBSERVED["inputs"] = inputs
        return {"out": inputs["value"]}


class BareOutput(Block):
    """Returns a bare data object, as a block written without ``pack`` does."""

    name = "BareOutput"
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[Text])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return a bare :class:`Text` rather than a Collection."""
        return {"out": Text(content=config.get("content", "hello"))}


class TwoOutputs(Block):
    """Declares two output ports, so the mapping form of a result is exercised."""

    name = "TwoOutputs"
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="left", accepted_types=[Text]),
        OutputPort(name="right", accepted_types=[Text]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return one value on each port."""
        return {"left": Text(content="L"), "right": Text(content="R")}


class DropsOutput(Block):
    """Declares a required output port and fails to produce it."""

    name = "DropsOutput"
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="required", accepted_types=[Text])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return nothing at all."""
        return {}


class Exploding(Block):
    """Raises from ``run``."""

    name = "Exploding"
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Raise a ``RuntimeError``."""
        raise RuntimeError("the detector is on fire")


class Decide(InteractiveMixin, Block):
    """An interactive block: shows two options and returns the chosen one."""

    name = "Decide"
    version = "0.9.0"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="core.interactive.data_router")
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="table", accepted_types=[])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="picked", accepted_types=[Text])]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the window-sized view of the choices."""
        OBSERVED["prompt_inputs"] = inputs
        return {"options": ["a", "b"]}

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the decision the panel produced."""
        response = config.get(INTERACTIVE_RESPONSE_KEY)
        OBSERVED.setdefault("runs", []).append(response)
        return {"picked": Text(content=str(response["choice"]))}


class CarriesIntermediate(InteractiveMixin, Block):
    """An interactive block whose prompt phase produces heavy work for its run to reuse."""

    name = "CarriesIntermediate"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="core.interactive.data_router")
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[Text])]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Return a payload plus one storage reference to carry forward."""
        return InteractivePrompt(
            panel_payload={"options": []},
            intermediate=(StorageReference(backend="zarr", path="scratch/partial.zarr"),),
        )

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Record the references the adapter carried across, and the decision."""
        OBSERVED["intermediate"] = load_intermediate(config)
        return {"out": Text(content=str(config.get(INTERACTIVE_RESPONSE_KEY)))}


class BadPanel(InteractiveMixin, Block):
    """An interactive block whose panel payload is not JSON."""

    name = "BadPanel"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="core.interactive.data_router")
    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[])]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return a payload holding an object json cannot encode."""
        return {"handle": object()}

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Never reached."""
        return {"out": Text(content="")}


_BLOCKS: tuple[type[Block], ...] = (
    ArrayDouble,
    PassThrough,
    BareOutput,
    TwoOutputs,
    DropsOutput,
    Exploding,
    Decide,
    CarriesIntermediate,
    BadPanel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_observations() -> None:
    """Empty the cross-test observation dict before each test."""
    OBSERVED.clear()


@pytest.fixture
def registry() -> BlockRegistry:
    """A registry holding only this module's blocks.

    Registered by hand rather than scanned: a scan would pull in every block in
    the repository and make the assertions here depend on what is installed.
    """
    reg = BlockRegistry()
    for cls in _BLOCKS:
        spec = BlockSpec(
            name=cls.name,
            type_name=cls.name.lower(),
            version=cls.version,
            module_path=__name__,
            class_name=cls.__name__,
            base_category="process",
            input_ports=list(cls.input_ports),
            output_ports=list(cls.output_ports),
            execution_mode=cls.execution_mode.value,
        )
        reg._registry[spec.name] = spec
        reg._aliases[spec.type_name] = spec.name
    return reg


class RecordingChannel:
    """A stand-in session service: records panel opens and closes, settles on demand."""

    def __init__(self) -> None:
        self.opened: list[PendingInteraction] = []
        self.closed: list[PendingInteraction] = []
        self._announced = threading.Event()

    def open(self, pending: PendingInteraction) -> None:
        """Record the panel open and return at once, as the protocol requires."""
        self.opened.append(pending)
        self._announced.set()

    def close(self, pending: PendingInteraction) -> None:
        """Record the panel close."""
        self.closed.append(pending)

    def await_open(self, timeout: float = 5.0) -> PendingInteraction:
        """Block until the adapter announces a panel, and return it."""
        assert self._announced.wait(timeout), "the adapter never opened a panel"
        return self.opened[-1]


def _call_in_thread(
    adapter: BlockCallAdapter,
    identifier: str,
    **kwargs: Any,
) -> tuple[threading.Thread, list[Any], list[BaseException], dict[str, float]]:
    """Run ``adapter.call_detailed`` on its own thread, capturing outcome and CPU time.

    Returns the thread (already started), the list the result lands in, the
    list an exception lands in, and a dict that receives the ``thread_time``
    the call actually burned on that thread.
    """
    results: list[Any] = []
    errors: list[BaseException] = []
    cpu: dict[str, float] = {}

    def target() -> None:
        started = time.thread_time()
        try:
            results.append(adapter.call_detailed(identifier, **kwargs))
        except BaseException as exc:
            errors.append(exc)
        finally:
            cpu["burned"] = time.thread_time() - started

    thread = threading.Thread(target=target, name="block-call")
    thread.start()
    return thread, results, errors, cpu


# ---------------------------------------------------------------------------
# FR-049 — the block runs in-process, with typed wrapping
# ---------------------------------------------------------------------------


def test_the_block_runs_in_the_calling_process(registry: BlockRegistry) -> None:
    """FR-049: the call executes in-kernel, not through the workflow runner.

    Asserted on the process id the block observes from inside its own ``run``.
    A runner-backed call would report a subprocess's id here.
    """
    adapter = BlockCallAdapter(registry=registry)
    adapter.call("ArrayDouble", img=np.ones((2, 3)))

    assert OBSERVED["pid"] == os.getpid()


def test_a_native_array_argument_arrives_as_the_ports_typed_collection(registry: BlockRegistry) -> None:
    """FR-049: a native argument is wrapped into the type its port accepts.

    The assertion is on the *type* that crossed the boundary — a Collection
    whose ``item_type`` is the port's declared ``Array``, carrying an ``Array``
    with named axes and the value's shape — not merely on the block having
    produced an answer.
    """
    adapter = BlockCallAdapter(registry=registry)
    adapter.call("ArrayDouble", img=np.ones((2, 3), dtype="float32"))

    received = OBSERVED["inputs"]["img"]
    assert isinstance(received, Collection)
    assert received.item_type is Array
    assert len(received) == 1

    item = received[0]
    assert isinstance(item, Array)
    assert item.axes == ["y", "x"]
    assert item.shape == (2, 3)
    np.testing.assert_array_equal(item.to_memory(), np.ones((2, 3), dtype="float32"))


def test_a_native_string_argument_becomes_a_text_object(registry: BlockRegistry) -> None:
    """FR-049: wrapping covers the whole core family, not only arrays."""
    adapter = BlockCallAdapter(registry=registry)
    adapter.call("PassThrough", value="a caption")

    received = OBSERVED["inputs"]["value"]
    assert isinstance(received, Collection)
    assert received.item_type is Text
    assert received[0].content == "a caption"


def test_a_data_object_argument_is_wrapped_into_a_length_one_collection(registry: BlockRegistry) -> None:
    """FR-049: the ADR-020 §3 transport contract holds on the way in.

    Every value crossing a block boundary is a Collection; a single object is a
    length-one Collection.
    """
    adapter = BlockCallAdapter(registry=registry)
    original = Array(axes=["y", "x"], data=np.zeros((2, 2)))
    adapter.call("ArrayDouble", img=original)

    received = OBSERVED["inputs"]["img"]
    assert isinstance(received, Collection)
    assert received.item_type is Array
    assert received[0] is original


def test_a_collection_argument_passes_through_untouched(registry: BlockRegistry) -> None:
    """FR-049: wrapping is idempotent — an already-typed argument is not re-wrapped."""
    adapter = BlockCallAdapter(registry=registry)
    batch = Collection([Array(axes=["y", "x"], data=np.zeros((2, 2)))], item_type=Array)
    adapter.call("ArrayDouble", img=batch)

    assert OBSERVED["inputs"]["img"] is batch


def test_the_result_is_unwrapped_to_a_native_object(registry: BlockRegistry) -> None:
    """FR-049: unwrapping on the way out is the mirror of wrapping on the way in.

    The cell that passed a numpy array gets a numpy array back, not a
    Collection and not a data object.
    """
    adapter = BlockCallAdapter(registry=registry)
    result = adapter.call("ArrayDouble", img=np.ones((2, 3)), factor=3)

    assert isinstance(result, np.ndarray)
    np.testing.assert_array_equal(result, np.full((2, 3), 3.0))


def test_the_typed_wrapping_is_still_available_beside_the_native_value(registry: BlockRegistry) -> None:
    """FR-049: a caller that wants what a downstream node would have received can have it."""
    adapter = BlockCallAdapter(registry=registry)
    detailed = adapter.call_detailed("ArrayDouble", img=np.ones((2, 3)))

    wrapped = detailed.collections["doubled"]
    assert isinstance(wrapped, Collection)
    assert wrapped.item_type is Array
    assert isinstance(detailed.outputs["doubled"], np.ndarray)


def test_a_bare_data_object_output_is_normalised_into_a_collection(registry: BlockRegistry) -> None:
    """FR-049: the output side of the transport contract is enforced too.

    A block that returns a bare data object — which block authors do — must
    still leave the boundary as a Collection, exactly as the engine's worker
    normalises it.
    """
    adapter = BlockCallAdapter(registry=registry)
    detailed = adapter.call_detailed("BareOutput", content="ok")

    assert isinstance(detailed.collections["out"], Collection)
    assert detailed.collections["out"].item_type is Text
    assert detailed.value == "ok"


def test_keyword_arguments_split_into_ports_and_configuration(registry: BlockRegistry) -> None:
    """FR-049: ``blocks.run(id, img=…, sigma=…)`` routes each keyword by port name."""
    adapter = BlockCallAdapter(registry=registry)
    adapter.call("ArrayDouble", img=np.ones((2, 2)), factor=5)

    assert set(OBSERVED["inputs"]) == {"img"}
    assert OBSERVED["config"].get("factor") == 5
    assert OBSERVED["config"].get("img") is None


def test_a_block_with_several_outputs_binds_a_mapping(registry: BlockRegistry) -> None:
    """FR-049: one output binds the value; more than one binds a mapping by port."""
    adapter = BlockCallAdapter(registry=registry)
    value = adapter.call("TwoOutputs")

    assert value == {"left": "L", "right": "R"}


def test_the_type_name_resolves_as_well_as_the_display_name(registry: BlockRegistry) -> None:
    """FR-049: the identifier is resolved through the registry, either name."""
    adapter = BlockCallAdapter(registry=registry)

    assert adapter.call("bareoutput", content="via type name") == "via type name"


# ---------------------------------------------------------------------------
# FR-049 — refusals
# ---------------------------------------------------------------------------


def test_calling_a_block_that_does_not_exist_names_the_block(registry: BlockRegistry) -> None:
    """A mistyped identifier must say which identifier failed."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockNotFoundError) as excinfo:
        adapter.call("imaging.find_peaks")

    assert "imaging.find_peaks" in str(excinfo.value)


def test_an_unknown_block_suggests_the_near_misses(registry: BlockRegistry) -> None:
    """A near-miss identifier gets the registered names it nearly matched."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockNotFoundError) as excinfo:
        adapter.call("ArrayDoubler")

    assert "ArrayDouble" in str(excinfo.value)


def test_a_value_with_no_scistudio_type_names_the_port(registry: BlockRegistry) -> None:
    """A value that is neither a data object nor a wrappable native is refused."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockCallValidationError) as excinfo:
        adapter.call("PassThrough", value=object())

    assert "'value'" in str(excinfo.value)


def test_a_native_value_the_port_cannot_accept_names_the_accepted_types(
    registry: BlockRegistry,
) -> None:
    """A string cannot become an ``Array``, and the refusal says so."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockCallValidationError) as excinfo:
        adapter.call("ArrayDouble", img="not an image")

    message = str(excinfo.value)
    assert "'img'" in message
    assert "Array" in message


def test_a_missing_required_input_is_refused_naming_the_port(registry: BlockRegistry) -> None:
    """FR-049: port validation runs before the block does."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockCallValidationError) as excinfo:
        adapter.call("ArrayDouble", factor=2)

    assert "'img'" in str(excinfo.value)
    assert "pid" not in OBSERVED


def test_a_dropped_required_output_is_refused(registry: BlockRegistry) -> None:
    """FR-049: the output-port contract is enforced at the producing boundary."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockCallValidationError) as excinfo:
        adapter.call("DropsOutput")

    assert "'required'" in str(excinfo.value)


def test_a_block_that_raises_is_translated_and_keeps_its_cause(registry: BlockRegistry) -> None:
    """FR-049: block exceptions are translated, not swallowed."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(BlockCallFailedError) as excinfo:
        adapter.call("Exploding")

    assert "Exploding" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "the detector is on fire" in str(excinfo.value.__cause__)


# ---------------------------------------------------------------------------
# FR-050 — the interactive call blocks
# ---------------------------------------------------------------------------


def test_an_interactive_call_does_not_return_before_the_value_arrives(
    registry: BlockRegistry,
) -> None:
    """FR-050: the cell blocks until the decision arrives.

    The two facts that make this "blocked" rather than "eventually returned":
    once the panel is open the call has neither produced a result nor reached
    the block's ``run``, and it only does both after the decision is submitted.
    """
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)
    thread, results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    pending = channel.await_open()
    # Give the call every chance to finish early if it were not really blocked.
    time.sleep(0.2)
    assert results == [], "the call returned before any decision was submitted"
    assert "runs" not in OBSERVED, "the block ran before the decision arrived"

    assert pending.submit({"choice": "b"}) is True
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert errors == []
    assert OBSERVED["runs"] == [{"choice": "b"}]
    assert results[0].value == "b"


@pytest.mark.serial
@pytest.mark.skipif(
    not hasattr(time, "thread_time"),
    reason="per-thread CPU accounting is unavailable on this platform",
)
def test_an_interactive_call_blocks_rather_than_busy_waiting(registry: BlockRegistry) -> None:
    """FR-050: the wait parks the thread; it neither spins nor polls.

    Two assertions, because each covers what the other misses. The CPU
    measurement rules out a tight spin — a loop over ``settled`` for the same
    interval would burn roughly the whole of it — but it cannot see a poll that
    sleeps between looks, which is just as wrong and just as invisible to a
    wall-clock test. ``wait_count`` rules that second one out: the adapter
    enters the blocking wait exactly once, and any implementation that woke up
    to re-check would leave it higher.
    """
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)
    thread, results, errors, cpu = _call_in_thread(adapter, "Decide", table="rows")

    pending = channel.await_open()
    blocked_for = 0.4
    time.sleep(blocked_for)
    assert results == []

    pending.submit({"choice": "a"})
    thread.join(timeout=10)
    assert errors == []

    assert pending.wait_count == 1, (
        f"the adapter entered the wait {pending.wait_count} times; FR-050 asks it to block once"
    )
    assert cpu["burned"] < 0.1, (
        f"the waiting thread burned {cpu['burned']:.3f}s of CPU while blocked for "
        f"{blocked_for}s, which is a spin rather than a wait"
    )


def test_the_panel_request_carries_what_the_session_needs_to_open_it(
    registry: BlockRegistry,
) -> None:
    """FR-050: the panel opens through the session service with the block's own prompt."""
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel, session_id="sess-7")
    thread, results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    pending = channel.await_open()
    request = pending.request
    assert request.block_identifier == "Decide"
    assert request.block_type == "decide"
    assert request.session_id == "sess-7"
    assert request.panel["panel_id"] == "core.interactive.data_router"
    assert request.panel_payload == {"options": ["a", "b"]}
    assert list(request.input_signature) == ["table"]

    pending.submit({"choice": "a"})
    thread.join(timeout=10)
    assert errors == []
    assert results


def test_the_decision_reaches_the_block_under_the_engines_own_key(
    registry: BlockRegistry,
) -> None:
    """FR-050: the compute half reads the decision exactly where a workflow run puts it."""
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)
    thread, results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    channel.await_open().submit({"choice": "a"})
    thread.join(timeout=10)

    assert errors == []
    assert results[0].lineage is not None
    assert results[0].lineage.block_config_resolved[INTERACTIVE_RESPONSE_KEY] == {"choice": "a"}


def test_the_panel_is_closed_when_the_call_completes(registry: BlockRegistry) -> None:
    """FR-050: the Explore tab never keeps a panel for a call that is no longer waiting."""
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)
    thread, results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    pending = channel.await_open()
    pending.submit({"choice": "a"})
    thread.join(timeout=10)

    assert errors == []
    assert results
    assert channel.closed == [pending]


def test_a_cancelled_interaction_raises_and_closes_the_panel(registry: BlockRegistry) -> None:
    """FR-050: dismissing the panel ends the cell with a cancellation, not a hang."""
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)
    thread, results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    pending = channel.await_open()
    pending.cancel("the panel was closed")
    thread.join(timeout=10)

    assert results == []
    assert isinstance(errors[0], BlockCallCancelledError)
    assert "the panel was closed" in str(errors[0])
    assert channel.closed == [pending]
    assert "runs" not in OBSERVED


def test_an_interactive_block_without_a_channel_is_refused_with_a_diagnosis(
    registry: BlockRegistry,
) -> None:
    """FR-050 / ADR-054 §5.5: outside SciStudio the panel never appears, so refuse at once."""
    adapter = BlockCallAdapter(registry=registry)

    with pytest.raises(InteractionUnavailableError) as excinfo:
        adapter.call("Decide", table="rows")

    message = str(excinfo.value)
    assert "Decide" in message
    assert "Explore session" in message


def test_the_prompt_phases_intermediate_reaches_the_run_but_not_the_lineage(
    registry: BlockRegistry,
) -> None:
    """FR-050: the two halves of an interactive block still meet, in-process.

    The engine carries an interactive block's heavy intermediate work across
    its pause under a config key its ``run`` reads back, and deliberately keeps
    that key out of lineage. There is no pause to cross in a kernel, but the
    block is the same block, so both halves of that arrangement hold: the
    references arrive at ``run``, and the recorded config carries the decision
    without them.
    """
    recorded: list[BlockCallLineage] = []
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel, on_call=recorded.append)
    thread, results, errors, _ = _call_in_thread(adapter, "CarriesIntermediate")

    channel.await_open().submit({"choice": "a"})
    thread.join(timeout=10)

    assert errors == []
    assert results
    carried = OBSERVED["intermediate"]
    assert [ref.path for ref in carried] == ["scratch/partial.zarr"]

    config = recorded[0].block_config_resolved
    assert config[INTERACTIVE_RESPONSE_KEY] == {"choice": "a"}
    assert "interactive_intermediate" not in config


def test_a_panel_payload_that_is_not_json_is_refused(registry: BlockRegistry) -> None:
    """FR-050: the payload crosses to a browser, so it must be JSON before anything blocks."""
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel)

    with pytest.raises(BlockCallFailedError) as excinfo:
        adapter.call("BadPanel")

    assert "not JSON" in str(excinfo.value)
    assert channel.opened == []


def _bare_pending() -> PendingInteraction:
    """A pending interaction with a minimal request, for testing the primitive alone."""
    return PendingInteraction(
        InteractionRequest(
            block_identifier="Decide",
            block_type="decide",
            panel={},
            panel_payload={},
            input_signature={},
        )
    )


def test_the_first_settle_wins() -> None:
    """A cancel racing an arriving value cannot corrupt the result."""
    pending = _bare_pending()

    assert pending.submit({"choice": "a"}) is True
    assert pending.cancel("too late") is False
    assert pending.await_value() == {"choice": "a"}


def test_a_bounded_wait_gives_up_and_says_so() -> None:
    """``await_value`` accepts a bound for a caller that must not block forever."""
    pending = _bare_pending()

    with pytest.raises(BlockCallCancelledError) as excinfo:
        pending.await_value(timeout=0.05)

    assert "Decide" in str(excinfo.value)
    assert pending.settled is True


def test_an_interrupted_cell_reraises_the_interrupt_and_reports_a_cancelled_call(
    registry: BlockRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-050: "or the cell is interrupted" — the notebook's own interrupt semantics survive.

    The kernel interrupts a cell by raising :class:`KeyboardInterrupt` in the
    thread running it, which breaks the blocking wait. There is no portable way
    to deliver a real interrupt to another thread, so the wait itself is
    replaced; everything the adapter does around it — take the panel down,
    report the call as cancelled, and let the interrupt through unchanged
    rather than converting it into a library error — is the behaviour under
    test and is exercised for real.
    """

    def interrupted(self: PendingInteraction, timeout: float | None = None) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(PendingInteraction, "await_value", interrupted)

    recorded: list[BlockCallLineage] = []
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel, on_call=recorded.append)

    with pytest.raises(KeyboardInterrupt):
        adapter.call("Decide", table="rows")

    assert channel.closed == channel.opened
    assert channel.opened != []
    assert recorded[0].termination == "cancelled"
    assert "runs" not in OBSERVED


# ---------------------------------------------------------------------------
# FR-051 — what a call reports for lineage
# ---------------------------------------------------------------------------


def test_a_call_reports_the_facts_a_block_execution_record_needs(
    registry: BlockRegistry,
) -> None:
    """FR-051: the record's fields come back to the caller, keyed to the session."""
    recorded: list[BlockCallLineage] = []
    adapter = BlockCallAdapter(registry=registry, session_id="sess-1", on_call=recorded.append)
    detailed = adapter.call_detailed("ArrayDouble", img=np.ones((2, 2)), factor=4)

    lineage = detailed.lineage
    assert lineage is not None
    assert recorded == [lineage], "on_call must receive exactly the lineage the caller gets"
    assert lineage.session_id == "sess-1"
    assert lineage.block_identifier == "ArrayDouble"
    assert lineage.block_type == "arraydouble"
    assert lineage.block_version == "2.1.0"
    assert lineage.block_config_resolved == {"factor": 4}
    assert lineage.termination == "completed"
    assert lineage.termination_detail == ""
    assert lineage.duration_ms >= 0
    assert lineage.started_at <= lineage.finished_at
    assert lineage.interactive is False


def test_the_lineage_edges_cover_every_item_of_every_port(registry: BlockRegistry) -> None:
    """FR-051: inputs and outputs are ``block_io`` edges, one row per Collection item."""
    adapter = BlockCallAdapter(registry=registry)
    items = [Array(axes=["x"], data=np.zeros(3)), Array(axes=["x"], data=np.ones(3))]
    detailed = adapter.call_detailed("PassThrough", value=Collection(items, item_type=Array))

    assert detailed.lineage is not None
    inputs = [edge for edge in detailed.lineage.edges if edge.direction == "input"]
    outputs = [edge for edge in detailed.lineage.edges if edge.direction == "output"]

    assert [edge.position for edge in inputs] == [0, 1]
    assert {edge.port_name for edge in inputs} == {"value"}
    assert [edge.object_id for edge in inputs] == [obj.framework.object_id for obj in items]
    assert {edge.type_name for edge in inputs} == {"Array"}
    assert [edge.data_object for edge in inputs] == items
    assert [edge.object_id for edge in outputs] == [obj.framework.object_id for obj in items]


def test_a_failed_call_still_reports_its_lineage(registry: BlockRegistry) -> None:
    """FR-051: a block execution is recorded when it reaches *any* terminal state."""
    recorded: list[BlockCallLineage] = []
    adapter = BlockCallAdapter(registry=registry, on_call=recorded.append)

    with pytest.raises(BlockCallFailedError):
        adapter.call("Exploding")

    assert len(recorded) == 1
    assert recorded[0].termination == "error"
    assert "the detector is on fire" in recorded[0].termination_detail


def test_a_cancelled_interactive_call_reports_a_cancelled_termination(
    registry: BlockRegistry,
) -> None:
    """FR-051: a cancelled interaction is a terminal state and is reported as one."""
    recorded: list[BlockCallLineage] = []
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel, on_call=recorded.append)
    thread, _results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    channel.await_open().cancel("the panel was closed")
    thread.join(timeout=10)

    assert isinstance(errors[0], BlockCallCancelledError)
    assert len(recorded) == 1
    assert recorded[0].termination == "cancelled"
    assert recorded[0].interactive is True


def test_an_interactive_calls_lineage_carries_the_decision(registry: BlockRegistry) -> None:
    """FR-051: the decision is part of the record, as it is for a paused workflow node."""
    recorded: list[BlockCallLineage] = []
    channel = RecordingChannel()
    adapter = BlockCallAdapter(registry=registry, interaction=channel, on_call=recorded.append)
    thread, _results, errors, _ = _call_in_thread(adapter, "Decide", table="rows")

    channel.await_open().submit({"choice": "b"})
    thread.join(timeout=10)

    assert errors == []
    assert recorded[0].interactive is True
    assert recorded[0].interactive_response == {"choice": "b"}
    assert recorded[0].termination == "completed"


def test_the_adapter_writes_no_lineage_of_its_own(registry: BlockRegistry) -> None:
    """FR-051 boundary: the adapter reports facts; the session lineage module records them.

    With no ``on_call`` and no store injected there is nowhere for the adapter
    to write, and the call still succeeds — which is the whole of the claim
    that recording is somebody else's task.
    """
    adapter = BlockCallAdapter(registry=registry)
    detailed = adapter.call_detailed("BareOutput", content="fine")

    assert detailed.lineage is not None
    assert detailed.value == "fine"


# ---------------------------------------------------------------------------
# Unwrapping edge cases
# ---------------------------------------------------------------------------


def test_a_metadata_only_result_comes_back_as_the_typed_object(registry: BlockRegistry) -> None:
    """An object with neither storage nor in-memory data has no native form.

    Rather than raise, the adapter hands the typed object back so the cell
    still receives the metadata the block produced.
    """
    adapter = BlockCallAdapter(registry=registry)
    empty = Array(axes=["y", "x"], shape=(4, 4))
    result = adapter.call("PassThrough", value=Collection([empty], item_type=Array))

    assert result is empty


def test_a_frame_result_is_unwrapped_from_its_transient_data(registry: BlockRegistry) -> None:
    """A table built in-process and never flushed still unwraps to its native form."""
    pandas = pytest.importorskip("pandas")
    frame = pandas.DataFrame({"mz": [1, 2], "intensity": [3, 4]})
    adapter = BlockCallAdapter(registry=registry)

    result = adapter.call("PassThrough", value=frame)

    assert result is frame
    received = OBSERVED["inputs"]["value"]
    assert isinstance(received, Collection)
    assert received.item_type is DataFrame
    assert isinstance(received[0], DataObject)
    assert received[0].columns == ["mz", "intensity"]
    assert received[0].row_count == 2


def test_the_production_adapter_has_no_interaction_channel() -> None:
    """FR-050's panel half is not built, and this is where that is visible (#2250).

    Every test above that exercises the interactive path constructs the adapter
    with a ``RecordingChannel`` — a double for the session service. That is the
    right shape for testing the adapter, and it is also how "``InteractionChannel``
    has no implementer anywhere in ``src/``" stayed invisible through two rounds
    of review: the requirement looked proved because the thing the requirement
    demands had been supplied by the test.

    So this asserts the opposite, against the adapter **production** builds:
    ``block_call_adapter()`` is what a cell's ``blocks.run(...)`` resolves, it
    carries no channel, and an interactive block through it is refused. When
    #2250 lands, this test is the one that must change — which is the point of
    writing it down rather than leaving the gap to the next audit.

    What a person gets instead is already covered by
    ``test_an_interactive_block_without_a_channel_is_refused_with_a_diagnosis``:
    a refusal naming the block and saying the notebook is not in an Explore
    session. Refusing is the safe answer — an interactive block exists because
    somebody has to choose something — and FR-039 refuses the same notebook at
    packaging, so a call that cannot open a panel cannot ship inside a block
    either. What was missing was any statement that the **production** adapter
    is the one without a channel.
    """
    from scistudio.explore import kernel_bridge

    kernel_bridge.set_block_call_adapter(None)
    try:
        adapter = kernel_bridge.block_call_adapter("sess-production")
        assert adapter._interaction is None, (
            "the production adapter grew a channel; #2250 has landed and this test must be rewritten"
        )
    finally:
        kernel_bridge.set_block_call_adapter(None)
