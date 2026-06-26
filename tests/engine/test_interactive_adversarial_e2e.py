"""ADR-051 adversarial end-to-end suite (real two-phase subprocess runtime).

NO-IMPLEMENTATION-CONTEXT design: these tests are written purely against the
ADR-051 contract (FR-001..FR-015, SC-001..SC-006, the §2 Edge Cases) and drive
the *real* runtime — a real :class:`DAGScheduler`, a real
:class:`~scistudio.engine.runners.local.LocalRunner`, and real worker
subprocesses — to find where the runtime breaks at its boundaries. They assume
the implementation may be wrong and exist to prove the contract holds at its
edges, not to confirm a happy path.

Timing-sensitive ordering / cancellation cells live in
``test_interactive_adversarial_timing.py`` (a controllable in-memory runner);
this file covers the guarantees that require genuine subprocess execution:
subprocess isolation (SC-001), JSON-safety enforcement in the worker (FR-004),
fault isolation (§2 Edge Cases), intermediate-by-reference + scratch release
(FR-010/FR-012), lineage recording (FR-011), single-pause-over-collection
(FR-005), and non-interactive regression (US2/SC-005-adjacent).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.blocks.registry import BlockRegistry
from scistudio.blocks.registry._spec import _spec_from_class
from scistudio.engine.events import (
    BLOCK_ERROR,
    BLOCK_PAUSED,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

# Well-behaved + adversarial fixture blocks (importable by the worker subprocess).
from tests.fixtures.interactive_adversarial_blocks import (
    CrashingComputeBlock,
    CrashingPromptBlock,
    EchoPanelBlock,
    ListPanelBlock,
    NanPanelBlock,
    NonePromptBlock,
    PidRecordingBlock,
    ScratchPromptBlock,
)
from tests.fixtures.interactive_blocks import (
    DoubleValueBlock,
    EmitNumbersBlock,
    SelectFromInputBlock,
    SelectOptionBlock,
)

E2E_TIMEOUT = 90


class _AllowAll:
    """ResourceManager stub that always permits dispatch."""

    def can_dispatch(self, *_args: object, **_kwargs: object) -> bool:
        return True


class Harness:
    """Builds the real engine stack and drives an interactive workflow to terminal."""

    def __init__(self, *block_classes: type) -> None:
        self.registry = BlockRegistry()
        for cls in block_classes:
            self.registry._register_spec(_spec_from_class(cls, source="builtin"))
        self.bus = EventBus()
        self.process_registry = ProcessRegistry()
        self.runner = LocalRunner(event_bus=self.bus, registry=self.process_registry)
        self.prompts: list[dict[str, Any]] = []
        self.events: list[tuple[str, str | None]] = []
        self._scheduler: DAGScheduler | None = None

    @staticmethod
    def block_type(cls: type) -> str:
        return _spec_from_class(cls).name

    def _record(self, event_type: str) -> Any:
        async def _cb(event: EngineEvent) -> None:
            self.events.append((event_type, event.block_id))

        return _cb

    def paused_count(self, block_id: str) -> int:
        return sum(1 for etype, bid in self.events if etype == BLOCK_PAUSED and bid == block_id)

    async def run(
        self,
        workflow: WorkflowDefinition,
        *,
        responses: dict[str, dict[str, Any]] | None = None,
        scoped: bool = True,
    ) -> DAGScheduler:
        """Execute *workflow*, auto-confirming each prompt with ``responses[block]``."""
        responses = responses or {}
        scheduler = DAGScheduler(
            workflow=workflow,
            event_bus=self.bus,
            resource_manager=_AllowAll(),
            process_registry=self.process_registry,
            runner=self.runner,
            registry=self.registry,
        )
        self._scheduler = scheduler

        for etype in (BLOCK_PAUSED, BLOCK_ERROR):
            self.bus.subscribe(etype, self._record(etype))

        async def _auto_confirm(event: EngineEvent) -> None:
            self.prompts.append(dict(event.data))
            block_id = event.block_id or ""
            decision = responses.get(block_id, {"choice": "default"})
            data: dict[str, Any] = {"response": decision}
            if scoped:
                data["workflow_id"] = workflow.id
            await self.bus.emit(EngineEvent(event_type=INTERACTIVE_COMPLETE, block_id=event.block_id, data=data))

        self.bus.subscribe(INTERACTIVE_PROMPT, _auto_confirm)
        try:
            await asyncio.wait_for(scheduler.execute(), timeout=E2E_TIMEOUT - 5)
        finally:
            scheduler.dispose()
        return scheduler


def _node(cls: type, node_id: str, config: dict[str, Any] | None = None) -> NodeDef:
    return NodeDef(id=node_id, block_type=Harness.block_type(cls), config=config or {})


# ---------------------------------------------------------------------------
# SC-001 — both phases run in worker subprocesses, neither in the engine.
# FR-007 / FR-015 — panel resolves from the manifest; identity travels on prompt.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(E2E_TIMEOUT)
def test_both_phases_run_in_distinct_subprocesses() -> None:
    """SC-001: prepare_prompt and run each run in a worker subprocess (distinct pids)."""
    h = Harness(PidRecordingBlock)
    wf = WorkflowDefinition(nodes=[_node(PidRecordingBlock, "X")], edges=[])

    sched = asyncio.run(h.run(wf, responses={"X": {"choice": "ok"}}))

    assert sched._block_states["X"] == BlockState.DONE
    outputs = sched._block_outputs["X"]
    engine_pid = os.getpid()
    prompt_pid = h.prompts[0]["panel_payload"]["prompt_pid"]
    compute_pid = outputs["compute_pid"]
    assert prompt_pid != engine_pid, "prepare_prompt ran in the engine process (SC-001 violated)"
    assert compute_pid != engine_pid, "run ran in the engine process (SC-001 violated)"
    assert prompt_pid != compute_pid, "compute phase reused the prompt subprocess (ADR-051 §3)"


@pytest.mark.timeout(E2E_TIMEOUT)
def test_prompt_carries_manifest_and_identity() -> None:
    """FR-007 + FR-015: the prompt event carries the panel manifest and block identity."""
    h = Harness(SelectOptionBlock)
    wf = WorkflowDefinition(nodes=[_node(SelectOptionBlock, "X", {"options": ["A", "B"]})], edges=[])
    asyncio.run(h.run(wf, responses={"X": {"choice": "B"}}))

    data = h.prompts[0]
    assert data["panel_manifest"] is not None, "FR-007: panel manifest missing from prompt event"
    assert data["panel_manifest"]["panel_id"] == "test.interactive.select_option"
    assert data["block_type"], "FR-015: block identity missing from prompt event"
    # The payload is nested, not spread, so it can never clobber identity fields.
    assert "panel_payload" in data and isinstance(data["panel_payload"], dict)


# ---------------------------------------------------------------------------
# FR-005 — one interaction spans the whole input; exactly one pause.
# E — empty collection, many-item collection, no-input block.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(E2E_TIMEOUT)
def test_many_item_collection_pauses_exactly_once() -> None:
    """FR-005: a 50-item input produces one pause, not one per item."""
    h = Harness(EmitNumbersBlock, EchoPanelBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(EmitNumbersBlock, "emit", {"numbers": list(range(50))}),
            _node(EchoPanelBlock, "echo", {"panel": {"k": "v"}}),
        ],
        edges=[EdgeDef(source="emit:numbers", target="echo:items")],
    )
    sched = asyncio.run(h.run(wf, responses={"echo": {"choice": "z"}}))

    assert sched._block_states["echo"] == BlockState.DONE
    assert h.paused_count("echo") == 1, "FR-005 violated: collection iterated into multiple pauses"
    assert h.prompts[0]["panel_payload"]["n_items"] == 50


@pytest.mark.timeout(E2E_TIMEOUT)
def test_empty_input_collection_pauses_once() -> None:
    """E: an empty input collection still pauses exactly once and computes."""
    h = Harness(EmitNumbersBlock, EchoPanelBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(EmitNumbersBlock, "emit", {"numbers": []}),
            _node(EchoPanelBlock, "echo", {"panel": {}}),
        ],
        edges=[EdgeDef(source="emit:numbers", target="echo:items")],
    )
    sched = asyncio.run(h.run(wf, responses={"echo": {"choice": "z"}}))

    assert sched._block_states["echo"] == BlockState.DONE
    assert h.paused_count("echo") == 1
    assert h.prompts[0]["panel_payload"]["n_items"] == 0


@pytest.mark.timeout(E2E_TIMEOUT)
def test_block_with_no_inputs_completes() -> None:
    """E: an interactive block declaring no input ports runs end to end."""
    h = Harness(SelectOptionBlock)
    wf = WorkflowDefinition(nodes=[_node(SelectOptionBlock, "X", {"options": [1, 2, 3]})], edges=[])
    sched = asyncio.run(h.run(wf, responses={"X": {"choice": 2}}))
    assert sched._block_states["X"] == BlockState.DONE
    assert sched._block_outputs["X"] == {"selected": 2}


@pytest.mark.timeout(E2E_TIMEOUT)
def test_duplicate_value_collection_pauses_once() -> None:
    """E (proxy): a collection with duplicate items still pauses once.

    True DataObject-identity duplicates need a storage backend; with the
    no-backend fixtures this exercises the duplicate-item shape via repeated
    scalar values, which is the observable single-pause guarantee (FR-005).
    """
    h = Harness(EmitNumbersBlock, EchoPanelBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(EmitNumbersBlock, "emit", {"numbers": [7, 7, 7, 7]}),
            _node(EchoPanelBlock, "echo", {"panel": {}}),
        ],
        edges=[EdgeDef(source="emit:numbers", target="echo:items")],
    )
    sched = asyncio.run(h.run(wf, responses={"echo": {"choice": "z"}}))
    assert sched._block_states["echo"] == BlockState.DONE
    assert h.paused_count("echo") == 1
    assert h.prompts[0]["panel_payload"]["n_items"] == 4


# ---------------------------------------------------------------------------
# FR-004 — panel_payload JSON-safe ACCEPTED edge values round-trip faithfully.
# ---------------------------------------------------------------------------

_DEEP_NEST: dict[str, Any] = {"v": 0}
for _i in range(40):
    _DEEP_NEST = {"child": _DEEP_NEST}

_ACCEPTED_PAYLOADS: dict[str, dict[str, Any]] = {
    "empty_dict": {},
    "unicode_control": {"text": "café ☃ \U0001f600", "ctrl": "a\u0000b\u001fc\n\t"},
    "deeply_nested": {"root": _DEEP_NEST},
    "large_list": {"xs": list(range(5000))},
    "engine_colliding_keys": {
        "workflow_id": "PANEL-WF",
        "block_type": "PANEL-BT",
        "panel_manifest": "PANEL-PM",
        "panel_payload": "PANEL-PP",
    },
}


@pytest.mark.timeout(E2E_TIMEOUT)
@pytest.mark.parametrize("case", sorted(_ACCEPTED_PAYLOADS))
def test_json_safe_panel_payloads_round_trip(case: str) -> None:
    """FR-004: JSON-safe panel payloads are delivered intact; identity is not clobbered."""
    payload = _ACCEPTED_PAYLOADS[case]
    h = Harness(EchoPanelBlock)
    wf = WorkflowDefinition(nodes=[_node(EchoPanelBlock, "X", {"panel": payload})], edges=[])
    sched = asyncio.run(h.run(wf, responses={"X": {"choice": "ok"}}))

    assert sched._block_states["X"] == BlockState.DONE
    data = h.prompts[0]
    delivered = data["panel_payload"]
    for key, value in payload.items():
        assert delivered[key] == value, f"payload key {key!r} not delivered intact"

    # Engine identity fields at the TOP level must never be clobbered by
    # colliding keys nested inside the payload.
    assert data["workflow_id"] == wf.id
    assert data["block_type"] and data["block_type"] != "PANEL-BT"
    assert data["panel_manifest"] != "PANEL-PM"


# ---------------------------------------------------------------------------
# FR-004 — panel_payload non-JSON-safe values are REJECTED by the worker,
# not pickled or truncated, and the failure is an isolated block error while a
# healthy companion block in the same workflow still completes (§2 Edge Cases).
# ---------------------------------------------------------------------------

_REJECTED_CASES: dict[str, tuple[type, dict[str, Any]]] = {
    "nan": (NanPanelBlock, {"mode": "nan"}),
    "pos_inf": (NanPanelBlock, {"mode": "inf"}),
    "neg_inf": (NanPanelBlock, {"mode": "neginf"}),
    "list_payload": (ListPanelBlock, {}),
    "none_payload": (NonePromptBlock, {}),
}


@pytest.mark.timeout(E2E_TIMEOUT)
@pytest.mark.parametrize("case", sorted(_REJECTED_CASES))
def test_non_json_panel_payload_rejected_as_isolated_error(case: str) -> None:
    """FR-004 + §2: a non-JSON panel payload fails the block; the engine is unaffected."""
    bad_cls, bad_cfg = _REJECTED_CASES[case]
    h = Harness(bad_cls, EmitNumbersBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(bad_cls, "bad", bad_cfg),
            _node(EmitNumbersBlock, "healthy", {"numbers": [1, 2]}),
        ],
        edges=[],
    )
    sched = asyncio.run(h.run(wf))

    assert sched._block_states["bad"] == BlockState.ERROR, "non-JSON payload was not rejected"
    # No pause => no compute phase was ever entered for the bad block.
    assert h.paused_count("bad") == 0, "block paused despite an invalid panel payload"
    # Engine + other blocks unaffected.
    assert sched._block_states["healthy"] == BlockState.DONE
    assert sched._block_outputs["healthy"] == {"numbers": [1, 2]}


# ---------------------------------------------------------------------------
# §2 Edge Cases — a crash in prepare_prompt or run is isolated as a block error;
# the engine and other blocks are unaffected; no pause/compute leaks.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(E2E_TIMEOUT)
def test_prompt_phase_crash_isolated() -> None:
    """A crash inside prepare_prompt fails only that block; the chain survives."""
    h = Harness(CrashingPromptBlock, EmitNumbersBlock, DoubleValueBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(CrashingPromptBlock, "bad"),
            _node(EmitNumbersBlock, "emit", {"numbers": [3]}),
            _node(DoubleValueBlock, "dbl"),
        ],
        edges=[EdgeDef(source="emit:numbers", target="dbl:value")],
    )
    sched = asyncio.run(h.run(wf))

    assert sched._block_states["bad"] == BlockState.ERROR
    assert h.paused_count("bad") == 0
    assert sched._block_states["emit"] == BlockState.DONE
    assert sched._block_states["dbl"] == BlockState.DONE


@pytest.mark.timeout(E2E_TIMEOUT)
def test_compute_phase_crash_isolated() -> None:
    """A crash inside run (after a clean pause) fails only that block."""
    h = Harness(CrashingComputeBlock, EmitNumbersBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(CrashingComputeBlock, "bad"),
            _node(EmitNumbersBlock, "emit", {"numbers": [9]}),
        ],
        edges=[],
    )
    sched = asyncio.run(h.run(wf, responses={"bad": {"choice": "x"}}))

    assert sched._block_states["bad"] == BlockState.ERROR
    assert h.paused_count("bad") == 1, "compute crash should follow exactly one clean pause"
    assert sched._block_states["emit"] == BlockState.DONE


# ---------------------------------------------------------------------------
# FR-010 / FR-011 / FR-012 — intermediate by reference, lineage, scratch release.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(E2E_TIMEOUT)
def test_intermediate_threaded_and_scratch_released_on_success(tmp_path: Path) -> None:
    """FR-010: intermediate crosses the pause by reference; FR-012: scratch released."""
    scratch = tmp_path / "scratch.txt"
    h = Harness(ScratchPromptBlock)
    wf = WorkflowDefinition(
        nodes=[_node(ScratchPromptBlock, "X", {"scratch_path": str(scratch).replace("\\", "/")})],
        edges=[],
    )

    done_configs: list[dict[str, Any]] = []

    async def _capture_done(event: EngineEvent) -> None:
        if event.block_id == "X" and isinstance(event.data, dict) and "config" in event.data:
            done_configs.append(event.data["config"])

    h.bus.subscribe("block_done", _capture_done)

    sched = asyncio.run(h.run(wf, responses={"X": {"choice": "picked"}}))

    assert sched._block_states["X"] == BlockState.DONE
    # FR-010: the compute phase loaded the scratch the prompt phase persisted.
    assert sched._block_outputs["X"]["scratch_content"] == "SCRATCH-PAYLOAD"
    # FR-012: the engine released (deleted) the scratch after the run.
    assert not scratch.exists(), "FR-012 violated: intermediate scratch left on disk after success"

    # FR-011: the decision is recorded; intermediate references are NOT.
    assert done_configs, "no BLOCK_DONE config captured"
    cfg = done_configs[0]
    assert cfg.get("interactive_response") == {"choice": "picked"}, "FR-011: decision not recorded"
    assert "interactive_intermediate" not in cfg, "FR-011: scratch reference leaked into lineage"


@pytest.mark.timeout(E2E_TIMEOUT)
def test_no_intermediate_rebuilds_from_inputs_config_decision() -> None:
    """§2 Edge Case: a block with no intermediate rebuilds from inputs+config+decision."""
    h = Harness(EmitNumbersBlock, SelectFromInputBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(EmitNumbersBlock, "emit", {"numbers": [10, 20, 30]}),
            _node(SelectFromInputBlock, "pick"),
        ],
        edges=[EdgeDef(source="emit:numbers", target="pick:numbers")],
    )
    sched = asyncio.run(h.run(wf, responses={"pick": {"index": 2}}))

    assert sched._block_states["pick"] == BlockState.DONE
    # Decision index 2 -> third input value, rebuilt purely from inputs+decision.
    assert sched._block_outputs["pick"] == {"selected": 30}


# ---------------------------------------------------------------------------
# US2 / regression — a non-interactive block in the same workflow is unaffected.
# ---------------------------------------------------------------------------


@pytest.mark.timeout(E2E_TIMEOUT)
def test_non_interactive_chain_unaffected_by_interactive_block() -> None:
    """J: non-interactive blocks complete normally alongside an interactive block."""
    h = Harness(EmitNumbersBlock, DoubleValueBlock, SelectOptionBlock)
    wf = WorkflowDefinition(
        nodes=[
            _node(EmitNumbersBlock, "emit", {"numbers": [21]}),
            _node(DoubleValueBlock, "dbl"),
            _node(SelectOptionBlock, "pick", {"options": ["a"]}),
        ],
        edges=[EdgeDef(source="emit:numbers", target="dbl:value")],
    )
    sched = asyncio.run(h.run(wf, responses={"pick": {"choice": "a"}}))

    assert sched._block_states["emit"] == BlockState.DONE
    assert sched._block_states["dbl"] == BlockState.DONE
    assert sched._block_states["pick"] == BlockState.DONE
    # EmitNumbers emits the list [21]; DoubleValue doubles the value it receives
    # (list repetition). The point is the non-interactive chain computed exactly
    # as it would without the interactive block present.
    assert sched._block_outputs["dbl"] == {"doubled": [21, 21]}
