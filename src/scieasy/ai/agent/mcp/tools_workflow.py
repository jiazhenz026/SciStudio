"""Category (a) MCP tools — workflow inspection and execution (10 tools).

ADR-040 §3.1 FastMCP migration, S40a skeleton phase. All tool functions
are decorated with ``@mcp.tool(name=...)`` and declare Pydantic result
models with ``next_step: str`` on write-class tools. Bodies raise
:class:`NotImplementedError` with a detailed ``# TODO(#1012)`` comment
block describing the impl approach for I40a Phase 2a.

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

import logging
from typing import Annotated, Any

from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic result models — ADR-040 §3.1 typed envelopes.
# ---------------------------------------------------------------------------


class BlockSpecEnvelope(BaseModel):
    """JSON-safe projection of a :class:`BlockSpec`.

    Mirrors what :func:`_spec_to_dict` produces in the ADR-033-era
    implementation: name, base_category, subcategory, version,
    description, input_ports, output_ports, config_schema. Ports are
    serialised as ``{name, type, required}`` triples.
    """

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
    """Decoded representation of a workflow YAML.

    The shape mirrors :func:`dataclasses.asdict` on a
    :class:`scieasy.workflow.schema.WorkflowDefinition` plus a top-level
    ``path`` echoing the absolute resolved file path.
    """

    path: str = Field(description="Absolute resolved file path the YAML was read from.")
    name: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    # I40a may add ``metadata``, ``version``, etc. fields per
    # WorkflowDefinition's actual shape.


class ValidateWorkflowResult(BaseModel):
    """Result of validating a workflow against runtime rules."""

    valid: bool = Field(description="True if validation passed.")
    errors: list[str] = Field(default_factory=list, description="Validation error messages.")


class WriteWorkflowResult(BaseModel):
    """Result envelope for ``write_workflow``.

    Carries ``next_step`` pointing at ``validate_workflow`` so the agent
    knows the canonical post-write verification step.
    """

    path: str = Field(description="Absolute resolved path of the written workflow.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
    diff_summary: str = Field(description="Compact diff vs prior file contents.")
    next_step: str = Field(
        default="Call mcp__scieasy__validate_workflow with the same path to confirm runtime acceptance.",
        description="Suggested next MCP call to maintain workflow integrity.",
    )


class RunWorkflowResult(BaseModel):
    """Result envelope for ``run_workflow``.

    ``next_step`` points at ``get_run_status`` so the agent knows to
    poll for completion.
    """

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
    """Error envelope for ``finish_ai_block``.

    Codes per ADR-035 §3.5:
      - ``not_in_ai_block_context`` — no active AI Block run dir.
      - ``invalid_outputs`` — outputs is not dict[str, str].
      - ``already_finished`` — signal file already present (ADR-035 §8 OQ-1).
      - ``io_error`` — disk-level write failure.
    """

    status: str = Field(default="error")
    code: str = Field(
        description="Error code: not_in_ai_block_context | invalid_outputs | already_finished | io_error."
    )
    message: str = Field(description="Human-readable error description.")


# ---------------------------------------------------------------------------
# (a.1) list_blocks
# ---------------------------------------------------------------------------


@mcp.tool(name="list_blocks")
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
    # TODO(#1012): port the ADR-033-era impl from the prior file shape.
    #   Reference impl (pre-FastMCP):
    #     ctx = get_context()
    #     specs = ctx.block_registry.all_specs()
    #     return [_spec_to_dict(spec) for spec in specs.values()]
    #
    #   I40a Phase 2a fills in: replace the dict return with
    #   ``[BlockSpecEnvelope(**_spec_to_dict(s)) for s in specs.values()]``
    #   so the FastMCP-generated inputSchema is precise.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.2) get_block_schema
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_schema")
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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #     ctx = get_context()
    #     spec = ctx.block_registry.get_spec(type_name)
    #     if spec is None: raise KeyError(...)
    #     return BlockSchemaResult(
    #         type_name=spec.name,
    #         ports={
    #             "input": [_port_to_dict(p) for p in spec.input_ports or []],
    #             "output": [_port_to_dict(p) for p in spec.output_ports or []],
    #         },
    #         config_schema=spec.config_schema or {"type": "object", "properties": {}},
    #         metadata={
    #             "description": spec.description,
    #             "version": spec.version,
    #             "base_category": spec.base_category,
    #             "subcategory": spec.subcategory,
    #         },
    #     )
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.3) list_types
# ---------------------------------------------------------------------------


@mcp.tool(name="list_types")
async def list_types() -> ListTypesResult:
    """Return the full data-type registry hierarchy.

    Use when:
      - You're choosing a port ``type`` for a new block (per the
        port-type selection rule in the scieasy-write-block skill).
      - You need to verify a type name is registered before referencing it.

    Do NOT use to:
      - List block types (use ``list_blocks``).
    """
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #     ctx = get_context()
    #     types_map = ctx.type_registry.all_types()
    #     entries = [
    #         TypeEntry(
    #             name=spec.name,
    #             parent=spec.base_type,
    #             description=spec.description,
    #             module_path=spec.module_path,
    #         )
    #         for spec in types_map.values()
    #     ]
    #     return ListTypesResult(types=entries, count=len(entries))
    #
    #   I40a notes:
    #   - This tool's output is the SOURCE for the §3.2a soft-validation
    #     warning text on scaffold_block ("Otherwise pick from list_types()").
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.4) get_workflow
# ---------------------------------------------------------------------------


@mcp.tool(name="get_workflow")
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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #     from scieasy.workflow.serializer import load_yaml
    #     p = _resolve_project_path(path)
    #     if not p.exists(): raise FileNotFoundError(...)
    #     definition = load_yaml(p)
    #     payload = dataclasses.asdict(definition)
    #     payload["path"] = str(p)  # issue #790
    #     return WorkflowDefinitionEnvelope(**payload)
    #
    #   I40a notes:
    #   - Preserve the issue #790 path-resolution semantics: project-relative
    #     paths resolve under ctx.project_dir, not the backend's CWD.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.5) validate_workflow
# ---------------------------------------------------------------------------


@mcp.tool(name="validate_workflow")
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
    # TODO(#1012): port from ADR-033-era impl including the
    #   _looks_like_inline_yaml heuristic and the path-resolution
    #   semantics (issue #790). Reference:
    #     - Inline YAML: yaml.safe_load → WorkflowFileModel.model_validate
    #       → definition.to_definition()
    #     - Path mode: _resolve_project_path → load_yaml
    #     - Run validator: _validate(definition, registry=ctx.block_registry)
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.6) write_workflow  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="write_workflow")
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
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. Pre-write schema validation via WorkflowFileModel.model_validate
    #      (turns ValidationError into a ValueError with embedded JSON
    #      error list so the agent gets actionable feedback).
    #   2. _resolve_project_path for issue #790 path semantics.
    #   3. FileLock with _LOCK_TIMEOUT_SECONDS = 10.0 per ADR-033 OQ7.
    #   4. _atomic_write_text (tempfile + rename).
    #   5. _diff_summary for the diff_summary field.
    #   6. logger.info("write_workflow: wrote %s (%s)", p, summary).
    #
    #   Concurrency note (ADR-039): the in-memory If-Match revision flow
    #   was removed in D39-2.1; filelock is the only in-process
    #   arbitrator. Cross-actor concurrency is mediated by git.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.7) run_workflow  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="run_workflow")
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
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. _ensure_error_subscriber() — installs the BLOCK_ERROR capture
    #      subscriber on first call so get_run_status surfaces tracebacks.
    #   2. _resolve_project_path(path).stem → workflow_id (the runtime
    #      keys runs by file stem).
    #   3. Clear stale _run_block_errors entries for re-runs.
    #   4. runtime.start_workflow(workflow_id) — runtime owns identity.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.8) cancel_run  (write-class)
# ---------------------------------------------------------------------------


@mcp.tool(name="cancel_run")
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
    # TODO(#1012): port from ADR-033-era impl. Reference impl uses:
    #   1. runtime.workflow_runs[run_id] lookup, raise KeyError if absent.
    #   2. event_bus.emit(EngineEvent(CANCEL_WORKFLOW_REQUEST, ...)) when
    #      the scheduler exposes an event bus.
    #   3. Best-effort fallback: run.task.cancel() if no event_bus.
    #   4. asyncio.get_running_loop().create_task(...) for the emit coro,
    #      keeping a reference on run._cancel_task to avoid RUF006 GC.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.9) get_run_status
# ---------------------------------------------------------------------------


@mcp.tool(name="get_run_status")
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
    # TODO(#1012): port from ADR-033-era impl. Reference impl surfaces:
    #   1. State derived from task.done()/cancelled()/exception().
    #   2. Per-block state map from scheduler._block_states.
    #   3. _collect_run_errors(run_id) → captured block_error tracebacks.
    #   4. Synthetic __run__ entry when the scheduler task itself raised
    #      before any block_error was emitted (DAG validation failure).
    #
    #   I40a notes: this tool's `errors` list is the agent's primary
    #   self-debug source; preserving the full traceback fidelity is
    #   load-bearing for the production debugging UX.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (a.10) finish_ai_block  (write-class, ADR-035 §3.5)
# ---------------------------------------------------------------------------


@mcp.tool(name="finish_ai_block")
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
    run dir; the CompletionWatcher (ADR-035 §3.5 path (a)) polls for
    that file and transitions the block from PAUSED → RUNNING for
    output validation. Atomic write (tempfile + os.replace) — partial
    writes cannot deceive the watcher.

    Error codes:
      - ``not_in_ai_block_context`` — no active AI Block run dir.
      - ``invalid_outputs`` — outputs is not dict[str, str].
      - ``already_finished`` — signal file already exists for this run.
      - ``io_error`` — disk-level write failure.
    """
    # TODO(#1012): port from ADR-033/ADR-035-era impl preserving all four
    #   error codes + the atomic write semantic. Reference impl:
    #   1. _resolve_ai_block_run_dir() — MCPContext.ai_block_run_dir OR
    #      SCIEASY_AI_BLOCK_RUN_DIR env var fallback.
    #   2. Normalise outputs (None → {}) + validate dict[str, str] shape.
    #   3. signals_dir = run_dir / "signals"; mkdir parents=True, exist_ok=True.
    #   4. Reject if signals/finish_ai_block.json already exists
    #      (ADR-035 §8 OQ-1 — already_finished).
    #   5. Build payload = {outputs, timestamp: datetime.utcnow().isoformat()}
    #   6. _atomic_write_text(signal_path, json.dumps(payload, indent=2, sort_keys=True)).
    #   7. Return FinishAIBlockOK(status="ok", signal_path=str(signal_path)).
    #
    #   I40a notes:
    #   - This tool's category is "workflow" + mutation "write" (ADR-035
    #     §3.5; see manifest §8.7 for the categorisation rationale).
    #   - Return type is the Union FinishAIBlockOK | FinishAIBlockError;
    #     FastMCP serialises Pydantic discriminated unions cleanly into
    #     the MCP content text block.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")
