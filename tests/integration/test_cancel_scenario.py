"""Integration tests: cancellation with skip propagation + cycle detection.

These tests verify that the DAGScheduler correctly propagates SKIPPED state
to downstream blocks when a block is cancelled or errors, and that the DAG
construction correctly detects cycles.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.dag import CycleError, build_dag, topological_sort
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheduler(
    workflow: WorkflowDefinition,
) -> tuple[DAGScheduler, EventBus, AsyncMock]:
    """Create a DAGScheduler with mocked runner/resource manager."""
    event_bus = EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()
    runner.run.return_value = {"output": "mock_result"}

    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
    )
    return scheduler, event_bus, runner


# ---------------------------------------------------------------------------
# Cancel propagation
# ---------------------------------------------------------------------------


class TestCancelPropagation:
    """Cancelling a block marks its downstream dependents as SKIPPED."""

    def test_cancel_propagates_skip_to_downstream(self) -> None:
        """Cancel B -> D (depends on B) should be SKIPPED, C should still run."""
        # A -> B (cancellable), A -> C (independent), B -> D
        workflow = WorkflowDefinition(
            id="cancel-test",
            nodes=[
                NodeDef(id="A", block_type="io_block"),
                NodeDef(id="B", block_type="process_block"),
                NodeDef(id="C", block_type="process_block"),
                NodeDef(id="D", block_type="io_block"),  # depends on B
            ],
            edges=[
                EdgeDef(source="A:data", target="B:data"),
                EdgeDef(source="A:data", target="C:data"),
                EdgeDef(source="B:output", target="D:data"),
            ],
        )

        # Verify DAG structure first
        dag = build_dag(workflow)
        assert "B" in dag.adjacency["A"]
        assert "C" in dag.adjacency["A"]
        assert "D" in dag.adjacency["B"]

        # Now test cancellation via scheduler
        scheduler, event_bus, _runner = _make_scheduler(workflow)

        # Simulate: A completed, B is running, C is idle, D is idle
        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"data": "some_data"}
        scheduler._block_states["B"] = BlockState.RUNNING

        # Cancel B
        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="B")))

        assert scheduler._block_states["B"] == BlockState.CANCELLED
        assert scheduler._block_states["D"] == BlockState.SKIPPED
        assert "B" in scheduler.skip_reasons["D"]

    def test_cancel_does_not_affect_independent_branch(self) -> None:
        """Cancel B should not skip C (independent branch from A)."""
        workflow = WorkflowDefinition(
            id="independent-branch-test",
            nodes=[
                NodeDef(id="A", block_type="io_block"),
                NodeDef(id="B", block_type="process_block"),
                NodeDef(id="C", block_type="process_block"),
            ],
            edges=[
                EdgeDef(source="A:data", target="B:data"),
                EdgeDef(source="A:data", target="C:data"),
            ],
        )
        scheduler, event_bus, _runner = _make_scheduler(workflow)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"data": "val"}
        scheduler._block_states["B"] = BlockState.RUNNING
        scheduler._block_states["C"] = BlockState.IDLE

        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="B")))

        assert scheduler._block_states["B"] == BlockState.CANCELLED
        # C is independent of B and should NOT be skipped
        assert scheduler._block_states["C"] != BlockState.SKIPPED

    def test_cancel_workflow_cancels_all_running(self) -> None:
        """Cancel workflow -> all running become cancelled, idle become skipped."""
        workflow = WorkflowDefinition(
            id="workflow-cancel-test",
            nodes=[
                NodeDef(id="A", block_type="proc"),
                NodeDef(id="B", block_type="proc"),
                NodeDef(id="C", block_type="proc"),
                NodeDef(id="D", block_type="proc"),
            ],
            edges=[
                EdgeDef(source="A:out", target="C:in"),
                EdgeDef(source="B:out", target="D:in"),
            ],
        )
        scheduler, event_bus, _runner = _make_scheduler(workflow)

        # A done, B running, C idle, D idle
        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "val"}
        scheduler._block_states["B"] = BlockState.RUNNING
        scheduler._block_states["C"] = BlockState.IDLE
        scheduler._block_states["D"] = BlockState.IDLE

        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST)))

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.CANCELLED
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        assert scheduler._block_states["D"] == BlockState.SKIPPED

    def test_error_propagates_skip_deep_chain(self) -> None:
        """A -> B -> C -> D: error in B skips C and D."""
        workflow = WorkflowDefinition(
            id="deep-chain-error",
            nodes=[
                NodeDef(id="A", block_type="proc"),
                NodeDef(id="B", block_type="proc"),
                NodeDef(id="C", block_type="proc"),
                NodeDef(id="D", block_type="proc"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="B:out", target="C:in"),
                EdgeDef(source="C:out", target="D:in"),
            ],
        )

        async def fail_on_b(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "B":  # type: ignore[attr-defined]
                raise RuntimeError("Block B crashed")
            return {"out": "ok"}

        scheduler, _event_bus, runner = _make_scheduler(workflow)
        runner.run.side_effect = fail_on_b

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.ERROR
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        assert scheduler._block_states["D"] == BlockState.SKIPPED

    def test_skip_events_emitted(self) -> None:
        """BLOCK_CANCELLED and BLOCK_SKIPPED events are emitted correctly."""
        workflow = WorkflowDefinition(
            id="skip-events-test",
            nodes=[
                NodeDef(id="A", block_type="proc"),
                NodeDef(id="B", block_type="proc"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
            ],
        )
        scheduler, event_bus, _runner = _make_scheduler(workflow)

        cancelled_events: list[str] = []
        skipped_events: list[str] = []

        event_bus.subscribe(
            BLOCK_CANCELLED,
            lambda e: cancelled_events.append(e.block_id or ""),
        )
        event_bus.subscribe(
            BLOCK_SKIPPED,
            lambda e: skipped_events.append(e.block_id or ""),
        )

        scheduler._block_states["A"] = BlockState.RUNNING
        scheduler._block_states["B"] = BlockState.IDLE

        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="A")))

        assert "A" in cancelled_events
        assert "B" in skipped_events


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Cyclic workflow is detected and raises CycleError."""

    def test_simple_cycle_raises(self) -> None:
        """A -> B -> C -> A raises CycleError."""
        workflow = WorkflowDefinition(
            id="cycle-test",
            nodes=[
                NodeDef(id="A", block_type="process_block"),
                NodeDef(id="B", block_type="process_block"),
                NodeDef(id="C", block_type="process_block"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="B:out", target="C:in"),
                EdgeDef(source="C:out", target="A:in"),
            ],
        )
        dag = build_dag(workflow)

        with pytest.raises(CycleError):
            topological_sort(dag)

    def test_self_loop_raises(self) -> None:
        """A -> A (self-loop) raises CycleError."""
        workflow = WorkflowDefinition(
            id="self-loop-test",
            nodes=[
                NodeDef(id="A", block_type="process_block"),
            ],
            edges=[
                EdgeDef(source="A:out", target="A:in"),
            ],
        )
        dag = build_dag(workflow)

        with pytest.raises(CycleError):
            topological_sort(dag)

    def test_two_node_cycle_raises(self) -> None:
        """A -> B -> A raises CycleError."""
        workflow = WorkflowDefinition(
            id="two-cycle-test",
            nodes=[
                NodeDef(id="A", block_type="process_block"),
                NodeDef(id="B", block_type="process_block"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="B:out", target="A:in"),
            ],
        )
        dag = build_dag(workflow)

        with pytest.raises(CycleError):
            topological_sort(dag)

    def test_acyclic_graph_no_error(self) -> None:
        """A diamond graph (A -> B, A -> C, B -> D, C -> D) is valid."""
        workflow = WorkflowDefinition(
            id="diamond-test",
            nodes=[
                NodeDef(id="A", block_type="proc"),
                NodeDef(id="B", block_type="proc"),
                NodeDef(id="C", block_type="proc"),
                NodeDef(id="D", block_type="proc"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="A:out", target="C:in"),
                EdgeDef(source="B:out", target="D:in1"),
                EdgeDef(source="C:out", target="D:in2"),
            ],
        )
        dag = build_dag(workflow)

        # Should not raise
        order = topological_sort(dag)
        assert len(order) == 4
        assert order[0] == "A"
        assert order[-1] == "D"
