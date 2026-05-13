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
    """Response body returned when reading a workflow.

    The ``revision`` field (#718 part a) is a monotonic integer tracked
    in-memory by ``ApiRuntime`` to support optimistic concurrency on the
    write path. It is distinct from the semver ``version`` string above
    (which describes the schema version of the YAML payload).
    """

    revision: int = 0


class WorkflowConflictResponse(BaseModel):
    """Response body for ``HTTP 412 Precondition Failed`` from PUT (#718 part a).

    Returned when the client's ``If-Match`` header is stale compared to the
    server's current revision. ``workflow`` carries the full latest payload so
    the client can rebase its local state without a second round-trip.
    """

    detail: str = "Workflow revision is stale"
    current_revision: int
    workflow: WorkflowResponse


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


# ---------------------------------------------------------------------------
# Embedded coding agent (ADR-033 / T-ECA-107) — schemas.
# Legacy single-call AI schemas were removed in Phase 4 (T-ECA-401).
# ---------------------------------------------------------------------------


class ProviderStatusItem(BaseModel):
    """One provider's discovery result, as returned by ``GET /api/ai/status``."""

    name: str
    available: bool
    binary_path: str | None = None
    version: str | None = None
    logged_in: bool = False
    install_hint: str | None = None


class ProviderStatusResponse(BaseModel):
    """Response body for ``GET /api/ai/status``."""

    providers: list[ProviderStatusItem] = Field(default_factory=list)


class ChatClientMessage(BaseModel):
    """Inbound WebSocket message on ``/api/ai/chat/{chat_id}``.

    The protocol mirrors ADR-033 §3 D5.2. ``user_message`` and
    ``cancel`` are handled in Phase 1 (T-ECA-107);
    ``permission_decision`` is wired in by T-ECA-110 and is accepted
    here for forward compatibility only — Phase 1 routes ignore it.
    """

    type: str
    content: str | None = None
    request_id: str | None = None
    decision: str | None = None


class AgentEventEnvelope(BaseModel):
    """Outbound WebSocket envelope wrapping a canonical ``AgentEvent``.

    Server → client. Type discriminator: ``"agent_event"``. The ``event``
    payload is the serialised :class:`scieasy.ai.agent.provider.AgentEvent`
    dataclass (kind, raw, plus kind-specific fields).
    """

    type: str = "agent_event"
    event: dict[str, Any] = Field(default_factory=dict)


class PermissionRequestEnvelope(BaseModel):
    """Outbound WebSocket envelope for a tool-permission prompt.

    Server → client. Type discriminator: ``"permission_request"``. The
    frontend renders a modal and replies with a ``permission_decision``
    client message (or a REST POST to ``/permission-decision``).
    """

    type: str = "permission_request"
    request_id: str
    tool: dict[str, Any] = Field(default_factory=dict)


class SessionEndedEnvelope(BaseModel):
    """Outbound WebSocket envelope announcing terminal session state.

    Server → client. Type discriminator: ``"session_ended"``. Emitted when
    the agent subprocess exits (cleanly or with error) so the frontend
    can transition the chat to a read-only state.
    """

    type: str = "session_ended"
    reason: str = ""


class ErrorEnvelope(BaseModel):
    """Outbound WebSocket envelope for non-fatal server-side errors.

    Server → client. Type discriminator: ``"error"``. Used for protocol
    violations (invalid client message, unknown permission request_id)
    and recoverable runtime failures (e.g. ``send_user_message`` raised).
    """

    type: str = "error"
    message: str


# ---------------------------------------------------------------------------
# T-ECA-110 — permission backend schemas.
# Both REST endpoints (``POST /api/ai/permission-check`` and
# ``POST /api/ai/permission-decision``) use these. The WS
# ``permission_decision`` message reuses :class:`ChatClientMessage`
# above (which already carries ``request_id`` + ``decision`` fields).
# ---------------------------------------------------------------------------


class PermissionCheckRequest(BaseModel):
    """Inbound payload for ``POST /api/ai/permission-check``.

    The ``scieasy hook-bridge`` CLI forwards CC's PreToolUse hook input
    here verbatim, plus the ``chat_id`` it inherits from the session's
    env. Only the four fields below are read; any extras the hook
    payload carries (``transcript_path``, ``permission_mode``, ...) are
    ignored.
    """

    chat_id: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    project_dir: str | None = None


class PermissionCheckResponse(BaseModel):
    """Outbound payload for ``POST /api/ai/permission-check``.

    ``action`` is ``"approve"`` or ``"deny"``; ``reason`` is populated on
    deny (e.g. ``"timed_out"``, ``"user_denied"``, free-form text the
    bridge then prints to stderr).
    """

    action: str
    reason: str | None = None
    request_id: str | None = None


class SessionListItem(BaseModel):
    """One entry returned by ``GET /api/ai/sessions`` (#783).

    Mirrors :class:`scieasy.ai.agent.session.SessionMetadata` projected
    to a JSON-friendly shape. The frontend uses this to render the
    sessions sidebar after a backend restart.
    """

    chat_id: str
    title: str = ""
    created: str
    last_active: str
    provider: str
    model: str | None = None
    session_id: str | None = None
    bypass_mode: bool = False
    total_turns: int = 0


class SessionListResponse(BaseModel):
    """Response body for ``GET /api/ai/sessions`` (#783)."""

    sessions: list[SessionListItem] = Field(default_factory=list)


class SlashCommandItem(BaseModel):
    """One entry returned by ``GET /api/ai/slash_commands`` (#786)."""

    name: str
    description: str = ""
    source: str  # "user-commands" | "user-skills" | "project" | "plugin"
    path: str = ""


class SlashCommandsResponse(BaseModel):
    """Response body for ``GET /api/ai/slash_commands`` (#786)."""

    commands: list[SlashCommandItem] = Field(default_factory=list)


class PermissionDecisionRequest(BaseModel):
    """Inbound payload for ``POST /api/ai/permission-decision``.

    The frontend sends this when the user clicks Approve / Deny in the
    permission UI. The WS ``permission_decision`` message has the same
    semantic content but reuses :class:`ChatClientMessage`.
    """

    chat_id: str
    request_id: str
    decision: str  # "approve" | "deny"
    reason: str | None = None
