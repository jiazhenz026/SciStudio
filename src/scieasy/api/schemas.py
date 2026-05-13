"""Pydantic models for API request and response shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowNode(BaseModel):
    """Serializable workflow node payload."""

    id: str
    block_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str | None = None
    layout: dict[str, float] | None = None


class WorkflowEdge(BaseModel):
    """Serializable workflow edge payload."""

    source: str
    target: str


class WorkflowCreate(BaseModel):
    """Request body for creating or replacing a workflow."""

    id: str
    version: str = "1.0.0"
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(WorkflowCreate):
    """Response body returned when reading a workflow."""


class WorkflowExecutionResponse(BaseModel):
    """Response body for workflow execution control endpoints."""

    workflow_id: str
    status: str
    message: str


class ExecuteFromRequest(BaseModel):
    """Request body for selective re-run."""

    block_id: str


class ExecuteFromResponse(WorkflowExecutionResponse):
    """Response body for execute-from."""

    reused_blocks: list[str] = Field(default_factory=list)
    reset_blocks: list[str] = Field(default_factory=list)


class BlockPortResponse(BaseModel):
    """Serializable block-port metadata."""

    name: str
    direction: str
    accepted_types: list[str] = Field(default_factory=list)
    required: bool = True
    description: str = ""
    constraint_description: str = ""
    is_collection: bool = False


class TypeHierarchyEntry(BaseModel):
    """Type hierarchy metadata for frontend color resolution."""

    name: str
    base_type: str = ""
    description: str = ""
    ui_ring_color: str | None = None


class BlockSummary(BaseModel):
    """Condensed block metadata for the palette."""

    name: str
    type_name: str
    # #588: base_category is always one of 6 base types (io, process, code,
    # app, ai, subworkflow).  subcategory is the optional palette grouping label.
    base_category: str = ""
    subcategory: str = ""
    description: str = ""
    version: str = "0.1.0"
    input_ports: list[BlockPortResponse] = Field(default_factory=list)
    output_ports: list[BlockPortResponse] = Field(default_factory=list)
    direction: str | None = None
    source: str = ""
    package_name: str = ""
    # ADR-029 D8: variadic port flags so the frontend palette can show [+]
    # affordances for variadic blocks even before the full schema is fetched.
    variadic_inputs: bool = False
    variadic_outputs: bool = False


class BlockListResponse(BaseModel):
    """Response body for the block palette listing."""

    blocks: list[BlockSummary] = Field(default_factory=list)


class BlockSchemaResponse(BlockSummary):
    """Detailed schema payload for a single block type."""

    config_schema: dict[str, Any] = Field(default_factory=dict)
    type_hierarchy: list[TypeHierarchyEntry] = Field(default_factory=list)
    # ADR-028 Addendum 1 D4: enum-driven dynamic-port descriptor (frontend
    # consumes this to recompute port ``accepted_types`` when the driving
    # config field changes). ``None`` for static blocks.
    dynamic_ports: dict[str, Any] | None = None
    # ADR-028 Addendum 1 D7: IO direction ("input" / "output") so the
    # frontend can render IO-specific UI (browse file vs directory) without
    # hardcoding ``blockType === "io_block"`` checks. ``None`` for
    # non-IO blocks.
    direction: str | None = None
    # ADR-029 D11: type name lists for variadic port editor dropdown.
    # Frontend uses these to populate the type selector when the user adds
    # a new port. Empty list means "any DataObject subclass".
    allowed_input_types: list[str] = Field(default_factory=list)
    allowed_output_types: list[str] = Field(default_factory=list)
    # ADR-029 Addendum 1: optional min/max constraints on variadic port count.
    # Frontend uses these to disable [+]/[-] buttons at limits.
    min_input_ports: int | None = None
    max_input_ports: int | None = None
    min_output_ports: int | None = None
    max_output_ports: int | None = None


class BlockConnectionValidation(BaseModel):
    """Request body for validating a proposed port connection."""

    source_block: str
    source_port: str
    target_block: str
    target_port: str


class ConnectionValidationResponse(BaseModel):
    """Response body for a proposed port connection."""

    compatible: bool
    reason: str = ""


class DataUploadResponse(BaseModel):
    """Response body after a successful data upload."""

    ref: str
    type_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataMetadataResponse(BaseModel):
    """Metadata for a stored data object."""

    ref: str
    type_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataPreviewResponse(BaseModel):
    """Response body for a lightweight data preview."""

    ref: str
    type_name: str
    preview: dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    """Request body for creating a project workspace."""

    name: str
    description: str = ""
    path: str | None = None


class ProjectUpdate(BaseModel):
    """Request body for updating project metadata."""

    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    """Response body for project management endpoints."""

    id: str
    name: str
    path: str
    description: str = ""
    last_opened: str | None = None
    workflow_count: int = 0
    workflows: list[str] = Field(default_factory=list)
    current_workflow_id: str | None = None


class AIGenerateBlockRequest(BaseModel):
    """Request body for AI block generation."""

    description: str
    block_category: str | None = None


class AIGenerateBlockResponse(BaseModel):
    """Response body after AI block generation."""

    code: str
    block_name: str
    validation_passed: bool
    validation_report: dict[str, Any] = Field(default_factory=dict)
    category: str = ""


class AISuggestWorkflowRequest(BaseModel):
    """Request body for AI workflow suggestion."""

    data_description: str
    goal: str


class AISuggestWorkflowResponse(BaseModel):
    """Response body after AI workflow suggestion."""

    workflow: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""


class CancelBlockRequest(BaseModel):
    """Request body for cancelling a single block."""

    block_id: str


class CancelWorkflowRequest(BaseModel):
    """Request body for cancelling an entire workflow."""


class CancelPropagationResponse(BaseModel):
    """Response body after cancellation propagation."""

    cancelled_blocks: list[str] = Field(default_factory=list)
    skipped_blocks: list[str] = Field(default_factory=list)
    skip_reasons: dict[str, str] = Field(default_factory=dict)


class AIOptimizeParamsRequest(BaseModel):
    """Request body for AI parameter optimization."""

    block_id: str
    intermediate_results: dict[str, Any] = Field(default_factory=dict)
    search_space: dict[str, Any] | None = None


class AIOptimizeParamsResponse(BaseModel):
    """Response body after AI parameter optimization."""

    suggestions: dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""


class ErrorResponse(BaseModel):
    """Standard error envelope returned by endpoints on failure."""

    detail: str
    error_code: str | None = None
