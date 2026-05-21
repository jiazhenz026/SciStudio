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

export type MetadataFidelityLevel =
  | "pixel_only"
  | "typed_meta"
  | "format_specific"
  | "lossless";

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

export interface DataPreviewResponse {
  ref: string;
  type_name: string;
  preview: Record<string, unknown>;
}

export interface DataPreviewQuery {
  /** 3-D image slider position (#899). */
  slice?: number;
  /** DataFrame page, 1-based. Clamped server-side. */
  page?: number;
  /** Rows per page. Capped server-side at 200. */
  pageSize?: number;
  /** Column name to sort by. Missing column → no sort applied. */
  sortBy?: string;
  /** Sort direction. Default ``asc``. */
  sortDir?: "asc" | "desc";
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

export interface TreeEntry {
  name: string;
  type: "file" | "directory";
  size?: number | null;
}

export interface TreeResponse {
  entries: TreeEntry[];
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
