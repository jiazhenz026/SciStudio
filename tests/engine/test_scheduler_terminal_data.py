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
        """``_on_cancel_block`` emits CANCELLED with block_type populated.

        #1376: an IDLE block now skips to SKIPPED, so seed RUNNING
        first — the architecture state table only permits
        RUNNING/PAUSED → CANCELLED.
        """
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="X", block_type="TypeX")],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        # Pre-set RUNNING so _on_cancel_block takes the
        # state-table-permitted RUNNING → CANCELLED branch.
        from scistudio.blocks.base.state import BlockState

        scheduler._block_states["X"] = BlockState.RUNNING

        asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="X")))

        cancelled = [e for e in seen if e.event_type == BLOCK_CANCELLED]
        assert len(cancelled) == 1
        assert cancelled[0].block_id == "X"
        assert cancelled[0].data["block_type"] == "TypeX"

    def test_cancel_block_idle_is_noop(self) -> None:
        """#1376: cancelling an IDLE block is a no-op.

        The architecture state table in
        ``docs/architecture/ARCHITECTURE.md`` §5.2 only permits
        ``CANCELLED`` from ``RUNNING`` / ``PAUSED``. The executable
        spec in
        ``tests/engine/test_scheduler_state_machine_contract.py``
        ``test_cancel_block_state_table[IDLE-noop]`` specifies a
        no-op: state stays ``IDLE`` and no lifecycle event fires.
        ``_on_cancel_workflow`` is responsible for skipping
        not-yet-started blocks when the whole workflow is cancelled.
        """
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="X", block_type="TypeX")],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        from scistudio.blocks.base.state import BlockState

        assert scheduler._block_states["X"] == BlockState.IDLE

        asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="X")))

        # State unchanged and no lifecycle event fired.
        assert scheduler._block_states["X"] == BlockState.IDLE
        assert "X" not in scheduler.skip_reasons
        assert seen == []

    def test_cancel_block_ready_is_noop(self) -> None:
        """#1376: cancelling a READY block is also a no-op.

        Mirror of the IDLE case for the second non-cancellable
        pre-start state.
        """
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="X", block_type="TypeX")],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        from scistudio.blocks.base.state import BlockState

        scheduler._block_states["X"] = BlockState.READY

        asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="X")))

        assert scheduler._block_states["X"] == BlockState.READY
        assert seen == []

    def test_cancel_block_terminal_state_is_noop(self) -> None:
        """#1376: cancelling a DONE/ERROR/SKIPPED block does nothing.

        Re-entering CANCELLED from a terminal state would violate
        the state table and would re-emit a contradictory terminal
        event. The handler must ignore the request and preserve the
        existing state.
        """
        wf = WorkflowDefinition(
            nodes=[
                NodeDef(id="A", block_type="TypeA"),
                NodeDef(id="B", block_type="TypeB"),
                NodeDef(id="C", block_type="TypeC"),
            ],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        from scistudio.blocks.base.state import BlockState

        # Seed each block in a different terminal state.
        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_states["B"] = BlockState.ERROR
        scheduler._block_states["C"] = BlockState.SKIPPED

        for block_id in ("A", "B", "C"):
            asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id=block_id)))

        # No terminal events emitted by _on_cancel_block — the seeded
        # terminal states are preserved untouched.
        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.ERROR
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        for block_id in ("A", "B", "C"):
            for event_type in (BLOCK_CANCELLED, BLOCK_SKIPPED, BLOCK_ERROR):
                matching = [e for e in seen if e.event_type == event_type and e.block_id == block_id]
                assert matching == [], f"unexpected {event_type} re-emitted for {block_id}"

    def test_cancel_block_unknown_block_is_silent(self) -> None:
        """#1376: cancelling an unknown block id is a silent no-op.

        Defensive check: the scheduler only tracks blocks in its
        DAG. A cancel for an unknown id must not raise and must not
        synthesize any terminal event.
        """
        wf = WorkflowDefinition(
            nodes=[NodeDef(id="A", block_type="TypeA")],
            edges=[],
        )
        bus, seen = _capturing_bus()
        scheduler = _build_scheduler(wf, bus)

        asyncio.run(scheduler._on_cancel_block(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="does-not-exist")))

        assert seen == []

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
