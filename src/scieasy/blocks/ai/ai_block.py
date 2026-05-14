"""AIBlock — PTY-tab agent runtime per ADR-035 (skeleton).

This module supersedes the previous one-shot Anthropic Messages API
``AIBlock`` (see ADR-035 §2.1, §4 "Delete"). Implementation phase agents
fill in the bodies; this skeleton only nails down the public surface and
documents the implementation plan inline.

References:
    docs/adr/ADR-035.md §3 (decision), §3.1 (block category),
    §3.2 (runtime topology), §3.4 (manifest), §3.5 (completion paths),
    §3.6 (output validation), §3.7 (permission), §3.9 (state machine),
    §3.10 (engine ↔ worker IPC).

Skeleton invariants (per docs/planning/agent-prompt-templates/skeleton-agent.md):
    * Every method body raises ``NotImplementedError("see comment block above")``
    * Every NotImplementedError is preceded by a docstring + structured
      implementation-plan comment.
    * No real logic — pure scaffolding.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.state import ExecutionMode
from scieasy.core.types.base import DataObject

if TYPE_CHECKING:
    from scieasy.core.types.collection import Collection

logger = logging.getLogger(__name__)


class AIBlock(Block):
    """Workflow-graph node that spawns a claude/codex agent in an ADR-034 PTY tab.

    Per ADR-035 §3.1 the block is **EXTERNAL** mode (same family as
    :class:`AppBlock`), not :class:`ProcessBlock`: the entire input
    Collection is presented to the agent at once via a manifest, the
    agent runs autonomously inside a visible PTY tab, and completion is
    signalled via one of three paths (MCP tool, file watcher, user
    button — see ADR-035 §3.5).

    Variadic ports reuse ADR-029 verbatim. Type allowlists are
    deliberately permissive — the agent can in principle produce any
    ``DataObject`` subtype.

    Implementation plan (per ADR-035 §3.2 "Runtime topology"):
        1. ``run()`` writes ``manifest.json`` under
           ``{project}/.scieasy/ai-block-runs/{run_id}/`` (see :class:`RunDir`).
        2. Worker → engine control event ``request_pty_tab(spec=...)``
           opens an ADR-034 PTY tab with the same argv shape as a
           hand-launched tab (no ``--add-dir`` restriction; full agent
           capabilities; see ADR-035 §3.7).
        3. Worker enters PAUSED, waits on the
           :class:`scieasy.blocks.ai.completion.CompletionWatcher`.
        4. On completion signal: validate outputs via the existing
           IOBlock loader registry (ADR-035 §3.6), wrap as typed
           ``DataObject``s keyed by output port name, return.
        5. On cancellation: ``ProcessHandle.terminate()`` with
           ``terminate_grace_sec`` grace, transition to CANCELLED.
        6. Tab stays open and remains interactive after DONE/ERROR
           (ADR-035 §3.9). Title gets a status decoration (✓ / ✗).

    State machine (ADR-035 §3.9 — same as AppBlock):
        IDLE → READY → RUNNING → PAUSED → DONE
                                 ↓        ↑
                                 ERROR / CANCELLED

    References:
        ADR-035 §3.1, §3.2, §3.5, §3.6, §3.9
        src/scieasy/blocks/app/app_block.py (sibling EXTERNAL-mode block)
    """

    # -- ClassVar metadata -----------------------------------------------------

    type_name: ClassVar[str] = "ai.agent"
    name: ClassVar[str] = "AI Agent"
    description: ClassVar[str] = "Spawn a claude/codex agent in a PTY tab to process inputs into typed outputs."
    subcategory: ClassVar[str] = "ai"
    version: ClassVar[str] = "0.2.0"

    # ADR-035 §3.1 decision: EXTERNAL mode (same family as AppBlock).
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL

    # ADR-035 §3.1 decision: variadic ports — user declares inputs/outputs at
    # config time via the ADR-029 port editor.
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True

    # ADR-035 §3.1 decision: deliberately permissive type allowlists.
    allowed_input_types: ClassVar[list[type]] = [DataObject]
    allowed_output_types: ClassVar[list[type]] = [DataObject]

    # ADR-035 §3.1: 10s grace period for ProcessHandle.terminate() on cancel.
    terminate_grace_sec: ClassVar[float] = 10.0

    # Default scaffold ports — replaced per-instance via the port editor when
    # variadic flags are True. Kept as a hint for users dragging the block in
    # from the palette.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="data",
            accepted_types=[DataObject],
            required=False,
            is_collection=True,
            description="Inputs handed to the agent via manifest.json (any DataObject).",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="result",
            accepted_types=[DataObject],
            is_collection=False,
            description="Output port; the agent writes a file at the configured expected_path.",
        ),
    ]

    # ADR-035 §3.3 block-level UI. Choices stored in ``block.config`` so they
    # survive workflow save/load and become part of lineage.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "enum": ["claude-code", "codex"],
                "default": "claude-code",
                "title": "Provider",
            },
            "permission_mode": {
                "type": "string",
                "enum": ["safe", "bypass"],
                "default": "safe",
                "title": "Permission mode",
                "description": (
                    "safe = agent prompts for sensitive tool use (default); "
                    "bypass = full filesystem access — same as a hand-launched ADR-034 tab."
                ),
            },
            "user_prompt": {
                "type": "string",
                "default": "",
                "title": "User prompt",
                "ui_widget": "textarea",
            },
            "timeout_sec": {
                "type": "integer",
                "default": 1800,
                "minimum": 1,
                "title": "Timeout (seconds)",
            },
            # ADR-029 D12: port editor fields injected via MRO merge (ADR-030).
            "input_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "default": [],
                "title": "Input Ports",
                "ui_widget": "port_editor",
                "ui_priority": 10,
            },
            "output_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                        "expected_path": {"type": "string"},
                    },
                },
                "default": [],
                "title": "Output Ports",
                "ui_widget": "port_editor",
                "ui_priority": 11,
            },
        },
        "required": ["user_prompt"],
    }

    # -- Lifecycle methods (all stubbed) --------------------------------------

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Drive the AI Block's PTY-tab lifecycle end-to-end.

        Implementation plan (per ADR-035 §3.2):
            1. Allocate a :class:`RunDir` under
               ``{project}/.scieasy/ai-block-runs/{run_id}/``.
            2. Materialize input storage refs to absolute paths (no copy /
               no symlink — paths are recorded verbatim per §3.4).
            3. Write ``manifest.json`` with the schema in ADR-035 §3.4 via
               :meth:`RunDir.write_manifest`.
            4. Build the spawn argv via the existing
               ``scieasy.ai.agent.terminal.spawn_claude/_codex`` builders;
               include ``--append-system-prompt`` (SKILL.md), ``--mcp-config``
               (project .mcp.json), and ``--permission-mode`` per
               ``config["permission_mode"]``.
            5. Call :func:`scieasy.engine.pty_control.request_pty_tab` to ask
               the engine to open the tab. Block until ``tab_id`` returned.
            6. Engine emits ``block_pty_opened`` to the frontend; the block
               transitions RUNNING → PAUSED.
            7. Construct a :class:`CompletionWatcher` covering all three
               paths (MCP signal file in run_dir, FileWatcher on each
               port's ``expected_path``, user "Mark done" event).
            8. ``await watcher.wait(timeout=config["timeout_sec"])`` until
               one signal fires (PAUSED → RUNNING).
            9. Validate outputs: for each declared output port, resolve its
               final path (from the MCP signal or ``expected_path``), check
               existence + size, dispatch to the IOBlock loader registered
               for the declared type. On any failure → ERROR with
               ``termination_detail`` containing the loader exception
               (ADR-035 §3.6). The run_dir is preserved for post-mortem.
            10. Wrap each loaded ``DataObject`` into a single-element
                :class:`Collection` keyed by port name. Return the dict.
            11. Notify engine of completion via
                :func:`scieasy.engine.pty_control.notify_block_pty_event`
                with ``event="completed"``.
            12. Tab stays open per ADR-035 §3.9 — caller (engine) does not
                close it; user closes manually.

        Edge cases:
            * Spawn fails (binary deleted between validate and run, etc.)
              → ERROR with ``termination_detail`` containing exception
              (ADR-035 §3.8 run-time tier).
            * Agent exits cleanly without ``finish_ai_block`` and not all
              ``expected_path`` files exist → ERROR with
              "agent exited without completing all outputs"
              (ADR-035 §8 OQ-2; tentative — confirm in PoC).
            * User closes tab → CANCELLED via worker's IPC subscription.
            * Workflow cancel → :meth:`ProcessHandle.terminate()` with
              :attr:`terminate_grace_sec` grace.
            * Timeout exceeded → CANCELLED with
              ``termination_detail="timeout"`` then graceful kill.
            * ``finish_ai_block`` called twice → second call is rejected
              by the MCP tool (ADR-035 §8 OQ-1; tentative error).

        Test plan:
            * test_run_writes_manifest_with_correct_shape (positive)
            * test_run_request_pty_tab_with_safe_permission (positive)
            * test_run_request_pty_tab_with_bypass_permission (positive)
            * test_run_completion_via_mcp_finish_ai_block (positive)
            * test_run_completion_via_file_watcher (positive — fallback path)
            * test_run_completion_via_mark_done_button (positive — escape hatch)
            * test_run_validation_fail_returns_error_state (negative)
            * test_run_spawn_fail_returns_error (negative)
            * test_run_user_close_tab_cancels (negative)
            * test_run_timeout_cancels (negative)
            * test_run_double_finish_call_rejected (edge — tentative per OQ-1)
            * test_run_preserves_run_dir_on_validation_fail (edge)

        References:
            ADR-035 §3.2, §3.5, §3.6, §3.8, §3.9, §8 (open questions);
            src/scieasy/blocks/app/app_block.py:: AppBlock.run() pattern.
        """
        raise NotImplementedError("see comment block above")

    def validate_config(self, config: BlockConfig) -> None:
        """Validate-time config checks (ADR-035 §3.8 validate-time tier).

        Distinct from :meth:`Block.validate` (which is run-time input
        validation). This is invoked by the workflow validator before any
        block runs, so a missing provider binary surfaces with an
        actionable error rather than waiting until run-time.

        Implementation plan:
            1. (No super() call — this is a separate, AIBlock-specific hook.)
            2. Resolve provider via ``config["provider"]``.
            3. Call ``scieasy.ai.agent.claude_code.discover.discover_<provider>()``
               (or codex variant). If binary not discoverable, raise
               ``ValueError`` with the actionable message including the exact
               ``scieasy install`` command per ADR-035 §3.8.
            4. Validate ``config["user_prompt"]`` is a non-empty string.
            5. Validate ``config["timeout_sec"] > 0``.
            6. For each declared output port, validate ``expected_path`` is a
               non-empty string. Defaults to
               ``./{block_name}_outputs/{port}.{ext}`` per ADR-035 §3.3.

        Edge cases:
            * Provider == "claude-code" but only "codex" installed → fail with
              the install hint for claude-code.
            * Both installed → succeed silently.
            * No output ports declared → succeed (degenerate; agent runs but
              nothing to validate). The watcher will then only have the user
              "Mark done" path.

        Test plan:
            * test_validate_succeeds_when_provider_installed
            * test_validate_fails_with_install_hint_when_missing
            * test_validate_rejects_empty_prompt
            * test_validate_rejects_negative_timeout

        References:
            ADR-035 §3.8 "Validate-time"; src/scieasy/ai/agent/claude_code/discover.py
        """
        raise NotImplementedError("see comment block above")

    def _build_spawn_argv(self, config: BlockConfig, manifest_path: str) -> list[str]:
        """Compose the agent spawn argv.

        Implementation plan (per ADR-035 §3.2 step 4):
            1. Resolve provider binary via ``discover_<provider>()``.
            2. Append ``--append-system-prompt <SKILL.md>`` (existing path).
            3. Append ``--mcp-config <project .mcp.json>``.
            4. Append ``--permission-mode <safe|bypass>`` (provider-specific
               flag spelling: claude uses ``--permission-mode bypassPermissions``;
               codex uses ``--dangerously-bypass-approvals-and-sandbox``).
            5. Append the initial prompt via stdin or as positional — match
               whatever the existing terminal builder uses for hand-launched
               tabs (the goal is shape-identical argv per ADR-035 §3.2).

        Edge cases:
            * Provider unrecognized → ``ValueError`` (caller has already
              validated; this is a defense-in-depth check).

        Test plan:
            * test_build_argv_claude_safe_mode
            * test_build_argv_claude_bypass_mode_uses_bypassPermissions_flag
            * test_build_argv_codex_safe_mode
            * test_build_argv_codex_bypass_mode_uses_dangerously_bypass_flag
            * test_build_argv_includes_skill_and_mcp_paths

        References:
            ADR-035 §3.2 step 4, §3.7 permission model;
            src/scieasy/ai/agent/terminal.py spawn_claude/spawn_codex
        """
        raise NotImplementedError("see comment block above")
