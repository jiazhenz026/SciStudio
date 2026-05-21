"""Tests for ``DAGScheduler._build_block_terminal_data`` (D38-3.2).

Closes audit findings:

* **D38-3.1a P1-1 / D38-3.1b P1-3**: BLOCK_ERROR / BLOCK_CANCELLED /
  BLOCK_SKIPPED emits previously carried only ``{workflow_id, error?}``.
  The recorder then wrote empty ``block_type`` / ``block_version`` /
  ``block_config_resolved`` columns into ``block_executions`` for any
  non-completed block, breaking ADR §3.7 Q3 (methods export, "which
  blocks ran") for failed / cancelled / skipped blocks.

D38-3.2 extracts ``_build_block_terminal_data`` and routes all eight
terminal emit sites in :mod:`scheduler` through it so the recorder
receives consistent metadata regardless of how the block terminated.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_ERROR,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


def _capturing_bus() -> tuple[EventBus, list[EngineEvent]]:
    bus = EventBus()
    seen: list[EngineEvent] = []

    async def _capture(event: EngineEvent) -> None:
        seen.append(event)

    for et in (BLOCK_ERROR, BLOCK_CANCELLED, BLOCK_SKIPPED):
        bus.subscribe(et, _capture)
    return bus, seen


def _build_scheduler(workflow: WorkflowDefinition, bus: EventBus) -> DAGScheduler:
    runner = MagicMock()
    runner.run = AsyncMock(return_value={})
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    return DAGScheduler(
        workflow=workflow,
        event_bus=bus,
        resource_manager=resource_manager,
        process_registry=None,
        runner=runner,
        registry=None,
        checkpoint_manager=None,
    )


class TestTerminalDataFromAllPaths:
    def test_propagate_skip_carries_block_type(self) -> None:
        """``_propagate_skip`` emits SKIPPED with block_type populated.

        Build a 2-node DAG A → B. Mark A as ERROR. Calling
        ``_propagate_skip`` should emit BLOCK_SKIPPED for B carrying
        ``block_type='TypeB'``.
        """
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="TypeA"), NodeDef(id="B", block_type="TypeB")],
            edges=[EdgeDef(source="A:out", target="B:in")],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        # Pre-set A to ERROR so propagate_skip considers B.
        from scistudio.blocks.base.state import BlockState

        scheduler._block_states["A"] = BlockState.ERROR

        asyncio.run(scheduler._propagate_skip("A", "error"))

        skipped = [e for e in seen if e.event_type == BLOCK_SKIPPED]
        assert len(skipped) == 1
        assert skipped[0].block_id == "B"
        assert skipped[0].data["block_type"] == "TypeB"
        assert skipped[0].data["workflow_id"] == wf.id

    def test_cancel_block_request_carries_block_type(self) -> None:
        """``_on_cancel_block`` emits CANCELLED with block_type populated."""
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="X", block_type="TypeX")],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        # No registry / process registry, no active task — _on_cancel_block
        # still emits the CANCELLED event.
        asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="X")))

        cancelled = [e for e in seen if e.event_type == BLOCK_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0].block_id == "X"
        assert cancelled[0].data["block_type"] == "TypeX"

    def test_build_terminal_data_handles_missing_node(self) -> None:
        """Calling _build_block_terminal_data for an unknown node id
        returns a payload with empty block_type rather than raising."""
        wf = WorkflowDefinition(nodes=[NodeDef(id="A", block_type="TypeA")], edges=[])
        bus = EventBus()
        scheduler = _build_scheduler(wf, bus)

        data = scheduler._build_block_terminal_data(node_id="missing-id", error="x")
        assert data["block_type"] == ""
        assert data["error"] == "x"
        assert data["workflow_id"] == wf.id

    def test_build_terminal_data_includes_config_from_node(self) -> None:
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="TypeA", config={"k": "v"})],
            edges=[],
        )
        bus = EventBus()
        scheduler = _build_scheduler(wf, bus)

        data = scheduler._build_block_terminal_data(node_id="A")
        assert data["config"] == {"k": "v"}
        assert data["block_type"] == "TypeA"
