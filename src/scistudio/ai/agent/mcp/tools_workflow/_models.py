"""Pydantic result-model envelopes for the ``tools_workflow`` tools.

ADR-040 §3.1 FastMCP migration — typed envelopes. Write-class tools
carry ``next_step: str`` per ADR-040 §3.2.

Extracted from the original single-file ``tools_workflow.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlockSummary(BaseModel):
    """Lean catalog entry for one block type (``list_blocks``).

    Carries only what the agent needs to *select* a block: identity,
    category, owning package, a one-line description, and a one-line I/O
    signature. The full I/O ports and ``config_schema`` are intentionally
    omitted to keep the catalog small even with many packages installed;
    fetch them on demand via ``get_block_schema``.
    """

    type_name: str = Field(
        description=(
            "Canonical block type id. THIS is the exact string to put in a "
            "workflow node's 'block_type'. The GUI resolves nodes by type_name, "
            "so writing anything else (a display name, a guessed dotted name) "
            "produces a node the GUI cannot resolve."
        ),
    )
    name: str = Field(
        description=(
            "Human-readable display name shown in the palette (e.g. 'Load'). "
            "For display only — do NOT use this as a workflow 'block_type'; "
            "use 'type_name' there."
        ),
    )
    base_category: str = Field(description="One of io/process/code/app/ai/subworkflow.")
    subcategory: str | None = Field(default=None, description="Optional subcategory string.")
    package_name: str = Field(
        default="",
        description="Owning plugin package name, or '' for core blocks.",
    )
    description: str = Field(description="One-line block description from BlockSpec.")
    signature: str = Field(
        description="One-line I/O signature, e.g. 'image:Image, mask?:Array → result:Image'.",
    )
    use_instead: str | None = Field(
        default=None,
        description=(
            "Set for package-specific IO blocks that the core Load/Save block "
            "already covers via its core_type enum. When present, do NOT use "
            "this block: use the named core block ('load_data'/'save_data') "
            "configured with the given core_type instead."
        ),
    )


class ListBlocksResult(BaseModel):
    """Return shape for the ``list_blocks`` tool.

    A progressive-disclosure catalog: ``blocks`` is the lean index;
    ``next_step`` points the agent at the detail tool for full schemas;
    ``io_block_guidance`` reminds the agent to read/write data through the
    core Load/Save block rather than a package-specific IO block.
    """

    blocks: list[BlockSummary] = Field(description="Lean catalog of every registered block type.")
    count: int = Field(description="Total number of registered block types.")
    next_step: str = Field(
        default=(
            "Call mcp__scistudio__get_block_schema with a block's 'type_name' to fetch "
            "its full I/O ports and config_schema before wiring edges or setting params. "
            "Always copy 'type_name' (not the display 'name') into a node's 'block_type'."
        ),
        description="Suggested next MCP call to obtain a block's full configuration.",
    )
    io_block_guidance: str = Field(
        default=(
            "To read or write data, default to the core 'load_data' / 'save_data' block "
            "configured with a 'core_type' (its enum covers package-registered types like "
            "Image, Spectrum, SpectralDataset, Mask and delegates to the package loader/saver "
            "under the hood, keeping one consistent GUI Load/Save node). Package-specific IO "
            "blocks are redundant and are flagged with a 'use_instead' hint in this catalog; "
            "do not use them."
        ),
        description="Guidance to prefer the core Load/Save block + core_type over package-specific IO blocks.",
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
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-blocking advisories about the written workflow, e.g. a node that "
            "uses a package-specific IO block the core Load/Save block already "
            "covers. The write still succeeds; act on these to keep the canvas "
            "consistent."
        ),
    )
    next_step: str = Field(
        default="Call mcp__scistudio__validate_workflow with the same path to confirm runtime acceptance.",
        description="Suggested next MCP call to maintain workflow integrity.",
    )


class EditWorkflowResult(BaseModel):
    """Result envelope for ``edit_workflow`` (surgical partial edit)."""

    path: str = Field(description="Absolute resolved path of the edited workflow.")
    bytes_written: int = Field(description="Number of bytes written to disk.")
    diff_summary: str = Field(description="Compact diff vs prior file contents.")
    edits_applied: int = Field(description="Number of search/replace edits applied to the workflow text.")
    next_step: str = Field(
        default="Call mcp__scistudio__validate_workflow with the same path to confirm runtime acceptance.",
        description="Suggested next MCP call to maintain workflow integrity.",
    )


class RunWorkflowResult(BaseModel):
    """Result envelope for ``run_workflow``."""

    run_id: str = Field(description="Identifier of the queued workflow run.")
    status: str = Field(description="Initial status, typically 'queued'.")
    next_step: str = Field(
        default="Poll mcp__scistudio__get_run_status with run_id until state is terminal (succeeded/failed/cancelled).",
        description="Suggested next MCP call to observe completion.",
    )


class CancelRunResult(BaseModel):
    """Result envelope for ``cancel_run``."""

    run_id: str = Field(description="The run that was targeted.")
    cancel_requested: bool = Field(description="True if cancellation was successfully signalled.")
    next_step: str = Field(
        default="Poll mcp__scistudio__get_run_status with run_id; state should transition to 'cancelled'.",
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


class ActiveWorkflowContextResult(BaseModel):
    """Result envelope for ``get_active_workflow_context``.

    ADR-040 Addendum 5 / #1488. Both fields are ``None`` when no
    workflow is open in the GUI. ``workflow_name`` falls back to
    ``workflow_id`` when the underlying YAML carries no separate
    ``metadata.title`` / ``metadata.name``.
    """

    workflow_id: str | None = Field(
        default=None,
        description="Identifier of the workflow the GUI is currently editing, or None when no workflow is open.",
    )
    workflow_name: str | None = Field(
        default=None,
        description="Display name of the active workflow (metadata.title when set, otherwise workflow_id), or None.",
    )


__all__ = [
    "ActiveWorkflowContextResult",
    "BlockErrorEntry",
    "BlockSchemaResult",
    "BlockSummary",
    "CancelRunResult",
    "EditWorkflowResult",
    "FinishAIBlockError",
    "FinishAIBlockOK",
    "GetRunStatusResult",
    "ListBlocksResult",
    "ListTypesResult",
    "RunWorkflowResult",
    "TypeEntry",
    "ValidateWorkflowResult",
    "WorkflowDefinitionEnvelope",
    "WriteWorkflowResult",
]
