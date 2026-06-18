export interface Position {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  block_type: string;
  config: Record<string, unknown>;
  execution_mode?: string | null;
  layout?: Position | null;
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

export interface BlockSummary {
  name: string;
  type_name: string;
  // #588: base_category is always one of 6 base types (io, process, code,
  // app, ai, subworkflow).  subcategory is the optional palette grouping label.
  base_category: string;
  subcategory: string;
  description: string;
  version: string;
  input_ports: BlockPortResponse[];
  output_ports: BlockPortResponse[];
  direction?: string | null;
  source?: string;
  package_name?: string;
  /** ADR-029 D8: true when this block supports user-configurable input port count. */
  variadic_inputs?: boolean;
  /** ADR-029 D8: true when this block supports user-configurable output port count. */
  variadic_outputs?: boolean;
  /** ADR-043: backend-owned IO format capabilities for aggregate IOBlocks. */
  format_capabilities?: FormatCapabilityResponse[];
}

export interface TypeHierarchyEntry {
  name: string;
  base_type: string;
  description: string;
  ui_ring_color?: string | null;
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

// ---------------------------------------------------------------------------
// ADR-048 SPEC 1 — routed previewer session API wire types (FR-020 .. FR-024).
//
// These mirror `scistudio.api.schemas` Pydantic models / the canonical
// `scistudio.previewers.models` dataclasses on the wire. The legacy
// `DataPreviewResponse` / `DataPreviewQuery` REST-preview wire types and the
// `GET /api/data/{ref}/preview` adapter were removed under ADR-048 no-compat
// (#1604); pagination/sort now flows through the routed session API below.
// ---------------------------------------------------------------------------

/** Canonical fallback kinds carried by a {@link PreviewEnvelope} (backend
 *  `EnvelopeKind`). The frontend routes core fallback viewers by this value
 *  when no validated previewer manifest is present. */
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

/** Same-origin descriptor for a dynamically loaded previewer ESM module
 *  (backend `FrontendManifest.to_dict()` — note: NO `asset_root`). A package
 *  or project previewer surfaces this in `envelope.metadata.frontend_manifest`
 *  so {@link PreviewHost} can validate + import + mount it (FR-022/FR-024). */
export interface PreviewerManifest {
  previewer_id: string;
  /** Backend-relative URL the host imports the ESM module from, e.g.
   *  `/api/previews/assets/<previewer_id>/<path>`. Remote (http/https/`//`)
   *  URLs are rejected by the frontend same-origin validator (FR-022). */
  module_url: string;
  /** Named export inside the module to mount. */
  export_name: string;
  /** Optional backend-relative CSS asset URLs. */
  css?: string[];
  /** Previewer bundle version (fingerprint or semver). */
  version?: string;
  /** Previewer API compatibility version; must match the host
   *  {@link PREVIEWER_HOST_API_VERSION} to mount without a diagnostic. */
  api_version?: string;
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
 *  The six boolean flags are mandatory (FR-011); previewer-owned shape/type/
 *  axis metadata and the optional `frontend_manifest` ride alongside them
 *  (the backend spreads `extra` into this object on the wire). */
export interface PreviewMetadata {
  sampled?: boolean;
  truncated?: boolean;
  cached?: boolean;
  derived?: boolean;
  complete?: boolean;
  failed?: boolean;
  /** Same-origin manifest a package/project previewer asks the host to mount.
   *  Absent for core fallbacks → the host renders the core viewer for `kind`. */
  frontend_manifest?: PreviewerManifest;
  /** Previewer-owned extra metadata (shape, dtype, axes, total_rows, ...). */
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
  /** First-class same-origin previewer manifest, framework-stamped by the
   *  session manager from the resolved PreviewerSpec (ADR-048 §4 / #1579).
   *  Absent for core fallbacks. Prefer this over `metadata.frontend_manifest`. */
  frontend_manifest?: PreviewerManifest | null;
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
 *  produced figure through the core PlotPreviewer. It is `null` when the run
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
