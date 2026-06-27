"""xfail baseline for the residual single-value transport drift (#1811).

ADR-020 §3 states the runtime transport contract:

    All values crossing a block boundary are represented as Collection
    objects. A single item is represented as a length-one Collection; a
    multi-file/multi-object input is a longer Collection.

#1330 (closed) enforced this **only** on ports already declared
``is_collection=True`` — :func:`_normalize_outputs` wraps a bare
DataObject into a length-one Collection on those ports. It did *not* make
single-value ports (``is_collection=False``) always-Collection. As a
result the engine still:

- serialises a single DataObject as a bare ``{backend, path, metadata}``
  reference (no ``_collection`` envelope) on ``is_collection=False`` ports
  (:func:`serialise_outputs`);
- reconstructs that wire shape as a **bare** DataObject downstream
  (:func:`reconstruct_inputs`); and
- re-emits a bare value from :meth:`ProcessBlock.run` when the primary
  input was itself bare (the non-Collection fallback branch).

Per ADR-020 §3 every one of these single values should be a length-one
Collection. The tests below pin that **target** behaviour. They are
marked ``xfail(strict=True)`` because the residual drift means they fail
today; when the #1811 root-cause fix lands (option (a): treat every
DataObject port as a Collection), each will start passing and the strict
marker forces us to delete it — a self-cleaning regression ratchet.

These tests are intentionally distinct from
``tests/engine/test_collection_wrap.py`` (the #1330 suite), whose
``TestEngineLeavesNonCollectionPortAlone`` pins the *current* drift as
intended #1330 behaviour. When #1811 lands, that #1330 test must be
revisited in the same change; this file documents why.

Completeness
------------
These boundaries are not a sample — they are the **closed set** of places a
bare single value can enter or leave a block boundary. A bare DataObject can
only exist where the transport codec produces or consumes one, and that codec
is a small, greppable API:

- In-memory raw objects enter ``DAGScheduler._block_outputs`` via exactly five
  writers (``_dispatch.py`` 249/327/588, ``scheduler/__init__.py`` 452/461).
  327/588 pass through ``_normalize_outputs`` first; 249 and 452/461 are
  wire-format paths (worker terminal outputs and checkpoint restore) that carry
  whatever the wire codec produced.
- Wire-format single values are produced **only** by ``_serialise_one`` and
  consumed **only** by ``_reconstruct_one``. At a port boundary the single-value
  branches are ``worker.serialise_outputs`` (worker.py:383) and
  ``worker.reconstruct_inputs`` (worker.py:176); every other caller is either
  Collection-item recursion, CompositeData slot recursion, a deprecated
  checkpoint deserialiser, or a metadata/preview side-channel.

So the root-cause surface reduces to three engine locations — ``_normalize_outputs``
(output produce), ``serialise_outputs`` (wire produce), ``reconstruct_inputs``
(wire consume) — plus the ``ProcessBlock.run`` non-Collection fallback (in-memory
consume + re-emit). The tests below pin all four. Checkpoint restore and worker
terminal outputs inherit the same codec and are fixed transitively when it is;
they are noted here so a future reviewer knows they were considered, not missed.
A new leak would require adding a new call site to one of those three functions,
which a grep-based guard can catch.

References: ADR-020 §3, §5, §7.1; #1330 (closed); #1811.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import BlockState
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.engine.events import EventBus
from scistudio.engine.runners.worker import (
    _normalize_outputs,
    reconstruct_inputs,
    serialise_outputs,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

_XFAIL_REASON = (
    "#1811: ADR-020 §3 requires single values on is_collection=False ports to "
    "transport as length-one Collections; the engine still uses the bare "
    "DataObject path. Remove this xfail when the option (a) fix lands."
)


def _ref(path: str = "/tmp/test.zarr", backend: str = "zarr") -> StorageReference:
    """Minimal StorageReference so serialise_outputs skips auto-flush."""
    return StorageReference(backend=backend, path=path)


def _make_array() -> Array:
    """Bare :class:`Array` with deterministic axes/shape and no storage."""
    return Array(axes=["y", "x"], shape=(4, 4), dtype="uint8")


# ---------------------------------------------------------------------------
# Output boundary: _normalize_outputs on single-value (is_collection=False)
# ---------------------------------------------------------------------------


class TestNormalizeSingleValuePort:
    """``_normalize_outputs`` should treat every DataObject port as Collection."""

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_normalize_wraps_bare_dataobject_on_single_value_port(self) -> None:
        """Bare DataObject on an ``is_collection=False`` port should become a
        length-one Collection. Today ``_normalize_outputs`` early-returns for
        non-Collection ports ([worker.py:257]) and leaves the bare object.
        """
        bare = _make_array()
        ports = [OutputPort(name="out", accepted_types=[Array], is_collection=False)]
        outputs: dict = {"out": bare}

        _normalize_outputs(outputs, ports)

        wrapped = outputs["out"]
        assert isinstance(wrapped, Collection)
        assert len(wrapped) == 1
        assert wrapped[0] is bare
        assert wrapped.item_type is Array

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_normalize_packs_bare_list_on_single_value_port(self) -> None:
        """A bare ``list[DataObject]`` on an ``is_collection=False`` port should
        pack into a Collection (ADR-020 §3 "multi-object input is a longer
        Collection"). Today the non-Collection port is skipped entirely.
        """
        a, b = _make_array(), _make_array()
        ports = [OutputPort(name="out", accepted_types=[Array], is_collection=False)]
        outputs: dict = {"out": [a, b]}

        _normalize_outputs(outputs, ports)

        packed = outputs["out"]
        assert isinstance(packed, Collection)
        assert len(packed) == 2
        assert packed[0] is a
        assert packed[1] is b
        assert packed.item_type is Array


# ---------------------------------------------------------------------------
# Wire format: serialise_outputs / reconstruct_inputs for single values
# ---------------------------------------------------------------------------


class TestSingleValueWireFormat:
    """A single DataObject should cross the wire as a ``_collection`` envelope."""

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_serialise_single_dataobject_emits_collection_envelope(self, tmp_path) -> None:
        """``serialise_outputs`` of a single DataObject should produce a
        ``{"_collection": True, "items": [...], "item_type": ...}`` payload,
        not a bare ``{backend, path, metadata}`` reference ([worker.py:383]).
        """
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "single.zarr")
        zarr.save(zarr_path, np.zeros((4, 4), dtype="uint8"))
        arr = Array(axes=["y", "x"], shape=(4, 4), dtype="uint8", storage_ref=_ref(zarr_path))

        wire = serialise_outputs({"out": arr}, str(tmp_path))
        payload = wire["out"]

        assert payload.get("_collection") is True
        assert payload["item_type"] == "Array"
        assert len(payload["items"]) == 1

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_reconstruct_bare_wire_dict_yields_length_one_collection(self, tmp_path) -> None:
        """A bare ``{backend, path, metadata}`` wire dict should reconstruct as a
        length-one Collection, not a bare DataObject ([worker.py:174-176]).

        Builds the bare wire shape via the existing single-value serialiser so
        the metadata is realistic, then asserts the target reconstruct result.
        """
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "bare.zarr")
        zarr.save(zarr_path, np.zeros((4, 4), dtype="uint8"))
        arr = Array(axes=["y", "x"], shape=(4, 4), dtype="uint8", storage_ref=_ref(zarr_path))

        bare_wire = serialise_outputs({"out": arr}, str(tmp_path))["out"]
        # Guard the test's own premise: today this is a bare reference, the
        # exact shape #1811 is about. (If this key appears, the fix landed and
        # this xfail test plus its premise must be revisited.)
        assert "backend" in bare_wire and "_collection" not in bare_wire

        rebuilt = reconstruct_inputs({"inputs": {"out": bare_wire}})["out"]

        assert isinstance(rebuilt, Collection)
        assert len(rebuilt) == 1
        assert isinstance(rebuilt[0], Array)

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_single_value_round_trip_is_length_one_collection(self, tmp_path) -> None:
        """End-to-end ``serialise_outputs`` -> ``reconstruct_inputs`` of a single
        value should hand the downstream block a length-one Collection.
        """
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "rt_single.zarr")
        zarr.save(zarr_path, np.zeros((8, 8), dtype="float32"))
        original = Array(axes=["y", "x"], shape=(8, 8), dtype="float32", storage_ref=_ref(zarr_path))

        wire = serialise_outputs({"out": original}, str(tmp_path))
        rebuilt = reconstruct_inputs({"inputs": wire})["out"]

        assert isinstance(rebuilt, Collection)
        assert len(rebuilt) == 1
        assert rebuilt[0].shape == original.shape


# ---------------------------------------------------------------------------
# Consumer boundary: ProcessBlock.run must not re-emit bare on bare input
# ---------------------------------------------------------------------------


class TestProcessBlockSingleValueOutput:
    """The non-Collection fallback in :meth:`ProcessBlock.run` propagates drift."""

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_process_block_emits_collection_for_bare_input(self) -> None:
        """When the primary input is a bare DataObject, ``ProcessBlock.run``
        should still emit a Collection on its output port. Today the
        non-Collection fallback ([process_block.py:174-177]) calls
        ``process_item`` once and returns the bare result, so the drift
        propagates transitively down the graph.
        """
        from scistudio.blocks.process.process_block import ProcessBlock

        class _Passthrough(ProcessBlock):
            type_name = "_test.single_value_passthrough"
            input_ports: ClassVar = [InputPort(name="data", accepted_types=[DataObject])]
            output_ports: ClassVar = [OutputPort(name="out", accepted_types=[DataObject])]

            def process_item(self, item, config, state=None):  # type: ignore[no-untyped-def]
                return item

        block = _Passthrough()
        bare = _make_array()

        result = block.run({"data": bare}, block.config)

        assert isinstance(result["out"], Collection)
        assert len(result["out"]) == 1


# ---------------------------------------------------------------------------
# Integration: scheduler in-process boundary (_dispatch.py:325)
# ---------------------------------------------------------------------------


class _BareSingleValueBlock(Block):
    """Non-interactive block returning a bare Array on an is_collection=False port.

    Mirrors the in-process drift: a runner returning a raw Python
    :class:`DataObject` (not a wire dict) on a single-value port. The
    engine's in-process ``_normalize_outputs`` call ([_dispatch.py:325])
    skips non-Collection ports today, so the bare Array lands in
    ``_block_outputs`` unwrapped.
    """

    name: ClassVar[str] = "BareSingleValue"
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="out", accepted_types=[Array], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # DAGScheduler._instantiate_block assigns ``.id`` after construction.
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"out": _make_array()}


def _make_single_value_scheduler() -> tuple[DAGScheduler, EventBus]:
    """Build a DAGScheduler whose registry returns ``_BareSingleValueBlock``.

    The mock runner returns the block's bare, un-normalised output so the
    in-process finalize ``_normalize_outputs`` call is the only thing that
    could honour ADR-020 §3 before the value lands in ``_block_outputs``.
    """
    wf = WorkflowDefinition(
        id="wf-1811-single-value",
        nodes=[NodeDef(id="a", block_type="bare-single-value", config={})],
        edges=[],
    )
    event_bus = EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()

    async def _compute(block: Block, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return block.run(inputs, BlockConfig(**config))

    runner.run.side_effect = _compute

    registry = MagicMock()
    registry.instantiate.side_effect = lambda name, config=None: _BareSingleValueBlock(config or {})
    registry.get_spec.return_value = None

    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, event_bus


class TestSchedulerInProcessSingleValueBoundary:
    """The second ``_normalize_outputs`` call site must wrap single values too."""

    @pytest.mark.xfail(reason=_XFAIL_REASON, strict=True)
    def test_in_process_dispatch_wraps_bare_single_value(self) -> None:
        """A bare Array produced in-process on an ``is_collection=False`` port
        should land in ``_block_outputs`` as a length-one Collection. Today the
        in-process boundary ([_dispatch.py:325]) skips non-Collection ports, so
        the bare value propagates to downstream blocks unwrapped.
        """
        scheduler, _event_bus = _make_single_value_scheduler()

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["a"] == BlockState.DONE
        stored = scheduler._block_outputs["a"]
        assert isinstance(stored, dict)
        wrapped = stored["out"]
        assert isinstance(wrapped, Collection)
        assert len(wrapped) == 1
        assert isinstance(wrapped[0], Array)
