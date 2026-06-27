"""ADR-051 FR-012 / SC-004: clean cancellation of a paused interaction.

Cancelling a paused interactive block transitions it to CANCELLED, spawns no
compute phase, and releases the intermediate scratch the prompt phase left
behind. Uses a mock runner whose prompt phase reports an intermediate reference
pointing at a real temp file; the test asserts that file is deleted and the
compute phase (``runner.run``) is never invoked.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.engine.events import (
    CANCEL_BLOCK_REQUEST,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition


class _StubInteractive(Block):
    name: ClassVar[str] = "StubInteractive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[], is_collection=False)]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"out": "should-not-run"}


def test_cancel_paused_interaction_releases_scratch_and_skips_compute(tmp_path: Path) -> None:
    # A real scratch file the prompt phase "persisted" as intermediate work.
    scratch = tmp_path / "intermediate_scratch.bin"
    scratch.write_bytes(b"heavy intermediate work")
    assert scratch.exists()

    wf = WorkflowDefinition(
        id="wf-cancel",
        description="ADR-051 cancellation",
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
        "panel_payload": {"options": [1, 2]},
        "intermediate": [{"backend": "filesystem", "path": str(scratch), "format": None, "metadata": None}],
        "environment": None,
    }

    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )

    async def _drive() -> None:
        spawned: list[asyncio.Task] = []

        async def _emit_cancel(block_id: str | None) -> None:
            # Cancel the paused interaction instead of confirming a decision.
            await event_bus.emit(
                EngineEvent(
                    event_type=CANCEL_BLOCK_REQUEST,
                    block_id=block_id,
                    data={"workflow_id": wf.id},
                )
            )

        async def _on_prompt(event: EngineEvent) -> None:
            spawned.append(asyncio.create_task(_emit_cancel(event.block_id)))

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        await scheduler.execute()
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)

    asyncio.run(_drive())

    # SC-004: CANCELLED, zero compute-phase spawns, zero residual scratch.
    assert scheduler._block_states["a"] == BlockState.CANCELLED
    assert runner.run.await_count == 0, "compute phase must not run after cancellation"
    assert not scratch.exists(), "intermediate scratch must be released on cancellation"
    # The engine-held intermediate map is cleared.
    assert "a" not in scheduler._interactive_intermediate
