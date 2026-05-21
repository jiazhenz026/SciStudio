"""Tests for SubWorkflowBlock — sequential executor and scheduler factory injection."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import BlockState
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.subworkflow.subworkflow_block import SubWorkflowBlock, _sequential_execute
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class AddOneBlock(ProcessBlock):
    """Trivial block that adds 1 to input value."""

    name = "AddOne"
    algorithm = "add_one"

    input_ports: ClassVar[list[InputPort]] = [InputPort(name="x", accepted_types=[])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="x", accepted_types=[])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"x": inputs["x"] + 1}


class DoubleBlock(ProcessBlock):
    """Trivial block that doubles input value."""

    name = "Double"
    algorithm = "double"

    input_ports: ClassVar[list[InputPort]] = [InputPort(name="x", accepted_types=[])]
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="x", accepted_types=[])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"x": inputs["x"] * 2}


class CollectionPassthroughBlock(ProcessBlock):
    """Block that receives a Collection on 'items' and passes it through unchanged."""

    name = "CollectionPassthrough"
    algorithm = "passthrough"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="items", accepted_types=[], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="items", accepted_types=[]),
    ]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"items": inputs["items"]}


class TestSequentialExecute:
    """_sequential_execute — chains blocks in order."""

    def test_single_block(self) -> None:
        blocks = [AddOneBlock()]
        result = _sequential_execute(blocks, {"x": 10})
        assert result["x"] == 11

    def test_chain_two_blocks(self) -> None:
        blocks = [AddOneBlock(), DoubleBlock()]
        result = _sequential_execute(blocks, {"x": 5})
        # (5 + 1) * 2 = 12
        assert result["x"] == 12

    def test_empty_chain(self) -> None:
        result = _sequential_execute([], {"x": 42})
        assert result["x"] == 42


class TestSubWorkflowBlock:
    """SubWorkflowBlock — input/output mapping and child execution."""

    def test_with_child_blocks(self) -> None:
        child_blocks = [AddOneBlock(), DoubleBlock()]
        block = SubWorkflowBlock(
            config={
                "params": {
                    "child_blocks": child_blocks,
                    "input_mapping": {"data": "x"},
                    "output_mapping": {"x": "result"},
                }
            }
        )
        block.transition(BlockState.READY)
        result = block.run({"data": 10}, block.config)
        # (10 + 1) * 2 = 22
        assert result["result"] == 22

    def test_unmapped_passthrough(self) -> None:
        block = SubWorkflowBlock(config={"params": {"child_blocks": [], "input_mapping": {}, "output_mapping": {}}})
        block.transition(BlockState.READY)
        result = block.run({"extra": 99}, block.config)
        assert result["extra"] == 99

    def test_state_transitions(self) -> None:
        block = SubWorkflowBlock(config={"params": {"child_blocks": []}})
        block.transition(BlockState.READY)
        block.run({}, block.config)

    def test_scheduler_factory_injection(self) -> None:
        """Verify that _scheduler_factory ClassVar can be set and triggers _run_with_scheduler."""
        call_log: list[str] = []

        def fake_factory() -> None:
            """Sentinel — not called directly; _run_with_scheduler is the real hook."""

        original = SubWorkflowBlock._scheduler_factory
        try:
            SubWorkflowBlock._scheduler_factory = fake_factory

            child_blocks = [AddOneBlock()]
            block = SubWorkflowBlock(
                config={
                    "params": {
                        "child_blocks": child_blocks,
                        "input_mapping": {"data": "x"},
                        "output_mapping": {"x": "result"},
                    }
                }
            )
            block.transition(BlockState.READY)

            # Monkey-patch _run_with_scheduler to prove it gets called.
            original_method = block._run_with_scheduler

            def tracking_run_with_scheduler(child_inputs: dict, config: BlockConfig) -> dict:
                call_log.append("_run_with_scheduler")
                return original_method(child_inputs, config)

            block._run_with_scheduler = tracking_run_with_scheduler  # type: ignore[assignment]

            result = block.run({"data": 10}, block.config)
            assert result["result"] == 11
            assert call_log == ["_run_with_scheduler"]
        finally:
            SubWorkflowBlock._scheduler_factory = original

    def test_run_with_scheduler_factory_none_uses_sequential(self) -> None:
        """When _scheduler_factory is None, run() uses _sequential_execute (fallback)."""
        assert SubWorkflowBlock._scheduler_factory is None  # default

        child_blocks = [AddOneBlock(), DoubleBlock()]
        block = SubWorkflowBlock(
            config={
                "params": {
                    "child_blocks": child_blocks,
                    "input_mapping": {"data": "x"},
                    "output_mapping": {"x": "result"},
                }
            }
        )
        block.transition(BlockState.READY)
        result = block.run({"data": 5}, block.config)
        # (5 + 1) * 2 = 12
        assert result["result"] == 12

    def test_collection_passthrough(self) -> None:
        """Collections flow through child workflow without unwrapping."""
        obj1 = DataObject()
        obj2 = DataObject()
        coll = Collection([obj1, obj2])

        child_blocks = [CollectionPassthroughBlock()]
        block = SubWorkflowBlock(
            config={
                "params": {
                    "child_blocks": child_blocks,
                    "input_mapping": {"data": "items"},
                    "output_mapping": {"items": "result"},
                }
            }
        )
        block.transition(BlockState.READY)
        result = block.run({"data": coll}, block.config)

        assert isinstance(result["result"], Collection)
        assert len(result["result"]) == 2
        assert result["result"][0] is obj1
        assert result["result"][1] is obj2


class TestCleanupCallback:
    """Tests for _cleanup_callback — ADR-017/019 nested subprocess cleanup."""

    def test_cleanup_callback_called_on_success(self) -> None:
        """Cleanup callback is called after successful run."""
        callback_called: list[bool] = []
        SubWorkflowBlock._cleanup_callback = lambda: callback_called.append(True)
        try:
            block = SubWorkflowBlock(config={"params": {"child_blocks": []}})
            block.transition(BlockState.READY)
            block.run({}, block.config)
            assert len(callback_called) == 1
        finally:
            SubWorkflowBlock._cleanup_callback = None

    def test_cleanup_callback_called_on_error(self) -> None:
        """Cleanup callback is called even when run() raises."""
        callback_called: list[bool] = []
        SubWorkflowBlock._cleanup_callback = lambda: callback_called.append(True)
        try:
            block = SubWorkflowBlock(config={"params": {"child_blocks": []}})
            block.transition(BlockState.READY)
            # Monkey-patch _run_with_scheduler to force an error during execution.

            def boom(*a: Any, **kw: Any) -> dict[str, Any]:
                raise RuntimeError("boom")

            block._run_with_scheduler = boom  # type: ignore[assignment]
            SubWorkflowBlock._scheduler_factory = lambda: None  # Trigger _run_with_scheduler path
            with pytest.raises(RuntimeError, match="boom"):
                block.run({}, block.config)
            assert len(callback_called) == 1
        finally:
            SubWorkflowBlock._cleanup_callback = None
            SubWorkflowBlock._scheduler_factory = None

    def test_cleanup_callback_exception_does_not_mask_original(self) -> None:
        """If cleanup callback itself raises, the original error is preserved."""

        def bad_cleanup() -> None:
            raise OSError("cleanup failed")

        SubWorkflowBlock._cleanup_callback = bad_cleanup
        try:
            block = SubWorkflowBlock(config={"params": {"child_blocks": []}})
            block.transition(BlockState.READY)
            # Monkey-patch _run_with_scheduler to force an error during execution.

            def boom(*a: Any, **kw: Any) -> dict[str, Any]:
                raise RuntimeError("original error")

            block._run_with_scheduler = boom  # type: ignore[assignment]
            SubWorkflowBlock._scheduler_factory = lambda: None  # Trigger _run_with_scheduler path
            # The original RuntimeError should propagate, not the OSError from cleanup.
            with pytest.raises(RuntimeError, match="original error"):
                block.run({}, block.config)
        finally:
            SubWorkflowBlock._cleanup_callback = None
            SubWorkflowBlock._scheduler_factory = None

    def test_cleanup_callback_none_is_default(self) -> None:
        """When no callback is set, no error occurs in finally block."""
        assert SubWorkflowBlock._cleanup_callback is None
        block = SubWorkflowBlock(config={"params": {"child_blocks": []}})
        block.transition(BlockState.READY)
        block.run({}, block.config)
        # Block no longer sets own DONE state (scheduler owns that).
        # Just verify run() completes without error.
        assert block.state == BlockState.READY
