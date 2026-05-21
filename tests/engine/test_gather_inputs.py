"""Regression tests for #435: _gather_inputs must not pass entire dict when port key is missing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from scistudio.engine.events import EventBus
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


def _make_scheduler(workflow: WorkflowDefinition) -> DAGScheduler:
    """Build a DAGScheduler with minimal mocks."""
    bus = EventBus()
    resource_mgr = MagicMock()
    resource_mgr.can_dispatch.return_value = True
    proc_reg = MagicMock()
    proc_reg.get_handle.return_value = None
    runner = AsyncMock()
    return DAGScheduler(
        workflow=workflow,
        event_bus=bus,
        resource_manager=resource_mgr,
        process_registry=proc_reg,
        runner=runner,
    )


def test_gather_inputs_matching_port() -> None:
    """When upstream output contains the named port, it should be passed through."""
    wf = WorkflowDefinition(
        id="test",
        description="test",
        nodes=[
            NodeDef(id="a", block_type="t", config={}),
            NodeDef(id="b", block_type="t", config={}),
        ],
        edges=[EdgeDef(source="a:image", target="b:input")],
    )
    scheduler = _make_scheduler(wf)
    scheduler._block_outputs["a"] = {"image": "my_image_data"}

    inputs = scheduler._gather_inputs("b")
    assert inputs == {"input": "my_image_data"}


def test_gather_inputs_missing_port_does_not_pass_dict() -> None:
    """When upstream output dict does NOT contain the named port, skip it (#435)."""
    wf = WorkflowDefinition(
        id="test",
        description="test",
        nodes=[
            NodeDef(id="a", block_type="t", config={}),
            NodeDef(id="b", block_type="t", config={}),
        ],
        edges=[EdgeDef(source="a:missing_port", target="b:input")],
    )
    scheduler = _make_scheduler(wf)
    scheduler._block_outputs["a"] = {"image": "my_image_data"}

    inputs = scheduler._gather_inputs("b")
    # #435: must NOT contain the entire upstream dict
    assert "input" not in inputs


def test_gather_inputs_no_upstream_output() -> None:
    """When upstream has no cached output at all, return empty inputs."""
    wf = WorkflowDefinition(
        id="test",
        description="test",
        nodes=[
            NodeDef(id="a", block_type="t", config={}),
            NodeDef(id="b", block_type="t", config={}),
        ],
        edges=[EdgeDef(source="a:out", target="b:in")],
    )
    scheduler = _make_scheduler(wf)
    # No outputs for "a" at all.

    inputs = scheduler._gather_inputs("b")
    assert inputs == {}
