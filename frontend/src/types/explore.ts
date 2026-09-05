/**
 * ADR-054 spec 4 (T-001) — the Explore Session API and its WebSocket events.
 *
 * A sibling of `api.ts` rather than a section inside it, for the same reason
 * `lineage.ts` is one: the session surface is large enough on its own that
 * folding it into the shared response module puts that module over the
 * repository's file-size rule. `api.ts` re-exports everything here, so the
 * import path every consumer already uses is unchanged.
 */

/** How a session is opened (`OpenSessionRequest.source`). */
export type ExploreSessionSource =
  | "block_outputs"
  | "file"
  | "paused_run"
  | "notebook"
  | "packaged_block";

/** `POST /api/explore/sessions` body. */
export interface ExploreOpenSessionRequest {
  source: ExploreSessionSource;
  /** Required for `block_outputs` and `paused_run`; optional for `packaged_block`. */
  block_id?: string | null;
  /** Required for `paused_run`; optional for `block_outputs` and `packaged_block`. */
  run_id?: string | null;
  /** Required for `file` and `notebook`. */
  path?: string | null;
  /** Required for `packaged_block`. */
  block_name?: string | null;
  /** Notebook file stem; the backend defaults it per source. */
  name?: string | null;
}

/** One port of the run a session is bound to (`PortModel`). */
export interface ExplorePort {
  name: string;
  type_name: string;
  backend: string;
  path: string;
  format?: string | null;
}

/** The run a session is bound to (`BoundRunModel`). */
export interface ExploreBoundRun {
  run_id: string;
  block_id: string;
  opened_over: string;
  ports: ExplorePort[];
}

/** One notebook cell with the session's marks on it (`CellModel`). */
export interface ExploreCell {
  cell_id: string | null;
  cell_type: string;
  source: string;
  enabled: boolean;
  marks: string[];
}

/** An open session as every route that returns one reports it (`SessionModel`). */
export interface ExploreSessionResponse {
  session_id: string;
  notebook_path: string;
  has_kernel: boolean;
  needs_restart: boolean;
  current_cell: string | null;
  notebook_commit: string | null;
  bound_run: ExploreBoundRun | null;
  cells: ExploreCell[];
}

/** One row of the session list (`SessionListItem`). */
export interface ExploreSessionListItem {
  notebook_path: string;
  session_id: string | null;
  has_kernel: boolean;
  is_open: boolean;
  readable: boolean;
}

export interface ExploreSessionListResponse {
  sessions: ExploreSessionListItem[];
}

export interface ExploreCloseSessionResponse {
  session_id: string;
  notebook_path: string;
  branch_commit: string | null;
}

export interface ExploreCommitResponse {
  session_id: string;
  sha: string | null;
}

export interface ExploreCellsResponse {
  session_id: string;
  cells: ExploreCell[];
}

export interface ExploreWriteCellRequest {
  source: string;
}

export interface ExploreInsertCellRequest {
  source?: string;
  after?: string | null;
}

export interface ExploreEnabledRequest {
  enabled: boolean;
}

/** What produced a queued request (`RequestKind`). */
export type ExploreRequestKind = "cell" | "snippet";

/** Where a queued request is in its life (`RequestState`). */
export type ExploreRequestState = "queued" | "running" | "done" | "failed" | "cancelled";

/** One queued execution request (`RequestModel`). */
export interface ExploreRequest {
  request_id: string;
  cell_id: string;
  kind: ExploreRequestKind | string;
  state: ExploreRequestState | string;
  panel?: string | null;
}

/** What a run control enqueued — never more than it says it does (`RunResponse`). */
export interface ExploreRunResponse {
  session_id: string;
  requests: ExploreRequest[];
}

/**
 * Where a kernel handle is in its life (`scistudio.explore.kernel.KernelState`).
 *
 * The runtime never reports "needs restart" as a state: that is the separate
 * `needs_restart` flag, which is why `ExploreKernelDisplayState` in `ui.ts` is
 * a different, wider union than this wire type.
 */
export type ExploreKernelState = "not-started" | "starting" | "idle" | "busy" | "dead";

export interface ExploreKernelStateResponse {
  session_id: string;
  state: ExploreKernelState | string;
  pid: number | null;
  memory_bytes: number | null;
  needs_restart: boolean;
}

/** One dependency edge (`EdgeModel`). */
export interface ExploreEdge {
  reader: string;
  definer: string;
  name: string;
  origin: string;
}

/** A read no enabled cell above resolves (`UnresolvedReadModel`). */
export interface ExploreUnresolvedRead {
  cell_id: string;
  name: string;
}

/** The dependency graph over the enabled code cells (`GraphResponse`). */
export interface ExploreGraphResponse {
  session_id: string;
  cells: string[];
  edges: ExploreEdge[];
  unresolved_reads: ExploreUnresolvedRead[];
  unknown_binding_cells: string[];
  changed_sets: Record<string, string[]>;
}

/** Why a cell is marked out of order (`OutOfOrderReadModel`). */
export interface ExploreOutOfOrderRead {
  name: string;
  definer: string | null;
  last_binder: string | null;
}

/** One cell's marks and the reasons behind an out-of-order one (`CellMarksModel`). */
export interface ExploreCellMarks {
  cell_id: string;
  marks: string[];
  out_of_order_reads: ExploreOutOfOrderRead[];
}

/** Every marked cell and which cell last bound each name (`MarksResponse`). */
export interface ExploreMarksResponse {
  session_id: string;
  marks: ExploreCellMarks[];
  stale: string[];
  out_of_order: string[];
  never_run: string[];
  last_bound_by: Record<string, string>;
}

/** One name, its type as the kernel reports it, and whether it is bound (`BindingModel`). */
export interface ExploreBinding {
  name: string;
  exists_in_kernel: boolean;
  type_name?: string | null;
  native_type_name?: string | null;
  type_module?: string | null;
  summary?: string | null;
  last_bound_by?: string | null;
}

export interface ExploreBindingsResponse {
  session_id: string;
  has_kernel: boolean;
  bindings: ExploreBinding[];
}

export interface ExploreWindowRequest {
  name: string;
  query?: Record<string, unknown> | null;
}

export interface ExploreWindowResponse {
  session_id: string;
  name: string;
  envelope: Record<string, unknown>;
}

/** A snippet a panel emitted into the notebook (`EmitSnippetRequest`). */
export interface ExploreEmitSnippetRequest {
  source: string;
  panel: string;
  bound_names?: string[];
}

export interface ExploreEmitSnippetResponse {
  session_id: string;
  cell_id: string;
  request: ExploreRequest;
}

/** One row of the kernel list (`KernelListItem`). */
export interface ExploreKernelListItem {
  session_id: string;
  notebook_path: string;
  state: ExploreKernelState | string;
  pid: number | null;
  memory_bytes: number | null;
  python_executable: string;
  started_at: number | null;
}

export interface ExploreKernelListResponse {
  kernels: ExploreKernelListItem[];
}

/** One thing packaging found, with the cells it is about (`PackagingProblemModel`). */
export interface ExplorePackagingProblem {
  kind: string;
  message: string;
  cell_ids: string[];
  names: string[];
  /** `false` for a problem packaging resolves on the way past rather than refuses. */
  refuses: boolean;
}

/** One port the generated block would declare (`PackagedPortModel`). */
export interface ExplorePackagedPort {
  name: string;
  direction: string;
  data_type: string;
  extension: string;
  bound_name: string;
}

export interface ExplorePackagingCheckRequest {
  /** Port name to notebook variable, for a session opened over a file. */
  file_ports?: Record<string, string>;
}

/** The plan: the slice, the ports, and every refusal reason (`PackagingCheckResponse`). */
export interface ExplorePackagingCheckResponse {
  session_id: string;
  is_packageable: boolean;
  cells: string[];
  inputs: ExplorePackagedPort[];
  outputs: ExplorePackagedPort[];
  problems: ExplorePackagingProblem[];
}

export interface ExplorePackageRequest extends ExplorePackagingCheckRequest {
  block_name: string;
  /** "replay" or "ask". */
  on_new_input?: string;
}

export interface ExplorePackageResponse {
  session_id: string;
  block_name: string;
  class_name: string;
  declaration_path: string;
  notebook_path: string;
  notebook_commit: string;
  cells: string[];
  inputs: ExplorePackagedPort[];
  outputs: ExplorePackagedPort[];
  on_new_input: string;
  problems: ExplorePackagingProblem[];
}

/**
 * One kernel output, as `_output_payload` renders it — the `.ipynb` MIME
 * bundle plus the error triple. `output_type` is nbformat's own vocabulary
 * ("stream", "display_data", "execute_result", "error").
 */
export interface ExploreOutput {
  output_type: string;
  name?: string;
  text?: string;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  ename?: string;
  evalue?: string;
  traceback?: string[];
  execution_count?: number | null;
}

// -- the events (FR-033) ----------------------------------------------------

/**
 * The prefix `serialise_session_event` puts on every session event type so it
 * cannot collide with an engine event on the shared WebSocket hub.
 */
export const EXPLORE_EVENT_PREFIX = "explore.";

/** Every session event type, prefixed as it arrives on the wire. */
export const EXPLORE_EVENT_TYPES = [
  "explore.session_opened",
  "explore.session_closed",
  "explore.kernel_state",
  "explore.cell_state",
  "explore.cell_output",
  "explore.changed_names",
  "explore.analysis_updated",
  "explore.commit_recorded",
  "explore.packaged",
] as const;

export type ExploreEventType = (typeof EXPLORE_EVENT_TYPES)[number];

export interface ExploreSessionOpenedPayload {
  notebook_path: string;
  opened_over: string;
  run_id?: string | null;
}

export interface ExploreSessionClosedPayload {
  notebook_path: string;
  branch_commit?: string | null;
}

export interface ExploreKernelStatePayload {
  state: ExploreKernelState | string;
  pid?: number | null;
  memory_bytes?: number | null;
  needs_restart?: boolean;
}

/**
 * `cell_state` is published in three shapes by the runtime, which is why every
 * field is optional and none can be relied on:
 *
 *   - a run starting: `{cell_id, state: "running", out_of_order: [names]}`
 *   - a run ending:   `{cell_id, state: "idle", marks: {cellId: [mark]}}`
 *   - a restart:      `{reason: "kernel_restarted", marks: {...}}` — no cell id
 */
export interface ExploreCellStatePayload {
  cell_id?: string | null;
  state?: string | null;
  reason?: string | null;
  /** Complete cell-id to marks map; the runtime sends every marked cell. */
  marks?: Record<string, string[]>;
  /** Names read out of order by the cell that is starting. */
  out_of_order?: string[];
}

export interface ExploreCellOutputPayload {
  cell_id: string;
  status: string;
  execution_count?: number | null;
  outputs: ExploreOutput[];
}

export interface ExploreChangedNamesPayload {
  cell_id: string;
  changed: string[];
  unobservable: string[];
}

export interface ExploreAnalysisUpdatedPayload {
  reason: string;
  cell_id?: string | null;
}

export interface ExploreCommitRecordedPayload {
  sha: string | null;
  ref?: string | null;
  cell_id?: string | null;
  notebook_path?: string | null;
  error?: string | null;
}

export interface ExplorePackagedPayload {
  block_name: string;
  class_name: string;
  declaration_path: string;
  notebook_path: string;
  notebook_commit: string;
  cells: string[];
  on_new_input: string;
}

/**
 * One session event as it arrives on the shared WebSocket.
 *
 * `serialise_session_event` puts the session id at the top level rather than
 * inside `data`, which is why this is not a `WorkflowEventMessage`: that shape
 * carries `block_id` / `workflow_id` instead.
 */
export interface ExploreSessionEventMessage {
  type: string;
  session_id: string;
  data: Record<string, unknown>;
  timestamp: string;
}
