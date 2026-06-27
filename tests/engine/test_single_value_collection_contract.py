"""Single-value transport contract — every port crosses as a Collection (#1811).

ADR-020 §3 states the runtime transport contract:

    All values crossing a block boundary are represented as Collection
    objects. A single item is represented as a length-one Collection; a
    multi-file/multi-object input is a longer Collection.

#1330 (closed) enforced this **only** on ports already declared
``is_collection=True``. #1811 makes the wrap **unconditional**: the
``is_collection`` flag is a UI hint only (collection-guide.md) and no
longer gates transport, so single-value (``is_collection=False``) ports
also cross the boundary as length-one Collections.

Enforcement point
-----------------
:func:`_normalize_outputs` is the single engine boundary that guarantees
the contract: it wraps every bare ``DataObject`` (or bare
``list[DataObject]``) on every declared output port into a Collection,
before serialisation and before the value lands in
``DAGScheduler._block_outputs``. Because normalize always runs first, the
downstream wire codec (:func:`serialise_outputs` /
:func:`reconstruct_inputs`) only ever sees an already-wrapped Collection in
the live flow and faithfully transports it as a ``_collection`` envelope —
the primitives are not single-value-aware and do not need to be.
:meth:`ProcessBlock.run` additionally wraps its own output so a block that
is handed a bare primary still emits a Collection.

This file pins that contract at each boundary a single value passes:

- output produce — :func:`_normalize_outputs` (the enforcement point);
- wire round-trip — a normalised single value serialises to a
  ``_collection`` envelope and reconstructs to a length-one Collection;
- in-memory consume + re-emit — :meth:`ProcessBlock.run`;
- the scheduler in-process boundary (``_dispatch.py``).

These tests were the ``xfail(strict=True)`` baseline that pinned the
residual drift before the fix (the Phase-1 ratchet, PR #1814); the strict
markers were removed when the #1811 fix landed and flipped them green.

References: ADR-020 §3, §5, §7.1; #1330 (closed); #1811.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

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


def _ref(path: str = "/tmp/test.zarr", backend: str = "zarr") -> StorageReference:
    """Minimal StorageReference so serialise_outputs skips auto-flush."""
    return StorageReference(backend=backend, path=path)


def _make_array() -> Array:
    """Bare :class:`Array` with deterministic axes/shape and no storage."""
    return Array(axes=["y", "x"], shape=(4, 4), dtype="uint8")


def _single_value_port() -> OutputPort:
    return OutputPort(name="out", accepted_types=[Array], is_collection=False)


# ---------------------------------------------------------------------------
# Output boundary: _normalize_outputs on single-value (is_collection=False)
# ---------------------------------------------------------------------------


class TestNormalizeSingleValuePort:
    """``_normalize_outputs`` treats every DataObject port as Collection."""

    def test_normalize_wraps_bare_dataobject_on_single_value_port(self) -> None:
        """Bare DataObject on an ``is_collection=False`` port becomes a
        length-one Collection (the #1811 unconditional wrap).
        """
        bare = _make_array()
        outputs: dict = {"out": bare}

        _normalize_outputs(outputs, [_single_value_port()])

        wrapped = outputs["out"]
        assert isinstance(wrapped, Collection)
        assert len(wrapped) == 1
        assert wrapped[0] is bare
        assert wrapped.item_type is Array

    def test_normalize_packs_bare_list_on_single_value_port(self) -> None:
        """A bare ``list[DataObject]`` on an ``is_collection=False`` port packs
        into a Collection (ADR-020 §3 "multi-object input is a longer
        Collection").
        """
        a, b = _make_array(), _make_array()
        outputs: dict = {"out": [a, b]}

        _normalize_outputs(outputs, [_single_value_port()])

        packed = outputs["out"]
        assert isinstance(packed, Collection)
        assert len(packed) == 2
        assert packed[0] is a
        assert packed[1] is b
        assert packed.item_type is Array


# ---------------------------------------------------------------------------
# Wire round-trip: a normalised single value crosses as a _collection envelope
# ---------------------------------------------------------------------------


class TestSingleValueWireFormat:
    """A normalised single value crosses the wire as a ``_collection`` envelope."""

    def test_normalized_single_value_serialises_as_collection_envelope(self, tmp_path) -> None:
        """After the engine boundary wraps a single value, ``serialise_outputs``
        emits a ``{"_collection": True, "items": [...], "item_type": ...}``
        payload — not a bare ``{backend, path, metadata}`` reference.
        """
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "single.zarr")
        zarr.save(zarr_path, np.zeros((4, 4), dtype="uint8"))
        arr = Array(axes=["y", "x"], shape=(4, 4), dtype="uint8", storage_ref=_ref(zarr_path))

        outputs: dict = {"out": arr}
        _normalize_outputs(outputs, [_single_value_port()])
        payload = serialise_outputs(outputs, str(tmp_path))["out"]

        assert payload.get("_collection") is True
        assert payload["item_type"] == "Array"
        assert len(payload["items"]) == 1

    def test_single_value_round_trip_is_length_one_collection(self, tmp_path) -> None:
        """End-to-end ``_normalize_outputs`` -> ``serialise_outputs`` ->
        ``reconstruct_inputs`` of a single value hands the downstream block a
        length-one Collection.
        """
        import numpy as np
        import zarr

        zarr_path = str(tmp_path / "rt_single.zarr")
        zarr.save(zarr_path, np.zeros((8, 8), dtype="float32"))
        original = Array(axes=["y", "x"], shape=(8, 8), dtype="float32", storage_ref=_ref(zarr_path))

        outputs: dict = {"out": original}
        _normalize_outputs(outputs, [_single_value_port()])
        wire = serialise_outputs(outputs, str(tmp_path))
        rebuilt = reconstruct_inputs({"inputs": wire})["out"]

        assert isinstance(rebuilt, Collection)
        assert len(rebuilt) == 1
        assert rebuilt[0].shape == original.shape


# ---------------------------------------------------------------------------
# Consumer boundary: ProcessBlock.run emits a Collection on bare input
# ---------------------------------------------------------------------------


class TestProcessBlockSingleValueOutput:
    """:meth:`ProcessBlock.run` wraps even a bare primary input."""

    def test_process_block_emits_collection_for_bare_input(self) -> None:
        """When the primary input is a bare DataObject, ``ProcessBlock.run``
        still emits a Collection on its output port, so the contract holds even
        for a legacy bare value reaching the block directly.
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
# Integration: scheduler in-process boundary (_dispatch.py)
# ---------------------------------------------------------------------------


class _BareSingleValueBlock(Block):
    """Non-interactive block returning a bare Array on an is_collection=False port.

    Mirrors the in-process path: a runner returning a raw Python
    :class:`DataObject` (not a wire dict) on a single-value port. The
    engine's in-process ``_normalize_outputs`` call must wrap it before it
    lands in ``_block_outputs``.
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
    can honour ADR-020 §3 before the value lands in ``_block_outputs``.
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
    """The in-process ``_normalize_outputs`` call site wraps single values too."""

    def test_in_process_dispatch_wraps_bare_single_value(self) -> None:
        """A bare Array produced in-process on an ``is_collection=False`` port
        lands in ``_block_outputs`` as a length-one Collection.
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
