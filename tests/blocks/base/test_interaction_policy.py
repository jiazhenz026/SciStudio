"""The ``on_new_input`` setting and the engine's remap policy (ADR-054 T-015).

Spec: ``docs/specs/adr-054-explore-session.md`` FR-044, FR-045, FR-047, FR-048.

``on_new_input`` is the policy that decides whether the ADR-051 interaction
memory's remap check is consulted at all when a node that remembers a decision
is dispatched:

* ``ask`` consults ``remap_saved_decision``, which replays the remembered
  decision while the input signature is unchanged and pauses otherwise. This is
  the behaviour every interactive block had before ADR-054, and it is what a
  node with no setting written anywhere resolves to.
* ``replay`` replays the remembered decision regardless of the signature, so the
  node never pauses on changed input. A packaged notebook block declares it as
  its default (FR-044/FR-046).

Spec §4.5 promises the change to these two protected core paths is additive —
"a setting with a default that preserves current behaviour". The
``TestDefaultPreservesExistingBehaviour`` class is that promise stated as tests:
the two shipped authored interactive blocks (``DataRouter``, ``PairEditor``)
declare no setting, and an authored interactive block driven through the real
engine dispatch with no setting anywhere replays on an unchanged signature,
pauses on a changed one, and pauses with no memory at all — exactly as before.

The engine-level tests drive the real ``DAGScheduler._run_interactive`` with a
mocked runner (the prompt and compute phases are subprocesses in production),
following the harness in ``tests/engine/test_scheduler_interactive.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    DEFAULT_INTERACTION_POLICY,
    INTERACTIVE_MEMORY_KEY,
    INTERACTIVE_RESPONSE_KEY,
    ON_NEW_INPUT_KEY,
    InteractionPolicy,
    InteractiveMixin,
    PanelManifest,
    resolve_interaction_policy,
)
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.blocks.process.builtins.data_router import DataRouter
from scistudio.blocks.process.builtins.pair_editor import PairEditor
from scistudio.core.types.base import DataObject
from scistudio.engine.events import (
    BLOCK_PAUSED,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

# --------------------------------------------------------------------------- #
# Fixtures: blocks
# --------------------------------------------------------------------------- #

_SAVED_SIGNATURE = {"input_1": ["a.csv", "b.csv"]}
_SAME_SIGNATURE = {"input_1": ["a.csv", "b.csv"]}
_CHANGED_SIGNATURE = {"input_1": ["a.csv", "c.csv"]}
_SAVED_DECISION = {"assignments": {"output_1": ["a.csv"]}}


class _AuthoredInteractiveBlock(InteractiveMixin, Block):
    """An authored interactive block, written the way one was before ADR-054.

    It declares no ``on_new_input``, so it inherits the mixin default and must
    behave exactly as it did before the setting existed. It also counts calls to
    :meth:`remap_saved_decision` so a test can assert the remap check was — or
    was not — consulted, which is how "the policy is read *before* the remap
    check" is observable from outside.
    """

    name: ClassVar[str] = "AuthoredInteractive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="core.interactive.data_router")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="out", accepted_types=[DataObject]),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # ``DAGScheduler._instantiate_block`` assigns ``.id`` after construction.
        self.id = ""
        self.remap_calls: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Minimal panel payload; the mocked prompt phase supplies the envelope."""
        return {"prompt": "choose"}

    def remap_saved_decision(
        self,
        saved_decision: dict[str, Any],
        saved_signature: dict[str, list[str]],
        current_signature: dict[str, list[str]],
    ) -> dict[str, Any] | None:
        """Record the call, then apply the inherited default policy unchanged."""
        self.remap_calls.append((saved_decision, dict(saved_signature), dict(current_signature)))
        return super().remap_saved_decision(saved_decision, saved_signature, current_signature)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        """Return a trivial output; the compute phase is mocked in these tests."""
        return {"out": None}


class _PackagedStyleBlock(_AuthoredInteractiveBlock):
    """Stands in for a packaged notebook block: declares ``replay`` (FR-044).

    The generated declaration a packaging run writes is agent S3-C2's and lives
    outside this scope; what matters to the engine is only that the block
    declares ``on_new_input = replay`` and carries the interaction capability,
    which is exactly what this fixture does.
    """

    name: ClassVar[str] = "PackagedStyleNotebook"
    on_new_input: ClassVar[InteractionPolicy] = InteractionPolicy.REPLAY


class _StringPolicyBlock(_AuthoredInteractiveBlock):
    """Declares the policy as the bare string an author may write."""

    name: ClassVar[str] = "StringPolicy"
    on_new_input: ClassVar[str] = "replay"


class _BadPolicyBlock(_AuthoredInteractiveBlock):
    """Declares a value that is not a policy at all."""

    name: ClassVar[str] = "BadPolicy"
    on_new_input: ClassVar[str] = "sometimes"


# --------------------------------------------------------------------------- #
# Fixtures: engine harness
# --------------------------------------------------------------------------- #


def _memory_config(
    *,
    saved_signature: dict[str, list[str]] | None = None,
    decision: dict[str, Any] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """A node config carrying an ADR-051 interaction-memory record."""
    return {
        INTERACTIVE_MEMORY_KEY: {
            "enabled": enabled,
            "decision": _SAVED_DECISION if decision is None else decision,
            "signature": _SAVED_SIGNATURE if saved_signature is None else saved_signature,
        }
    }


class _Driver:
    """Runs one interactive node and records whether it paused.

    Subscribes to ``BLOCK_PAUSED`` and ``INTERACTIVE_PROMPT``, and answers every
    prompt with ``response`` so a test that expects a pause still terminates.
    The completion emit is deferred onto the loop for the reason the ADR-051
    harness documents: the prompt handler runs inside ``_run_interactive``, and
    resolving inline would race the announce.
    """

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = {"choice": "fresh"} if response is None else response
        self.paused: list[EngineEvent] = []
        self.prompts: list[EngineEvent] = []
        self._tasks: list[asyncio.Task[None]] = []

    async def _emit_completion(self, block_id: str | None) -> None:
        await self._bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id=block_id,
                data={"response": self.response},
            )
        )

    async def _on_prompt(self, event: EngineEvent) -> None:
        self.prompts.append(event)
        self._tasks.append(asyncio.create_task(self._emit_completion(event.block_id), name="test:emit-complete"))

    async def _on_paused(self, event: EngineEvent) -> None:
        self.paused.append(event)

    async def run(self, scheduler: DAGScheduler, bus: EventBus) -> None:
        """Execute *scheduler* to completion, answering any prompt it raises."""
        self._bus = bus
        bus.subscribe(INTERACTIVE_PROMPT, self._on_prompt)
        bus.subscribe(BLOCK_PAUSED, self._on_paused)
        await scheduler.execute()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def did_pause(self) -> bool:
        """Whether the node actually paused for a human."""
        return bool(self.paused) or bool(self.prompts)


def _make_scheduler(
    block_cls: type[Block],
    node_config: dict[str, Any],
    *,
    current_signature: dict[str, list[str]],
) -> tuple[DAGScheduler, EventBus, dict[str, Any], AsyncMock]:
    """Build a scheduler over one interactive node with a mocked two-phase runner.

    Returns the scheduler, its event bus, the (single) block instance the mock
    registry handed out, and the runner mock so a test can inspect the prompt
    and compute calls.
    """
    workflow = WorkflowDefinition(
        id="test-wf-on-new-input",
        description="on_new_input policy",
        nodes=[NodeDef(id="a", block_type="interactive-under-test", config=dict(node_config))],
        edges=[],
    )
    instances: dict[str, Any] = {}
    registry = MagicMock()

    def _instantiate(name: str, config: dict[str, Any] | None = None) -> Block:
        block = block_cls(config or {})
        instances["block"] = block
        return block

    registry.instantiate.side_effect = _instantiate
    registry.get_spec.return_value = None

    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()
    runner.run_prompt.return_value = {
        "panel_payload": {"prompt": "choose"},
        "input_signature": current_signature,
        "intermediate": [],
        "environment": None,
    }
    runner.run.return_value = {"out": None}

    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=EventBus(),
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, scheduler._event_bus, instances, runner


def _dispatch(
    block_cls: type[Block],
    node_config: dict[str, Any],
    *,
    current_signature: dict[str, list[str]],
    response: dict[str, Any] | None = None,
) -> tuple[_Driver, Any, AsyncMock, DAGScheduler]:
    """Run one interactive node end to end and return what happened."""
    scheduler, bus, instances, runner = _make_scheduler(block_cls, node_config, current_signature=current_signature)
    driver = _Driver(response=response)
    asyncio.run(driver.run(scheduler, bus))
    return driver, instances["block"], runner, scheduler


def _compute_config(runner: AsyncMock) -> dict[str, Any]:
    """The config the compute phase (``runner.run``) was called with."""
    assert runner.run.await_count == 1, f"expected exactly one compute phase, got {runner.run.await_count}"
    return runner.run.await_args.args[2]


# --------------------------------------------------------------------------- #
# FR-044: the setting itself
# --------------------------------------------------------------------------- #


class TestInteractionPolicySetting:
    """``on_new_input`` is declared on the block and overridable on the node."""

    def test_policy_has_exactly_replay_and_ask(self) -> None:
        """FR-044 names two values and no others."""
        assert {member.value for member in InteractionPolicy} == {"replay", "ask"}

    def test_mixin_default_is_ask(self) -> None:
        """An authored interactive block defaults to ``ask`` (FR-044/FR-045)."""
        assert InteractiveMixin.on_new_input is InteractionPolicy.ASK
        assert DEFAULT_INTERACTION_POLICY is InteractionPolicy.ASK

    def test_block_declaration_is_read(self) -> None:
        """A block that declares ``replay`` resolves to ``replay``."""
        assert resolve_interaction_policy(_PackagedStyleBlock(), {}) is InteractionPolicy.REPLAY

    def test_block_may_declare_the_bare_string(self) -> None:
        """An author need not import the enum to set the setting."""
        assert resolve_interaction_policy(_StringPolicyBlock(), {}) is InteractionPolicy.REPLAY

    @pytest.mark.parametrize("raw", ["replay", "REPLAY", " Replay ", InteractionPolicy.REPLAY])
    def test_node_override_beats_the_block_default(self, raw: Any) -> None:
        """A node may override an ``ask`` block to ``replay``."""
        block = _AuthoredInteractiveBlock()
        assert resolve_interaction_policy(block, {ON_NEW_INPUT_KEY: raw}) is InteractionPolicy.REPLAY

    def test_node_override_can_force_ask_on_a_replay_block(self) -> None:
        """The override works in the other direction too (FR-044)."""
        block = _PackagedStyleBlock()
        assert resolve_interaction_policy(block, {ON_NEW_INPUT_KEY: "ask"}) is InteractionPolicy.ASK

    def test_node_override_is_read_from_params(self) -> None:
        """Block configs carry user fields under ``params`` as well."""
        block = _AuthoredInteractiveBlock()
        config = {"params": {ON_NEW_INPUT_KEY: "replay"}}
        assert resolve_interaction_policy(block, config) is InteractionPolicy.REPLAY

    def test_top_level_override_wins_over_params(self) -> None:
        """Same precedence the memory record uses: top level first."""
        block = _AuthoredInteractiveBlock()
        config = {ON_NEW_INPUT_KEY: "ask", "params": {ON_NEW_INPUT_KEY: "replay"}}
        assert resolve_interaction_policy(block, config) is InteractionPolicy.ASK

    def test_unknown_node_value_falls_back_to_the_block_declaration(self, caplog: pytest.LogCaptureFixture) -> None:
        """A typo in a node config must not fail a run, and must be visible."""
        block = _PackagedStyleBlock()
        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.base.interactive"):
            resolved = resolve_interaction_policy(block, {ON_NEW_INPUT_KEY: "maybe"})
        assert resolved is InteractionPolicy.REPLAY
        assert any("maybe" in record.getMessage() for record in caplog.records)

    def test_unknown_block_value_falls_back_to_ask(self, caplog: pytest.LogCaptureFixture) -> None:
        """Falling through to ``ask`` only ever means the user is asked."""
        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.base.interactive"):
            resolved = resolve_interaction_policy(_BadPolicyBlock(), {})
        assert resolved is InteractionPolicy.ASK
        assert any("sometimes" in record.getMessage() for record in caplog.records)

    @pytest.mark.parametrize("config", [{}, None, "not-a-config", {"params": None}, {ON_NEW_INPUT_KEY: None}])
    def test_missing_or_unusable_config_resolves_to_ask(self, config: Any) -> None:
        """Nothing declared anywhere is today's behaviour: ``ask``."""
        assert resolve_interaction_policy(_AuthoredInteractiveBlock(), config) is InteractionPolicy.ASK

    def test_a_block_without_the_attribute_resolves_to_ask(self) -> None:
        """A block object predating the setting entirely still resolves."""

        class _Legacy:
            pass

        assert resolve_interaction_policy(_Legacy(), {}) is InteractionPolicy.ASK


# --------------------------------------------------------------------------- #
# FR-045 / spec §4.5: the default preserves today's behaviour exactly
# --------------------------------------------------------------------------- #


class TestDefaultPreservesExistingBehaviour:
    """The additive promise: nothing changes for a block written before ADR-054."""

    @pytest.mark.parametrize("block_cls", [DataRouter, PairEditor])
    def test_shipped_authored_blocks_declare_no_setting_and_resolve_to_ask(self, block_cls: type[Block]) -> None:
        """The two shipped interactive blocks are untouched and still ask.

        Neither declares ``on_new_input`` of its own — the value they resolve to
        comes from the mixin default — so their behaviour cannot have moved.
        """
        assert "on_new_input" not in vars(block_cls)
        assert resolve_interaction_policy(block_cls(), {}) is InteractionPolicy.ASK

    def test_unchanged_signature_replays_without_pausing(self) -> None:
        """Pre-ADR-054 behaviour #1: memory hit on an unchanged signature.

        No setting is written on the block or the node.
        """
        driver, block, runner, _ = _dispatch(
            _AuthoredInteractiveBlock,
            _memory_config(),
            current_signature=_SAME_SIGNATURE,
        )

        assert not driver.did_pause, "an unchanged signature must replay, not pause"
        assert block.remap_calls, "the remap check must still be consulted under the default"
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == _SAVED_DECISION

    def test_changed_signature_pauses_and_asks(self) -> None:
        """Pre-ADR-054 behaviour #2: a changed signature reopens the panel."""
        driver, block, runner, _ = _dispatch(
            _AuthoredInteractiveBlock,
            _memory_config(),
            current_signature=_CHANGED_SIGNATURE,
            response={"choice": "fresh"},
        )

        assert driver.did_pause, "a changed signature must pause under the default"
        assert len(driver.prompts) == 1
        assert block.remap_calls == [(_SAVED_DECISION, _SAVED_SIGNATURE, _CHANGED_SIGNATURE)]
        # The user's fresh decision — not the remembered one — reaches compute.
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == {"choice": "fresh"}

    def test_no_memory_record_pauses(self) -> None:
        """Pre-ADR-054 behaviour #3: with nothing remembered, the block asks."""
        driver, block, runner, _ = _dispatch(
            _AuthoredInteractiveBlock,
            {},
            current_signature=_SAME_SIGNATURE,
        )

        assert driver.did_pause
        assert block.remap_calls == [], "no memory means no remap check, as before"
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == {"choice": "fresh"}

    def test_disabled_memory_record_pauses(self) -> None:
        """Pre-ADR-054 behaviour #4: an opted-out memory record is inert."""
        driver, block, _, _ = _dispatch(
            _AuthoredInteractiveBlock,
            _memory_config(enabled=False),
            current_signature=_SAME_SIGNATURE,
        )

        assert driver.did_pause
        assert block.remap_calls == []

    def test_prompt_event_payload_is_unchanged(self) -> None:
        """FR-044 adds no key to the INTERACTIVE_PROMPT contract the frontend reads.

        ``panel_descriptor`` is spec 1's addition, not this spec's: the unified
        panel contract sends the descriptor beside the legacy manifest so the
        panel host can resolve a framed document while the old field keeps the
        pre-ADR-054 frontend working. The policy of FR-044 decides *whether* a
        prompt is raised at all and contributes no field of its own, which is
        what this assertion is here to prove.
        """
        driver, _, _, _ = _dispatch(
            _AuthoredInteractiveBlock,
            _memory_config(),
            current_signature=_CHANGED_SIGNATURE,
        )

        (prompt,) = driver.prompts
        assert set(prompt.data) == {
            "workflow_id",
            "block_type",
            "panel_manifest",
            "panel_descriptor",
            "panel_payload",
            "input_signature",
        }
        assert prompt.data["input_signature"] == _CHANGED_SIGNATURE


# --------------------------------------------------------------------------- #
# FR-045: replay is the policy, and it is read before the remap check
# --------------------------------------------------------------------------- #


class TestReplayPolicy:
    """``replay`` replays the remembered decision regardless of the signature."""

    def test_replay_never_pauses_on_a_changed_signature(self) -> None:
        """FR-045, the verification T-015 names: replay never pauses."""
        driver, _block, runner, scheduler = _dispatch(
            _PackagedStyleBlock,
            _memory_config(),
            current_signature=_CHANGED_SIGNATURE,
        )

        assert not driver.did_pause, "replay must not pause on a changed input signature"
        assert scheduler._block_states["a"] == BlockState.DONE
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == _SAVED_DECISION

    def test_replay_does_not_consult_the_remap_check(self) -> None:
        """The setting is read *before* the remap check, not after it.

        The remap check is the thing the policy decides about; under ``replay``
        it must not run at all, or a block whose override refuses a changed
        signature would still pause.
        """
        _, block, _, _ = _dispatch(
            _PackagedStyleBlock,
            _memory_config(),
            current_signature=_CHANGED_SIGNATURE,
        )

        assert block.remap_calls == []

    def test_replay_also_replays_on_an_unchanged_signature(self) -> None:
        """ "Regardless of the signature" includes the matching case."""
        driver, _, runner, _ = _dispatch(
            _PackagedStyleBlock,
            _memory_config(),
            current_signature=_SAME_SIGNATURE,
        )

        assert not driver.did_pause
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == _SAVED_DECISION

    def test_replay_with_no_memory_still_pauses(self) -> None:
        """``replay`` chooses what to do with a remembered decision.

        With nothing remembered there is nothing to replay, so the node asks —
        under ``replay`` as under ``ask``. This is what makes the setting a
        policy over the memory rather than a "never pause" switch.
        """
        driver, _, runner, _ = _dispatch(
            _PackagedStyleBlock,
            {},
            current_signature=_SAME_SIGNATURE,
        )

        assert driver.did_pause
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == {"choice": "fresh"}

    def test_node_override_replays_an_authored_block(self) -> None:
        """The node override reaches the engine, not just the resolver."""
        driver, block, runner, _ = _dispatch(
            _AuthoredInteractiveBlock,
            {**_memory_config(), ON_NEW_INPUT_KEY: "replay"},
            current_signature=_CHANGED_SIGNATURE,
        )

        assert not driver.did_pause
        assert block.remap_calls == []
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == _SAVED_DECISION

    def test_node_override_forces_a_replay_block_to_ask(self) -> None:
        """A node may put a packaged block back on the asking path."""
        driver, block, _, _ = _dispatch(
            _PackagedStyleBlock,
            {**_memory_config(), ON_NEW_INPUT_KEY: "ask"},
            current_signature=_CHANGED_SIGNATURE,
        )

        assert driver.did_pause
        assert block.remap_calls == [(_SAVED_DECISION, _SAVED_SIGNATURE, _CHANGED_SIGNATURE)]


# --------------------------------------------------------------------------- #
# FR-047 / FR-048: the packaged block's pause is the engine's existing pause
# --------------------------------------------------------------------------- #


class TestPackagedBlockReusesTheInteractivePause:
    """A packaged notebook block gets no pause of its own (FR-047, FR-048)."""

    def test_ask_pause_carries_the_confirmed_notebook_commit_to_compute(self) -> None:
        """FR-047: the confirmed decision carries a commit, and compute reads it.

        The engine treats the decision as opaque JSON, so a decision naming a
        notebook commit crosses the pause in ``interactive_response`` like any
        other — which is what lets the compute phase execute that commit's
        slice without the engine knowing anything about notebooks.
        """
        commit_decision = {"notebook_commit": "9f1c0de", "session_id": "s-1"}
        driver, _, runner, scheduler = _dispatch(
            _PackagedStyleBlock,
            {**_memory_config(), ON_NEW_INPUT_KEY: "ask"},
            current_signature=_CHANGED_SIGNATURE,
            response=commit_decision,
        )

        assert driver.did_pause
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == commit_decision
        assert scheduler._block_states["a"] == BlockState.DONE

    def test_the_pause_is_the_existing_two_phase_pause(self) -> None:
        """FR-048: one prompt phase, one PAUSED state, one fresh compute phase.

        No second pause mechanism, and the compute phase is a separate runner
        call rather than a resumption of the prompt phase.
        """
        driver, _, runner, _ = _dispatch(
            _PackagedStyleBlock,
            {**_memory_config(), ON_NEW_INPUT_KEY: "ask"},
            current_signature=_CHANGED_SIGNATURE,
        )

        assert len(driver.paused) == 1
        assert runner.run_prompt.await_count == 1
        assert runner.run.await_count == 1
        assert driver.paused[0].block_id == "a"

    def test_the_pause_holds_nothing_resident(self) -> None:
        """FR-048: the engine keeps no session, kernel, or block state alive.

        What survives the pause is the pending future and the JSON-safe
        intermediate storage references — nothing the explore subsystem owns,
        which the engine cannot import anyway. Both are released once the node
        finishes.
        """
        _, _, _, scheduler = _dispatch(
            _PackagedStyleBlock,
            {**_memory_config(), ON_NEW_INPUT_KEY: "ask"},
            current_signature=_CHANGED_SIGNATURE,
        )

        assert scheduler._interactive_futures == {}
        assert scheduler._interactive_intermediate == {}

    def test_replay_of_a_notebook_commit_runs_without_a_pause(self) -> None:
        """FR-046 read from the engine's side: replay executes the commit.

        The remembered decision of a packaged block is the notebook commit it
        was packaged from; under the default ``replay`` a run reaches the
        compute phase carrying that commit and never pauses.
        """
        commit_memory = _memory_config(decision={"notebook_commit": "9f1c0de"})
        driver, _, runner, _ = _dispatch(
            _PackagedStyleBlock,
            commit_memory,
            current_signature=_CHANGED_SIGNATURE,
        )

        assert not driver.did_pause
        assert _compute_config(runner)[INTERACTIVE_RESPONSE_KEY] == {"notebook_commit": "9f1c0de"}
