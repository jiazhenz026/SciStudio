"""Category (a) MCP tools — workflow inspection and execution (10 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation. All tool
functions are decorated with ``@mcp.tool(name=..., tags={...})`` and
return Pydantic result models with ``next_step: str`` on write-class
tools per ADR-040 §3.2.

The 10 tools are:

Read-class (6): ``list_blocks``, ``get_block_schema``, ``list_types``,
``get_workflow``, ``validate_workflow``, ``get_run_status``.

Write-class (4): ``write_workflow``, ``run_workflow``, ``cancel_run``,
``finish_ai_block`` (ADR-035 §3.5 path (a)).

Per ADR-040 §3.2 style guide, each docstring is an imperative
one-liner followed by a "Use when … / Do NOT use to …" anti-pattern
section, and each write-class result model carries ``next_step``
pointing at the canonical follow-up tool.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import json
import logging
import os
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Annotated, Any

import yaml as yaml_module
from filelock import FileLock, Timeout
from pydantic import BaseModel, Field, ValidationError

from scieasy.ai.agent.mcp._context import _resolve_project_path, get_context
from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


_LOCK_TIMEOUT_SECONDS = 10.0
"""ADR-033 OQ7: file lock timeout for atomic-write tools."""


# ---------------------------------------------------------------------------
# Run-level error capture
#
# The engine emits ``block_error`` events whose ``data["error"]`` is the full
# Python traceback. The MCP layer surfaces it so the embedded agent can
# self-debug without copy/paste from the GUI.
# ---------------------------------------------------------------------------

_run_block_errors: dict[tuple[str, str], dict[str, Any]] = {}
"""``{(workflow_id, block_id): {"error": traceback, "summary": one_line}}``."""

_error_subscriber_installed: bool = False


def _ensure_error_subscriber() -> None:
    """Install a BLOCK_ERROR subscriber on the runtime's event_bus.

    Idempotent + best-effort: if the context doesn't expose ``event_bus``
    (e.g. an MCP standalone-mode runtime stub used by tests), this is a
    no-op and ``get_run_status`` will simply return an empty ``errors``
    list.
    """
    global _error_subscriber_installed
    if _error_subscriber_installed:
        return
    try:
        ctx = get_context()
    except Exception:
        return
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None or not hasattr(event_bus, "subscribe"):
        return

    async def _capture(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        if not isinstance(data, dict):
            return
        workflow_id = data.get("workflow_id")
        block_id = getattr(event, "block_id", None)
        error = data.get("error")
        summary = data.get("error_summary")
        if not workflow_id or not block_id or error is None:
            return
        _run_block_errors[(str(workflow_id), str(block_id))] = {
            "error": str(error),
            "summary": str(summary) if summary else None,
        }

    try:
        event_bus.subscribe("block_error", _capture)
        _error_subscriber_installed = True
        logger.info("MCP: installed block_error capture subscriber")
    except Exception:
        logger.warning("MCP: failed to install block_error capture", exc_info=True)


def _collect_run_errors(run_id: str) -> list[dict[str, Any]]:
    """Return the captured block errors for ``run_id`` (its workflow_id)."""
    return [
        {"block_id": block_id, "error": record["error"], "summary": record["summary"]}
        for (workflow_id, block_id), record in _run_block_errors.items()
        if workflow_id == run_id
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Serialise a :class:`BlockSpec` (dataclass) to a JSON-safe dict.

    ``input_ports`` and ``output_ports`` carry :class:`Port` instances
    that are not natively JSON-serialisable; we project them to a
    minimal {name, type, required} envelope.
    """
    if dataclasses.is_dataclass(spec) and not isinstance(spec, type):
        raw = dataclasses.asdict(spec)
    else:  # pragma: no cover - non-dataclass spec
        raw = dict(spec.__dict__)
    raw["input_ports"] = [_port_to_dict(p) for p in (spec.input_ports or [])]
    raw["output_ports"] = [_port_to_dict(p) for p in (spec.output_ports or [])]
    return raw


def _port_to_dict(port: Any) -> dict[str, Any]:
    """Project a :class:`Port` to a JSON-safe dict."""
    if isinstance(port, dict):
        return port
    type_obj = getattr(port, "type", None)
    type_name = getattr(type_obj, "__name__", str(type_obj)) if type_obj is not None else ""
    return {
        "name": getattr(port, "name", ""),
        "type": type_name,
        "required": bool(getattr(port, "required", False)),
    }


def _atomic_write_text(path: Path, text: str) -> int:
    """Write *text* to *path* via tempfile + rename. Returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return len(text.encode("utf-8"))


def _diff_summary(old: str, new: str) -> str:
    """Compact diff summary used in INFO log + return envelope."""
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines()
    added = max(0, len(new_lines) - len(old_lines))
    removed = max(0, len(old_lines) - len(new_lines))
    return f"+{added}/-{removed} lines, {len(new.encode('utf-8'))} bytes"


# ---------------------------------------------------------------------------
# Pydantic result models — ADR-040 §3.1 typed envelopes.
# ---------------------------------------------------------------------------


class BlockSpecEnvelope(BaseModel):
    """JSON-safe projection of a :class:`BlockSpec`."""

    name: str = Field(description="Registered block type name.")
    base_category: str = Field(description="One of io/process/code/app/ai/subworkflow.")
    subcategory: str | None = Field(default=None, description="Optional subcategory string.")
    version: str = Field(description="Block version string.")
    description: str = Field(description="One-line block description from BlockSpec.")
    input_ports: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Input port specs: {name, type, required}.",
    )
    output_ports: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Output port specs: {name, type, required}.",
    )
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the block's static config.",
    )

    model_config = {"extra": "allow"}


class BlockSchemaResult(BaseModel):
    """Detailed I/O ports + config_schema for one block type."""

    type_name: str = Field(description="Block type name.")
    ports: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="{'input': [...], 'output': [...]} port lists.",
    )
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the block's static config.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Block metadata: description, version, base_category, subcategory.",
    )


class TypeEntry(BaseModel):
    """One entry in the data-type registry."""

    name: str
    parent: str | None
    description: str | None
    module_path: str | None


class ListTypesResult(BaseModel):
    """Return shape for the ``list_types`` tool."""

    types: list[TypeEntry] = Field(description="Registered DataObject subtypes in declaration order.")
    count: int = Field(description="Total number of registered types.")


class WorkflowDefinitionEnvelope(BaseModel):
    """Decoded representation of a workflow YAML."""

    path: str = Field(description="Absolute resolved file path the YAML was read from.")
    name: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class ValidateWorkflowResult(BaseModel):
    """Result of validating a workflow against runtime rules."""

    valid: bool = Field(description="True if validation passed.")
    errors: list[str] = Field(default_factory=list, description="Validation error messages.")


class WriteWorkflowResult(BaseModel):
    """Result envelope for ``write_workflow``."""

    path: str = Field(description="Absolute resolved path of the written workflow.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
    diff_summary: str = Field(description="Compact diff vs prior file contents.")
    next_step: str = Field(
        default="Call mcp__scieasy__validate_workflow with the same path to confirm runtime acceptance.",
        description="Suggested next MCP call to maintain workflow integrity.",
    )


class RunWorkflowResult(BaseModel):
    """Result envelope for ``run_workflow``."""

    run_id: str = Field(description="Identifier of the queued workflow run.")
    status: str = Field(description="Initial status, typically 'queued'.")
    next_step: str = Field(
        default="Poll mcp__scieasy__get_run_status with run_id until state is terminal (succeeded/failed/cancelled).",
        description="Suggested next MCP call to observe completion.",
    )


class CancelRunResult(BaseModel):
    """Result envelope for ``cancel_run``."""

    run_id: str = Field(description="The run that was targeted.")
    cancel_requested: bool = Field(description="True if cancellation was successfully signalled.")
    next_step: str = Field(
        default="Poll mcp__scieasy__get_run_status with run_id; state should transition to 'cancelled'.",
        description="Suggested next MCP call to confirm cancellation completed.",
    )


class BlockErrorEntry(BaseModel):
    """One captured block-level error from a run."""

    block_id: str
    error: str = Field(description="Full Python traceback.")
    summary: str | None = Field(default=None, description="One-line summary of the error.")


class GetRunStatusResult(BaseModel):
    """Result envelope for ``get_run_status``."""

    run_id: str
    state: str = Field(description="One of queued/running/succeeded/failed/cancelled/unknown.")
    progress: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-block state map: {'block_states': {block_id: STATE_NAME}}.",
    )
    errors: list[BlockErrorEntry] = Field(
        default_factory=list,
        description="Captured block_error events for failed runs (full tracebacks).",
    )


class FinishAIBlockOK(BaseModel):
    """Success envelope for ``finish_ai_block``."""

    status: str = Field(default="ok", description="Always 'ok' on success.")
    signal_path: str = Field(description="Absolute path of the written signal file.")
    next_step: str = Field(
        default=(
            "The AI Block's CompletionWatcher will detect the signal and transition "
            "the block from PAUSED to RUNNING for output validation. No further MCP "
            "action required from the agent."
        ),
        description="What happens after the signal lands.",
    )


class FinishAIBlockError(BaseModel):
    """Error envelope for ``finish_ai_block``."""

    status: str = Field(default="error")
    code: str = Field(
        description="Error code: not_in_ai_block_context | invalid_outputs | already_finished | io_error."
    )
    message: str = Field(description="Human-readable error description.")


# ---------------------------------------------------------------------------
# (a.1) list_blocks
# ---------------------------------------------------------------------------


@mcp.tool(name="list_blocks", tags={"category:workflow", "read"})
async def list_blocks() -> list[BlockSpecEnvelope]:
    """List every block type registered in the active block registry.

    Use when:
      - You need to choose a block type for a new workflow node.
      - You're verifying a block name before referencing it in YAML.
      - Closing the #875 block-reuse gap before authoring a new block.

    Do NOT use to:
      - Inspect a specific block's full schema — call ``get_block_schema``.
      - Enumerate data types (use ``list_types``).
    """
    ctx = get_context()
    specs = ctx.block_registry.all_specs()
    return [BlockSpecEnvelope.model_validate(_spec_to_dict(s)) for s in specs.values()]


# ---------------------------------------------------------------------------
# (a.2) get_block_schema
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_schema", tags={"category:workflow", "read"})
async def get_block_schema(
    type_name: str = Field(description="Registered block type name (from list_blocks)."),
) -> BlockSchemaResult:
    """Return the I/O ports and config_schema for one block type.

    Use when:
      - You need port names + expected types before wiring edges.
      - You need the config_schema to populate a block's static params.

    Do NOT use to:
      - Discover available block types — call ``list_blocks`` first.

    Raises ``KeyError`` if the type is not registered.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(type_name)
    if spec is None:
        raise KeyError(f"Block type '{type_name}' is not registered")
    return BlockSchemaResult(
        type_name=spec.name,
        ports={
            "input": [_port_to_dict(p) for p in (spec.input_ports or [])],
            "output": [_port_to_dict(p) for p in (spec.output_ports or [])],
        },
        config_schema=spec.config_schema or {"type": "object", "properties": {}},
        metadata={
            "description": spec.description,
            "version": spec.version,
            "base_category": spec.base_category,
            "subcategory": spec.subcategory,
        },
    )


# ---------------------------------------------------------------------------
# (a.3) list_types
# ---------------------------------------------------------------------------


@mcp.tool(name="list_types", tags={"category:workflow", "read"})
async def list_types() -> ListTypesResult:
    """Return the full data-type registry hierarchy.

    Use when:
      - You're choosing a port ``type`` for a new block (per the
        port-type selection rule in the scieasy-write-block skill).
      - You need to verify a type name is registered before referencing it.

    Do NOT use to:
      - List block types (use ``list_blocks``).
    """
    ctx = get_context()
    types_map = ctx.type_registry.all_types()
    entries = [
        TypeEntry(
            name=spec.name,
            parent=spec.base_type,
            description=spec.description,
            module_path=spec.module_path,
        )
        for spec in types_map.values()
    ]
    return ListTypesResult(types=entries, count=len(entries))


# ---------------------------------------------------------------------------
# (a.4) get_workflow
# ---------------------------------------------------------------------------


@mcp.tool(name="get_workflow", tags={"category:workflow", "read"})
async def get_workflow(
    path: str = Field(description="Project-relative path under workflows/ (e.g. 'workflows/main.yaml')."),
) -> WorkflowDefinitionEnvelope:
    """Load a workflow YAML and return its decoded representation.

    Use when:
      - You need to read a workflow's structure before editing.
      - You need to confirm a node/edge layout before re-emitting YAML.

    Do NOT use to:
      - Validate a workflow (use ``validate_workflow``).
      - Modify a workflow (use ``write_workflow`` or ``update_block_config``).

    Raises:
      - FileNotFoundError: resolved path does not exist.
      - PermissionError: path escapes the project root.
      - RuntimeError: no project is currently open.
    """
    from scieasy.workflow.serializer import load_yaml

    p = _resolve_project_path(path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    definition = load_yaml(p)
    payload = dataclasses.asdict(definition)
    payload["path"] = str(p)
    return WorkflowDefinitionEnvelope.model_validate(payload)


# ---------------------------------------------------------------------------
# (a.5) validate_workflow
# ---------------------------------------------------------------------------


def _looks_like_inline_yaml(s: str) -> bool:
    """Heuristic: starts with ``name:`` or contains ``nodes:`` ⇒ inline."""
    stripped = s.lstrip()
    if stripped.startswith(("name:", "workflow:", "id:", "version:")):
        return True
    return "nodes:" in s and "\n" in s


@mcp.tool(name="validate_workflow", tags={"category:workflow", "read"})
async def validate_workflow(
    yaml_or_path: str = Field(
        description=(
            "Either inline YAML (starts with name:/workflow:/id:/version: or contains nodes:) "
            "or a project-relative path to a workflow YAML."
        ),
    ),
) -> ValidateWorkflowResult:
    """Validate a workflow (inline YAML or path) against runtime rules.

    Use when:
      - You want a dry-run check before calling ``write_workflow``.
      - You're diagnosing why a workflow won't run.

    Do NOT use to:
      - Persist a workflow — call ``write_workflow`` (which also validates).
      - Inspect a workflow's structure — call ``get_workflow``.
    """
    from scieasy.workflow.schema import WorkflowFileModel
    from scieasy.workflow.validator import validate_workflow as _validate

    ctx = get_context()
    inline = _looks_like_inline_yaml(yaml_or_path)
    try:
        if inline:
            raw = yaml_module.safe_load(yaml_or_path)
            validated = WorkflowFileModel.model_validate(raw)
            definition = validated.workflow.to_definition()
        else:
            from scieasy.workflow.serializer import load_yaml

            resolved = _resolve_project_path(yaml_or_path)
            definition = load_yaml(resolved)
    except Exception as exc:
        return ValidateWorkflowResult(valid=False, errors=[f"parse failure: {exc}"])

    errors = _validate(definition, registry=ctx.block_registry)
    return ValidateWorkflowResult(valid=not errors, errors=list(errors))


# ---------------------------------------------------------------------------
# (a.6) write_workflow  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="write_workflow", tags={"category:workflow", "write"})
async def write_workflow(
    path: str = Field(description="Project-relative path under workflows/."),
    yaml: str = Field(description="Full workflow YAML content; will be schema-validated before write."),
) -> WriteWorkflowResult:
    """Persist a workflow YAML to disk with a file lock and pre-write schema validation.

    Use when:
      - You're creating a new workflow or replacing an existing one.

    Do NOT use to:
      - Patch one block's config (use ``update_block_config`` — preserves
        comments and key order via ruamel.yaml round-trip).
      - Edit ``workflows/*.yaml`` via Bash/Edit/Write tools — the
        protect_workflow_yaml hook (ADR-040 §3.6) will block such calls.
        This tool is the ONLY supported write path for workflows.

    Returns ``WriteWorkflowResult`` with ``next_step`` pointing at
    ``validate_workflow`` for canonical post-write verification.
    """
    from scieasy.workflow.schema import WorkflowFileModel

    # Pre-write validation: parse YAML and run through the same pydantic
    # model the runtime + GET route use. Failure raises ValueError with
    # JSON-embedded structured pydantic errors.
    try:
        parsed = yaml_module.safe_load(yaml)
    except yaml_module.YAMLError as exc:
        raise ValueError(f"write_workflow: YAML parse failure: {exc}") from exc
    try:
        WorkflowFileModel.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(
            "write_workflow: refusing to write — workflow does not match "
            "the SciEasy schema. Errors (JSON):\n" + json.dumps(exc.errors(), indent=2, default=str)
        ) from exc

    p = _resolve_project_path(path)
    lock_path = str(p) + ".lock"
    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            bytes_written = _atomic_write_text(p, yaml)
            summary = _diff_summary(old, yaml)
    except Timeout as exc:
        raise TimeoutError(
            f"write_workflow: could not acquire lock for {p} within {_LOCK_TIMEOUT_SECONDS}s (someone else is editing?)"
        ) from exc

    logger.info("write_workflow: wrote %s (%s)", p, summary)
    return WriteWorkflowResult(path=str(p), bytes_written=bytes_written, diff_summary=summary)


# ---------------------------------------------------------------------------
# (a.7) run_workflow  (write-class)
# ---------------------------------------------------------------------------


def _get_workflow_runtime() -> Any:
    """Locate a runtime that knows how to start workflows."""
    ctx = get_context()
    if not hasattr(ctx, "start_workflow"):
        raise RuntimeError(
            "Active MCPContext does not expose start_workflow(); run_workflow requires a full ApiRuntime."
        )
    return ctx


@mcp.tool(name="run_workflow", tags={"category:workflow", "write"})
async def run_workflow(
    path: str = Field(description="Project-relative path to the workflow YAML to execute."),
) -> RunWorkflowResult:
    """Submit a workflow for execution and return its run identifier.

    Use when:
      - You've written/validated a workflow and want to execute it.

    Do NOT use to:
      - Re-run a previously failed run with code fixes — write the fix
        first (``write_workflow`` or block source edit + ``reload_blocks``),
        then call this.
      - Inspect run progress — poll ``get_run_status`` with the returned
        ``run_id``.

    Returns immediately with status='queued'. Progress is observable via
    ``get_run_status``.
    """
    runtime = _get_workflow_runtime()
    _ensure_error_subscriber()
    resolved = _resolve_project_path(path)
    workflow_id = resolved.stem
    # Clear stale errors from a prior failed run with the same id.
    for key in list(_run_block_errors.keys()):
        if key[0] == workflow_id:
            del _run_block_errors[key]
    result = runtime.start_workflow(workflow_id)
    run_id = result.get("workflow_id", workflow_id) if isinstance(result, dict) else workflow_id
    logger.info("run_workflow: started run %s for %s", run_id, resolved)
    return RunWorkflowResult(run_id=str(run_id), status="queued")


# ---------------------------------------------------------------------------
# (a.8) cancel_run  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="cancel_run", tags={"category:workflow", "write"})
async def cancel_run(
    run_id: str = Field(description="Identifier returned by run_workflow."),
) -> CancelRunResult:
    """Request cancellation of an in-flight workflow run.

    Use when:
      - A run is producing wrong results and you want to stop it early.
      - A run is hung and needs to be terminated.

    Do NOT use to:
      - Inspect run state — use ``get_run_status``.

    Raises ``KeyError`` if the run_id is unknown.
    """
    import asyncio

    from scieasy.engine.events import CANCEL_WORKFLOW_REQUEST, EngineEvent

    runtime = _get_workflow_runtime()
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")

    run = runs[run_id]
    event_bus = getattr(run.scheduler, "_event_bus", None) if hasattr(run, "scheduler") else None
    if event_bus is None:
        if hasattr(run, "task") and not run.task.done():
            run.task.cancel()
        cancel_requested = True
    else:
        coro = event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": run_id}))
        try:
            loop = asyncio.get_running_loop()
            run._cancel_task = loop.create_task(coro)  # type: ignore[attr-defined]
        except RuntimeError:
            await coro
        cancel_requested = True

    logger.info("cancel_run: requested cancellation for %s", run_id)
    return CancelRunResult(run_id=run_id, cancel_requested=cancel_requested)


# ---------------------------------------------------------------------------
# (a.9) get_run_status
# ---------------------------------------------------------------------------


@mcp.tool(name="get_run_status", tags={"category:workflow", "read"})
async def get_run_status(
    run_id: str = Field(description="Identifier returned by run_workflow."),
) -> GetRunStatusResult:
    """Return the current status of a workflow run.

    Use when:
      - Polling for completion after ``run_workflow``.
      - Diagnosing a failed run — failed runs include full Python
        tracebacks per block in the ``errors`` field.

    Do NOT use to:
      - Inspect block outputs — use ``get_block_output``.
      - Read block log files — use ``get_block_logs``.

    Raises ``KeyError`` if the run_id is unknown.
    """
    runtime = _get_workflow_runtime()
    runs = getattr(runtime, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")

    _ensure_error_subscriber()

    run = runs[run_id]
    task = getattr(run, "task", None)
    if task is None:
        state = "unknown"
    elif task.done():
        if task.cancelled():
            state = "cancelled"
        elif task.exception() is not None:
            state = "failed"
        else:
            state = "succeeded"
    else:
        state = "running"

    block_states: dict[str, str] = {}
    scheduler = getattr(run, "scheduler", None)
    if scheduler is not None:
        raw_states = getattr(scheduler, "_block_states", {})
        block_states = {
            block_id: getattr(state_obj, "name", str(state_obj)) for block_id, state_obj in raw_states.items()
        }

    raw_errors = _collect_run_errors(run_id)
    if state == "failed" and not raw_errors and task is not None:
        try:
            exc = task.exception()
        except Exception:
            exc = None
        if exc is not None:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            raw_errors.append(
                {
                    "block_id": "__run__",
                    "error": tb_str,
                    "summary": str(exc) or type(exc).__name__,
                }
            )

    return GetRunStatusResult(
        run_id=run_id,
        state=state,
        progress={"block_states": block_states},
        errors=[BlockErrorEntry(**e) for e in raw_errors],
    )


# Synthesised module ID for log correlation.
_TOOL_MODULE_ID = f"mcp-workflow-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# (a.10) finish_ai_block  (write-class, ADR-035 §3.5)
# ---------------------------------------------------------------------------


def _resolve_ai_block_run_dir() -> Path | None:
    """Locate the active AI Block run dir from MCP context or env var.

    Resolution order (first hit wins):

      1. ``MCPContext.ai_block_run_dir`` attribute, when present.
      2. ``SCIEASY_AI_BLOCK_RUN_DIR`` environment variable.

    Returns ``None`` when neither is configured.
    """
    try:
        ctx = get_context()
    except Exception:
        ctx = None
    if ctx is not None:
        run_dir = getattr(ctx, "ai_block_run_dir", None)
        if run_dir is not None:
            return Path(run_dir)
    raw = os.environ.get("SCIEASY_AI_BLOCK_RUN_DIR")
    if raw:
        candidate = Path(raw)
        if candidate.is_dir():
            return candidate
    return None


@mcp.tool(name="finish_ai_block", tags={"category:workflow", "write"})
async def finish_ai_block(
    outputs: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "{port_name: absolute_or_project_relative_path} for every declared output port. "
                "None is accepted and treated as {} (FileWatcher path will validate via expected_path)."
            ),
        ),
    ] = None,
) -> FinishAIBlockOK | FinishAIBlockError:
    """Signal the active AI Block that all declared outputs have been written.

    Use when:
      - You're an AI Block worker that has finished writing every output
        file declared in the block's port manifest. Call this exactly once.

    Do NOT use to:
      - Signal partial completion — the AI Block treats the signal as
        terminal. If you can't produce an output, raise an error in your
        worker code instead.
      - Call from outside an AI Block context — returns
        ``not_in_ai_block_context`` error envelope per ADR-035 §3.5.

    The tool writes ``signals/finish_ai_block.json`` under the active
    run dir; the CompletionWatcher polls for that file and transitions
    the block from PAUSED → RUNNING for output validation. Atomic write
    (tempfile + os.replace) — partial writes cannot deceive the watcher.

    Error codes:
      - ``not_in_ai_block_context`` — no active AI Block run dir.
      - ``invalid_outputs`` — outputs is not dict[str, str].
      - ``already_finished`` — signal file already exists for this run.
      - ``io_error`` — disk-level write failure.
    """
    run_dir = _resolve_ai_block_run_dir()
    if run_dir is None:
        return FinishAIBlockError(
            code="not_in_ai_block_context",
            message=(
                "finish_ai_block can only be called from inside an AI Block. "
                "No active AI Block run dir was found via MCPContext.ai_block_run_dir "
                "or the SCIEASY_AI_BLOCK_RUN_DIR environment variable."
            ),
        )

    if outputs is None:
        outputs_norm: dict[str, str] = {}
    elif isinstance(outputs, dict):
        bad = [(k, type(v).__name__) for k, v in outputs.items() if not isinstance(k, str) or not isinstance(v, str)]
        if bad:
            return FinishAIBlockError(
                code="invalid_outputs",
                message=(f"finish_ai_block: outputs must be dict[str, str]. Bad entries (key, value-type): {bad}"),
            )
        outputs_norm = dict(outputs)
    else:
        return FinishAIBlockError(
            code="invalid_outputs",
            message=(f"finish_ai_block: outputs must be a dict, got {type(outputs).__name__}"),
        )

    signals_dir = run_dir / "signals"
    try:
        signals_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FinishAIBlockError(
            code="io_error",
            message=f"finish_ai_block: failed to create signals dir: {exc}",
        )

    signal_path = signals_dir / "finish_ai_block.json"
    if signal_path.exists():
        return FinishAIBlockError(
            code="already_finished",
            message=(f"finish_ai_block has already been called for this AI Block run. Existing signal: {signal_path}"),
        )

    payload = {
        "outputs": outputs_norm,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    body = json.dumps(payload, indent=2, sort_keys=True)
    try:
        _atomic_write_text(signal_path, body)
    except OSError as exc:
        return FinishAIBlockError(
            code="io_error",
            message=f"finish_ai_block: failed to write signal file: {exc}",
        )

    logger.info(
        "finish_ai_block: wrote signal %s with %d output(s)",
        signal_path,
        len(outputs_norm),
    )
    return FinishAIBlockOK(signal_path=str(signal_path))
