"""#2433 — engine events, scheduler scoping and lineage recording carry the run id.

Two runs of the same workflow share a ``workflow_id``. Before #2433 the scheduler
and the lineage recorder told runs apart by that id alone, so a cancel or a
terminal event of one run reached every run of the same workflow on the shared
bus, and a run's blocks could be recorded into another run's lineage.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from scistudio.blocks.base.state import BlockState
from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.recorder import LineageRecorder
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import (
    BLOCK_DONE,
    CANCEL_WORKFLOW_REQUEST,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition


def _scheduler(event_bus: EventBus, runner: Any, *, run_id: str | None) -> DAGScheduler:
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None
    return DAGScheduler(
        workflow=WorkflowDefinition(id="main", nodes=[NodeDef(id="load", block_type="proc")]),
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        run_id=run_id,
    )


def test_every_event_a_run_emits_carries_its_run_id() -> None:
    bus = EventBus()
    seen: list[EngineEvent] = []

    async def record(event: EngineEvent) -> None:
        seen.append(event)

    for event_type in (WORKFLOW_STARTED, WORKFLOW_COMPLETED, BLOCK_DONE, "block_ready", "block_running"):
        bus.subscribe(event_type, record)
    runner = AsyncMock()
    runner.run.return_value = {"out": {"value": 1}}

    scheduler = _scheduler(bus, runner, run_id="run-1")
    asyncio.run(scheduler.execute())

    assert {event.event_type for event in seen} >= {WORKFLOW_STARTED, WORKFLOW_COMPLETED, BLOCK_DONE}
    assert all(event.data.get("run_id") == "run-1" for event in seen)
    assert all(event.data.get("workflow_id") == "main" for event in seen)
    # The block sees the run too, so per-run files it writes are addressable by it.
    config = runner.run.call_args.args[2]
    assert config["run_id"] == "run-1"


def test_a_scheduler_without_a_run_id_emits_the_workflow_scope_only() -> None:
    bus = EventBus()
    seen: list[EngineEvent] = []

    async def record(event: EngineEvent) -> None:
        seen.append(event)

    bus.subscribe(WORKFLOW_STARTED, record)
    runner = AsyncMock()
    runner.run.return_value = {}
    asyncio.run(_scheduler(bus, runner, run_id=None).execute())

    assert seen[0].data == {"workflow_id": "main"}


def test_a_cancel_addressed_to_one_run_leaves_another_run_of_the_same_workflow_alone() -> None:
    async def scenario() -> tuple[BlockState, BlockState]:
        bus = EventBus()
        release = asyncio.Event()

        async def wait_for_release(block: Any, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
            await release.wait()
            return {}

        runner = AsyncMock()
        runner.run.side_effect = wait_for_release
        first = _scheduler(bus, runner, run_id="run-1")
        second = _scheduler(bus, runner, run_id="run-2")
        tasks = [asyncio.create_task(first.execute()), asyncio.create_task(second.execute())]
        for _ in range(50):
            if (
                first.block_states()["load"] == BlockState.RUNNING
                and second.block_states()["load"] == BlockState.RUNNING
            ):
                break
            await asyncio.sleep(0.01)

        await bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": "main", "run_id": "run-1"}))
        states = (first.block_states()["load"], second.block_states()["load"])
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
        first.dispose()
        second.dispose()
        return states

    first_state, second_state = asyncio.run(scenario())
    assert first_state == BlockState.CANCELLED
    assert second_state == BlockState.RUNNING


def _recorder(bus: EventBus, run_id: str) -> tuple[LineageRecorder, LineageStore]:
    store = LineageStore(":memory:")
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id="main",
            workflow_yaml_snapshot="",
            started_at="2026-09-15T00:00:00",
            status="running",
            environment_snapshot={},
        )
    )
    return LineageRecorder(bus, lineage_store=store, run_id=run_id, workflow_id="main"), store


def test_the_recorder_ignores_another_run_of_the_same_workflow() -> None:
    bus = EventBus()
    _recorder_one, store = _recorder(bus, "run-1")

    asyncio.run(
        bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="load", data={"workflow_id": "main", "run_id": "run-2"}))
    )
    assert store.list_block_executions("run-1") == []

    asyncio.run(
        bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="load", data={"workflow_id": "main", "run_id": "run-1"}))
    )
    assert [row["block_id"] for row in store.list_block_executions("run-1")] == ["load"]


def test_the_recorder_still_matches_an_event_without_a_run_id_by_workflow() -> None:
    bus = EventBus()
    _recorder_one, store = _recorder(bus, "run-1")

    asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="other", data={"workflow_id": "elsewhere"})))
    asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="load", data={"workflow_id": "main"})))

    assert [row["block_id"] for row in store.list_block_executions("run-1")] == ["load"]
