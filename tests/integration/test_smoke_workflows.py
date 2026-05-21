"""Layer 3: Smoke workflow tests that run minimal workflows through the real scheduler.

Builds WorkflowDefinitions programmatically, uses a mock runner (to avoid
subprocess overhead), and verifies the scheduler orchestrates blocks correctly.

Covers #441.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import EventBus
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(side_effect: Any = None) -> MagicMock:
    """Build a mock runner whose .run() is an AsyncMock."""
    runner = MagicMock()
    if side_effect is not None:
        runner.run = AsyncMock(side_effect=side_effect)
    else:
        runner.run = AsyncMock(return_value={})
    return runner


def _make_scheduler(
    workflow: WorkflowDefinition,
    runner: Any | None = None,
    *,
    project_dir: str | None = None,
) -> DAGScheduler:
    """Build a DAGScheduler with minimal mocks and a mock runner."""
    bus = EventBus()
    resource_mgr = MagicMock()
    resource_mgr.can_dispatch.return_value = True
    proc_reg = MagicMock()
    proc_reg.get_handle.return_value = None
    rnr = runner or _make_runner()
    return DAGScheduler(
        workflow=workflow,
        event_bus=bus,
        resource_manager=resource_mgr,
        process_registry=proc_reg,
        runner=rnr,
        project_dir=project_dir,
    )


# ---------------------------------------------------------------------------
# Test 1: Two-node linear workflow (A -> B)
# ---------------------------------------------------------------------------


def test_two_node_linear_workflow() -> None:
    """A simple A -> B workflow should complete with both blocks DONE."""
    wf = WorkflowDefinition(
        id="smoke-linear",
        description="A -> B linear pipeline",
        nodes=[
            NodeDef(id="a", block_type="mock_block", config={"step": "first"}),
            NodeDef(id="b", block_type="mock_block", config={"step": "second"}),
        ],
        edges=[EdgeDef(source="a:out", target="b:in")],
    )

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        node_id = block.id if hasattr(block, "id") else str(block)
        return {"out": f"result-from-{node_id}"}

    runner = _make_runner(side_effect=mock_run)
    scheduler = _make_scheduler(wf, runner=runner)

    asyncio.run(scheduler.execute())

    # Both blocks should be DONE
    assert scheduler._block_states["a"] == BlockState.DONE
    assert scheduler._block_states["b"] == BlockState.DONE

    # Runner.run called twice
    assert runner.run.call_count == 2

    # Block B should have received A's output as input
    b_call = runner.run.call_args_list[1]
    b_inputs = b_call[0][1]  # second positional arg is inputs
    assert "in" in b_inputs
    assert b_inputs["in"] == "result-from-a"


# ---------------------------------------------------------------------------
# Test 2: Diamond workflow (A -> B, A -> C, B -> D, C -> D)
# ---------------------------------------------------------------------------


def test_diamond_workflow() -> None:
    """A diamond workflow (fan-out + fan-in) should complete all blocks."""
    wf = WorkflowDefinition(
        id="smoke-diamond",
        description="diamond: A -> B,C -> D",
        nodes=[
            NodeDef(id="a", block_type="mock_block", config={}),
            NodeDef(id="b", block_type="mock_block", config={}),
            NodeDef(id="c", block_type="mock_block", config={}),
            NodeDef(id="d", block_type="mock_block", config={}),
        ],
        edges=[
            EdgeDef(source="a:out", target="b:in"),
            EdgeDef(source="a:out2", target="c:in"),
            EdgeDef(source="b:out", target="d:in1"),
            EdgeDef(source="c:out", target="d:in2"),
        ],
    )

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        return {"out": "ok", "out2": "ok"}

    runner = _make_runner(side_effect=mock_run)
    scheduler = _make_scheduler(wf, runner=runner)

    asyncio.run(scheduler.execute())

    for node_id in ["a", "b", "c", "d"]:
        assert scheduler._block_states[node_id] == BlockState.DONE, (
            f"Block {node_id} should be DONE, got {scheduler._block_states[node_id]}"
        )

    # D should have received inputs from both B and C
    d_calls = [c for c in runner.run.call_args_list if c[0][0].id == "d"]
    assert len(d_calls) == 1
    d_inputs = d_calls[0][0][1]
    assert "in1" in d_inputs
    assert "in2" in d_inputs


# ---------------------------------------------------------------------------
# Test 3: Error propagation (A -> B -> C, B errors -> C skipped)
# ---------------------------------------------------------------------------


def test_error_propagation_skips_downstream() -> None:
    """When B errors, downstream C should be SKIPPED."""
    wf = WorkflowDefinition(
        id="smoke-error",
        description="A -> B(error) -> C(skipped)",
        nodes=[
            NodeDef(id="a", block_type="mock_block", config={}),
            NodeDef(id="b", block_type="mock_block", config={}),
            NodeDef(id="c", block_type="mock_block", config={}),
        ],
        edges=[
            EdgeDef(source="a:out", target="b:in"),
            EdgeDef(source="b:out", target="c:in"),
        ],
    )

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        node_id = block.id
        if node_id == "b":
            raise RuntimeError("Simulated block error")
        return {"out": f"result-{node_id}"}

    runner = _make_runner(side_effect=mock_run)
    scheduler = _make_scheduler(wf, runner=runner)

    asyncio.run(scheduler.execute())

    assert scheduler._block_states["a"] == BlockState.DONE
    assert scheduler._block_states["b"] == BlockState.ERROR
    assert scheduler._block_states["c"] == BlockState.SKIPPED


# ---------------------------------------------------------------------------
# Test 4: project_dir injection (#444)
# ---------------------------------------------------------------------------


def test_project_dir_injected_into_config() -> None:
    """When project_dir is set on DAGScheduler, it appears in the config passed to runner."""
    wf = WorkflowDefinition(
        id="smoke-project-dir",
        description="single block with project_dir",
        nodes=[
            NodeDef(id="a", block_type="mock_block", config={"foo": "bar"}),
        ],
        edges=[],
    )

    received_configs: list[dict] = []

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        received_configs.append(config)
        return {}

    runner = _make_runner(side_effect=mock_run)
    scheduler = _make_scheduler(wf, runner=runner, project_dir="/my/project")

    asyncio.run(scheduler.execute())

    assert len(received_configs) == 1
    cfg = received_configs[0]
    assert cfg["project_dir"] == "/my/project"
    assert cfg["block_id"] == "a"
    assert cfg["workflow_id"] == "smoke-project-dir"
    # Original config key preserved
    assert cfg["foo"] == "bar"


def test_project_dir_absent_when_not_set() -> None:
    """When project_dir is not set, config should not contain project_dir key."""
    wf = WorkflowDefinition(
        id="smoke-no-project-dir",
        nodes=[NodeDef(id="a", block_type="mock_block", config={})],
        edges=[],
    )

    received_configs: list[dict] = []

    async def mock_run(block: Any, inputs: dict, config: dict) -> dict:
        received_configs.append(config)
        return {}

    runner = _make_runner(side_effect=mock_run)
    scheduler = _make_scheduler(wf, runner=runner)

    asyncio.run(scheduler.execute())

    assert len(received_configs) == 1
    assert "project_dir" not in received_configs[0]
    # block_id and workflow_id are always injected
    assert "block_id" in received_configs[0]
    assert "workflow_id" in received_configs[0]
