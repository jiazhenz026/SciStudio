import type { BlockSchemaResponse, BlockSummary, DataPreviewResponse, LogEntry, ProjectResponse, WorkflowEdge, WorkflowEventMessage, WorkflowNode, WorkflowResponse } from "../types/api";
import type { BottomTab } from "../types/ui";

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
  workflowHistory: WorkflowHistoryEntry[];
  workflowFuture: WorkflowHistoryEntry[];
  setWorkflow: (workflow: WorkflowResponse | null) => void;
  setWorkflowName: (name: string) => void;
  addNode: (block: BlockSummary, position: { x: number; y: number }, defaultParams?: Record<string, unknown>) => void;
  addAnnotationNode: (position: { x: number; y: number }) => void;
  addGroupNode: (position: { x: number; y: number }) => void;
  updateNodeConfig: (nodeId: string, config: Record<string, unknown>) => void;
  updateNodeLayout: (nodeId: string, position: { x: number; y: number }) => void;
  connectNodes: (edge: WorkflowEdge) => void;
  removeNode: (nodeId: string) => void;
  removeEdge: (edge: WorkflowEdge) => void;
  setWorkflowDescription: (description: string) => void;
  markWorkflowSaved: () => void;
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

export interface UISlice {
  selectedNodeId: string | null;
  activeBottomTab: BottomTab;
  paletteCollapsed: boolean;
  previewCollapsed: boolean;
  bottomPanelCollapsed: boolean;
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
  bumpUnreadLogs: () => void;
  bumpProjectTreeRefresh: () => void;
  togglePalette: () => void;
  togglePreview: () => void;
  toggleBottomPanel: () => void;
  toggleMinimap: () => void;
  setPanelSize: (panel: "palette" | "preview" | "bottom", size: number) => void;
  setLastError: (message: string | null) => void;
}

export interface PreviewSlice {
  previewCache: Record<string, DataPreviewResponse>;
  previewLoading: Record<string, boolean>;
  cachePreview: (payload: DataPreviewResponse) => void;
  setPreviewLoading: (ref: string, loading: boolean) => void;
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
export interface TerminalTab {
  id: string;
  title: string;
  provider: "claude-code" | "codex" | null;
  permissionMode: "safe" | "dangerous" | null;
  state: "setup" | "running" | "closed";
  exitCode?: number;
}

export interface TerminalTabsSlice {
  terminalTabs: TerminalTab[];
  activeTerminalTabId: string | null;
  /** Create a new tab in `setup` state and make it active. Returns its id. */
  addTerminalTab: () => string;
  closeTerminalTab: (id: string) => void;
  renameTerminalTab: (id: string, title: string) => void;
  launchTerminalTab: (
    id: string,
    provider: "claude-code" | "codex",
    permissionMode: "safe" | "dangerous",
  ) => void;
  markTerminalTabExited: (id: string, code: number) => void;
  reopenTerminalTab: (id: string) => void;
  setActiveTerminalTab: (id: string) => void;
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
 * `contentLoadedAt` stores the server `mtime` at the most recent fetch so
 * the implementation phase can detect "file changed externally" on save
 * (not implemented in skeleton).
 */
export interface FileTab {
  /** ADR-036 §3.10 — discriminator. Always "file" for editor tabs. */
  kind: "file";
  id: string;
  filePath: string;
  displayName: string;
  language: "python" | "yaml" | "json" | "text" | "markdown";
  content: string;
  contentLoadedAt: number;
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
   * SKELETON: throws. Phase 2A (I36a) implements:
   *   1. Compute id = ``opts?.readOnly ? "source:" + filePath : "file:" + filePath``.
   *   2. If a tab with that id exists, switch to it; return.
   *   3. Otherwise GET /api/projects/{id}/file?path=<filePath>, derive
   *      language from extension, build a FileTab, append to tabs, set active.
   *
   * Test plan:
   *   - opens new tab on first call
   *   - second call to same path focuses existing tab (no duplicate)
   *   - "source:" id used when ``opts.readOnly`` is true
   *   - sets ``language`` based on extension
   */
  openFileTab: (filePath: string, opts?: { readOnly?: boolean }) => void;
  /**
   * ADR-036 §3.10 — save a file tab's content to disk.
   *
   * SKELETON: throws. Phase 2A (I36a) implements:
   *   1. Look up the tab by id.
   *   2. PUT /api/projects/{id}/file?path=<tab.filePath> with body
   *      ``{content: tab.content}``.
   *   3. On success, set ``tab.dirty = false`` and update
   *      ``contentLoadedAt`` from the response mtime.
   *   4. On 4xx/5xx, surface a toast and leave dirty=true.
   *
   * Test plan:
   *   - happy path clears dirty and updates mtime
   *   - 413 surfaces a "file too large" toast
   *   - read-only tab is a no-op (or throws — TBD by I36a)
   */
  saveFileTab: (id: string) => Promise<void>;
  /**
   * ADR-036 §3.10 — update the in-memory content for a file tab.
   *
   * SKELETON: throws. Phase 2A (I36a) implements:
   *   1. Look up the tab by id.
   *   2. Set ``tab.content = content``, ``tab.dirty = true``.
   *   3. Auto-save debounce (800 ms) lives in the consumer (App.tsx),
   *      mirroring the canvas auto-save loop at App.tsx:478-487.
   *
   * Test plan:
   *   - flips dirty true on first edit
   *   - subsequent edits keep dirty true
   *   - read-only tab rejects updates (or no-ops — TBD by I36a)
   */
  updateFileTabContent: (id: string, content: string) => void;
}

export type AppStore = ProjectSlice &
  WorkflowSlice &
  ExecutionSlice &
  UISlice &
  PreviewSlice &
  PaletteSlice &
  TabSlice &
  TerminalTabsSlice;
