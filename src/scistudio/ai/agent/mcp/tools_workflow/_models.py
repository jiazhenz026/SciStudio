"""Pydantic result-model envelopes for the ``tools_workflow`` tools.

ADR-040 §3.1 FastMCP migration — typed envelopes. Write-class tools
carry ``next_step: str`` per ADR-040 §3.2.

Extracted from the original single-file ``tools_workflow.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


__all__ = [
    "BlockErrorEntry",
    "BlockSchemaResult",
    "BlockSpecEnvelope",
    "CancelRunResult",
    "FinishAIBlockError",
    "FinishAIBlockOK",
    "GetRunStatusResult",
    "ListTypesResult",
    "RunWorkflowResult",
    "TypeEntry",
    "ValidateWorkflowResult",
    "WorkflowDefinitionEnvelope",
    "WriteWorkflowResult",
]
