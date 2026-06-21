import type {
  BlockSchemaResponse,
  BlockSummary,
  PreviewEnvelope,
  GitBranch,
  GitCommit,
  GitHistoryFilter,
  GitStatus,
  LogEntry,
  PreviewTarget,
  ProjectResponse,
  ResolvedSubworkflowPorts,
  WorkflowEdge,
  WorkflowEventMessage,
  WorkflowNode,
  WorkflowResponse,
} from "../types/api";
import type { LineageRunDetail, LineageRunSummary } from "../types/lineage";
import type { BottomTab } from "../types/ui";

// Issue #1482: ``GitSlice`` and ``LineageSlice`` interfaces previously
// lived in their respective slice files and were re-imported here for
// the ``AppStore`` union. Sentrux flagged the resulting
// types ↔ gitSlice ↔ lineageSlice triangle as a cycle. The interfaces
// now live here next to every other slice type
// (ProjectSlice / WorkflowSlice / …); the slice files re-export them
// for any downstream consumer.

export interface ProjectDialogState {
  mode: "new" | "open";
  name: string;
  description: string;
  path: string;
}

export interface WorkflowHistoryEntry {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  description: string;
}

export type VersionedChangeSource =
  | "canvas"
  | "agent"
  | "gitRestore"
  | "import"
  | "external"
  | string;

export type VersionedEntityClass = "workflow" | "file";

export interface VersionConflictState {
  entityClass: VersionedEntityClass;
  entityId: string;
  kind: string;
  source: VersionedChangeSource | null;
  sourceId: string | null;
  baseVersion: number | null;
  pendingVersion: number | null;
  remoteVersion: number | null;
  detectedAt: string;
  message: string;
  remoteWorkflow?: WorkflowResponse | null;
  remoteContent?: string | null;
}

export interface ProjectSlice {
  currentProject: ProjectResponse | null;
  recentProjects: ProjectResponse[];
  projectDialogOpen: boolean;
  projectDialog: ProjectDialogState;
  setProjects: (projects: ProjectResponse[]) => void;
  setCurrentProject: (project: ProjectResponse | null) => void;
  openProjectDialog: (mode: "new" | "open", partial?: Partial<ProjectDialogState>) => void;
  closeProjectDialog: () => void;
  updateProjectDialog: (patch: Partial<ProjectDialogState>) => void;
}

export interface WorkflowSlice {
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;
  workflowVersion: string;
  workflowMetadata: Record<string, unknown>;
  workflowNodes: WorkflowNode[];
  workflowEdges: WorkflowEdge[];
  workflowDirty: boolean;
  workflowBaseVersion: number | null;
  workflowPendingVersion: number | null;
  workflowPendingSourceId: string | null;
  workflowConflict: VersionConflictState | null;
  workflowHistory: WorkflowHistoryEntry[];
  workflowFuture: WorkflowHistoryEntry[];
  setWorkflow: (workflow: WorkflowResponse | null) => void;
  setWorkflowName: (name: string) => void;
  addNode: (
    block: BlockSummary,
    position: { x: number; y: number },
    defaultParams?: Record<string, unknown>,
  ) => void;
  addAnnotationNode: (position: { x: number; y: number }) => void;
  updateNodeConfig: (nodeId: string, config: Record<string, unknown>) => void;
  /**
   * ADR-044 FR-011 / US5 + US6 — repoint a `subworkflow` / `subworkflow_broken`
   * node's referenced file by writing `config.ref.path` at the TOP level of the
   * node config (NOT under `config.params`, where `updateNodeConfig` merges). The
   * canvas (`buildSubWorkflowNode`) and the flattener read `config.ref.path`, so
   * the ref must live there. Marks the workflow dirty so the autosave persists it.
   */
  setNodeRef: (nodeId: string, refPath: string) => void;
  /**
   * ADR-044 FR-004 / US5 — set the response-only `resolved_ports` surface on a
   * subworkflow node so its exposed-port handles refresh immediately (un-break +
   * show `raw_in` / `report`) after an import or repoint, WITHOUT a workflow
   * reload. `resolved_ports` is never persisted, so this does NOT mark dirty and
   * does NOT push history.
   */
  setNodeResolvedPorts: (nodeId: string, resolvedPorts: ResolvedSubworkflowPorts) => void;
  updateNodeLayout: (nodeId: string, position: { x: number; y: number }) => void;
  updateNodeSize: (nodeId: string, size: { width: number; height: number }) => void;
  /**
   * ADR-050 §3.2 / FR-022 / FR-024 — apply many node layout positions in one
   * history entry. Writes ONLY `node.layout`; used by the tidy action.
   */
  updateNodeLayoutBatch: (positions: Record<string, { x: number; y: number }>) => void;
  connectNodes: (edge: WorkflowEdge) => void;
  removeNode: (nodeId: string) => void;
  removeEdge: (edge: WorkflowEdge) => void;
  setWorkflowDescription: (description: string) => void;
  markWorkflowSaved: () => void;
  beginWorkflowSave: (workflowId: string, sourceId: string) => void;
  confirmWorkflowVersion: (version: number, sourceId?: string | null) => void;
  markWorkflowRemoteConflict: (conflict: VersionConflictState) => void;
  clearWorkflowConflict: () => void;
  undoWorkflow: () => void;
  redoWorkflow: () => void;
}

/** #591/#594: Data for an interactive block prompt (DataRouter, PairEditor). */
export interface InteractivePrompt {
  blockId: string;
  blockType: string;
  data: Record<string, unknown>;
}

export interface ExecutionSlice {
  blockStates: Record<string, string>;
  blockOutputs: Record<string, Record<string, unknown>>;
  blockErrors: Record<string, string>;
  blockErrorSummaries: Record<string, string>;
  executionMessages: string[];
  logEntries: LogEntry[];
  /** True while a workflow execution is in progress. */
  isRunning: boolean;
  /** #591/#594: Active interactive prompt from a PAUSED block (DataRouter/PairEditor). */
  interactivePrompt: InteractivePrompt | null;
  consumeEvent: (event: WorkflowEventMessage) => void;
  appendLog: (entry: LogEntry) => void;
  resetExecution: () => void;
  setInteractivePrompt: (prompt: InteractivePrompt | null) => void;
}

/**
 * ADR-050 §3.1 — frontend-only focus-mode view state (FR-017/FR-018).
 *
 * This state is never persisted to workflow YAML and never mutates workflow
 * nodes/edges/config. `selectedIds` is the snapshot of the selection captured
 * when focus was entered; `depth` controls how many neighbor hops are kept
 * visible (1 = the spec default of immediate upstream/downstream neighbors).
 */
export interface FocusModeState {
  enabled: boolean;
  selectedIds: string[];
  depth: number;
}

export interface UISlice {
  selectedNodeId: string | null;
  activeBottomTab: BottomTab;
  /** ADR-050 §3.1 — focus-mode view state (frontend-only, not persisted). */
  focusMode: FocusModeState;
  paletteCollapsed: boolean;
  previewCollapsed: boolean;
  bottomPanelCollapsed: boolean;
  /**
   * When true, the bottom panel does not auto-collapse on canvas-pane
   * clicks. Toggled via the pin button in the BottomPanel tab strip.
   * Useful when the user is actively chatting in the AI Chat tab, working in
   * Terminal, and doesn't want a stray canvas click to fold the panel closed.
   */
  bottomPanelPinned: boolean;
  panelSizes: { palette: number; preview: number; bottom: number };
  minimapVisible: boolean;
  lastError: string | null;
  /** #793: count of unseen rows in the Logs panel since the user last viewed it. */
  unreadLogsCount: number;
  /**
   * ADR-034: monotonically increased whenever the file-system watcher
   * reports a project-tree-relevant change. ``ProjectTree`` subscribes to
   * this counter so external edits (e.g. ``write_workflow`` from the
   * embedded agent) trigger an auto-refresh without the user clicking
   * the Refresh button.
   */
  projectTreeRefreshCounter: number;
  setSelectedNodeId: (nodeId: string | null) => void;
  setActiveBottomTab: (tab: BottomTab) => void;
  /**
   * ADR-050 §3.1 — enter focus mode around the given selection. A no-op when
   * `selectedIds` is empty (focus mode is unavailable without a selection).
   */
  enterFocusMode: (selectedIds: string[], depth?: number) => void;
  /** ADR-050 §3.1 — exit focus mode and restore normal canvas visibility. */
  exitFocusMode: () => void;
  /** ADR-050 §3.1 — set the focus neighbor depth (expand/collapse controls). */
  setFocusDepth: (depth: number) => void;
  bumpUnreadLogs: () => void;
  bumpProjectTreeRefresh: () => void;
  togglePalette: () => void;
  togglePreview: () => void;
  toggleBottomPanel: () => void;
  toggleBottomPanelPinned: () => void;
  toggleMinimap: () => void;
  setPanelSize: (panel: "palette" | "preview" | "bottom", size: number) => void;
  setLastError: (message: string | null) => void;
}

export interface PreviewSlice {
  // ADR-048 SPEC 1 — routed session-envelope cache (FR-021). Keyed by the
  // composite key built from data/collection ref + previewer id + session id +
  // query (slice/page/sort/slot/item) + data version when available. Values
  // are UI-only; the backend stays authoritative for routing/sessions.
  previewEnvelopeCache: Record<string, PreviewEnvelope>;
  cachePreviewEnvelope: (key: string, envelope: PreviewEnvelope) => void;
  clearPreviewEnvelopeCache: () => void;
  /**
   * #1713 — the routed preview target produced by running a plot from the
   * dedicated Plots tab (`runPlotJob` → `plotTargetFromRunResponse`). The
   * plot list moved out of the Preview panel into its own bottom-panel tab,
   * so the Run action lives there while the result must still render in the
   * right-hand Preview panel (`DataPreview`). This shared slot is the only
   * cross-panel state needed to keep that behavior unchanged. `null` when no
   * plot result is being shown; cleared when the user selects a canvas node.
   */
  plotPreviewTarget: PreviewTarget | null;
  setPlotPreviewTarget: (target: PreviewTarget | null) => void;
}

export interface PaletteSlice {
  blocks: BlockSummary[];
  blockSchemas: Record<string, BlockSchemaResponse>;
  paletteSearch: string;
  setBlocks: (blocks: BlockSummary[]) => void;
  setBlockSchema: (schema: BlockSchemaResponse) => void;
  setPaletteSearch: (search: string) => void;
}

/**
 * ADR-034 Phase 1.3: one PTY-backed terminal tab.
 *
 * State machine:
 *   setup   — user picks provider + permission mode, no subprocess yet
 *   running — subprocess + WebSocket alive
 *   closed  — subprocess exited (real or synthesised after reload)
 *
 * On launch: provider + permissionMode are filled in.
 * On exit: state -> closed, exitCode set (-1 means synthesised after reload
 * because the PTY did not survive page unload).
 */
/**
 * ADR-035 §3.9 / §3.10 — block-tab status union.
 *
 * Tracks the lifecycle of an AI Block tab the engine spawned:
 *   - "running"   — agent process is alive, no completion signal yet
 *   - "paused"    — block is in PAUSED state (default after spawn);
 *                   the Mark-done escape-hatch button shows in this state
 *   - "done"      — completion signal received and outputs validated
 *   - "error"     — completion failed validation OR agent exited error
 *   - "cancelled" — user closed the tab while running OR workflow cancelled mid-block
 *
 * "cancelled" is a terminal state distinct from "error" so the UI can
 * distinguish user intent (the user closed the tab) from agent failure
 * (the agent crashed). Per ADR-035 §3.9, tabs survive done/error/cancelled
 * transitions and remain interactive.
 */
export type AiBlockStatus = "running" | "paused" | "done" | "error" | "cancelled";
export type TerminalProvider = "claude-code" | "codex" | "user-terminal";

export interface TerminalTab {
  id: string;
  title: string;
  provider: TerminalProvider | null;
  permissionMode: "safe" | "dangerous" | null;
  state: "setup" | "running" | "closed";
  exitCode?: number;
  errorMessage?: string;
  /**
   * ADR-035 §3.10 — origin of the tab.
   *   - "user"     (default) — user clicked the `+` button or Ctrl+T
   *   - "ai-block" — engine spawned the tab on behalf of an AI Block worker
   * Optional for backwards-compat with persisted tabs from before ADR-035.
   */
  source?: "user" | "ai-block";
  /**
   * ADR-035 §3.10 — id of the originating AI Block run (matches the
   * worker-side `RunDir.run_id`). Used by the Mark-done button to address
   * the right block when sending the `block_user_marked_done` WS message.
   */
  blockRunId?: string;
  /**
   * ADR-035 §3.9 — current status of the AI Block. Only meaningful when
   * `source === "ai-block"`.
   */
  blockStatus?: AiBlockStatus;
}

export interface TerminalTabsSlice {
  terminalTabs: TerminalTab[];
  activeTerminalTabId: string | null;
  /** Create a new tab in `setup` state and make it active. Returns its id. */
  addTerminalTab: () => string;
  /** Create a user shell tab backed by the desktop Python dependency env. */
  addUserTerminalTab: () => string;
  closeTerminalTab: (id: string) => void;
  renameTerminalTab: (id: string, title: string) => void;
  launchTerminalTab: (
    id: string,
    provider: TerminalProvider,
    permissionMode: "safe" | "dangerous",
  ) => void;
  markTerminalTabExited: (id: string, code: number) => void;
  markTerminalTabErrored: (id: string, message: string) => void;
  reopenTerminalTab: (id: string) => void;
  setActiveTerminalTab: (id: string) => void;
  /**
   * ADR-035 §3.10 — register an engine-initiated AI Block tab.
   *
   * Pre-allocates a `TerminalTab` with `source="ai-block"`, `state="running"`
   * (skipping the SetupScreen — the engine has already spawned the PTY),
   * `blockStatus="paused"` (the block is paused waiting for completion),
   * and makes it the active tab. Idempotent on `tabId` — calling twice with
   * the same id replaces the existing entry rather than duplicating it.
   */
  addAiBlockTerminalTab: (args: {
    tabId: string;
    title: string;
    blockRunId: string;
    permissionMode: "safe" | "dangerous";
  }) => void;
  /**
   * ADR-035 §3.9 — update the AI Block status for a tab. No-op if the tab
   * does not exist (engine may emit a `block_pty_closed` for a tab the
   * frontend never received the open event for, e.g. after a page reload).
   */
  updateAiBlockStatus: (tabId: string, status: AiBlockStatus) => void;
  /** Internal: replace the entire slice (used by tests + rehydration helper). */
  _replaceTerminalTabs: (tabs: TerminalTab[], activeId: string | null) => void;
}

/**
 * Per-tab snapshot of workflow + UI state.
 *
 * ADR-036 §3.10 (Phase 2A — I36a migration complete): ``TabState`` is now
 * the discriminated union ``WorkflowTab | FileTab`` and ``kind`` is a
 * required literal on each variant. All consumers (App.tsx, TabBar.tsx,
 * captureTab/restoreTab, useWebSocket.ts) type-guard on ``tab.kind ===
 * "workflow"`` before reading the workflow-specific fields.
 *
 * Loading state: file tabs that are still being fetched (e.g. on
 * rehydrate after a reload) carry ``loading: true`` until the GET
 * resolves. The CodeEditor component (Phase 2B, I36b) renders a
 * placeholder while ``loading`` is set.
 */

/** ADR-036 §3.10 — workflow (canvas) tab. */
export interface WorkflowTab {
  kind: "workflow";
  id: string;
  workflowId: string;
  workflowName: string;
  workflowDescription: string;
  workflowVersion: string;
  workflowMetadata: Record<string, unknown>;
  workflowNodes: WorkflowNode[];
  workflowEdges: WorkflowEdge[];
  workflowDirty: boolean;
  workflowBaseVersion?: number | null;
  workflowPendingVersion?: number | null;
  workflowPendingSourceId?: string | null;
  workflowConflict?: VersionConflictState | null;
  workflowHistory: WorkflowHistoryEntry[];
  workflowFuture: WorkflowHistoryEntry[];
  selectedNodeId: string | null;
}

/**
 * ADR-036 §3.10 — file (Monaco editor) tab.
 *
 * The id convention disambiguates editor sources:
 *   "file:<path>"           — user opened a file via ProjectTree double-click
 *   "source:<workflow_id>"  — read-only YAML source view of a workflow
 *
 * `contentLoadedAt` is retained for persisted-tab compatibility. ADR-045
 * conflict detection uses `baseVersion` / `pendingVersion` instead.
 */
export interface FileTab {
  /** ADR-036 §3.10 — discriminator. Always "file" for editor tabs. */
  kind: "file";
  id: string;
  filePath: string;
  displayName: string;
  language: "python" | "r" | "yaml" | "json" | "text" | "markdown";
  content: string;
  contentLoadedAt: number;
  baseVersion?: number | null;
  pendingVersion?: number | null;
  pendingSourceId?: string | null;
  conflict?: VersionConflictState | null;
  dirty: boolean;
  readOnly: boolean;
  /**
   * ADR-036 §3.11: true while a rehydrated file tab is being re-fetched
   * from the backend. The CodeEditor (Phase 2B) renders a placeholder
   * while loading; once the GET resolves, ``loading`` flips to false and
   * ``content`` is populated.
   */
  loading?: boolean;
}

/**
 * ADR-036 §3.10 — discriminated union of all tab kinds.
 *
 * Phase 2A (I36a) migration: ``TabState`` is now ``WorkflowTab | FileTab``.
 * ``AnyTab`` is retained as an alias for backward compatibility with any
 * code that imported it during the transition; new code should use
 * ``TabState`` directly.
 */
export type TabState = WorkflowTab | FileTab;
export type AnyTab = TabState;

export interface TabSlice {
  /** All open tabs (order = display order). */
  tabs: TabState[];
  /** ID of the currently active tab. */
  activeTabId: string | null;
  /**
   * Open (or switch to) a workflow in a tab.
   *
   * #796: ``displayName`` is an optional fallback used when ``workflow.id`` is
   * empty (e.g. a workflow YAML missing the ``id:`` field). Without it, the tab
   * label and top-left title render as a blank string.
   */
  openTab: (workflow: WorkflowResponse, displayName?: string) => void;
  /** Switch to an existing tab. */
  switchTab: (tabId: string) => void;
  /** Close a tab by ID. Returns true if closed, false if cancelled. */
  closeTab: (tabId: string) => boolean;
  /** Sync the active tab's snapshot from current workflow state. */
  syncActiveTab: () => void;
  /**
   * ADR-036 §3.10 — open (or focus) a file editor tab.
   *
   *   1. Compute id = ``opts?.readOnly ? "source:" + filePath : "file:" + filePath``.
   *   2. If a tab with that id exists, switch to it; return.
   *   3. Otherwise GET /api/projects/{id}/file?path=<filePath>, derive
   *      language from extension, build a FileTab, append to tabs, set active.
   */
  openFileTab: (filePath: string, opts?: { readOnly?: boolean }) => void;
  /**
   * ADR-036 §3.10 — save a file tab's content to disk.
   *
   *   1. Look up the tab by id.
   *   2. PUT /api/projects/{id}/file?path=<tab.filePath> with body
   *      ``{content: tab.content}``.
   *   3. On success, set ``tab.dirty = false`` and update
   *      ``contentLoadedAt`` from the response mtime.
   *   4. On 4xx/5xx, surface a toast and leave dirty=true.
   *   5. Read-only tabs are a no-op.
   */
  saveFileTab: (id: string) => Promise<void>;
  /**
   * ADR-036 §3.10 — update the in-memory content for a file tab.
   *
   *   1. Look up the tab by id.
   *   2. Set ``tab.content = content``, ``tab.dirty = true``.
   *   3. Auto-save debounce (800 ms) lives in the consumer (App.tsx),
   *      mirroring the canvas auto-save loop at App.tsx:478-487.
   *   4. Read-only tabs ignore updates (no-op).
   */
  updateFileTabContent: (id: string, content: string) => void;
  confirmFileVersion: (id: string, version: number, sourceId?: string | null) => void;
  applyFileRemoteContent: (
    id: string,
    response: { content: string; mtime: number; state_version?: number },
  ) => void;
  markFileRemoteConflict: (id: string, conflict: VersionConflictState) => void;
}

// ADR-039 §6 Phase 2 — git versioning slice (interfaces relocated here
// from gitSlice.ts per issue #1482 to break the store ↔ types triangle).

export interface GitMergeInProgress {
  source_branch: string;
  conflicted_files: string[];
}

export interface GitSlice {
  branches: GitBranch[] | null;
  currentBranch: string | null;
  logCache: Record<string, GitCommit[]>;
  logLoading: Record<string, boolean>;
  historyFilter: GitHistoryFilter;
  status: GitStatus | null;
  mergeInProgress: GitMergeInProgress | null;
  lastError: string | null;
  /**
   * ADR-039 Addendum 1 (#1354) — transient "safety auto-commit landed"
   * notice. Set by `switchBranch` / `restore` when the backend
   * response carries a non-null `auto_commit_sha`, consumed by
   * `BranchPicker` (toast on switch) and `RestoreWorkflowButton`
   * (inline hint on restore). Components clear it via
   * `setLastNotice(null)` after rendering, mirroring the
   * `lastError` lifecycle. Kept distinct from `lastError` so
   * downstream UI does not confuse "your change was committed
   * safely" with "something failed".
   */
  lastNotice: string | null;
  /**
   * ADR-039 §3.5 (#972 — Codex P1 on PR #974) — branch the user clicked
   * "Merge into current" on. Driving this from the slice (rather than
   * local Git-tab state) keeps the MergeFlow modal mounted at the
   * BottomPanel level so switching bottom tabs during an in-flight
   * conflict resolution does NOT tear it down and orphan the merge
   * (MergeFlow's close guard would otherwise be bypassed). `null` =
   * modal hidden.
   */
  mergeFlowSource: string | null;

  /**
   * Project ID active when `mergeFlowSource` was set (#975 Codex P1 on
   * PR #980). Used by the App-level `<AppLevelMergeFlow>` mount to
   * gate visibility: the modal renders only when the current open
   * project matches this id. Switching to a different project hides
   * the modal (state preserved); switching back re-shows it. Without
   * this gate, modal actions like `complete merge` / `abort merge`
   * would run against the wrong backend project context. `null` when
   * no merge is in flight.
   */
  mergeFlowProjectId: string | null;

  // Actions — D39-2.3b fills bodies.
  setHistoryFilter: (filter: GitHistoryFilter) => void;
  invalidateHistory: () => void;
  loadBranches: () => Promise<void>;
  loadLog: (branch?: string) => Promise<void>;
  loadStatus: () => Promise<void>;
  commit: (message: string, files?: string[]) => Promise<string>;
  switchBranch: (name: string) => Promise<{ auto_commit_sha: string | null }>;
  createBranch: (name: string, baseSha?: string) => Promise<void>;
  deleteBranch: (name: string, force?: boolean) => Promise<void>;
  restore: (
    commitSha: string,
    files?: string[],
  ) => Promise<{ status: "ok"; auto_commit_sha: string | null }>;
  setMergeInProgress: (state: GitMergeInProgress | null) => void;
  /**
   * Open or close MergeFlow. `source` is the branch being merged into
   * the current branch (or `null` to close). `projectId` is the
   * current open project's id — stamped here so the App-level mount
   * can gate visibility against project switches (#975 Codex P1 on
   * PR #980). Pass `null` for `projectId` when closing (`source=null`)
   * or when opening outside any project context (test fixtures).
   */
  setMergeFlowSource: (source: string | null, projectId?: string | null) => void;
  setLastError: (message: string | null) => void;
  setLastNotice: (message: string | null) => void;
}

// ADR-038 §3.8 — Lineage tab client state (interface relocated here from
// lineageSlice.ts per issue #1482).
export interface LineageSlice {
  // list pane
  runs: LineageRunSummary[];
  runsLoading: boolean;
  runsError: string | null;
  // detail pane
  selectedRunId: string | null;
  runDetails: Record<string, LineageRunDetail>;
  runDetailLoading: Record<string, boolean>;
  runDetailError: Record<string, string | null>;
  // per-block expansion (UI-only)
  expandedBlockExecutionIds: string[];
  // dialogs (UI-only)
  methodsDialogRunId: string | null;
  rerunDialogRunId: string | null;
  // actions
  fetchRuns: (opts?: { workflowId?: string; limit?: number }) => Promise<void>;
  fetchRunDetail: (runId: string) => Promise<void>;
  selectRun: (runId: string | null) => void;
  toggleBlockExecutionExpanded: (blockExecutionId: string) => void;
  openMethodsDialog: (runId: string) => void;
  closeMethodsDialog: () => void;
  openRerunDialog: (runId: string) => void;
  closeRerunDialog: () => void;
  clearLineage: () => void;
}

export type AppStore = ProjectSlice &
  WorkflowSlice &
  ExecutionSlice &
  UISlice &
  PreviewSlice &
  PaletteSlice &
  TabSlice &
  TerminalTabsSlice &
  // ADR-038 §3.8 — Lineage tab client state.
  LineageSlice &
  // ADR-039 §6 Phase 2 — git versioning slice.
  GitSlice;
