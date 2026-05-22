"""Contract tests for EventBus lifecycle payloads.

This slice covers the public runtime events consumed by API/WebSocket/lineage
layers. Rows marked xfail document desired #1454 contract drift without
changing product code in this test-only worker task.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_READY,
    BLOCK_RUNNING,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

WORKFLOW_ID = "eventbus-lifecycle-contract"


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id=WORKFLOW_ID,
        nodes=[
            NodeDef(id="A", block_type="contract.type.A", config={"alpha": 1}),
            NodeDef(id="B", block_type="contract.type.B", config={"beta": 2}),
        ],
        edges=[EdgeDef(source="A:out", target="B:in")],
    )


def _make_scheduler(
    *,
    bus: EventBus | None = None,
    runner: Any | None = None,
) -> tuple[DAGScheduler, EventBus]:
    event_bus = bus or EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None
    scheduler_runner = runner or AsyncMock()
    scheduler_runner.run.return_value = {"out": "ok"}

    scheduler = DAGScheduler(
        workflow=_workflow(),
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=scheduler_runner,
        registry=None,
        checkpoint_manager=None,
    )
    return scheduler, event_bus


def _capture(
    bus: EventBus,
    event_types: tuple[str, ...] = (
        BLOCK_READY,
        BLOCK_RUNNING,
        BLOCK_DONE,
        BLOCK_ERROR,
        BLOCK_CANCELLED,
        BLOCK_SKIPPED,
    ),
) -> list[EngineEvent]:
    seen: list[EngineEvent] = []
    for event_type in event_types:
        bus.subscribe(event_type, seen.append)
    return seen


def _event_pairs(events: list[EngineEvent]) -> list[tuple[str, str | None]]:
    return [(event.event_type, event.block_id) for event in events]


def _assert_public_identity(
    event: EngineEvent,
    *,
    block_id: str,
    workflow_id: str = WORKFLOW_ID,
) -> None:
    assert event.block_id == block_id
    assert event.data["workflow_id"] == workflow_id


def _assert_terminal_payload(
    event: EngineEvent,
    *,
    block_id: str,
    block_type: str,
) -> None:
    _assert_public_identity(event, block_id=block_id)
    assert event.data["block_type"] == block_type
    assert "block_version" in event.data
    assert isinstance(event.data["config"], dict)
    assert isinstance(event.data["inputs"], dict)
    assert isinstance(event.data["input_object_ids"], dict)
    assert isinstance(event.data["output_object_ids"], dict)


def test_linear_workflow_emits_ready_running_done_with_public_identity() -> None:
    """A small linear run exposes stable lifecycle identity to subscribers."""
    bus = EventBus()
    seen = _capture(bus)
    scheduler, _ = _make_scheduler(bus=bus)

    asyncio.run(scheduler.execute())

    assert _event_pairs(seen) == [
        (BLOCK_READY, "A"),
        (BLOCK_RUNNING, "A"),
        (BLOCK_DONE, "A"),
        (BLOCK_READY, "B"),
        (BLOCK_RUNNING, "B"),
        (BLOCK_DONE, "B"),
    ]
    for event in seen:
        _assert_public_identity(event, block_id=event.block_id or "")


@pytest.mark.parametrize(
    ("event_type", "block_id", "expected_block_type"),
    [
        pytest.param(
            BLOCK_READY,
            "A",
            "contract.type.A",
            marks=pytest.mark.xfail(
                reason="#1454: BLOCK_READY should carry block_type for downstream lifecycle consumers",
                strict=False,
            ),
            id="ready-block-type",
        ),
        pytest.param(
            BLOCK_RUNNING,
            "A",
            "contract.type.A",
            marks=pytest.mark.xfail(
                reason="#1454: BLOCK_RUNNING should carry block_type for downstream lifecycle consumers",
                strict=False,
            ),
            id="running-block-type",
        ),
        pytest.param(BLOCK_DONE, "A", "contract.type.A", id="done-block-type"),
        pytest.param(
            BLOCK_READY,
            "B",
            "contract.type.B",
            marks=pytest.mark.xfail(
                reason="#1454: BLOCK_READY should carry block_type for downstream lifecycle consumers",
                strict=False,
            ),
            id="downstream-ready-block-type",
        ),
        pytest.param(
            BLOCK_RUNNING,
            "B",
            "contract.type.B",
            marks=pytest.mark.xfail(
                reason="#1454: BLOCK_RUNNING should carry block_type for downstream lifecycle consumers",
                strict=False,
            ),
            id="downstream-running-block-type",
        ),
        pytest.param(BLOCK_DONE, "B", "contract.type.B", id="downstream-done-block-type"),
    ],
)
def test_public_lifecycle_events_carry_consistent_workflow_id_and_block_type(
    event_type: str,
    block_id: str,
    expected_block_type: str,
) -> None:
    """Public lifecycle events should carry workflow_id and block_type."""
    bus = EventBus()
    seen = _capture(bus)
    scheduler, _ = _make_scheduler(bus=bus)

    asyncio.run(scheduler.execute())

    matching = [
        event
        for event in seen
        if event.event_type == event_type and event.block_id == block_id
    ]
    assert len(matching) == 1
    event = matching[0]
    _assert_public_identity(event, block_id=block_id)
    assert event.data["block_type"] == expected_block_type


@pytest.mark.parametrize(
    ("scenario", "terminal_event", "block_id", "block_type", "configure", "trigger"),
    [
        (
            "runner-error",
            BLOCK_ERROR,
            "A",
            "contract.type.A",
            lambda scheduler: None,
            lambda scheduler, bus: scheduler.execute(),
        ),
        (
            "cancel-running",
            BLOCK_CANCELLED,
            "A",
            "contract.type.A",
            lambda scheduler: scheduler._block_states.update(
                {"A": BlockState.RUNNING, "B": BlockState.IDLE}
            ),
            lambda scheduler, bus: bus.emit(
                EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="A")
            ),
        ),
        (
            "workflow-cancel-skips-idle",
            BLOCK_SKIPPED,
            "B",
            "contract.type.B",
            lambda scheduler: scheduler._block_states.update(
                {"A": BlockState.DONE, "B": BlockState.IDLE}
            ),
            lambda scheduler, bus: bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST)),
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_error_cancel_skip_terminal_events_have_downstream_payload_shape(
    scenario: str,
    terminal_event: str,
    block_id: str,
    block_type: str,
    configure: Callable[[DAGScheduler], None],
    trigger: Callable[[DAGScheduler, EventBus], Any],
) -> None:
    """Terminal events expose the payload shape API/WS/lineage layers need."""
    bus = EventBus()
    seen = _capture(bus, (BLOCK_ERROR, BLOCK_CANCELLED, BLOCK_SKIPPED))
    runner = AsyncMock()

    async def _run(block: Any, inputs: dict[str, Any], config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if scenario == "runner-error" and block.id == "A":
            raise RuntimeError("contract boom")
        return {"out": "ok"}

    runner.run.side_effect = _run
    scheduler, _ = _make_scheduler(bus=bus, runner=runner)
    configure(scheduler)

    asyncio.run(trigger(scheduler, bus))

    events = [
        event
        for event in seen
        if event.event_type == terminal_event and event.block_id == block_id
    ]
    assert len(events) == 1
    event = events[0]
    _assert_terminal_payload(event, block_id=block_id, block_type=block_type)
    if terminal_event == BLOCK_ERROR:
        assert event.data["error"]
        assert event.data["error_summary"]


def test_eventbus_subscriber_failure_does_not_block_later_subscribers() -> None:
    """One failing subscriber is isolated from later EventBus subscribers."""
    bus = EventBus()
    calls: list[str] = []
    received: list[EngineEvent] = []

    def bad_subscriber(event: EngineEvent) -> None:
        calls.append("bad")
        raise RuntimeError("subscriber failed")

    def later_subscriber(event: EngineEvent) -> None:
        calls.append("later")
        received.append(event)

    bus.subscribe(BLOCK_DONE, bad_subscriber)
    bus.subscribe(BLOCK_DONE, later_subscriber)

    event = EngineEvent(
        event_type=BLOCK_DONE,
        block_id="A",
        data={"workflow_id": WORKFLOW_ID, "block_type": "contract.type.A"},
    )
    asyncio.run(bus.emit(event))

    assert calls == ["bad", "later"]
    assert received == [event]
