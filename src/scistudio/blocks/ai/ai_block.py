"""AIBlock — PTY-tab agent runtime per ADR-035.

This module supersedes the previous one-shot Anthropic Messages API
``AIBlock`` (see ADR-035 §2.1, §4 "Delete"). It is now an EXTERNAL-mode
block (same family as :class:`AppBlock`) that spawns a claude/codex agent
inside an ADR-034 PTY tab, hands the agent a manifest describing its
inputs and expected outputs, and waits for one of three completion
signals (MCP tool call, file watcher, user "Mark done" button) before
validating outputs and resuming the workflow.

ADR-039 §3.4a — agent commit convention
---------------------------------------
AIBlock does **not** itself invoke ``GitEngine.commit()``. When the
spawned agent (claude / codex) makes a programmatic commit on the user's
behalf, that commit MUST use the ``agent:`` prefix per ADR-039 §3.4a:

    agent: <short summary> (session=<block_execution_id>)

**Current enforcement (D39-3.2 / #968 truth check)** — there is no
in-tree ``GitEngine``-mediated path that an agent can call to apply the
prefix automatically. The convention is enforced **convention-by-prompt**:
the agent's system prompt (and ``docs/cli-integration.md``) instructs
claude / codex to prefix any ``git commit -m`` invocation it issues in
its PTY shell with ``agent: ``. The History "Manual milestones" filter
(ADR-039 §3.4) classifies commits by reading this prefix from the commit
subject directly.

A future enhancement may register an ``mcp__scistudio__git_commit`` MCP
tool that wraps ``GitEngine.commit(prefix="agent")`` so the prefix is
enforced server-side rather than by prompt. That tool does **not** exist
today; the previous version of this docstring referenced it
incorrectly.

If a future direct commit path is added inside this module, it MUST
pass ``prefix="agent"`` to keep the History filter classifying the
result correctly.

References:
    docs/adr/ADR-035.md §3 (decision), §3.1 (block category),
    §3.2 (runtime topology), §3.4 (manifest), §3.5 (completion paths),
    §3.6 (output validation), §3.7 (permission), §3.9 (state machine),
    §3.10 (engine ↔ worker IPC).
    docs/adr/ADR-039.md §3.4a (``agent:`` commit prefix convention).
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import time
import uuid
from typing import TYPE_CHECKING, Any, ClassVar, cast

from scistudio.blocks.ai.completion import (
    CompletionWatcher,
    WatcherCancelledError,
)
from scistudio.blocks.ai.run_dir import RunDir
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.exceptions import BlockCancelledByAppError
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.core.types.base import DataObject

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection

logger = logging.getLogger(__name__)


# Provider-specific spelling of bypass-permissions flag (ADR-035 §3.7).
_BYPASS_FLAG = {
    "claude-code": ["--permission-mode", "bypassPermissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
}

# Mapping from ``expected_type`` (DataObject subclass name in the manifest)
# to the ``core_type`` enum string accepted by ``LoadData`` (ADR-028 Add 1
# §C5). When a port declares a non-core type we fall back to ``Artifact``
# so the workflow still produces something loadable by downstream blocks.
_LOADER_CORE_TYPE = {
    "Array": "Array",
    "DataFrame": "DataFrame",
    "Series": "Series",
    "Text": "Text",
    "Artifact": "Artifact",
    "CompositeData": "CompositeData",
}


def _discover_provider(provider: str) -> str | None:
    """Return absolute path to the provider binary or ``None`` if missing.

    ADR-035 §3.8 references ``scistudio.ai.agent.claude_code.discover`` —
    that module does not yet exist (it is implied by ADR-034). For now
    we use ``shutil.which`` against a known executable name. The discover
    module can replace this lookup later without changing the call site.
    """
    candidates = {
        "claude-code": ["claude"],
        "codex": ["codex"],
    }
    for name in candidates.get(provider, []):
        path = shutil.which(name)
        if path:
            return path
    return None


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

    State machine (ADR-035 §3.9 — same as AppBlock)::

        IDLE → READY → RUNNING → PAUSED → DONE
                                 ↓        ↑
                                 ERROR / CANCELLED
    """

    # -- ClassVar metadata -----------------------------------------------------

    type_name: ClassVar[str] = "ai.agent"
    name: ClassVar[str] = "AI Agent"
    description: ClassVar[str] = "Spawn a claude/codex agent in a PTY tab to process inputs into typed outputs."
    subcategory: ClassVar[str] = "ai"
    version: ClassVar[str] = "0.2.0"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL

    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True

    allowed_input_types: ClassVar[list[type]] = [DataObject]
    allowed_output_types: ClassVar[list[type]] = [DataObject]

    terminate_grace_sec: ClassVar[float] = 10.0

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

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            # Hotfix 2026-05-14 (#880): BlockNode shows the top-3 by ui_priority
            # on canvas. Promote prompt + provider so users can author the agent
            # task without opening the side panel; ports stay in the side panel
            # (ui_priority unset → 999 → not in top-3) where the port editor has
            # room to breathe.
            "user_prompt": {
                "type": "string",
                "default": "",
                "title": "User prompt",
                "ui_widget": "textarea",
                "ui_priority": 1,
            },
            "provider": {
                "type": "string",
                "enum": ["claude-code", "codex"],
                "default": "claude-code",
                "title": "Provider",
                "ui_priority": 2,
            },
            "permission_mode": {
                "type": "string",
                "enum": ["safe", "bypass"],
                # Display labels are unified with the ADR-034 AI chat
                # PermissionModePicker (value ``safe`` shows as "Ask", ``bypass``
                # shows as "Bypass"). The stored enum values stay ``safe``/
                # ``bypass`` because the spawn argv logic keys on them.
                "ui_enum_labels": {"safe": "Ask", "bypass": "Bypass"},
                "default": "safe",
                "title": "Permission mode",
                "description": (
                    "Ask = agent prompts for sensitive tool use (default); "
                    "Bypass = full filesystem access — same as a hand-launched ADR-034 tab."
                ),
                "ui_priority": 3,
            },
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
            },
        },
        "required": ["user_prompt"],
    }

    # -- Lifecycle methods -----------------------------------------------------

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Drive the AI Block's PTY-tab lifecycle end-to-end (ADR-035 §3.2).

        Returns ``{port_name: Collection([loaded_obj])}`` on success.
        Returns ``{}`` after transitioning to ``CANCELLED`` (user closed
        tab, workflow cancelled, or timeout).

        Raises whatever the validation loaders raise (after recording the
        block as ERROR) — the exception text + the offending file path are
        the user-facing diagnostic per ADR-035 §3.6.
        """
        from scistudio.core.types.collection import Collection

        # 1. Resolve project_dir + block_execution_id, allocate run_dir.
        # ADR-038 §5.2: this identifier is **per AI Block execution** (one
        # per invocation of this block in a workflow run). It is NOT the
        # workflow-level ``runs.run_id`` — see ADR-038 §3.1 for that table.
        # The Python identifier was renamed in PR #933 to disambiguate the
        # two layers; the on-the-wire ``PtyTabSpec.block_run_id`` and the
        # manifest ``block.run_id`` JSON key keep their legacy spellings
        # (engine-surface + agent-facing contracts respectively).
        project_dir_raw = config.get("project_dir") or os.getcwd()
        project_dir = _to_path(project_dir_raw)
        block_execution_id = _make_block_execution_id(getattr(self, "_instance_name", None) or type(self).__name__)
        run_dir = RunDir(project_dir, block_execution_id)
        try:
            run_dir.create()
        except (PermissionError, FileExistsError) as exc:
            raise RuntimeError(f"AIBlock: cannot create run dir at {run_dir.path}: {exc}") from exc

        # 2. Build inputs → list[DataObject] per port (Collection unpack).
        inputs_unpacked: dict[str, list[DataObject]] = {}
        for port_name, value in (inputs or {}).items():
            if isinstance(value, Collection):
                inputs_unpacked[port_name] = list(value)
            elif isinstance(value, DataObject):
                inputs_unpacked[port_name] = [value]
            elif isinstance(value, list):
                inputs_unpacked[port_name] = [v for v in value if isinstance(v, DataObject)]
            # else: ignore non-DataObject values (scalar configs etc.)

        # 3. Resolve declared output ports + per-port expected_path overrides.
        # The port editor stores ``expected_path`` on each entry under
        # ``output_ports`` in the *instance* config (per ADR-029 D12); the
        # run-time ``config`` may or may not duplicate it. Prefer run-time,
        # fall back to instance config.
        effective_outputs = self.get_effective_output_ports()
        output_path_overrides = _output_path_overrides(config)
        if not output_path_overrides:
            output_path_overrides = _output_path_overrides(self.config)

        # 4. Write manifest. AIBlock runs without a wall-clock timeout: the
        #    agent is driven interactively and only stops on completion or
        #    explicit cancellation (tab close / workflow cancel), so no
        #    deadline is computed, recorded, or enforced.
        block_name = config.get("block_id") or type(self).__name__
        try:
            manifest_path = run_dir.write_manifest(
                block_name=str(block_name),
                block_type=type(self).__name__,
                user_prompt=str(config.get("user_prompt", "")),
                inputs=cast(dict[str, list[Any]], inputs_unpacked),
                outputs=effective_outputs,
                deadline_iso=None,
                output_paths=output_path_overrides,
            )
        except Exception as exc:
            raise RuntimeError(f"AIBlock: failed to write manifest: {exc}") from exc

        # 4b. Resolve declared output specs and clear any stale leftovers BEFORE
        # the agent starts (#1789). The FileWatcher completion path fires when all
        # declared expected_path files exist and are size-stable; a leftover file
        # from a previous run (the ``<block>_outputs`` dir persists) would
        # otherwise complete the block instantly before the agent produces
        # anything. Clearing them up front means completion only triggers on this
        # run's output (or the MCP finish tool / user "Mark done").
        output_specs: dict[str, dict[str, Any]] = {}
        for port in effective_outputs:
            expected_path = output_path_overrides.get(port.name) or RunDir._default_expected_path(str(block_name), port)
            expected_type = port.accepted_types[0].__name__ if port.accepted_types else "DataObject"
            output_specs[port.name] = {
                "expected_path": expected_path,
                "expected_type": expected_type,
            }
        _clear_expected_outputs(output_specs, project_dir)

        # 5. Build spawn argv.
        spawn_argv = self._build_spawn_argv(config, str(manifest_path))

        # 6. Ask engine to open a PTY tab.
        from scistudio.engine import pty_control as _pty_control

        permission_mode = str(config.get("permission_mode", "safe"))
        spec = _pty_control.PtyTabSpec(
            title=f"AI: {block_name}",
            spawn_argv=spawn_argv,
            cwd=str(project_dir),
            # #1789: ``initial_stdin`` carries the composed prompt. The engine
            # delivers it to claude/codex as a positional CLI argument at spawn
            # (see open_engine_initiated_tab → _spawn → spawn_claude/spawn_codex),
            # not by typing it into the TUI — a raw-mode TUI ignored the trailing
            # carriage return, so the prompt sat unsubmitted.
            initial_stdin=_compose_initial_stdin(str(config.get("user_prompt", "")), str(manifest_path)),
            # ``block_run_id`` is the engine-surface field name (ADR-034
            # PtyTabSpec, kept for back-compat per ADR-038 §5.2). The
            # value is the per-block-execution identifier.
            block_run_id=block_execution_id,
            permission_mode="bypass" if permission_mode == "bypass" else "safe",
            run_dir_path=str(run_dir.path),
        )
        try:
            tab_id = _pty_control.request_pty_tab(spec)
        except Exception as exc:
            raise RuntimeError(f"AIBlock: PTY spawn failed: {exc}") from exc
        logger.info("AIBlock %s: PTY tab opened, tab_id=%s", block_execution_id, tab_id)

        # 7. Agent works in the PTY tab. PAUSED visibility is tracked in #56.

        # 8. Race the three completion signals (output_specs resolved in step 4b).
        watcher = CompletionWatcher(
            run_dir=run_dir,
            output_specs=output_specs,
            project_dir=project_dir,
        )

        try:
            # No wall-clock timeout: the watcher blocks until the agent
            # completes or the run is cancelled. ``timeout_sec=None`` disables
            # the deadline in CompletionWatcher.wait.
            event = watcher.wait(timeout_sec=None)
        except WatcherCancelledError as exc:
            _safe_notify(_pty_control, block_execution_id, "cancelled_by_user_close", {"reason": "cancelled"})
            raise BlockCancelledByAppError(f"AIBlock cancelled: {exc}") from exc
        except ValueError as exc:
            # Malformed MCP signal — preserve run_dir, surface as ERROR.
            _safe_notify(_pty_control, block_execution_id, "error", {"reason": str(exc)})
            raise

        # 9. Validate + load outputs via IOBlock loaders.
        try:
            results = self._validate_and_load_outputs(
                event.outputs, output_specs, project_dir, str(config.get("output_dir", ""))
            )
        except Exception as exc:
            _safe_notify(_pty_control, block_execution_id, "error", {"reason": str(exc)})
            raise

        # 11. Notify engine; return.
        _safe_notify(
            _pty_control,
            block_execution_id,
            "completed",
            {"source": event.source.value, "tab_id": tab_id},
        )
        return results

    def validate_config(self, config: BlockConfig) -> None:
        """Validate-time config checks (ADR-035 §3.8 validate-time tier).

        Distinct from :meth:`Block.validate` (which is run-time input
        validation). Surfaces "provider not installed" before run-time so
        the user sees an actionable error message.
        """
        provider = str(config.get("provider", "claude-code"))
        if provider not in _BYPASS_FLAG:
            raise ValueError(f"AIBlock: unknown provider {provider!r}; expected one of {sorted(_BYPASS_FLAG.keys())}.")
        binary = _discover_provider(provider)
        if binary is None:
            install_hint = "scistudio install --target " + ("claude-code" if provider == "claude-code" else "codex")
            raise ValueError(
                f"AIBlock: provider {provider!r} is not installed. "
                f"Run `{install_hint}` to install it, or change the block's "
                f"provider config to a different provider."
            )
        prompt = config.get("user_prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("AIBlock: 'user_prompt' must be a non-empty string.")

    def _build_spawn_argv(self, config: BlockConfig, manifest_path: str) -> list[str]:
        """Compose the agent spawn argv (ADR-035 §3.2 step 4, §3.7).

        Argv shape mirrors the ADR-034 hand-launched tab plus the
        permission-mode flag. The initial prompt is delivered via stdin
        (see :func:`_compose_initial_stdin`); we do not put it on the
        command line.

        Raises:
            ValueError: provider unrecognised or binary not discoverable.
                (Caller has typically already run :meth:`validate_config`;
                this is defense-in-depth.)
        """
        provider = str(config.get("provider", "claude-code"))
        if provider not in _BYPASS_FLAG:
            raise ValueError(f"AIBlock: unknown provider {provider!r}.")
        binary = _discover_provider(provider)
        if binary is None:
            raise ValueError(f"AIBlock: provider {provider!r} not discoverable on PATH at spawn time.")

        argv: list[str] = [binary]

        # Provider-specific extra args. Matches the existing
        # spawn_claude/spawn_codex argv shape (see
        # src/scistudio/ai/agent/terminal.py) so a hand-launched tab and a
        # block-launched tab look identical from the agent's perspective.
        permission_mode = str(config.get("permission_mode", "safe"))
        if provider == "claude-code":
            project_dir = _to_path(config.get("project_dir") or os.getcwd())
            from scistudio.ai.agent.terminal import _ensure_mcp_config, _write_system_prompt_tempfile

            try:
                prompt_file = _write_system_prompt_tempfile(project_dir)
                mcp_config = _ensure_mcp_config(project_dir)
            except Exception as exc:
                # Audit P1-A (Codex #862-1): silently degrading argv produced a
                # `claude` invocation without --append-system-prompt /
                # --mcp-config so the worker could not call finish_ai_block and
                # the user saw a hung block. Re-raise so AIBlock.run()
                # transitions to ERROR with an actionable message.
                logger.exception("AIBlock: failed to compose system prompt / MCP config")
                raise RuntimeError(
                    f"AIBlock bootstrap failed: cannot write system prompt or MCP config: {exc}"
                ) from exc
            argv.extend(
                [
                    "--append-system-prompt",
                    f"@{prompt_file}",
                    "--mcp-config",
                    str(mcp_config),
                ]
            )
            if permission_mode == "bypass":
                # Match ADR-035 §3.7: claude uses --permission-mode bypassPermissions.
                argv.extend(_BYPASS_FLAG["claude-code"])
            # safe mode: no flag — claude defaults to interactive prompts.
        elif provider == "codex":
            if permission_mode == "bypass":
                argv.extend(_BYPASS_FLAG["codex"])
            # codex auto-reads ~/.codex/config.toml for MCP, no --mcp-config flag.

        return argv

    # -- helpers ---------------------------------------------------------------

    def _validate_and_load_outputs(
        self,
        resolved_paths: dict[str, Any],
        output_specs: dict[str, dict[str, Any]],
        project_dir: Any,
        output_dir: str,
    ) -> dict[str, Collection]:
        """Validate + load each declared output port via ``LoadData``.

        ADR-035 §3.6: validation failures keep the run_dir intact (we
        don't delete it) so the user can inspect the offending file.

        Raises ``FileNotFoundError`` when a declared output is missing,
        and propagates loader exceptions otherwise.
        """
        from pathlib import Path

        from scistudio.blocks.io.loaders.load_data import LoadData
        from scistudio.core.types.collection import Collection

        loader = LoadData()
        results: dict[str, Collection] = {}
        for port_name, spec in output_specs.items():
            path = resolved_paths.get(port_name)
            if path is None:
                raise FileNotFoundError(f"AIBlock: output port {port_name!r} resolved to no path")
            path = Path(str(path))
            if not path.is_absolute():
                path = (Path(str(project_dir)) / path).resolve()
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"AIBlock: declared output {port_name!r} not found at {path}.")
            if path.stat().st_size == 0:
                raise ValueError(f"AIBlock: declared output {port_name!r} is empty at {path}.")

            expected_type = spec.get("expected_type", "DataObject")
            core_type = _LOADER_CORE_TYPE.get(expected_type, "Artifact")
            load_config = BlockConfig(params={"core_type": core_type, "path": str(path)})
            obj = loader.load(load_config, output_dir=output_dir)
            if isinstance(obj, Collection):
                results[port_name] = obj
            else:
                results[port_name] = Collection([obj], item_type=type(obj))
        return results


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _to_path(value: Any) -> Any:
    """Coerce *value* to ``Path``; tolerate already-Path inputs."""
    from pathlib import Path

    return value if isinstance(value, Path) else Path(str(value))


def _make_block_execution_id(block_name: str) -> str:
    """``YYYYMMDD-HHMMSS-{name}-{nonce}`` per ADR-035 §3.4 example.

    Renamed from ``_make_run_id`` per ADR-038 §5.2 — this identifier is
    per AI Block execution, not per workflow run. Each invocation of one
    AI Block within a workflow run produces a fresh value.
    """
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in block_name)[:48]
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    nonce = uuid.uuid4().hex[:7]
    return f"{ts}-{safe_name}-{nonce}"


def _output_path_overrides(config: BlockConfig) -> dict[str, str]:
    """Read ``{port_name: expected_path}`` from ``config["output_ports"]``."""
    raw = config.get("output_ports") or []
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        path = entry.get("expected_path")
        if name and path:
            out[str(name)] = str(path)
    return out


def _clear_expected_outputs(output_specs: dict[str, dict[str, Any]], project_dir: Any) -> None:
    """#1789: remove pre-existing declared-output files before the agent runs.

    The FileWatcher completion path (CompletionWatcher) fires when every declared
    ``expected_path`` exists and is size-stable. The ``<block>_outputs`` dir
    persists across runs, so a leftover file from a previous run would complete
    the block immediately — before the agent produces anything. Clearing them up
    front means completion only triggers on output this run actually creates (or
    the MCP finish tool / user "Mark done"). Best-effort; missing files and
    unlink errors are ignored.
    """
    from pathlib import Path

    for spec in output_specs.values():
        raw = spec.get("expected_path")
        if not raw:
            continue
        path = Path(str(raw))
        if not path.is_absolute():
            path = (Path(str(project_dir)) / path).resolve()
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def _compose_initial_stdin(user_prompt: str, manifest_path: str) -> str:
    """First user message piped to the agent — references the manifest path."""
    return (
        f"You are running as an AI Block. Your task is in the manifest at:\n"
        f"  {manifest_path}\n\n"
        f"Read the manifest first, then complete the user's instruction:\n\n"
        f"{user_prompt}\n"
    )


def _safe_notify(
    pty_control_module: Any,
    block_run_id: str,
    event: str,
    detail: dict[str, Any],
) -> None:
    """Best-effort wrapper around ``pty_control.notify_block_pty_event``.

    Failures are logged but never propagated — the worker has already
    produced (or definitively failed to produce) its outputs; the engine
    will reconcile via the worker's exit status independently.
    """
    try:
        pty_control_module.notify_block_pty_event(block_run_id, event, detail)
    except Exception:  # pragma: no cover - best-effort lineage notification
        logger.warning("AIBlock: notify_block_pty_event failed", exc_info=True)
