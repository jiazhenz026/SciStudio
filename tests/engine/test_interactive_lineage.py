"""ADR-051 FR-011 / SC-003: the interactive decision is recorded in lineage,
intermediate scratch is excluded.

Uses a mock runner so the orchestration is deterministic: ``run_prompt`` returns
an intermediate storage reference, the compute phase is invoked with both the
decision and the intermediate threaded into config, and the BLOCK_DONE lineage
config carries ``interactive_response`` but never ``interactive_intermediate``.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.engine.events import (
    BLOCK_DONE,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

_DECISION = {"choice": "blank-run-2"}
_INTERMEDIATE = [{"backend": "zarr", "path": "scratch/xyz", "format": None, "metadata": None}]


class _StubInteractive(Block):
    name: ClassVar[str] = "StubInteractive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[], is_collection=False)]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"out": "ignored-by-mock-runner"}


def _make_scheduler() -> tuple[DAGScheduler, EventBus, AsyncMock, list[EngineEvent]]:
    wf = WorkflowDefinition(
        id="wf-lineage",
        description="ADR-051 lineage",
        nodes=[NodeDef(id="a", block_type="stub-interactive", config={})],
        edges=[],
    )
    event_bus = EventBus()
    registry = MagicMock()
    registry.instantiate.side_effect = lambda name, config=None: _StubInteractive(config or {})
    registry.get_spec.return_value = None
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()
    runner.run_prompt.return_value = {
        "panel_payload": {"runs": ["a", "b"]},
        "intermediate": _INTERMEDIATE,
        "environment": {"python": "3.11"},
    }
    runner.run.return_value = {"out": "computed", "__scistudio_env__": {"python": "3.11"}}

    done_events: list[EngineEvent] = []
    event_bus.subscribe(BLOCK_DONE, lambda e: done_events.append(e))

    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, event_bus, runner, done_events


async def _drive(scheduler: DAGScheduler, event_bus: EventBus) -> None:
    spawned: list[asyncio.Task] = []

    async def _emit_complete(block_id: str | None) -> None:
        await event_bus.emit(EngineEvent(event_type=INTERACTIVE_COMPLETE, block_id=block_id, data=dict(_DECISION)))

    async def _on_prompt(event: EngineEvent) -> None:
        spawned.append(asyncio.create_task(_emit_complete(event.block_id)))

    event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
    await scheduler.execute()
    if spawned:
        await asyncio.gather(*spawned, return_exceptions=True)


def test_decision_recorded_intermediate_excluded() -> None:
    scheduler, event_bus, runner, done_events = _make_scheduler()
    asyncio.run(_drive(scheduler, event_bus))

    assert scheduler._block_states["a"] == BlockState.DONE

    # The compute phase received the decision AND the intermediate references.
    assert runner.run.await_count == 1
    compute_config = runner.run.await_args.args[2]
    assert compute_config["interactive_response"] == _DECISION
    assert compute_config["interactive_intermediate"] == _INTERMEDIATE

    # FR-011 / SC-003: BLOCK_DONE lineage config records the decision but NOT
    # the intermediate scratch references.
    assert done_events, "no BLOCK_DONE emitted"
    recorded = done_events[-1].data["config"]
    assert recorded["interactive_response"] == _DECISION
    assert "interactive_intermediate" not in recorded


def test_synchronous_complete_does_not_hang() -> None:
    """ADR-051 audit P1: a synchronously-delivered interactive_complete resolves.

    A subscriber that emits ``interactive_complete`` from inside the
    ``INTERACTIVE_PROMPT`` handler (no deferral) must still resolve the block.
    Before the fix the rendezvous future was registered AFTER the prompt emit,
    so the synchronous response found no future, was dropped, and the block hung
    forever in PAUSED. The future is now registered before the prompt is
    announced, so the response is delivered even without deferral.
    """
    scheduler, event_bus, runner, _done_events = _make_scheduler()

    async def _drive() -> None:
        async def _on_prompt(event: EngineEvent) -> None:
            # Emit the completion synchronously within the prompt handler.
            await event_bus.emit(
                EngineEvent(
                    event_type=INTERACTIVE_COMPLETE,
                    block_id=event.block_id,
                    data={"workflow_id": "wf-lineage", "response": dict(_DECISION)},
                )
            )

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        # wait_for guards against a regression of the hang (would otherwise block).
        await asyncio.wait_for(scheduler.execute(), timeout=15)

    asyncio.run(_drive())

    assert scheduler._block_states["a"] == BlockState.DONE
    assert runner.run.await_count == 1, "compute phase did not run after a synchronous complete"
    assert runner.run.await_args.args[2]["interactive_response"] == _DECISION


def test_nan_response_is_rejected() -> None:
    """ADR-051 audit P2 / FR-004: a NaN/Infinity decision is rejected (allow_nan=False).

    NaN/Infinity serialize to non-standard JSON tokens under the default
    ``json.dumps``; the runtime must reject them rather than carry them into the
    compute config / lineage. A rejected response fails the block (no compute).
    """
    scheduler, event_bus, runner, _done = _make_scheduler()

    async def _drive() -> None:
        async def _on_prompt(event: EngineEvent) -> None:
            await event_bus.emit(
                EngineEvent(
                    event_type=INTERACTIVE_COMPLETE,
                    block_id=event.block_id,
                    data={"workflow_id": "wf-lineage", "response": {"value": float("nan")}},
                )
            )

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        await asyncio.wait_for(scheduler.execute(), timeout=15)

    asyncio.run(_drive())

    assert scheduler._block_states["a"] == BlockState.ERROR
    assert runner.run.await_count == 0, "compute phase must not run with a non-JSON-safe response"
