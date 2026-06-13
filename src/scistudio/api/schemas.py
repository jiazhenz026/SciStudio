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
    source_id: str | None = None
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowResponse(WorkflowCreate):
    """Response body returned when reading a workflow.

    The legacy ``revision`` field (#718 part a) was removed by ADR-039 §5.2
    / D39-2.1; durable concurrency control lives in git now. The semver
    ``version`` string above still describes the schema version of the
    YAML payload.
    """


class WorkflowExecutionResponse(BaseModel):
    """Response body for workflow execution control endpoints."""

    workflow_id: str
    status: str
    message: str


class ExecuteWorkflowRequest(BaseModel):
    """Request body for workflow execution."""

    overwrite_node_ids: list[str] = Field(default_factory=list)


class ExecuteFromRequest(BaseModel):
    """Request body for selective re-run."""

    block_id: str
    overwrite_node_ids: list[str] = Field(default_factory=list)


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


class MetadataFidelityResponse(BaseModel):
    """Serializable ADR-043 metadata-fidelity declaration."""

    level: str = "pixel_only"
    typed_meta_reads: list[str] = Field(default_factory=list)
    typed_meta_writes: list[str] = Field(default_factory=list)
    format_metadata_reads: list[str] = Field(default_factory=list)
    format_metadata_writes: list[str] = Field(default_factory=list)
    notes: str | None = None


class FormatCapabilityResponse(BaseModel):
    """Serializable ADR-043 IO format capability metadata."""

    id: str
    direction: str
    data_type: str
    format_id: str
    extensions: list[str] = Field(default_factory=list)
    label: str
    block_type: str
    handler: str
    is_default: bool = False
    priority: int = 0
    roundtrip_group: str | None = None
    metadata_fidelity: MetadataFidelityResponse = Field(default_factory=MetadataFidelityResponse)
    is_synthesized: bool = False
    migration_scaffold: bool = False


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
    # ADR-043: capabilities are metadata for aggregate IOBlocks, not separate
    # palette entries. The frontend uses them for format selection only.
    format_capabilities: list[FormatCapabilityResponse] = Field(default_factory=list)


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
    """Request body for validating a proposed port connection.

    ``source_node_config`` and ``target_node_config`` are optional per
    #889 (ADR-028 / ADR-029 effective-ports drift). When provided, the
    backend resolves each endpoint's effective ports from the per-node
    config — required for ``LoadData`` (``core_type`` chooses the
    output type) and variadic blocks (``AIBlock`` / ``CodeBlock`` /
    ``AppBlock``) whose true ports live in
    ``node.config.input_ports`` / ``node.config.output_ports``. When
    absent, the backend falls back to the static class-level port
    spec (legacy behaviour) so older clients keep working.
    """

    source_block: str
    source_port: str
    target_block: str
    target_port: str
    source_node_config: dict[str, Any] | None = None
    target_node_config: dict[str, Any] | None = None


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


# ---------------------------------------------------------------------------
# ADR-048 SPEC 1: routed previewer session API schemas.
#
# These mirror the canonical ``scistudio.previewers`` models on the wire. The
# legacy one-shot ``DataPreviewResponse`` REST-preview body and its
# ``GET /api/data/{ref}/preview`` route were removed under ADR-048 no-compat
# (#1604); previews now flow exclusively through the session API below.
# ---------------------------------------------------------------------------


class PreviewTargetModel(BaseModel):
    """Wire shape of a previewer :class:`PreviewTarget`."""

    kind: str = Field(description="data_ref / collection_ref / artifact / plot_artifact.")
    ref: str = Field(description="Data, collection, or artifact reference (catalog id or path).")
    recorded_type: str = Field(default="", description="Most-specific recorded type name.")
    type_chain: list[str] = Field(default_factory=list, description="Ordered general -> specific type chain.")
    collection_item_type: str | None = Field(default=None)
    source: dict[str, Any] | None = Field(default=None, description="Optional workflow/node/output display identity.")


class PreviewSessionCreate(BaseModel):
    """Request body for ``POST /api/previews/sessions``."""

    target: PreviewTargetModel
    query: dict[str, Any] = Field(default_factory=dict, description="Initial normalized query state.")


class PreviewSessionPatch(BaseModel):
    """Request body for ``PATCH /api/previews/sessions/{session_id}``."""

    query: dict[str, Any] = Field(default_factory=dict, description="Query state to merge (slice/page/sort/slot/item).")


class PreviewFrontendManifestModel(BaseModel):
    """Wire shape of a previewer :class:`FrontendManifest` (same-origin only)."""

    previewer_id: str
    module_url: str
    export_name: str = "default"
    css: list[str] = Field(default_factory=list)
    version: str = "0"
    api_version: str = "1"


class PreviewEnvelopeModel(BaseModel):
    """Wire shape of a canonical :class:`PreviewEnvelope`."""

    session_id: str | None = None
    previewer_id: str
    target: dict[str, Any] = Field(default_factory=dict)
    kind: str = Field(description="dataframe/array/series/text/artifact/composite/collection/plot/error.")
    payload: dict[str, Any] = Field(default_factory=dict)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    frontend_manifest: PreviewFrontendManifestModel | None = None


class PreviewerSpecModel(BaseModel):
    """Wire shape of a :class:`PreviewerSpec` for capability discovery."""

    previewer_id: str
    owner_kind: str
    owner_name: str
    target_type: str
    supports_collection: bool = False
    priority: int = 0
    capabilities: list[str] = Field(default_factory=list)
    backend_provider: str | None = None
    frontend_manifest: PreviewFrontendManifestModel | None = None
    api_version: str = "1"


class PreviewResourceResponse(BaseModel):
    """Response body for a bounded session resource read."""

    resource_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class PreviewResourceSaveRequest(BaseModel):
    """Request body for saving a bounded preview resource to a user path."""

    destination_path: str = Field(description="Absolute path selected by the native save dialog.")
    params: dict[str, Any] = Field(default_factory=dict, description="Resource params copied from the descriptor.")


class PreviewResourceSaveResponse(BaseModel):
    """Response body after a preview resource is saved to disk."""

    path: str
    filename: str
    size_bytes: int
    mime_type: str | None = None


# ---------------------------------------------------------------------------
# ADR-048 SPEC 2 / #1606: plot-job run + preview wiring.
#
# These wire the producer (run_plot_job) to the consumer (PlotPreviewer): the
# run route executes the plot job and, on success, registers the produced
# artifact as a previewable catalog record so the frontend can open a routed
# ``plot_artifact`` preview session through the existing previews API.
# ---------------------------------------------------------------------------


class PlotRunRequest(BaseModel):
    """Request body for ``POST /api/plots/run``."""

    plot_id: str = Field(description="Plot id under plots/ to execute.")
    run_id: str | None = Field(
        default=None,
        description="Optional run id to source the target output from; defaults to latest.",
    )
    timeout_seconds: float | None = Field(
        default=None,
        description="Optional override of the manifest timeout (re-clamped to the absolute ceiling).",
    )


class PlotRunResponse(BaseModel):
    """Response body for ``POST /api/plots/run``.

    On success ``data_ref`` is the catalog id the frontend passes to
    ``POST /api/previews/sessions`` (with ``target.kind="plot_artifact"``) to
    render the produced artifact through the core ``PlotPreviewer``. It is
    ``None`` when the plot run failed / produced no artifact, in which case
    ``status`` plus ``errors`` explain why.
    """

    status: str = Field(description="succeeded / failed / cancelled / timed_out.")
    data_ref: str | None = Field(
        default=None,
        description="Catalog id of the registered plot artifact; open a preview session with this ref.",
    )
    recorded_type: str = Field(default="PlotArtifact", description="Recorded type of the artifact record.")
    type_chain: list[str] = Field(default_factory=list, description="Ordered general -> specific type chain.")
    cache_key: str | None = Field(default=None, description="Preview cache key for UI refresh (FR-030).")
    artifact_paths: list[str] = Field(default_factory=list, description="Absolute preview-cache artifact paths.")
    source: dict[str, Any] | None = Field(
        default=None,
        description="Display-only workflow/node/output identity for the preview panel label.",
    )
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PlotListItem(BaseModel):
    """One project-local plot manifest summary for the app shell."""

    plot_id: str
    title: str = ""
    workflow_id: str | None = None
    node_id: str
    output_port: str
    display_label: str = ""
    language: str
    preferred_format: str
    manifest_path: str
    script_path: str


class PlotListResponse(BaseModel):
    """Response body for ``GET /api/plots``."""

    plots: list[PlotListItem] = Field(default_factory=list)
    count: int
    warnings: list[str] = Field(default_factory=list)


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


class ErrorResponse(BaseModel):
    """Standard error envelope returned by endpoints on failure."""

    detail: str
    error_code: str | None = None
