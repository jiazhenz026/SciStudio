export interface Position {
  x: number;
  y: number;
}

/**
 * ADR-044 §3 / spec FR-004 — one exposed port surfaced by a SubWorkflowBlock,
 * derived (response-only) from the referenced subworkflow's `exposed_ports`.
 * `name` MUST equal the React Flow handle id so existing colon-ref edge
 * connect/persist logic works unchanged (`<node_id>:<port_name>`).
 */
export interface ResolvedSubworkflowPort {
  name: string;
  accepted_types: string[];
  /** ADR-044 — owning inner block provenance so the editor can show which inner
   *  block each exposed port belongs to. Optional/`""` for older payloads or
   *  unresolvable refs. */
  block_id?: string;
  block_type?: string;
  block_label?: string;
  port?: string;
}

/**
 * ADR-044 — the response-only port surface attached to `subworkflow` /
 * `subworkflow_broken` nodes on the `GET /api/workflows/{id}` response. This
 * field is NEVER persisted; the backend recomputes it per load from the
 * referenced file's `exposed_ports` (or marks `broken: true` with empty port
 * lists when `config.ref.path` does not resolve).
 */
export interface ResolvedSubworkflowPorts {
  inputs: ResolvedSubworkflowPort[];
  outputs: ResolvedSubworkflowPort[];
  /** True for `subworkflow_broken` nodes whose `config.ref.path` is unresolved. */
  broken: boolean;
  /** The (unresolved-or-resolved) project-relative reference path, or null. */
  ref_path: string | null;
}

/**
 * ADR-044 FR-011 / US5 — response of `POST /api/workflows/import-subworkflow`.
 * The backend copies the chosen external file into `<project>/subworkflows/`,
 * returns its new project-relative `ref_path`, and re-resolves the referenced
 * file's exposed-port surface (`resolved_ports`) so the caller can repoint a
 * node's `config.ref.path` AND refresh its handles without a full reload. The
 * `resolved_ports` shape mirrors the response-only surface attached to
 * `subworkflow` / `subworkflow_broken` nodes on the workflow GET response.
 */
export interface ImportSubworkflowResponse {
  /** Project-relative path of the copied file (e.g. `subworkflows/foo.swf.yaml`). */
  ref_path: string;
  resolved_ports: ResolvedSubworkflowPorts;
}

export interface WorkflowNode {
  id: string;
  block_type: string;
  config: Record<string, unknown>;
  execution_mode?: string | null;
  layout?: Position | null;
  /**
   * ADR-044 — present only on `subworkflow` / `subworkflow_broken` nodes. The
   * authored graph (load path, NOT flattened) carries this so the editor can
   * render handles for the referenced subworkflow's exposed ports without
   * whole-graph flattening (spec FR-002 / FR-004). Response-only; absent on
   * every other block type.
   */
  resolved_ports?: ResolvedSubworkflowPorts;
}

export interface WorkflowEdge {
  source: string;
  target: string;
}

export interface WorkflowResponse {
  id: string;
  version: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: Record<string, unknown>;
}

export interface WorkflowExecutionResponse {
  workflow_id: string;
  status: string;
  message: string;
}

export interface WorkflowExecutionOptions {
  overwriteNodeIds?: string[];
}

export interface ExecuteFromResponse extends WorkflowExecutionResponse {
  reused_blocks: string[];
  reset_blocks: string[];
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string;
  path: string;
  last_opened?: string | null;
  workflow_count: number;
  workflows: string[];
  current_workflow_id?: string | null;
}

/*
 * ADR-053 FR-001 — `RunFirstWorkflowBootstrapRequest` / `...Response` were the
 * wire types of the single hardcoded tutorial's bootstrap route, removed with
 * it (FR-003). The Learning Center's shapes live beside their client in
 * `lib/api/learningCenter.ts`, since they describe one feature's contract
 * rather than the shared product API.
 */

export interface BlockPortResponse {
  name: string;
  direction: string;
  accepted_types: string[];
  required: boolean;
  description: string;
  constraint_description: string;
  is_collection: boolean;
}

export type MetadataFidelityLevel = "pixel_only" | "typed_meta" | "format_specific" | "lossless";

export interface MetadataFidelityResponse {
  level: MetadataFidelityLevel;
  typed_meta_reads: string[];
  typed_meta_writes: string[];
  format_metadata_reads: string[];
  format_metadata_writes: string[];
  notes?: string | null;
}

export interface FormatCapabilityResponse {
  id: string;
  direction: "load" | "save";
  data_type: string;
  format_id: string;
  extensions: string[];
  label: string;
  block_type: string;
  handler: string;
  is_default: boolean;
  priority: number;
  roundtrip_group?: string | null;
  metadata_fidelity: MetadataFidelityResponse;
  is_synthesized: boolean;
  migration_scaffold: boolean;
}

/**
 * ADR-051: the serialized interactive panel manifest surfaced on block metadata
 * (the wire shape of the backend ``PanelManifest.to_dict()``; the server-only
 * ``asset_root`` is intentionally absent). Mirrors {@link PanelManifestDescriptor}
 * in the store, which carries the same shape for the live prompt flow.
 */
export interface PanelManifest {
  panel_id: string;
  module_url: string;
  export_name: string;
  css: string[];
  version: string;
  api_version: string;
  response_schema?: Record<string, unknown> | null;
}

/**
 * ADR-053 FR-001/FR-002/FR-004 — which tier a registered block came from.
 *
 * `builtin` and `package` are unchanged from the pre-ADR-053 vocabulary. The
 * single `custom` label that used to cover both tier-1 drop-in directories
 * splits into `user` (`~/.scistudio/blocks/`) and `project`
 * (`{project}/blocks/`); `custom` survives only as the FR-002 fallback for a
 * block whose `file_path` resolves to neither root — an absent path, a symlink
 * escaping both, a differing Windows drive.
 */
export type BlockOrigin = "builtin" | "user" | "project" | "package" | "custom";

export interface BlockSummary {
  name: string;
  type_name: string;
  // #588: base_category is always one of 6 base types (io, process, code,
  // app, ai, subworkflow).  subcategory is the optional palette grouping label.
  base_category: string;
  subcategory: string;
  /** #1839: block-declared canvas-node color (CSS hex) — null/undefined uses the
   *  base_category default. */
  ui_color?: string | null;
  /** #1839: block-declared canvas-node icon (a Lucide icon name) — unknown names
   *  fall back to the category icon. */
  ui_icon?: string | null;
  description: string;
  version: string;
  input_ports: BlockPortResponse[];
  output_ports: BlockPortResponse[];
  direction?: string | null;
  source?: string;
  /** ADR-053 FR-004: the resolved origin tier, used for palette grouping and
   *  for gating the promotion action. Optional so a payload from a backend
   *  that predates the tier split still deserializes; the palette falls back to
   *  `source` in that case. */
  origin?: BlockOrigin;
  package_name?: string;
  /** ADR-029 D8: true when this block supports user-configurable input port count. */
  variadic_inputs?: boolean;
  /** ADR-029 D8: true when this block supports user-configurable output port count. */
  variadic_outputs?: boolean;
  /** ADR-043: backend-owned IO format capabilities for aggregate IOBlocks. */
  format_capabilities?: FormatCapabilityResponse[];
  /** ADR-051: execution mode hint ("auto" | "interactive" | "external") so the
   *  palette/schema can identify interactive blocks. */
  execution_mode?: string;
  /** ADR-051: interactive panel manifest; null unless the block is interactive. */
  panel_manifest?: PanelManifest | null;
  /**
   * ADR-054 FR-004 / FR-030 - the notebook a packaged block was generated
   * from, which is what marks a block as packaged rather than hand-written.
   *
   * `scistudio.explore.packaging` writes it as a `ClassVar` on the generated
   * class, but `scistudio.api.schemas.BlockSummary` does not carry it and
   * `routes/blocks.py::_summary` does not read it, so **the backend does not
   * send this field yet**. It is declared here so the double-click (FR-004)
   * and the notebook badge (FR-030) share one definition of "packaged" rather
   * than each inventing a heuristic; until the backend surfaces it, both read
   * `undefined` and keep their pre-ADR-054 behaviour.
   *
   * See `frontend/src/explore/packagedBlock.ts` and the S4-A1 entry in
   * `docs/planning/adr-054-assembly-followups.md`.
   */
  notebook_filename?: string | null;
}

export interface TypeHierarchyEntry {
  name: string;
  base_type: string;
  description: string;
  /**
   * Mirrors `TypeHierarchyEntry.ui_ring_color` on the backend schema, which
   * nothing has ever populated (ADR-053 spec §2.8). ADR-053 FR-066 leaves it
   * dead rather than reviving it — declared type colour travels on
   * `TypeSummary` from `GET /api/types/`, and `type_hierarchy` keeps serving
   * `base_type` lookups only. Kept here because the backend field still
   * exists; not read by any colour resolution.
   */
  ui_ring_color?: string | null;
}

/**
 * ADR-053 FR-005 — the tier a registered data type came from.
 *
 * Same vocabulary as `BlockOrigin` with `core` in place of `builtin`, because
 * the two surfaces share one backend resolver. `custom` is the fallback for a
 * drop-in whose file path resolves under neither tier root.
 */
export type TypeOrigin = "core" | "user" | "project" | "package" | "custom";

/**
 * One registered `DataObject` type, as `GET /api/types/` reports it
 * (ADR-053 FR-026).
 *
 * Deliberately not an extension of `TypeHierarchyEntry`: FR-027 makes the
 * types listing independent of the block listing, so the Data types tab
 * neither waits for nor re-triggers a palette fetch.
 */
export interface TypeSummary {
  name: string;
  /** Immediate parent type name; `""` for `DataObject` itself. */
  base_type: string;
  /** First line of the class docstring; may be `""`. */
  description: string;
  origin: TypeOrigin;
  /**
   * ADR-053 FR-040 — the owning distribution, byte-identical to the
   * `BlockSummary.package_name` the same distribution reports, because the
   * backend reads one string rather than deriving two. `null` for core, both
   * drop-in tiers, and any package the block side does not name either; such a
   * type keeps the lumped `Packages` section rather than disappearing.
   */
  package_name: string | null;
  /** Absolute path of the defining file, or null when unresolvable. */
  file_path: string | null;
  /**
   * ADR-053 FR-049/FR-050 — the fill the type declared, already validated and
   * normalised to long-form `#rrggbb` / `#rrggbbaa` by the registry (FR-052).
   * `null` means the type declared nothing, and the rest of the FR-051
   * precedence applies.
   */
  ui_color: string | null;
  /** As `ui_color`, for the ring. `null` derives the ring from the fill. */
  ui_ring_color: string | null;
  /**
   * ADR-053 FR-054 – FR-056 — always present, possibly empty. Load and save
   * are reported separately (FR-055) because a type readable from a format it
   * cannot be written back to is a real asymmetry; empty means "no format
   * capability registered for this direction", which the popover states
   * outright (FR-056).
   */
  load_extensions: string[];
  save_extensions: string[];
}

/** Response body of `GET /api/types/` — sorted by `name` ascending. */
export interface TypeListResponse {
  types: TypeSummary[];
}

/** Response body of `GET /api/types/template` (ADR-053 FR-028). */
export interface TypeTemplateResponse {
  kind: string;
  content: string;
  suggested_filename: string;
}

/**
 * Response body of `GET /api/types/{type_name}/source` (ADR-053 FR-068).
 *
 * Read-only for every tier, structurally: `path` is absolute, and every save
 * route takes either a project-relative path or a library target plus bare
 * filename. Only core and packaged types are opened through it — the two
 * drop-in tiers open through their own editable path instead.
 */
export interface TypeSourceResponse {
  type_name: string;
  path: string;
  source: string;
  language: string;
  origin: TypeOrigin;
}

/**
 * ADR-053 FR-006 — which user library directory a write or read addresses.
 *
 * Named by the caller and never inferred from file content: `blocks` is
 * `~/.scistudio/blocks/`, `types` is `~/.scistudio/types/`, and `panels`
 * is `~/.scistudio/previewers/` (Learning Center #2086). Inside a tutorial
 * project the backend swaps the library root for the tutorial-scoped one; the
 * target names the tier, never the root.
 */
export type UserLibraryTarget = "blocks" | "types" | "previewers";

/** Response body of `GET /api/user-library/file` (ADR-053 FR-031). */
export interface UserLibraryFileResponse {
  target: UserLibraryTarget;
  filename: string;
  /** Absolute path of the file inside the user library. */
  path: string;
  content: string;
  mtime: number;
  size: number;
  encoding?: string;
}

/** Response body of `PUT /api/user-library/file` (ADR-053 FR-006 / FR-010). */
export interface UserLibraryWriteResponse {
  target: UserLibraryTarget;
  filename: string;
  /** Absolute path of the file inside the user library. */
  path: string;
  mtime: number;
  size: number;
  /** `created` for a new file, `modified` for an accepted overwrite. */
  kind: "created" | "modified";
  /**
   * FR-010: whether the post-write registry refresh succeeded. `false` means
   * the file landed but the caller should trigger a palette reload itself.
   */
  registries_refreshed: boolean;
  /**
   * FR-017: the project file the server removed, making this a move rather
   * than a copy. `null` when the request named no source, or when the removal
   * failed — in which case `move_error` says why and the original is still
   * there.
   */
  moved_from: string | null;
  /**
   * Why the original could not be removed, or `null`. Never fails the request:
   * the library copy exists, so the promotion succeeded and the outcome is a
   * copy, which the UI reports rather than hides.
   */
  move_error: string | null;
}

/**
 * Declarative dynamic-port descriptor for blocks whose port types depend on
 * a config field selection (e.g. ``LoadData``'s ``core_type`` dropdown).
 *
 * Mirrors the backend ``Block.dynamic_ports`` ClassVar shape defined in
 * ADR-028 Addendum 1 §D2'. The mapping is strictly two-level:
 *
 *     {port_name: {enum_value: [type_name, ...]}}
 *
 * The frontend consumes this descriptor via ``computeEffectivePorts()`` to
 * resolve the per-instance ``accepted_types`` for each port without making a
 * backend round-trip when the user changes the driving config field.
 *
 * Per ADR-028 Addendum 1 D4 / D8, this descriptor is delivered to the
 * frontend on ``BlockSchemaResponse.dynamic_ports`` (set to ``null`` for
 * static blocks).
 */
export interface DynamicPortsConfig {
  /** Name of the config field whose value drives the port-type mapping. */
  source_config_key: string;
  /** Per-output-port enum-value to type-name list mapping. */
  output_port_mapping?: Record<string, Record<string, string[]>>;
  /** Per-input-port enum-value to type-name list mapping. */
  input_port_mapping?: Record<string, Record<string, string[]>>;
}

export interface BlockSchemaResponse extends BlockSummary {
  config_schema: {
    type?: string;
    properties?: Record<string, Record<string, unknown>>;
    required?: string[];
  };
  type_hierarchy: TypeHierarchyEntry[];
  /**
   * Enum-driven dynamic-port descriptor (ADR-028 Addendum 1 D4).
   *
   * ``null`` (or ``undefined``) for static blocks. Populated by the
   * backend from ``cls.dynamic_ports`` at registry scan time. Consumed
   * by ``computeEffectivePorts()`` in the frontend.
   */
  dynamic_ports?: DynamicPortsConfig | null;
  /**
   * IO direction (ADR-028 Addendum 1 D8). One of ``"input"`` or
   * ``"output"`` for IO blocks; ``null`` (or ``undefined``) for
   * non-IO blocks. Populated by the backend from ``cls.direction`` so
   * the frontend can render IO-specific UI (e.g. file-vs-directory
   * picker on the Browse button) without hardcoding
   * ``blockType === "io_block"`` checks.
   */
  direction?: string | null;
  /**
   * ADR-029 D11: type names accepted by variadic input ports.
   * Frontend uses this to populate the type dropdown in the port editor.
   * Empty array means "any DataObject subclass".
   */
  allowed_input_types?: string[];
  /**
   * ADR-029 D11: type names accepted by variadic output ports.
   * Empty array means "any DataObject subclass".
   */
  allowed_output_types?: string[];
  /**
   * ADR-029 Addendum 1: minimum number of variadic input ports.
   * null/undefined means no minimum.
   */
  min_input_ports?: number | null;
  /**
   * ADR-029 Addendum 1: maximum number of variadic input ports.
   * null/undefined means no maximum.
   */
  max_input_ports?: number | null;
  /**
   * ADR-029 Addendum 1: minimum number of variadic output ports.
   * null/undefined means no minimum.
   */
  min_output_ports?: number | null;
  /**
   * ADR-029 Addendum 1: maximum number of variadic output ports.
   * null/undefined means no maximum.
   */
  max_output_ports?: number | null;
}

export interface BlockListResponse {
  blocks: BlockSummary[];
}

/** Read-only source code backing a registered block type (#1758). */
export interface BlockSourceResponse {
  block_type: string;
  path: string;
  source: string;
  language: string;
  origin: string;
}

export interface ConnectionValidationResponse {
  compatible: boolean;
  reason: string;
}

export interface DataUploadResponse {
  ref: string;
  type_name: string;
  metadata: Record<string, unknown>;
}

export interface DataMetadataResponse {
  ref: string;
  type_name: string;
  metadata: Record<string, unknown>;
}

/** Response of `POST /api/data/register-path` (#2112). Field names mirror the
 *  backend `DataRegisterPathResponse` and feed a `data_ref`
 *  {@link PreviewTarget} directly (snake_case on the wire, like the other
 *  data/preview types here). */
export interface DataRegisterPathResponse {
  ref: string;
  recorded_type: string;
  type_chain: string[];
  display_name: string | null;
  /** Normalized extension (".tif") the open-as choice is keyed on (#2112). */
  extension: string;
  /** Whether `recorded_type` is the project's remembered choice for it. */
  remembered: boolean;
}

/** One type a file could be opened as (#2112). `origin` / `package_name` are
 *  the same tier facts the Data types tab reports, so the picker can say where
 *  a candidate came from instead of listing bare names. */
export interface DataOpenAsCandidate {
  name: string;
  base_type: string;
  description: string;
  origin: string;
  package_name: string | null;
  /** False for `Artifact` offered as a plain-file fallback rather than a
   *  declared loader for this extension. */
  loadable: boolean;
}

/** `GET /api/data/open-as/candidates` (#2112). `candidates` is ordered
 *  project -> package -> core, so the first entry is the picker's default;
 *  `remembered` short-circuits the picker entirely. */
export interface DataOpenAsCandidatesResponse {
  path: string;
  extension: string;
  candidates: DataOpenAsCandidate[];
  remembered: string | null;
}

/** One remembered extension -> type choice (#2112). */
export interface DataOpenAsEntry {
  extension: string;
  type_name: string;
  available: boolean;
}

/** `GET /api/data/open-as` — the open project's remembered choices (#2112). */
export interface DataOpenAsListResponse {
  entries: DataOpenAsEntry[];
}

// ---------------------------------------------------------------------------
// ADR-048 SPEC 1 — routed panel session API wire types (FR-020 .. FR-024).
//
// These mirror `scistudio.api.schemas` Pydantic models / the canonical
// `scistudio.panels.models` dataclasses on the wire. The legacy
// `DataPreviewResponse` / `DataPreviewQuery` REST-preview wire types and the
// `GET /api/data/{ref}/preview` adapter were removed under ADR-048 no-compat
// (#1604); pagination/sort now flows through the routed session API below.
// ---------------------------------------------------------------------------

/** Canonical fallback kinds carried by a {@link PreviewEnvelope} (backend
 *  `EnvelopeKind`). The frontend routes core fallback viewers by this value
 *  when no validated panel manifest is present. */
export type EnvelopeKind =
  | "dataframe"
  | "array"
  | "series"
  | "text"
  | "artifact"
  | "composite"
  | "collection"
  | "plot"
  | "error";

/** What a {@link PreviewTarget} points at (backend `TargetKind`). */
export type PreviewTargetKind = "data_ref" | "collection_ref" | "artifact" | "plot_artifact";

/** Optional workflow/node/output identity for UI display only — carries no
 *  workflow truth (backend `PreviewSource`). */
export interface PreviewSource {
  workflow_id?: string | null;
  node_id?: string | null;
  output_port?: string | null;
}

/** Identifies what is being previewed (backend `PreviewTarget`). */
export interface PreviewTarget {
  kind: PreviewTargetKind;
  ref: string;
  recorded_type?: string;
  type_chain?: string[];
  collection_item_type?: string | null;
  source?: PreviewSource | null;
}

/** Same-origin descriptor for a dynamically loaded panel ESM module
 *  (backend `FrontendManifest.to_dict()` — note: NO `asset_root`). A package
 *  or project panel surfaces this in `envelope.metadata.frontend_manifest`
 *  so {@link PreviewHost} can validate + import + mount it (FR-022/FR-024). */
export interface PanelFrontendManifest {
  previewer_id: string;
  /** Backend-relative URL the host imports the ESM module from, e.g.
   *  `/api/previews/assets/<previewer_id>/<path>`. Remote (http/https/`//`)
   *  URLs are rejected by the frontend same-origin validator (FR-022). */
  module_url: string;
  /** Named export inside the module to mount. */
  export_name: string;
  /** Optional backend-relative CSS asset URLs. */
  css?: string[];
  /** Panel bundle version (fingerprint or semver). */
  version?: string;
  /** Panel API compatibility version. The host compares it against the
   *  `accepted_api_version` the backend sends; nothing in the frontend spells
   *  a version literal of its own (ADR-054 FR-004, D-010, SC-001). */
  api_version?: string;
}

/**
 * ADR-054 D-016.3 / D-020 — everything the host needs to mount one panel,
 * exactly as `scistudio.panels.descriptor.PanelDescriptor.to_dict()` emits it.
 *
 * The frontend invents none of it. The accepted API version, the granted
 * capability, the entry document, the asset base and the read limits are the
 * backend's answers, carried on the response the caller is already reading; a
 * descriptor missing `accepted_api_version` or `read_limits` is a backend
 * defect and the host refuses to mount rather than inventing a bound or a
 * version.
 */
export interface PanelDescriptorResponse {
  panel_id: string;
  display_name: string;
  /** The version this panel's declaration states. */
  api_version: string;
  /** The backend's `PANEL_API_VERSION` — the one definition in the tree. */
  accepted_api_version: string;
  capability: "displaying" | "producing";
  /** Same-origin path of the entry document on the merged asset route. */
  document_url: string;
  /** Same-origin base the panel fetches its own bulk assets from. */
  asset_base_url: string;
  read_limits: { max_rows: number; max_bytes: number; [key: string]: number };
  /** Which of the four tiers this panel resolved from. Diagnostics only. */
  tier?: string;
  features?: string[];
  supports_collection?: boolean;
}

/** Descriptor for a bounded follow-up resource read (backend `PreviewResource`). */
export interface PreviewResource {
  resource_id: string;
  kind: string;
  media_type?: string | null;
  description?: string;
  params?: Record<string, unknown>;
}

/** Display + state metadata on every envelope (backend `PreviewMetadata`).
 *  The six boolean flags are mandatory (FR-011); panel-owned shape/type/
 *  axis metadata and the optional `frontend_manifest` ride alongside them
 *  (the backend spreads `extra` into this object on the wire). */
export interface PreviewMetadata {
  sampled?: boolean;
  truncated?: boolean;
  cached?: boolean;
  derived?: boolean;
  complete?: boolean;
  failed?: boolean;
  /** Same-origin manifest a package/project panel asks the host to mount.
   *  Absent for core fallbacks → the host renders the core viewer for `kind`. */
  frontend_manifest?: PanelFrontendManifest;
  /** Panel-owned extra metadata (shape, dtype, axes, total_rows, ...). */
  [key: string]: unknown;
}

/** Deterministic preview error codes (backend `PreviewErrorCode`). */
export type PreviewErrorCode =
  | "routing_ambiguity"
  | "unknown_previewer"
  | "unknown_target"
  | "missing_bundle"
  | "provider_exception"
  | "invalid_spec"
  | "duplicate_previewer_id"
  | "budget_exceeded";

/** Typed error payload embedded in a failed envelope (backend `PreviewErrorInfo`). */
export interface PreviewErrorInfo {
  code: PreviewErrorCode | string;
  message: string;
  detail?: Record<string, unknown>;
}

/** Canonical backend preview response (backend `PreviewEnvelope` /
 *  `PreviewEnvelopeModel`). */
export interface PreviewEnvelope {
  session_id: string | null;
  previewer_id: string;
  target: PreviewTarget;
  kind: EnvelopeKind;
  payload: Record<string, unknown>;
  resources: PreviewResource[];
  metadata: PreviewMetadata;
  diagnostics: string[];
  error: PreviewErrorInfo | null;
  /** First-class same-origin panel manifest, framework-stamped by the
   *  session manager from the resolved PanelSpec (ADR-048 §4 / #1579).
   *  Absent for core fallbacks. Prefer this over `metadata.frontend_manifest`.
   *
   *  ADR-054 FR-036: the host no longer mounts from this. It is the ADR-048
   *  module form, kept on the wire for the compatibility shim (FR-044). */
  frontend_manifest?: PanelFrontendManifest | null;
  /**
   * ADR-054 D-020 — the descriptor for the panel the *backend* chose for this
   * target. The host mounts what it was told; it holds no mapping from a
   * response's kind to a panel (FR-036, SC-010).
   */
  panel?: PanelDescriptorResponse | null;
  /**
   * ADR-054 FR-015, D-013 — the id of the panel to mount when the chosen one
   * fails. Named by the backend, never chosen here.
   */
  fallback_panel_id?: string | null;
  /**
   * The fallback panel's own descriptor.
   *
   * FR-015 names the fallback by id, but an id alone cannot be mounted: a mount
   * needs the entry document, the asset base, the granted capability and the
   * read limits, and every one of those is the backend's to state (D-016.3).
   * Deriving them here from the id would be the frontend re-deciding what the
   * backend already decided, which is the thing SC-010 measures the absence of.
   * So the host mounts the fallback when the response carries its descriptor
   * and, when it carries only the id, says which panel it could not reach
   * instead of guessing at a URL.
   */
  fallback_panel?: PanelDescriptorResponse | null;
}

/** Request body for `POST /api/previews/sessions`. */
export interface PreviewSessionCreate {
  target: PreviewTarget;
  query?: Record<string, unknown>;
}

/** Request body for `PATCH /api/previews/sessions/{session_id}`. */
export interface PreviewSessionPatch {
  query: Record<string, unknown>;
}

/** Response body for a bounded session resource read
 *  (`GET /api/previews/sessions/{id}/resources/{resource_id}`). The `data`
 *  field is either a child {@link PreviewEnvelope} or a bounded tile payload. */
export interface PreviewResourceResponse {
  resource_id: string;
  data: Record<string, unknown>;
}

/** Request body for saving a bounded session resource to a user-selected path. */
export interface PreviewResourceSaveRequest {
  destination_path: string;
  params?: Record<string, unknown>;
}

/** Response body after a session resource save. */
export interface PreviewResourceSaveResponse {
  path: string;
  filename: string;
  size_bytes: number;
  mime_type?: string | null;
}

// ---------------------------------------------------------------------------
// #2095 / #2049 — panel discovery, reload, and per-type choice (#2113
// surfaces all three in the left-panel Panels tab).
// ---------------------------------------------------------------------------

/** Where a panel was discovered from (backend `OwnerKind`; sets the
 *  FR-003 routing precedence project → user → package → core). */
export type PanelOwnerKind = "project" | "user" | "package" | "core";

/** One registered panel (backend `PanelSpecModel`).
 *
 *  The id field is `panel_id`. It was `previewer_id` until ADR-054 renamed the
 *  subsystem, and the backend model was renamed with it (`schemas.py`
 *  `PanelSpecModel`) — this shape follows the wire, not the history. */
export interface PanelSpecSummary {
  panel_id: string;
  display_name: string;
  owner_kind: PanelOwnerKind;
  owner_name: string;
  target_type: string;
  target_types: string[];
  supports_collection: boolean;
  priority: number;
  features: string[];
  /** `displaying` or `producing`, as the panel declares it (FR-005). */
  capability: string;
  backend_provider: string | null;
  frontend_manifest: PanelFrontendManifest | null;
  api_version: string;
  /** The tier the panel's directory was found in, or `null` for a routing
   *  entry with no on-disk document. */
  tier: PanelOwnerKind | null;
  /** The tier of the panel this one shadows, or `null`. What tells a caller
   *  whether `DELETE /api/panels/{panel_id}/override` has anything to
   *  restore (FR-029). */
  shadows: PanelOwnerKind | null;
}

/** `GET /api/panels` response (#2095, moved under the panel naming by
 *  ADR-054 D-020). */
export interface PanelListResponse {
  /** Registered panels, ordered project -> user -> package -> core. The
   *  backend field is `panels` (ADR-054 FR-023); it was `previewers` before
   *  the endpoint moved under the panel naming. */
  panels: PanelSpecSummary[];
  /** Discovery problems recorded during the scan (duplicate ids, refused
   *  drop-ins, broken entry points). */
  diagnostics: string[];
}

/** `POST /api/panels/reload` response (#2095, ADR-054 D-020). */
export interface PanelReloadResponse {
  reloaded: number;
  added: string[];
  removed: string[];
  diagnostics: string[];
}

/** Which layer a per-type panel choice lives at (#2049). */
export type PanelChoiceScope = "user" | "project";

/** One effective per-type panel choice (backend `PanelChoiceModel`). */
export interface PanelChoice {
  target_type: string;
  /** Renamed from `previewer_id` with the subsystem; the request body of
   *  `PUT /api/panels/choices/{target_type}` takes the same key. */
  panel_id: string;
  /** Which of the two preferences this records — `displaying` or
   *  `producing` (FR-049). */
  capability: string;
  /** Which layer this effective choice came from; a project-layer choice
   *  overrides the user-layer choice for the same type. */
  scope: PanelChoiceScope;
  /** False when the chosen panel is not registered right now — the choice
   *  stays recorded and routing falls back to the FR-003 ladder. */
  available: boolean;
}

/** `GET /api/panels/choices` response (#2049, ADR-054 D-020). */
export interface PanelChoiceListResponse {
  choices: PanelChoice[];
}

// ---------------------------------------------------------------------------
// ADR-054 T-010 / D-020 — reading a panel, saving it, and reverting (FR-024
// to FR-030). The host consumes all three; `PanelPalette` opens a panel's
// source and `PanelErrorSurface` offers the revert FR-028 requires.
// ---------------------------------------------------------------------------

/** `GET /api/panels/{panel_id}/source` response (FR-024). */
export interface PanelSourceResponse {
  panel_id: string;
  /** The tier the panel resolved from, which is also where a save lands
   *  (FR-025) — unless it is read-only, in which case a save copies it into
   *  the open project (FR-026). */
  tier: PanelOwnerKind;
  /** The entry document's file name inside the panel directory. */
  entry: string;
  /** The entry document's text. */
  source: string;
  /** The `panel.json` text. */
  declaration: string;
  /** Whether a save writes in place. `false` means a save copies the panel
   *  into the project first. Reported so the interface can *say* what a save
   *  will do — not so it can offer a choice; FR-025 forbids asking. */
  editable: boolean;
  /** The tier of the panel this one shadows, or `null`. */
  shadows: PanelOwnerKind | null;
  descriptor: PanelDescriptorResponse | null;
}

/** `PUT /api/panels/{panel_id}/source` request body (FR-025). */
export interface PanelSourceSaveRequest {
  source: string;
  /** An optional replacement `panel.json`. It must parse and must keep the
   *  panel's id (FR-027). */
  declaration?: string | null;
}

/** `PUT /api/panels/{panel_id}/source` response (FR-025 to FR-027, FR-030). */
export interface PanelSourceSaveResponse {
  panel_id: string;
  /** The tier that was written. */
  tier: PanelOwnerKind;
  /** `true` when the save copied a read-only panel into the project. */
  copied: boolean;
  descriptor: PanelDescriptorResponse | null;
}

/** `DELETE /api/panels/{panel_id}/override` response (FR-029). */
export interface PanelOverrideRevertResponse {
  panel_id: string;
  /** The tier the deleted copy lived in. */
  removed_tier: PanelOwnerKind;
  /** The tier of the panel the copy was shadowing, now resolving again. */
  restored_tier: PanelOwnerKind;
  descriptor: PanelDescriptorResponse | null;
}

// ---------------------------------------------------------------------------
// ADR-048 SPEC 2 / #1606: plot-job run + preview wiring.
// ---------------------------------------------------------------------------

export type PlotLanguage = "python" | "r";

/** One workflow output target a new plot can bind to. */
export interface PlotTargetItem {
  target_id: string;
  workflow_path: string;
  workflow_id?: string | null;
  node_id: string;
  node_label: string;
  block_type: string;
  output_port: string;
  output_type: string;
  is_collection: boolean;
  latest_run_id?: string | null;
  latest_output_available: boolean;
  diagnostics: string[];
}

/** Response body for `GET /api/plots/targets`. */
export interface PlotTargetListResponse {
  targets: PlotTargetItem[];
  count: number;
}

/** Request body for `POST /api/plots`. */
export interface PlotCreateRequest {
  plot_id: string;
  target_id: string;
  title?: string | null;
  language?: PlotLanguage;
  overwrite?: boolean;
}

/** Response body for `POST /api/plots`. */
export interface PlotCreateResponse {
  plot_id: string;
  manifest_path: string;
  script_path: string;
  bytes_written: number;
  warnings: string[];
  target: PlotTargetItem;
}

/** Request body for `POST /api/plots/{plot_id}/relink` (backend
 *  `PlotRelinkRequest`, bug#7). Re-points an existing plot at a new workflow
 *  output target (strict 1:1). */
export interface PlotRelinkRequest {
  target_id: string;
}

/** Response body for `POST /api/plots/{plot_id}/relink` (backend
 *  `PlotRelinkResponse`, bug#7). `valid` plus `errors`/`warnings` reflect a
 *  fresh validation of the relinked plot, so a previously broken target reports
 *  `valid: true`. */
export interface PlotRelinkResponse {
  plot_id: string;
  manifest_path: string;
  target: PlotTargetItem;
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/** Request body for `POST /api/plots/run` (backend `PlotRunRequest`). */
export interface PlotRunRequest {
  plot_id: string;
  /** Optional run id to source the target output from; defaults to latest. */
  run_id?: string | null;
  /** Optional manifest-timeout override (re-clamped to the absolute ceiling). */
  timeout_seconds?: number | null;
}

/** Response body for `POST /api/plots/run` (backend `PlotRunResponse`).
 *
 *  On success, `data_ref` is the catalog id passed to
 *  {@link PreviewTarget.ref} (with `kind: "plot_artifact"`) to render the
 *  produced figure through the core PlotPanel. It is `null` when the run
 *  failed / produced no artifact — `status` + `errors` then explain why. */
export interface PlotRunResponse {
  status: "succeeded" | "failed" | "cancelled" | "timed_out";
  data_ref: string | null;
  recorded_type: string;
  type_chain: string[];
  cache_key: string | null;
  artifact_paths: string[];
  source: PreviewSource | null;
  warnings: string[];
  errors: string[];
}

/** One project-local plot manifest returned by `GET /api/plots`. */
export interface PlotListItem {
  plot_id: string;
  title: string;
  workflow_id?: string | null;
  node_id: string;
  output_port: string;
  display_label: string;
  language: string;
  preferred_format: string;
  manifest_path: string;
  script_path: string;
  /** True when the bound target no longer resolves (source block deleted/
   *  recreated) — the app shell flags these for relink (bug#7 / PR #1712). */
  broken?: boolean;
  /** Core type of the bound output port (e.g. "Spectrum"), resolved live from
   *  the workflow. Empty when the target no longer resolves. Shown on the plot
   *  card so the linked block info is complete. */
  output_type?: string;
}

/** Response body for `GET /api/plots`. */
export interface PlotListResponse {
  plots: PlotListItem[];
  count: number;
  warnings: string[];
}

export interface CancelPropagationResponse {
  cancelled_blocks: string[];
  skipped_blocks: string[];
  skip_reasons: Record<string, string>;
}

export interface WorkflowEventMessage {
  type: string;
  block_id?: string | null;
  workflow_id?: string | null;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  details?: string | null;
  workflow_id?: string | null;
  block_id?: string | null;
}

export interface FilesystemEntry {
  name: string;
  type: "file" | "directory";
  size?: number | null;
}

export interface FilesystemBrowseResponse {
  path: string;
  entries: FilesystemEntry[];
}

export interface FilesystemStatResponse {
  path: string;
  exists: boolean;
  type?: "file" | "directory" | null;
  size?: number | null;
}

export interface TreeEntry {
  name: string;
  type: "file" | "directory";
  size?: number | null;
}

export interface TreeResponse {
  entries: TreeEntry[];
}

export interface LocalPackageInstallResponse {
  package_name: string;
  version: string;
  install_path: string;
  modules: string[];
  blocks_count: number;
  replaced: boolean;
}

// #1784 — Package Manager (install / update / delete / rollback) types.
export interface InstalledPackage {
  package_name: string;
  version: string;
  install_path: string;
  modules: string[];
  has_backup: boolean;
  backup_version: string;
  /** Present only via the live registry (bundled / entry point), not on disk.
   *  Can be updated (installs a shadowing copy) but not deleted. */
  bundled: boolean;
}

export interface InstalledPackagesResponse {
  packages: InstalledPackage[];
}

export interface PackageUpdateStatus {
  package_name: string;
  current_version: string;
  channel: string;
  manifest_url: string;
  /** "update" | "incompatible" | "none" | "invalid" | "error" */
  status: string;
  available_version: string;
  min_core_base: string;
  notes: string;
  reason: string;
  update_available: boolean;
}

export interface PackageUpdatesResponse {
  core_base: string;
  statuses: PackageUpdateStatus[];
}

export interface PackageActionResponse {
  package_name: string;
  version: string;
  /** "update" | "rollback" | "delete" */
  action: string;
  previous_version: string;
  needs_relaunch: boolean;
}

// ---------------------------------------------------------------------------
// ADR-039 — Git versioning API types
// ---------------------------------------------------------------------------
//
// These mirror the JSON shapes returned by `src/scistudio/api/routes/git.py`
// (merged in PR #927). When the backend GitEngine returns a `log()` row, a
// branch listing, a status payload, or a merge result, the FastAPI route
// emits it as JSON of one of the shapes below.
//
// Shapes intentionally mirror python keys (`commit_sha`, `short_sha`, etc.)
// rather than camelCasing because:
//   1. The values pass through `api.ts.apiFetch` unmodified.
//   2. The diff viewer / history list show these raw fields in tooltips and
//      it is useful to grep them across stack.
// If TypeScript style ever requires camelCase, do that translation in the
// `api` wrapper (gitLog → { commitSha, ... }), not by changing the wire shape.

/**
 * One commit row returned by `GET /api/git/log`. Shape per ADR-039 §3.5
 * and the backend `GitEngine.log()` plumbing parser (commits are formatted
 * with `--format=...` so this is the stable wire contract).
 *
 * Wire shape per `src/scistudio/core/versioning/git_engine.py::log()`:
 *   `{ sha, short_sha, parents, author_name, author_email, author_date,
 *      subject, body, branches }`
 *
 * Note: the full SHA field is named `sha` on the wire (NOT `commit_sha`)
 * — that mirrors what `git log --format=%H` produces. Other endpoints
 * (`/api/git/commit` response, `head_state()` dataclass) DO use
 * `commit_sha`. Consumers must respect the per-endpoint naming.
 *
 * The `prefix` legend is derived client-side from the subject in
 * `gitSlice.classifyPrefix()` (NOT a wire field) — see ADR-039 §3.4 /
 * §3.4a:
 *   - "auto"   → subject starts with `auto:`  (hidden by default filter)
 *   - "agent"  → subject starts with `agent:` (visible with 🤖 icon)
 *   - "user"   → no recognized prefix         (visible with 👤 icon)
 */
export interface GitCommit {
  /** Full 40-char commit SHA. Backend wire field is `sha`, NOT `commit_sha`. */
  sha: string;
  short_sha: string;
  parents: string[];
  author_name: string;
  author_email: string;
  author_date: string;
  subject: string;
  body: string;
  /** Branch names whose tip is this commit (zero, one, or many). */
  branches: string[];
}

/**
 * Local branch row from `GET /api/git/branches`.
 *
 * Wire shape is `{ name, head_sha, is_current }` per
 * `GitEngine.branches()` in `src/scistudio/core/versioning/git_engine.py`.
 * Codex review on PR #930 flagged a draft `commit_sha` field that did
 * not match the backend; fixed to mirror the actual payload.
 */
export interface GitBranch {
  name: string;
  /** Tip commit sha (backend field is `head_sha`, NOT `commit_sha`). */
  head_sha: string;
  /** True if this branch is currently checked out. */
  is_current: boolean;
}

/** Diff payload from `GET /api/git/diff`. */
export interface GitDiff {
  /** Unified diff as a single string (consumer feeds it to react-diff-viewer-continued). */
  diff: string;
}

/** Working-tree status from `GET /api/git/status`. */
export interface GitStatus {
  dirty: boolean;
  modified: string[];
  staged: string[];
  untracked: string[];
  conflicted: string[];
}

/**
 * Result of `POST /api/git/merge` and `/cherry-pick`.
 *
 * Wire shape is uniformly `{ result, conflicted_files }` for ALL three
 * variants per `GitEngine.merge()` / `cherry_pick()` in
 * `src/scistudio/core/versioning/git_engine.py`. Successful (FF / clean)
 * results return `conflicted_files: []` and do NOT include a separate
 * `commit_sha`; consumers that need the post-merge HEAD must call
 * `GET /api/git/log?limit=1` (or wait for the `git.head_changed` WS
 * event) after a successful merge.
 *
 * Codex review on PR #930 flagged a draft union that put `commit_sha`
 * on the success variants; fixed to mirror the actual payload.
 */
export type GitMergeResult =
  | { result: "fast-forward"; conflicted_files: [] }
  | { result: "clean"; conflicted_files: [] }
  | { result: "conflict"; conflicted_files: string[] };

/** Response shape for `POST /api/git/commit`. */
export interface GitCommitResponse {
  commit_sha: string;
}

/**
 * Response shape for `/api/git/restore`.
 *
 * ADR-039 Addendum 1 (#1354): when the working tree was dirty before the
 * restore, the backend auto-commits the dirty content first (prefix
 * `auto`, message `pre-restore @ <iso-ts> (target=<short_sha>)`) and
 * returns the new commit SHA in `auto_commit_sha`. When the tree was
 * clean, `auto_commit_sha` is `null`.
 */
export type GitRestoreResult = {
  status: "ok";
  auto_commit_sha: string | null;
};

/**
 * Filter modes for the History panel dropdown per ADR-039 §3.4 / §3.5c.
 *
 *   - "manual" (DEFAULT): hide `auto:` and `agent:` prefixed commits.
 *   - "all":              show every commit.
 *   - "auto":             show only `auto:` prefixed commits (debugging).
 *   - "agent":            show only `agent:` prefixed commits (debugging).
 */
export type GitHistoryFilter = "manual" | "all" | "auto" | "agent";

/**
 * In-memory commit prefix classification. Computed client-side by
 * `gitSlice.classifyPrefix(message)` — NOT a wire field. The History view
 * and the GitGraph reference this to decide icon rendering (§3.4a).
 */
export type GitCommitPrefix = "auto" | "agent" | "user";

// ---------------------------------------------------------------------------
// ADR-054 spec 4 (T-001) — the Explore Session API and its WebSocket events.
//
// Defined in `./explore.ts` and re-exported here so this module stays the one
// door every consumer imports response and event shapes through. They were
// split out for size alone: `api.ts` with them inline is over the repository's
// per-file line limit.
// ---------------------------------------------------------------------------
export * from "./explore";
