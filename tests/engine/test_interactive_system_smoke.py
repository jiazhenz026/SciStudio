"""ADR-051 system-level / e2e smoke for interactive data-processing blocks.

These tests drive the FULL runtime path — a real :class:`DAGScheduler` with a
real :class:`LocalRunner` spawning real worker subprocesses — and exercise the
integration shapes the existing per-block / single-block suites do not:

* ``test_multi_block_interactive_workflow_end_to_end`` (FR-005/FR-006/FR-009/
  FR-011, SC-001): an interactive block wired *between* two non-interactive
  blocks. The upstream block's output becomes the interactive block's real
  input (its panel view is built from it), the workflow pauses exactly once at
  the right node, the decision drives the compute phase, and a downstream block
  computes from the interactive result. Proves pause-and-resume at the correct
  node and correct downstream/output state through the real scheduler.
* ``test_real_subprocess_cancellation_releases_and_skips_compute`` (FR-012,
  SC-004): reach an interactive block via the real runner, PAUSE it, then cancel
  (CANCEL_BLOCK_REQUEST). The block ends CANCELLED with no compute output — the
  real runner path, complementing the existing mock-runner cancellation test.
* ``test_non_json_panel_payload_fails_block_in_real_subprocess`` (FR-004): an
  interactive block whose ``prepare_prompt`` returns a non-JSON ``panel_payload``
  is failed by the real prompt-phase worker as an isolated block error, not a
  silent pass — the block never pauses and runs no compute phase.
* ``test_real_scan_registers_interactive_blocks_and_rejects_malformed``
  (FR-002/FR-007/FR-014, SC-002/SC-005/SC-006): a real ``BlockRegistry().scan()``
  registers Data Router and Pair Editor *with* their panel manifests (resolved
  through the real scan -> instantiate path), and a malformed interactive block
  dropped into a scanned source is rejected at scan time end-to-end (not just by
  the unit validator) while the good blocks still register.

Determinism: no sleeps/races. The completion/cancel emit is scheduled as a
follow-up task from the INTERACTIVE_PROMPT subscriber (the deferred pattern from
``test_interactive_two_phase.py``), so the interactive future already exists when
the emit runs.

Down-scoped candidate — migration parity at the *system* level. Running
``DataRouter`` / ``PairEditor`` through the real two-phase subprocess path with
real ``Collection`` inputs is disproportionate here: ``build_worker_payload``
``json.dumps`` the inputs, so a Collection of in-memory ``DataObject`` items is
not transportable to the worker — it must first be persisted to a storage
backend (zarr/arrow) by an upstream loader block and reconstructed via the
TypeRegistry. That is exactly the disproportionate storage-backend setup ADR-051
test guidance says to avoid faking. Their routing/reorder parity is already
covered at the block level by ``tests/blocks/test_data_router.py`` and
``tests/blocks/test_pair_editor.py`` (real Collections, in-process), and their
two-phase runtime routing is exercised generically by the multi-block test here.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.blocks.registry import BlockRegistry
from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_PAUSED,
    CANCEL_BLOCK_REQUEST,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

pytestmark = pytest.mark.timeout(120)


def _instantiate(name: str, config: dict[str, Any] | None = None) -> Any:
    """Map a workflow ``block_type`` to its fixture block (mirrors registry.instantiate)."""
    from tests.fixtures.interactive_blocks import (
        DoubleValueBlock,
        EmitNumbersBlock,
        NonJsonPanelBlock,
        SelectFromInputBlock,
        SelectOptionBlock,
    )

    mapping = {
        "emit-numbers": EmitNumbersBlock,
        "select-from-input": SelectFromInputBlock,
        "double-value": DoubleValueBlock,
        "non-json-panel": NonJsonPanelBlock,
        "select-option": SelectOptionBlock,
    }
    return mapping[name](config or {})


def _make_scheduler(wf: WorkflowDefinition) -> tuple[DAGScheduler, EventBus]:
    """Build a scheduler over a real LocalRunner + ProcessRegistry (real subprocesses).

    Only the block registry and resource manager are mocked; ``instantiate``
    resolves fixture blocks by workflow ``block_type`` and ``get_spec`` returns
    ``None`` (no version lookup needed for these JSON-able fixtures).
    """
    event_bus = EventBus()
    process_registry = ProcessRegistry()
    runner = LocalRunner(event_bus=event_bus, registry=process_registry)

    registry = MagicMock()
    registry.instantiate.side_effect = _instantiate
    registry.get_spec.return_value = None
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True

    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, event_bus


# ---------------------------------------------------------------------------
# Candidate 1: multi-block workflow with an interactive node in the middle.
# ---------------------------------------------------------------------------


def test_multi_block_interactive_workflow_end_to_end() -> None:
    """An interactive block wired between two non-interactive blocks, driven e2e.

    Graph: ``emit -> select(interactive) -> double``. The interactive block
    builds its panel from the upstream numbers, the user picks index 2, and the
    downstream block doubles the chosen value. Asserts the pause happens exactly
    once at the interactive node and the whole chain's output state is correct.
    """
    wf = WorkflowDefinition(
        id="wf-multi-interactive",
        description="ADR-051 multi-block interactive smoke",
        nodes=[
            NodeDef(id="emit", block_type="emit-numbers", config={"numbers": [10, 20, 30, 40]}),
            NodeDef(id="pick", block_type="select-from-input", config={}),
            NodeDef(id="sink", block_type="double-value", config={}),
        ],
        edges=[
            EdgeDef(source="emit:numbers", target="pick:numbers"),
            EdgeDef(source="pick:selected", target="sink:value"),
        ],
    )
    scheduler, event_bus = _make_scheduler(wf)

    prompts: list[EngineEvent] = []
    done_by_block: dict[str, EngineEvent] = {}
    event_bus.subscribe(BLOCK_DONE, lambda e: done_by_block.__setitem__(e.block_id, e))

    async def _drive() -> None:
        spawned: list[asyncio.Task[None]] = []

        async def _emit_complete(block_id: str | None) -> None:
            # Mirror the real api/ws.py frame: run-scoping workflow_id alongside
            # the decision nested under ``response``.
            await event_bus.emit(
                EngineEvent(
                    event_type=INTERACTIVE_COMPLETE,
                    block_id=block_id,
                    data={"workflow_id": wf.id, "response": {"index": 2}},
                )
            )

        async def _on_prompt(event: EngineEvent) -> None:
            prompts.append(event)
            spawned.append(asyncio.create_task(_emit_complete(event.block_id)))

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        await scheduler.execute()
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)

    asyncio.run(_drive())

    # Every block ran and finished DONE.
    assert scheduler._block_states["emit"] == BlockState.DONE
    assert scheduler._block_states["pick"] == BlockState.DONE
    assert scheduler._block_states["sink"] == BlockState.DONE

    # The workflow paused exactly once, and at the interactive node (FR-005/FR-006).
    assert len(prompts) == 1
    assert prompts[0].block_id == "pick"

    # The interactive panel was built from the REAL upstream input, in a worker
    # subprocess (prompt pid differs from this process's pid -> SC-001).
    panel_payload = prompts[0].data["panel_payload"]
    assert panel_payload["choices"] == [10, 20, 30, 40]
    assert panel_payload["prompt_pid"] != os.getpid()
    # The prompt carries the manifest so the frontend resolves the panel (FR-007).
    assert prompts[0].data["panel_manifest"]["panel_id"] == "test.interactive.select_from_input"

    # The decision drove the compute phase, and its result flowed downstream.
    assert scheduler._block_outputs["emit"]["numbers"] == [10, 20, 30, 40]
    assert scheduler._block_outputs["pick"]["selected"] == 30, "compute phase ignored the injected decision"
    assert scheduler._block_outputs["sink"]["doubled"] == 60, "downstream block did not consume the interactive result"

    # FR-011: the decision is recorded in the interactive block's BLOCK_DONE
    # lineage config; the non-interactive blocks carry no such field.
    assert done_by_block["pick"].data["config"]["interactive_response"] == {"index": 2}
    assert "interactive_response" not in done_by_block["emit"].data["config"]


# ---------------------------------------------------------------------------
# Candidate 2: real-subprocess cancellation of a paused interaction.
# ---------------------------------------------------------------------------


def test_real_subprocess_cancellation_releases_and_skips_compute() -> None:
    """Reach an interactive block via the real runner, PAUSE, then cancel.

    Complements ``test_interactive_cancellation.py`` (mock runner): here the
    prompt phase runs in a real worker subprocess, the block pauses, and a
    CANCEL_BLOCK_REQUEST transitions it to CANCELLED with no compute phase and no
    output (FR-012 / SC-004).
    """
    wf = WorkflowDefinition(
        id="wf-cancel-real",
        description="ADR-051 real-subprocess cancellation smoke",
        nodes=[NodeDef(id="a", block_type="select-option", config={"options": [0, 1, 2]})],
        edges=[],
    )
    scheduler, event_bus = _make_scheduler(wf)

    prompts: list[EngineEvent] = []
    paused: list[EngineEvent] = []
    done: list[EngineEvent] = []
    event_bus.subscribe(BLOCK_PAUSED, lambda e: paused.append(e))
    event_bus.subscribe(BLOCK_DONE, lambda e: done.append(e))

    async def _drive() -> None:
        spawned: list[asyncio.Task[None]] = []

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
            prompts.append(event)
            # Deferred emit: by the time this task runs, ``_run_interactive`` has
            # created the interactive future and is awaiting it in PAUSED.
            spawned.append(asyncio.create_task(_emit_cancel(event.block_id)))

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        await scheduler.execute()
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)

    asyncio.run(_drive())

    # We genuinely reached the paused interactive block via the real runner: the
    # prompt phase ran in a worker subprocess (pid differs) and PAUSED was emitted.
    assert len(prompts) == 1
    assert paused, "block never reached PAUSED"
    assert prompts[0].data["panel_payload"]["prompt_pid"] != os.getpid()

    # SC-004: CANCELLED, zero compute output, intermediate map cleared.
    assert scheduler._block_states["a"] == BlockState.CANCELLED
    assert "a" not in scheduler._block_outputs, "compute phase must not produce outputs after cancellation"
    assert "a" not in scheduler._interactive_intermediate
    assert not any(e.block_id == "a" for e in done), "no BLOCK_DONE may be emitted for a cancelled interaction"


# ---------------------------------------------------------------------------
# Candidate 3: FR-004 — non-JSON panel payload fails the block (system proof).
# ---------------------------------------------------------------------------


def test_non_json_panel_payload_fails_block_in_real_subprocess() -> None:
    """A non-JSON ``panel_payload`` is rejected by the real prompt-phase worker.

    ADR-051 FR-004: the runtime must reject a payload that is not JSON-safe
    rather than pickle or truncate it. The block fails as an isolated block error
    (BLOCK_ERROR), never pauses, and never runs a compute phase.
    """
    wf = WorkflowDefinition(
        id="wf-non-json",
        description="ADR-051 FR-004 non-JSON panel payload smoke",
        nodes=[NodeDef(id="a", block_type="non-json-panel", config={})],
        edges=[],
    )
    scheduler, event_bus = _make_scheduler(wf)

    prompts: list[EngineEvent] = []
    paused: list[EngineEvent] = []
    errors: list[EngineEvent] = []
    event_bus.subscribe(INTERACTIVE_PROMPT, lambda e: prompts.append(e))
    event_bus.subscribe(BLOCK_PAUSED, lambda e: paused.append(e))
    event_bus.subscribe(BLOCK_ERROR, lambda e: errors.append(e))

    asyncio.run(scheduler.execute())

    # The block failed as an isolated error before ever pausing or prompting.
    assert scheduler._block_states["a"] == BlockState.ERROR
    assert not paused, "a block with a non-JSON panel payload must not reach PAUSED"
    assert not prompts, "a non-JSON panel payload must not be emitted to the frontend"
    assert "a" not in scheduler._block_outputs, "no compute phase may run after a failed prompt phase"

    # The failure is surfaced (not a silent pass) and identifies the JSON cause.
    assert errors, "no BLOCK_ERROR emitted for the non-JSON panel payload"
    error_text = str(errors[-1].data.get("error", "")).lower()
    assert "json serializable" in error_text, error_text


# ---------------------------------------------------------------------------
# Candidate 4: real scan registers interactive blocks (with manifests) and
# rejects a malformed interactive block dropped into a scanned source.
# ---------------------------------------------------------------------------


_GOOD_DROPIN = '''\
"""ADR-051 smoke drop-in: a VALID interactive block (must register)."""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class GoodDropinInteractive(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "Good Dropin Interactive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.dropin.good", version="1")
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[], is_collection=False)]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"out": None}
'''


_BAD_DROPIN = '''\
"""ADR-051 smoke drop-in: a MALFORMED interactive block (must be rejected).

INTERACTIVE + InteractiveMixin but no ``interactive_panel`` manifest -> the
scan-time guard (_validate_interactive_capability, via _spec_from_class) raises
ValueError, so the scan drops the block instead of registering it (FR-002).
"""

from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class BadDropinInteractive(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "Bad Dropin Interactive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[], is_collection=False)]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"out": None}
'''


def test_real_scan_registers_interactive_blocks_and_rejects_malformed(tmp_path: Path) -> None:
    """End-to-end scan: builtins register with manifests; a malformed drop-in is dropped."""
    scan_dir = tmp_path / "dropins"
    scan_dir.mkdir()
    (scan_dir / "good_interactive_dropin.py").write_text(_GOOD_DROPIN, encoding="utf-8")
    (scan_dir / "bad_interactive_dropin.py").write_text(_BAD_DROPIN, encoding="utf-8")

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    registry.scan()  # builtins + Tier-1 drop-ins + Tier-2/3; must not raise.

    # FR-007/FR-014/SC-006: the migrated core interactive blocks register and
    # carry their panel manifests, resolved through the real scan -> instantiate
    # path (not just by reading the class ClassVar).
    assert registry.get_spec("Data Router") is not None
    assert registry.get_spec("Pair Editor") is not None
    data_router = registry.instantiate("Data Router")
    pair_editor = registry.instantiate("Pair Editor")
    assert data_router.get_panel_manifest().panel_id == "core.interactive.data_router"
    assert pair_editor.get_panel_manifest().panel_id == "core.interactive.pair_editor"

    # FR-002/SC-002 end-to-end: the valid drop-in registers; the malformed one
    # is rejected at scan time and contributes no block, and the scan as a whole
    # survives (builtins above still present -> no blanket scan failure).
    assert registry.get_spec("Good Dropin Interactive") is not None
    assert registry.get_spec("Bad Dropin Interactive") is None
