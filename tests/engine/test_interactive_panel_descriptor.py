"""ADR-054 spec 1 — a paused block's panel mounts, and its emission is settled.

Two gaps closed here, driven together because they are the two halves of one
sentence a person says: *open the panel, make the decision, press Confirm, and
the block computes.*

**The descriptor (D-020, D-016.3).** A paused block's panel does not arrive
through a route; it arrives on ``INTERACTIVE_PROMPT``. The event used to carry
only ``panel_manifest`` — the retired ES-module shape, with no capability, no
document URL, no asset base and no read limits — which
``frontend/src/panels/panelDescriptor.ts`` refuses, so the reader got the host's
error surface instead of the panel. The event now carries a descriptor beside
it, and the manifest stays for the migration (FR-022).

**The emission (FR-012, ADR-054 §3.6).** The two built-in interactive panels are
producing panels, so their only outbound path is the emission of code. The host
commits the newest emission as ``{"code": ...}``; the engine settles it into the
``interactive_response`` the block reads. Without this the two shipped blocks
paused, drew their panel, and could not be confirmed.

The two tests below run the **real** ``DataRouter`` and ``PairEditor`` through a
real ``DAGScheduler``, resolve the pause with the **verbatim snippet the shipped
panel document emits**, and assert the block's routed output — which is the
whole path from Confirm to a computed result.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState
from scistudio.blocks.process.builtins.data_router import DataRouter
from scistudio.blocks.process.builtins.pair_editor import PairEditor
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.panels import PANEL_API_VERSION
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.engine.events import (
    BLOCK_ERROR,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


def _ports(*names: str) -> list[dict[str, Any]]:
    """ADR-029 D1 variadic port list, as a block config stores it."""
    return [{"name": name, "types": ["DataObject"]} for name in names]


#: The two shipped interactive blocks, configured as the canvas configures them.
_ROUTER_CONFIG: dict[str, Any] = {
    "input_ports": _ports("input_1", "input_2"),
    "output_ports": _ports("port_1", "port_2"),
}
_PAIR_CONFIG: dict[str, Any] = {"input_ports": _ports("input_1", "input_2")}


class Item(DataObject):
    """A minimal routable item that carries a recognisable name."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class _EmitItems(ProcessBlock):
    """Upstream source: hands one Collection down each of its two ports."""

    name: ClassVar[str] = "EmitItems"
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="a", accepted_types=[], is_collection=True),
        OutputPort(name="b", accepted_types=[], is_collection=True),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {
            "a": Collection([Item("alpha.tif"), Item("beta.tif")], item_type=Item),
            "b": Collection([Item("gamma.tif"), Item("delta.tif")], item_type=Item),
        }


def _scheduler(interactive: type[Block], config: dict[str, Any]) -> tuple[DAGScheduler, EventBus, list[EngineEvent]]:
    """A two-node workflow: the source above feeding the real interactive block.

    The runner is in-process (the two-phase *subprocess* contract is pinned by
    ``test_interactive_two_phase.py``); what is under test here is what the
    engine puts on the prompt event and what it does with the answer.
    """
    workflow = WorkflowDefinition(
        id="wf-panel-descriptor",
        description="ADR-054 spec 1 paused-block panel",
        nodes=[
            NodeDef(id="src", block_type="emit-items", config={}),
            NodeDef(id="node", block_type="interactive", config=config),
        ],
        edges=[
            EdgeDef(source="src:a", target="node:input_1"),
            EdgeDef(source="src:b", target="node:input_2"),
        ],
    )
    event_bus = EventBus()
    errors: list[EngineEvent] = []
    event_bus.subscribe(BLOCK_ERROR, lambda event: errors.append(event))

    def _instantiate(block_type: str, node_config: dict[str, Any] | None = None) -> Block:
        if block_type == "emit-items":
            return _EmitItems(node_config or {})
        return interactive(node_config or {})  # type: ignore[call-arg]

    registry = MagicMock()
    registry.instantiate.side_effect = _instantiate
    registry.get_spec.return_value = None

    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()

    async def _prompt(block: Block, inputs: dict[str, Any], node_config: dict[str, Any]) -> dict[str, Any]:
        from scistudio.blocks.base.interactive import coerce_prompt, interactive_input_signature

        prompt = coerce_prompt(block.prepare_prompt(inputs, BlockConfig(**node_config)))  # type: ignore[attr-defined]
        return {
            "panel_payload": prompt.panel_payload,
            "input_signature": interactive_input_signature(inputs),
            "intermediate": [],
            "environment": None,
        }

    async def _compute(block: Block, inputs: dict[str, Any], node_config: dict[str, Any]) -> dict[str, Any]:
        return block.run(inputs, BlockConfig(**node_config))

    runner.run_prompt.side_effect = _prompt
    runner.run.side_effect = _compute

    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, event_bus, errors


async def _confirm_with(
    scheduler: DAGScheduler,
    event_bus: EventBus,
    emitted_code: str,
) -> list[EngineEvent]:
    """Run the workflow, and answer the pause the way the host's Confirm does.

    ``{"code": ...}`` nested under ``response`` alongside the run-scoping
    ``workflow_id`` is the exact frame ``api/ws.py`` builds from what
    ``InteractivePanelHost`` sends when a person presses Confirm.
    """
    prompts: list[EngineEvent] = []
    spawned: list[asyncio.Task[None]] = []

    async def _emit_complete(block_id: str | None) -> None:
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id=block_id,
                data={
                    "workflow_id": scheduler._workflow.id,
                    "response": {"code": emitted_code},
                },
            )
        )

    async def _on_prompt(event: EngineEvent) -> None:
        prompts.append(event)
        spawned.append(asyncio.create_task(_emit_complete(event.block_id)))

    event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
    await scheduler.execute()
    if spawned:
        await asyncio.gather(*spawned, return_exceptions=True)
    return prompts


def _assert_mountable(descriptor: dict[str, Any], panel_id: str) -> None:
    """Every field ``validatePanelDescriptor`` refuses a mount without (D-016.3)."""
    assert descriptor is not None, "the prompt carried no panel descriptor"
    assert descriptor["panel_id"] == panel_id
    assert descriptor["capability"] == "producing"
    assert descriptor["document_url"] == f"/api/panels/assets/{panel_id}/index.html"
    assert descriptor["asset_base_url"] == f"/api/panels/assets/{panel_id}/"
    assert descriptor["accepted_api_version"] == PANEL_API_VERSION
    assert descriptor["api_version"] == PANEL_API_VERSION
    assert isinstance(descriptor["read_limits"]["max_rows"], int)
    assert isinstance(descriptor["read_limits"]["max_bytes"], int)
    assert descriptor["display_name"]


class TestDataRouterCanBeConfirmedAgain:
    """Pause, mount, emit, Confirm, compute — for the real ``DataRouter``."""

    CODE = (
        'assignments = {"port_1": ["input_1:0", "input_2:1"], "port_2": ["input_1:1"]}\n'
        "scistudio.output(assignments=assignments)"
    )

    def test_end_to_end(self) -> None:
        scheduler, event_bus, errors = _scheduler(
            DataRouter,
            _ROUTER_CONFIG,
        )
        prompts = asyncio.run(_confirm_with(scheduler, event_bus, self.CODE))

        assert not errors, [event.data for event in errors]
        assert len(prompts) == 1
        data = prompts[0].data

        # Gap 2: the host has something it can mount.
        _assert_mountable(data["panel_descriptor"], "core.interactive.data_router")
        # FR-022: the retired shape rides along for the migration.
        assert data["panel_manifest"]["panel_id"] == "core.interactive.data_router"
        # The panel is given the block's window-sized view, nested not spread.
        assert data["panel_payload"]["output_ports"] == ["port_1", "port_2"]

        # Gap 1: the emission became the decision, and the block computed it.
        assert scheduler._block_states["node"] == BlockState.DONE
        outputs = scheduler._block_outputs["node"]
        assert [item.name for item in outputs["port_1"]] == ["alpha.tif", "delta.tif"]
        assert [item.name for item in outputs["port_2"]] == ["beta.tif"]

    def test_the_settled_decision_is_what_lands_in_the_config(self) -> None:
        # The block reads ``interactive_response["assignments"]`` and is
        # unchanged by this work; the translation is what meets it there.
        scheduler, event_bus, _ = _scheduler(
            DataRouter,
            _ROUTER_CONFIG,
        )
        recorded: list[dict[str, Any]] = []
        event_bus.subscribe(
            "block_done",
            lambda event: recorded.append(event.data.get("config", {})),
        )
        asyncio.run(_confirm_with(scheduler, event_bus, self.CODE))

        node_config = next(config for config in recorded if "interactive_response" in config)
        assert node_config["interactive_response"] == {
            "assignments": {"port_1": ["input_1:0", "input_2:1"], "port_2": ["input_1:1"]}
        }


class TestPairEditorCanBeConfirmedAgain:
    """The same sentence, for the real ``PairEditor`` and ``reorder``."""

    CODE = 'reorder = {"input_1": [1, 0], "input_2": [0, 1]}\nscistudio.output(reorder=reorder)'

    def test_end_to_end(self) -> None:
        scheduler, event_bus, errors = _scheduler(
            PairEditor,
            _PAIR_CONFIG,
        )
        prompts = asyncio.run(_confirm_with(scheduler, event_bus, self.CODE))

        assert not errors, [event.data for event in errors]
        _assert_mountable(prompts[0].data["panel_descriptor"], "core.interactive.pair_editor")

        assert scheduler._block_states["node"] == BlockState.DONE
        outputs = scheduler._block_outputs["node"]
        ports = sorted(outputs)
        # input_1 was reversed; input_2 was left alone.
        assert [item.name for item in outputs[ports[0]]] == ["beta.tif", "alpha.tif"]
        assert [item.name for item in outputs[ports[1]]] == ["gamma.tif", "delta.tif"]


class TestARefusedEmissionIsTheBlocksError:
    """A person who presses Confirm gets an error, not silence.

    The engine surfaces a refused emission exactly as it surfaces a response
    that is not JSON-safe: the block goes to ERROR and the message reaches the
    reader, naming the block and the panel.
    """

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            pytest.param("assignments = {", "does not parse", id="does not parse"),
            pytest.param('assignments = {"port_1": []}', "never called scistudio.output", id="calls nothing"),
            pytest.param(
                "scistudio.output(assignments={})\nscistudio.output(assignments={})",
                "2 times",
                id="calls output twice",
            ),
            pytest.param("import os", "__import__ not found", id="tries to import"),
            pytest.param('open("/etc/passwd")', "name 'open' is not defined", id="tries to open a file"),
            pytest.param("x = ().__class__.__bases__", "refused", id="tries to reach a dunder"),
        ],
    )
    def test_the_block_errors_and_the_message_names_the_block_and_panel(self, code: str, expected: str) -> None:
        scheduler, event_bus, errors = _scheduler(
            DataRouter,
            _ROUTER_CONFIG,
        )
        asyncio.run(_confirm_with(scheduler, event_bus, code))

        assert scheduler._block_states["node"] == BlockState.ERROR
        assert errors, "no BLOCK_ERROR reached the reader"
        message = str(errors[-1].data.get("error", ""))
        assert expected in message
        assert "core.interactive.data_router" in message
        assert "Data Router" in message or "DataRouter" in message


def test_a_decision_that_is_not_an_emission_still_passes_straight_through() -> None:
    """The migration boundary: a programmatic driver keeps working unchanged."""
    scheduler, event_bus, errors = _scheduler(
        DataRouter,
        _ROUTER_CONFIG,
    )

    spawned: list[asyncio.Task[None]] = []

    async def _drive() -> None:
        async def _emit(block_id: str | None) -> None:
            await event_bus.emit(
                EngineEvent(
                    event_type=INTERACTIVE_COMPLETE,
                    block_id=block_id,
                    data={
                        "workflow_id": scheduler._workflow.id,
                        "response": {"assignments": {"port_1": ["input_1:0"], "port_2": []}},
                    },
                )
            )

        async def _on_prompt(event: EngineEvent) -> None:
            spawned.append(asyncio.create_task(_emit(event.block_id)))

        event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
        await scheduler.execute()
        if spawned:
            await asyncio.gather(*spawned, return_exceptions=True)

    asyncio.run(_drive())

    assert not errors, [event.data for event in errors]
    assert scheduler._block_states["node"] == BlockState.DONE
    assert [item.name for item in scheduler._block_outputs["node"]["port_1"]] == ["alpha.tif"]
