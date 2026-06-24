"""Read-class workflow tools (6 of 10).

Tools: ``list_blocks``, ``get_block_schema``, ``list_types``,
``get_workflow``, ``validate_workflow``, ``get_run_status``.

Extracted from the original single-file ``tools_workflow.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

import dataclasses
import logging
import traceback

import yaml as yaml_module
from pydantic import Field

from scistudio.ai.agent.mcp._context import _resolve_project_path, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_workflow._errors import (
    _collect_run_errors,
    _ensure_error_subscriber,
)
from scistudio.ai.agent.mcp.tools_workflow._helpers import (
    _get_workflow_runtime,
    _looks_like_inline_yaml,
    _port_to_dict,
    _spec_to_dict,
)
from scistudio.ai.agent.mcp.tools_workflow._models import (
    ActiveWorkflowContextResult,
    BlockErrorEntry,
    BlockSchemaResult,
    BlockSpecEnvelope,
    GetRunStatusResult,
    ListTypesResult,
    TypeEntry,
    ValidateWorkflowResult,
    WorkflowDefinitionEnvelope,
)
from scistudio.blocks.io._config_enrichment import enrich_io_config_schema

logger = logging.getLogger(__name__)


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
    envelopes: list[BlockSpecEnvelope] = []
    for spec in specs.values():
        raw = _spec_to_dict(spec)
        # Apply the same dynamic core_type enum the HTTP block API serves, so the
        # agent's contract matches the GUI / validate_workflow (shared source of
        # truth in scistudio.blocks.io._config_enrichment).
        raw["config_schema"] = enrich_io_config_schema(spec, ctx.block_registry, ctx.type_registry)
        envelopes.append(BlockSpecEnvelope.model_validate(raw))
    return envelopes


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
        config_schema=enrich_io_config_schema(spec, ctx.block_registry, ctx.type_registry),
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
        port-type selection rule in the scistudio-write-block skill).
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
    from scistudio.workflow.serializer import load_yaml

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
    from scistudio.workflow.schema import WorkflowFileModel
    from scistudio.workflow.validator import validate_workflow as _validate

    ctx = get_context()
    inline = _looks_like_inline_yaml(yaml_or_path)
    try:
        if inline:
            raw = yaml_module.safe_load(yaml_or_path)
            validated = WorkflowFileModel.model_validate(raw)
            definition = validated.workflow.to_definition()
        else:
            from scistudio.workflow.serializer import load_yaml

            resolved = _resolve_project_path(yaml_or_path)
            definition = load_yaml(resolved)
    except Exception as exc:
        return ValidateWorkflowResult(valid=False, errors=[f"parse failure: {exc}"])

    errors = _validate(definition, registry=ctx.block_registry)
    return ValidateWorkflowResult(valid=not errors, errors=list(errors))


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


# ---------------------------------------------------------------------------
# (a.10) get_active_workflow_context — ADR-040 Addendum 5 / #1488
# ---------------------------------------------------------------------------


@mcp.tool(name="get_active_workflow_context", tags={"category:workflow", "read"})
async def get_active_workflow_context() -> ActiveWorkflowContextResult:
    """Return the workflow id the GUI editor currently has open.

    Use when:
      - The user mentions "this workflow" / "the current workflow"
        without naming it.
      - You need editor-context awareness (VS Code Copilot-style)
        before deciding which `get_workflow` to call.

    Do NOT use to:
      - Load a workflow's full structure — call ``get_workflow`` with
        the returned id (``workflows/<id>.yaml``).
      - List every workflow in the project — call ``list_workflows``
        via the runtime instead.

    Both fields are ``None`` when no workflow is open in the GUI or
    when no project is active. ``workflow_name`` falls back to the
    workflow id when the underlying YAML carries no
    ``metadata.title`` / ``metadata.name``.
    """
    ctx = get_context()
    # ADR-040 Addendum 5 / #1488. Defensive read: older third-party
    # MCPContext implementations (e.g. test stubs, alternate adapters)
    # predate this Protocol member, so an AttributeError here would
    # take the whole tool offline. ``getattr`` keeps the worst case
    # to a None envelope rather than a 500.
    workflow_id = getattr(ctx, "active_workflow_id", None)
    if not workflow_id:
        return ActiveWorkflowContextResult(workflow_id=None, workflow_name=None)
    # Best-effort name resolution. A missing / unreadable file MUST NOT
    # raise — the agent gets at least the id back so it can still pass
    # the right key to ``get_workflow`` for the authoritative load.
    workflow_name: str | None = workflow_id
    try:
        path = _resolve_project_path(f"workflows/{workflow_id}.yaml")
        if path.exists():
            raw = yaml_module.safe_load(path.read_text(encoding="utf-8")) or {}
            metadata = raw.get("metadata") if isinstance(raw, dict) else None
            if isinstance(metadata, dict):
                candidate = metadata.get("title") or metadata.get("name")
                if isinstance(candidate, str) and candidate:
                    workflow_name = candidate
    except (OSError, ValueError, RuntimeError, PermissionError, yaml_module.YAMLError) as exc:
        logger.debug(
            "get_active_workflow_context: name resolution failed for %s (%s)",
            workflow_id,
            exc,
        )
    return ActiveWorkflowContextResult(workflow_id=workflow_id, workflow_name=workflow_name)


__all__: list[str] = [
    "get_active_workflow_context",
    "get_block_schema",
    "get_run_status",
    "get_workflow",
    "list_blocks",
    "list_types",
    "validate_workflow",
]
