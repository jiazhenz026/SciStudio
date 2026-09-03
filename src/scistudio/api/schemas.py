"""Pydantic models for API request and response shapes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SubworkflowPortEntry(BaseModel):
    """One exposed port of a referenced subworkflow (ADR-044 FR-004).

    ``block_id`` / ``block_type`` / ``block_label`` / ``port`` carry the owning
    inner block's provenance so the editor can show which inner block each
    exposed port belongs to (the exposed ``name`` is the opaque ``"<block>.<port>"``
    dot form). Defaulted so older clients and broken refs stay valid.
    """

    name: str
    accepted_types: list[str] = Field(default_factory=list)
    block_id: str = ""
    block_type: str = ""
    block_label: str = ""
    port: str = ""


class SubworkflowPortSurface(BaseModel):
    """Resolved exposed-port surface for a SubWorkflowBlock node (ADR-044 FR-004).

    Response-only: computed server-side from the referenced file's
    ``exposed_ports`` and never persisted to the workflow YAML. The editor
    renders the node's handles from this; ``broken`` is ``True`` when the
    reference cannot be resolved (FR-010).
    """

    inputs: list[SubworkflowPortEntry] = Field(default_factory=list)
    outputs: list[SubworkflowPortEntry] = Field(default_factory=list)
    broken: bool = False
    ref_path: str | None = None


class WorkflowNode(BaseModel):
    """Serializable workflow node payload."""

    id: str
    block_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str | None = None
    layout: dict[str, float] | None = None
    # ADR-044 FR-004 / D4: response-only resolved exposed-port surface for
    # ``subworkflow`` / ``subworkflow_broken`` nodes. ``None`` for every other
    # block type. Never round-trips into the saved YAML (``WorkflowCreate`` has
    # no such field; ``save_workflow`` builds ``NodeDef`` which drops it).
    resolved_ports: SubworkflowPortSurface | None = None


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
    # #588: base_category is one of the 6 base types (io, process, code, app,
    # ai, subworkflow). #1988: it is also "unknown" for a block that extends
    # Block directly, which _infer_category resolves by issubclass and cannot
    # place — a valid block, drawn with its own node colour rather than as an
    # error. subcategory is the optional palette grouping label.
    base_category: str = ""
    subcategory: str = ""
    # #1839: optional block-declared canvas-node display hints. ``ui_color`` is
    # a CSS hex string; ``ui_icon`` is a Lucide icon name. Both ``None`` (the
    # default) means the frontend uses the base_category default. Mirrors the
    # ``TypeHierarchyEntry.ui_ring_color`` precedent for ports.
    ui_color: str | None = None
    ui_icon: str | None = None
    description: str = ""
    version: str = "0.1.0"
    input_ports: list[BlockPortResponse] = Field(default_factory=list)
    output_ports: list[BlockPortResponse] = Field(default_factory=list)
    direction: str | None = None
    source: str = ""
    # ADR-053 FR-001/FR-002/FR-004: the resolved origin tier —
    # ``builtin`` | ``user`` | ``project`` | ``package`` | ``custom``, where
    # ``custom`` is the unresolvable-path fallback only. Additive rather than a
    # redefinition of ``source``, which keeps its pre-ADR-053 collapsed
    # vocabulary so existing consumers of ``custom`` keep working (FR-002).
    origin: str = ""
    package_name: str = ""
    # ADR-029 D8: variadic port flags so the frontend palette can show [+]
    # affordances for variadic blocks even before the full schema is fetched.
    variadic_inputs: bool = False
    variadic_outputs: bool = False
    # ADR-043: capabilities are metadata for aggregate IOBlocks, not separate
    # palette entries. The frontend uses them for format selection only.
    format_capabilities: list[FormatCapabilityResponse] = Field(default_factory=list)
    # ADR-051: execution mode + the interactive panel manifest (None unless the
    # block is interactive) so the palette/API can identify interactive blocks
    # and resolve their window without instantiating the block.
    execution_mode: str = "auto"
    panel_manifest: dict[str, Any] | None = None


class DropinFailureResponse(BaseModel):
    """One drop-in file the block scan refused (ADR-053 FR-015/FR-016)."""

    file_path: str = Field(description="Absolute path of the drop-in file that was refused.")
    error_type: str = Field(description="Exception class name, or 'DropinTypeNameCollision' for FR-016.")
    message: str = Field(description="One-line explanation the palette can show to the user.")


class BlockListResponse(BaseModel):
    """Response body for the block palette listing."""

    blocks: list[BlockSummary] = Field(default_factory=list)
    # ADR-053 FR-015: a drop-in block that fails to import used to vanish with
    # nothing but a server-side warning. The palette already fetches this
    # response, so the refusals ride along with it rather than needing a new
    # polling surface.
    dropin_failures: list[DropinFailureResponse] = Field(default_factory=list)


class TypeSummary(BaseModel):
    """One registered ``DataObject`` type, as the Data types tab sees it.

    ADR-053 FR-026. Deliberately not an extension of :class:`TypeHierarchyEntry`
    on the block response: FR-027 makes the types listing independent of the
    block listing, so the Data types tab neither waits for nor re-triggers a
    palette fetch.
    """

    name: str = Field(description="Registered type name, e.g. 'DataFrame'.")
    base_type: str = Field(default="", description="Immediate parent type name, or '' for DataObject itself.")
    description: str = Field(default="", description="First line of the class docstring.")
    origin: str = Field(
        description=(
            "ADR-053 FR-005 resolved origin tier: 'core' | 'user' | 'project' | "
            "'package' | 'custom', where 'custom' is the unresolvable-path fallback."
        )
    )
    file_path: str | None = Field(
        default=None,
        description="Absolute path of the file defining the type, or null when unresolvable.",
    )
    # ADR-053 FR-040: the Data types tab splits per-package sections the way the
    # Blocks tab does, which means a package-tier type has to name its
    # distribution. The value is the very string ``BlockSummary.package_name``
    # reports for that distribution — looked up, not derived a second time — so
    # the two tabs cannot title one package two different ways. Null everywhere
    # else, including a distribution the block side does not name either.
    package_name: str | None = Field(
        default=None,
        description=(
            "Owning distribution, exactly as BlockSummary.package_name reports it. "
            "Null for core, user-tier, project-tier, and unattributable types."
        ),
    )
    # ADR-053 FR-049/FR-050: the colours the type itself declared, already
    # validated and normalised to long-form CSS hex by the registry (FR-052),
    # so an unusable value arrives here as null rather than as a string no
    # consumer can parse. Null means "this type declared nothing" and the
    # frontend applies the rest of the FR-051 precedence.
    ui_color: str | None = Field(default=None, description="Type-declared fill colour, or null.")
    ui_ring_color: str | None = Field(default=None, description="Type-declared ring colour, or null.")
    # ADR-053 FR-054/FR-055/FR-056: always present, possibly empty. An empty
    # list means "no format capability registered for this direction", which
    # the popover states outright — absence of IO support is information.
    load_extensions: list[str] = Field(
        default_factory=list,
        description="File extensions this type can be loaded from, sorted. Empty when none.",
    )
    save_extensions: list[str] = Field(
        default_factory=list,
        description="File extensions this type can be saved to, sorted. Empty when none.",
    )


class TypeListResponse(BaseModel):
    """Response body for the registered data type listing (ADR-053 FR-026)."""

    types: list[TypeSummary] = Field(default_factory=list)


class TypeTemplateResponse(BaseModel):
    """Response shape for ``GET /api/types/template`` (ADR-053 FR-028).

    Identical in shape to ``BlockTemplateResponse`` so the new-block and
    new-data-type flows can share their fetch-write-open steps (FR-033).
    """

    kind: str
    content: str
    suggested_filename: str


class BlockSourceResponse(BaseModel):
    """Read-only source code backing a registered block type (#1758)."""

    block_type: str = Field(description="Registered block type name the source belongs to.")
    path: str = Field(description="Absolute filesystem path of the block's source file.")
    source: str = Field(description="Full source text of the block's file.")
    language: str = Field(default="python", description="Source language (always 'python' today).")
    origin: str = Field(
        description=(
            "ADR-053 FR-001 resolved origin tier: 'builtin' | 'user' | 'project' | "
            "'package' | 'custom', where 'custom' is the unresolvable-path fallback."
        )
    )


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


class DataRegisterPathRequest(BaseModel):
    """Request body for ``POST /api/data/register-path``."""

    project_id: str | None = Field(default=None, description="Project id; defaults to the active project.")
    path: str = Field(description="Project-relative or absolute path of the file to register.")
    type_name: str | None = Field(
        default=None,
        description="Open the file as this registered type. Omit to use the remembered or inferred type.",
    )
    remember: bool = Field(
        default=False,
        description="Remember type_name for this extension in the open project (#2112).",
    )


class DataRegisterPathResponse(BaseModel):
    """Catalog registration result for ``POST /api/data/register-path``.

    Field names mirror the frontend ``PreviewTarget``: the caller opens a
    preview with ``{kind: "data_ref", ref, recorded_type, type_chain}``.
    ``extension`` and ``remembered`` let the caller show, and undo, the
    remembered open-as choice without a second round trip (#2112).
    """

    ref: str
    recorded_type: str
    type_chain: list[str] = Field(default_factory=list)
    display_name: str | None = None
    extension: str = Field(default="", description="Normalized extension the open-as choice is keyed on.")
    remembered: bool = Field(default=False, description="Whether this type is remembered for the extension.")


class DataOpenAsCandidate(BaseModel):
    """One type a file could be opened as (#2112).

    ``origin`` and ``package_name`` are the same tier facts the Data types tab
    reports, so the picker can say where a candidate came from rather than
    offering a bare list of names.
    """

    name: str
    base_type: str = ""
    description: str = ""
    origin: str = ""
    package_name: str | None = None
    loadable: bool = Field(
        default=True,
        description="False for a candidate offered as a plain-file fallback rather than a declared loader.",
    )


class DataOpenAsCandidatesResponse(BaseModel):
    """Answer to ``GET /api/data/open-as/candidates`` (#2112).

    ``candidates`` is ordered project -> package -> core, so the first entry is
    the picker's default. ``remembered`` is the project's recorded choice for
    this extension when there is one, in which case the caller opens the file
    without asking.
    """

    path: str
    extension: str
    candidates: list[DataOpenAsCandidate] = Field(default_factory=list)
    remembered: str | None = None


class DataOpenAsEntry(BaseModel):
    """One remembered extension -> type choice (#2112)."""

    extension: str
    type_name: str
    available: bool = Field(default=True, description="Whether the remembered type is still registered.")


class DataOpenAsListResponse(BaseModel):
    """The open project's remembered open-as choices (#2112)."""

    entries: list[DataOpenAsEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ADR-048 SPEC 1: routed panel session API schemas.
#
# These mirror the canonical ``scistudio.previewers`` models on the wire. The
# legacy one-shot ``DataPreviewResponse`` REST-preview body and its
# ``GET /api/data/{ref}/preview`` route were removed under ADR-048 no-compat
# (#1604); previews now flow exclusively through the session API below.
# ---------------------------------------------------------------------------


class PreviewTargetModel(BaseModel):
    """Wire shape of a panel :class:`PreviewTarget`."""

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
    """Wire shape of a panel :class:`FrontendManifest` (same-origin only)."""

    previewer_id: str
    module_url: str
    export_name: str = "default"
    css: list[str] = Field(default_factory=list)
    version: str = "0"
    api_version: str = "1"


class PanelDescriptorModel(BaseModel):
    """Everything the frame host needs to mount one panel (D-016.3, D-020).

    The wire form of :class:`scistudio.panels.descriptor.PanelDescriptor`, and
    the field names are the ones ``frontend/src/panels/panelDescriptor.ts``
    validates, so a caller hands a response object straight in.

    ``accepted_api_version`` and ``read_limits`` are always present: the host
    refuses to mount without either rather than inventing a bound or a version,
    so a descriptor missing them is a backend defect, not a host fallback.
    """

    panel_id: str
    display_name: str = ""
    api_version: str
    """The version this panel's declaration states."""
    accepted_api_version: str
    """The version the backend accepts -- its ``PANEL_API_VERSION`` (D-010)."""
    capability: str
    """The capability *this mount* is granted, which is not always the one the
    panel declares: a producing panel opened from the preview surface is granted
    display only (FR-049)."""
    document_url: str
    """Same-origin path of the entry document on the merged asset route."""
    asset_base_url: str
    """Same-origin base the panel fetches its own bulk assets from."""
    read_limits: dict[str, Any] = Field(default_factory=dict)
    tier: str = ""
    features: list[str] = Field(default_factory=list)
    supports_collection: bool = False


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

    # ADR-054 spec 1 FR-015 / T-008, D-013: the backend names both the panel to
    # mount and the panel to fall back to, so the frontend keeps no mapping from
    # a response's kind to a component (FR-036, SC-010).
    panel: PanelDescriptorModel | None = None
    """Descriptor of the panel that was chosen. ``None`` when the chosen panel
    has no on-disk document -- an unmigrated package previewer crossing the
    compatibility shim."""
    fallback_panel_id: str = ""
    """Id of the panel to mount when the chosen panel fails to load, fails to
    validate, fails the version gate, or fails the handshake (FR-014)."""
    fallback_panel: PanelDescriptorModel | None = None
    """Descriptor of that fallback, so mounting it needs no second request."""


class PanelChoiceModel(BaseModel):
    """One recorded per-type, per-capability panel choice (#2049, FR-049)."""

    target_type: str
    """Type name the choice applies to. Exact: a choice on a type does not
    govern types that merely descend from it."""
    panel_id: str
    """Panel the person picked for that type and capability."""
    capability: str
    """``displaying`` or ``producing``. The panel a person prefers for looking
    at a frame and the one they prefer for producing from it are different
    preferences about different situations (FR-049)."""
    scope: str
    """``user`` or ``project`` -- which layer this effective choice came from.
    A project-layer choice overrides the user-layer choice for the same type."""
    available: bool
    """Whether ``panel_id`` is registered right now. A choice whose panel was
    uninstalled stays recorded and reads ``false``; routing falls back to the
    ordinary precedence ladder until it returns."""


class PanelChoiceListResponse(BaseModel):
    """Response body for ``GET /api/panels/choices`` (#2049, FR-049)."""

    choices: list[PanelChoiceModel] = Field(default_factory=list)
    """Every capability's effective choices, after the project layer overrides
    the user layer."""


class PanelChoiceRequest(BaseModel):
    """Request body for ``PUT /api/panels/choices/{target_type}`` (FR-049)."""

    panel_id: str
    scope: str = "user"
    """``user`` (default, every project) or ``project`` (this project only)."""
    capability: str = "displaying"
    """Which of the two preferences this records (FR-049)."""


class PanelSpecModel(BaseModel):
    """One entry in the panel catalogue (FR-023).

    The registry's routing entry and the on-disk panel joined by their shared
    id: ``capability``, ``tier``, ``shadows`` and ``descriptor`` come from the
    four-tier scan, everything else from the routing spec. A panel addressed by
    the block that opens it declares no target type (FR-017) and so has only the
    scan half.
    """

    panel_id: str
    display_name: str = ""
    owner_kind: str = ""
    owner_name: str = ""
    target_type: str = ""
    target_types: list[str] = Field(default_factory=list)
    supports_collection: bool = False
    priority: int = 0
    features: list[str] = Field(default_factory=list)
    capability: str = ""
    """``displaying`` or ``producing``, as the panel declares it (FR-005)."""
    backend_provider: str | None = None
    frontend_manifest: PreviewFrontendManifestModel | None = None
    api_version: str = "1"
    tier: str | None = None
    """The tier the panel's directory was found in, or ``None`` for a routing
    entry with no on-disk document (a module-form package previewer)."""
    shadows: str | None = None
    """The tier of the panel this one shadows, or ``None``. What tells a caller
    whether ``DELETE /api/panels/{panel_id}/override`` has anything to restore."""
    descriptor: PanelDescriptorModel | None = None
    """What the frame host mounts this panel from, when it has a document."""


class PanelListResponse(BaseModel):
    """Response body for ``GET /api/panels`` (#2095, FR-023)."""

    panels: list[PanelSpecModel] = Field(default_factory=list)
    """Registered panels, ordered project -> user -> package -> core, then by
    id, with the block-addressed panels the type ladder never sees appended."""
    diagnostics: list[str] = Field(default_factory=list)
    """Discovery problems recorded during the scan: a duplicate panel id, a
    drop-in refused for a module-name collision, an entry point that failed to
    import, a declaration missing a required field. Nothing surfaced these
    before, so a refused drop-in was silent."""


class PanelReloadResponse(BaseModel):
    """Response body for ``POST /api/panels/reload`` (#2095, FR-046)."""

    reloaded: int
    """Number of panel specs registered after the rebuild."""
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class PanelSourceResponse(BaseModel):
    """Response body for ``GET /api/panels/{panel_id}/source`` (FR-024)."""

    panel_id: str
    tier: str
    """The tier the panel resolved from, which is also where a save lands
    (FR-025) -- unless it is read-only, in which case a save copies it into the
    open project (FR-026)."""
    entry: str
    """The entry document's file name inside the panel directory."""
    source: str
    """The entry document's text."""
    declaration: str
    """The ``panel.json`` text, so an editor can show both halves of a panel."""
    editable: bool
    """Whether a save writes in place. ``False`` means a save copies the panel
    into the project first. Reported so the interface can *say* what a save will
    do -- not so it can offer a choice; FR-025 forbids asking."""
    shadows: str | None = None
    """The tier of the panel this one shadows, or ``None``."""
    descriptor: PanelDescriptorModel | None = None


class PanelSourceSaveRequest(BaseModel):
    """Request body for ``PUT /api/panels/{panel_id}/source`` (FR-025)."""

    source: str
    """The new entry-document text."""
    declaration: str | None = None
    """An optional replacement ``panel.json``. It must parse and must keep the
    panel's id: FR-027 is what makes a copy take effect, so a save that renamed
    the panel would leave the original visible and the edit apparently lost."""


class PanelSourceSaveResponse(BaseModel):
    """Response body after a panel edit is saved (FR-025 to FR-027, FR-030)."""

    panel_id: str
    tier: str
    """The tier that was written."""
    copied: bool
    """``True`` when the save copied a read-only panel into the project."""
    descriptor: PanelDescriptorModel | None = None
    """The panel as it now resolves, so the host can remount from the response
    rather than asking again (FR-030)."""


class PanelOverrideRevertResponse(BaseModel):
    """Response body for ``DELETE /api/panels/{panel_id}/override`` (FR-029)."""

    panel_id: str
    removed_tier: str
    """The tier the deleted copy lived in."""
    restored_tier: str
    """The tier of the panel the copy was shadowing, now resolving again."""
    descriptor: PanelDescriptorModel | None = None


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
# These wire the producer (run_plot_job) to the consumer (PlotPanel): the
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


class PlotTargetItem(BaseModel):
    """One selectable workflow output target for a new plot."""

    target_id: str
    workflow_path: str
    workflow_id: str | None = None
    node_id: str
    node_label: str = ""
    block_type: str
    output_port: str
    output_type: str = ""
    is_collection: bool = False
    latest_run_id: str | None = None
    latest_output_available: bool = False
    diagnostics: list[str] = Field(default_factory=list)


class PlotTargetListResponse(BaseModel):
    """Response body for ``GET /api/plots/targets``."""

    targets: list[PlotTargetItem] = Field(default_factory=list)
    count: int


class PlotCreateRequest(BaseModel):
    """Request body for ``POST /api/plots``."""

    plot_id: str = Field(description="Plot id and plots/<id> directory name.")
    target_id: str = Field(description="Target id selected from GET /api/plots/targets.")
    title: str | None = Field(default=None, description="Human title written to plot.yaml.")
    language: Literal["python", "r"] = Field(default="python")
    overwrite: bool = Field(default=False)


class PlotCreateResponse(BaseModel):
    """Response body after creating a plot scaffold."""

    plot_id: str
    manifest_path: str
    script_path: str
    bytes_written: int
    warnings: list[str] = Field(default_factory=list)
    target: PlotTargetItem


class PlotRelinkRequest(BaseModel):
    """Request body for ``POST /api/plots/{plot_id}/relink`` (bug#7).

    Re-points an existing plot at a new workflow output target (strict 1:1).
    """

    target_id: str = Field(description="New target id selected from GET /api/plots/targets.")


class PlotRelinkResponse(BaseModel):
    """Response body after relinking a plot's data source (bug#7).

    ``valid`` plus ``errors``/``warnings`` reflect a fresh validation of the
    relinked plot, so a previously broken target reports ``valid=true`` here.
    """

    plot_id: str
    manifest_path: str
    target: PlotTargetItem
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlotRunResponse(BaseModel):
    """Response body for ``POST /api/plots/run``.

    On success ``data_ref`` is the catalog id the frontend passes to
    ``POST /api/previews/sessions`` (with ``target.kind="plot_artifact"``) to
    render the produced artifact through the core ``PlotPanel``. It is
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
    broken: bool = False
    """True when the bound target (node_id + output_port) no longer resolves in
    its workflow — e.g. the source block was deleted/recreated. The app shell
    flags these for relink (bug#7 / PR #1712 review)."""
    output_type: str = ""
    """Core type of the bound output port (e.g. ``Spectrum``), resolved live from
    the workflow's current targets so the plot card can show the full block info.
    Empty when the target no longer resolves or discovery is unavailable."""


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


# ---------------------------------------------------------------------------
# ADR-053 §4 — the user-wide library write path (FR-006 to FR-008).
#
# The user library is the one place in the product that lives outside every
# project root, so its request shapes are deliberately narrow: the caller names
# the target tier explicitly (FR-006 forbids inferring it from file content)
# and supplies a bare filename, never a path. Nothing here can express a
# directory, which is what makes the route's containment check a confirmation
# rather than the only line of defence.
# ---------------------------------------------------------------------------

#: FR-006: the three user-library targets, chosen by the caller and never
#: inferred. The values are the drop-in child directory names from
#: :mod:`scistudio.core.dropins`. ``panels`` joined when the
#: tutorial-scoped library grew its panel tier (Learning Center FR-070,
#: #2086), so promoting a project panel resolves through the same route —
#: and the same library-root swap — as blocks and types.
UserLibraryTarget = Literal["blocks", "types", "previewers"]


class MoveSourceRef(BaseModel):
    """The project file a library write should consume (ADR-053 FR-017).

    Promotion **moves**: the copy in the library becomes the only copy, so the
    write that creates it is also what removes the original. Naming the source
    here rather than adding a general project-file delete endpoint keeps the
    blast radius at exactly this operation — there is no way to reach the
    removal except by first writing that file's content somewhere else.
    """

    project_id: str = Field(description="Project whose root the path is resolved against.")
    path: str = Field(
        description=(
            "Project-relative path of the file to remove once the write has succeeded. "
            "Sandboxed by the same resolver the project file read and write use."
        )
    )


class UserLibraryWriteRequest(BaseModel):
    """Request body for ``PUT /api/user-library/file`` (ADR-053 FR-006)."""

    content: str = Field(description="Full UTF-8 text to write to the file.")
    overwrite: bool = Field(
        default=False,
        description=(
            "ADR-053 FR-008: writing over an existing file requires this explicit "
            "opt-in. Without it an existing target is reported as a 409 conflict so "
            "the UI can prompt for overwrite or save-as-new-name."
        ),
    )
    move_from: MoveSourceRef | None = Field(
        default=None,
        description=(
            "ADR-053 FR-017: when set, the named project file is removed after the write "
            "succeeds, which is what makes promotion a move rather than a copy. Omitted "
            "by callers creating a new file rather than promoting an existing one."
        ),
    )


class UserLibraryFileResponse(BaseModel):
    """Response body for ``GET /api/user-library/file`` (ADR-053 FR-031).

    The user-library counterpart of the project file read: a 200 means the file
    exists, a 404 means it does not, which is exactly the signal the frontend's
    existence probe needs before offering to create or promote.
    """

    target: UserLibraryTarget
    filename: str
    path: str = Field(description="Absolute path of the file inside the user library.")
    content: str
    mtime: float
    size: int
    encoding: str = "utf-8"


class UserLibraryWriteResponse(BaseModel):
    """Response body for ``PUT /api/user-library/file`` (ADR-053 FR-006/FR-010)."""

    target: UserLibraryTarget
    filename: str
    path: str = Field(description="Absolute path of the file inside the user library.")
    mtime: float
    size: int
    kind: str = Field(description="'created' for a new file, 'modified' for an accepted overwrite.")
    registries_refreshed: bool = Field(
        description=(
            "ADR-053 FR-010: whether the post-write registry refresh succeeded, so the "
            "new block or type is discoverable without a restart. False means the file "
            "landed but the caller should trigger a palette reload."
        )
    )
    moved_from: str | None = Field(
        default=None,
        description=(
            "ADR-053 FR-017: the project file that was removed, making this a move. "
            "None when the request named no source, or when removing it failed — in "
            "which case ``move_error`` says why and the original is still there."
        ),
    )
    move_error: str | None = Field(
        default=None,
        description=(
            "Why the source could not be removed, or None. A failure here never fails "
            "the request: the library copy exists, so the promotion succeeded, and the "
            "outcome is a copy rather than a move — which the UI reports rather than "
            "hides."
        ),
    )
