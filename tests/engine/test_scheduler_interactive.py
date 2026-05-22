"""Regression tests for interactive scheduler path collection normalization (#1370).

#1338 added engine-side wrapping of bare ``DataObject`` / ``list[DataObject]``
outputs on ``is_collection=True`` ports via
:func:`scistudio.engine.runners.worker._normalize_outputs`, but the call site
was only wired into the worker subprocess path and ``_run_and_finalize``'s
in-process path. ``_run_interactive`` stored the interactive block's result
directly, bypassing the ADR-020 §3 transport contract.

These tests construct a minimal interactive block, drive
``DAGScheduler._run_interactive`` end-to-end with a mock registry, and assert
that bare-DataObject and bare-``list[DataObject]`` outputs on
``is_collection=True`` ports are normalised into :class:`Collection` instances
before they land in ``self._block_outputs``.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.engine.events import (
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_array() -> Array:
    """Return a bare :class:`Array` with deterministic axes/shape."""
    return Array(axes=["y", "x"], shape=(4, 4), dtype="uint8")


class _BareInteractiveBlock(Block):
    """Interactive block whose ``run`` returns a bare ``DataObject``.

    The block declares an ``is_collection=True`` output port and returns a
    raw :class:`Array` (not a :class:`Collection`). Without #1370's
    ``_normalize_outputs`` call the bare instance would land in
    ``_block_outputs`` unwrapped, violating ADR-020 §3.
    """

    name: ClassVar[str] = "BareInteractive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="out", accepted_types=[Array], is_collection=True),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # ``DAGScheduler._instantiate_block`` assigns ``.id`` after construction.
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Minimal prompt; the test scheduler ignores the contents."""
        return {"prompt": "select"}

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        """Return a bare :class:`Array` on the ``is_collection=True`` port."""
        return {"out": _make_array()}


class _BareListInteractiveBlock(_BareInteractiveBlock):
    """Interactive block whose ``run`` returns a bare ``list[DataObject]``."""

    name: ClassVar[str] = "BareListInteractive"

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        """Return a bare ``list[Array]`` on the ``is_collection=True`` port."""
        return {"out": [_make_array(), _make_array(), _make_array()]}


def _make_registry(block_cls: type[Block]) -> MagicMock:
    """Return a mock :class:`BlockRegistry` that instantiates *block_cls*.

    The scheduler calls :meth:`BlockRegistry.instantiate(name, config)` from
    ``_instantiate_block``. The returned instance carries its own
    ``execution_mode`` ClassVar so the ``is_interactive`` branch of
    ``_dispatch`` fires and routes into ``_run_interactive``.
    """
    registry = MagicMock()

    def _instantiate(name: str, config: dict[str, Any] | None = None) -> Block:
        return block_cls(config or {})

    registry.instantiate.side_effect = _instantiate
    registry.get_spec.return_value = None
    return registry


def _make_workflow() -> WorkflowDefinition:
    """Single-node workflow whose block resolves to the interactive stub."""
    return WorkflowDefinition(
        id="test-wf-interactive",
        description="interactive normalize regression",
        nodes=[NodeDef(id="a", block_type="bare-interactive", config={})],
        edges=[],
    )


def _make_scheduler(block_cls: type[Block]) -> tuple[DAGScheduler, EventBus]:
    """Build a DAGScheduler whose registry returns *block_cls*."""
    wf = _make_workflow()
    event_bus = EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None
    runner = AsyncMock()
    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=_make_registry(block_cls),
    )
    return scheduler, event_bus


async def _drive_interactive(scheduler: DAGScheduler, event_bus: EventBus) -> None:
    """Run ``scheduler.execute()`` and resolve the interactive future.

    The scheduler's interactive path:

    1. emits ``INTERACTIVE_PROMPT``
    2. awaits a ``loop.create_future()``
    3. resumes once ``INTERACTIVE_COMPLETE`` arrives via ``_on_interactive_complete``

    The future is created **after** step 1, so the prompt handler cannot
    synchronously emit ``INTERACTIVE_COMPLETE`` — by the time the
    completion handler runs, the future doesn't exist yet and the event is
    silently dropped. Instead we schedule the completion emit on the event
    loop as a follow-up task, then return from the prompt handler so
    ``_run_interactive`` can advance to ``loop.create_future()`` and
    ``await future``. The deferred task fires after the future exists,
    resolving it and unblocking the block ``run``.
    """
    completion_scheduled = asyncio.Event()
    # Strong references to the deferred emit tasks so Python does not
    # garbage-collect them mid-await (ruff RUF006).
    spawned_tasks: list[asyncio.Task[None]] = []

    async def _emit_completion(block_id: str | None) -> None:
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id=block_id,
                data={"choice": "ok"},
            )
        )

    async def _on_prompt(event: EngineEvent) -> None:
        # Defer the INTERACTIVE_COMPLETE emit so ``_run_interactive`` has a
        # chance to register its pending future first. ``create_task``
        # returns immediately; the task is awaited via the event loop.
        task = asyncio.create_task(_emit_completion(event.block_id), name="test:emit-complete")
        spawned_tasks.append(task)
        completion_scheduled.set()

    event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
    await scheduler.execute()
    # Ensure the prompt handler fired exactly once (sanity guard).
    assert completion_scheduled.is_set()
    # Drain spawned tasks so the test does not leave dangling futures.
    if spawned_tasks:
        await asyncio.gather(*spawned_tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Regression tests for #1370
# ---------------------------------------------------------------------------


class TestInteractiveCollectionNormalize:
    """``_run_interactive`` must apply ``_normalize_outputs`` like the non-interactive paths."""

    def test_interactive_wraps_bare_dataobject_on_is_collection_port(self) -> None:
        """Bare :class:`Array` on an ``is_collection=True`` port is auto-wrapped.

        Without #1370's fix the stored output would be the raw ``Array`` and
        the downstream port would see a non-Collection value, violating the
        ADR-020 §3 transport contract.
        """
        scheduler, event_bus = _make_scheduler(_BareInteractiveBlock)

        asyncio.run(_drive_interactive(scheduler, event_bus))

        assert scheduler._block_states["a"] == BlockState.DONE
        stored = scheduler._block_outputs["a"]
        assert isinstance(stored, dict)
        wrapped = stored["out"]
        assert isinstance(wrapped, Collection), (
            f"interactive output on is_collection=True port should be wrapped; got {type(wrapped).__name__}"
        )
        assert len(wrapped) == 1
        assert isinstance(wrapped[0], Array)
        # _normalize_outputs uses type(value) per #1330; for a bare Array this
        # is Array itself.
        assert wrapped.item_type is Array

    def test_interactive_packs_bare_list_of_dataobjects_into_collection(self) -> None:
        """Bare ``list[Array]`` on an ``is_collection=True`` port is packed.

        ADR-020 §3 covers "multi-object input is a longer Collection" — the
        engine must pack a native ``list`` of homogeneous DataObjects into a
        single Collection so the downstream block does not observe a bare
        list. The interactive path used to drop this case.
        """
        scheduler, event_bus = _make_scheduler(_BareListInteractiveBlock)

        asyncio.run(_drive_interactive(scheduler, event_bus))

        assert scheduler._block_states["a"] == BlockState.DONE
        stored = scheduler._block_outputs["a"]
        assert isinstance(stored, dict)
        packed = stored["out"]
        assert isinstance(packed, Collection), (
            f"interactive output list on is_collection=True port should be packed; got {type(packed).__name__}"
        )
        assert len(packed) == 3
        assert all(isinstance(item, Array) for item in packed)
        assert packed.item_type is Array
