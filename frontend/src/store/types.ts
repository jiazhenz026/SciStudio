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

export interface TerminalTab {
  id: string;
  title: string;
  provider: "claude-code" | "codex" | null;
  permissionMode: "safe" | "dangerous" | null;
  state: "setup" | "running" | "closed";
  exitCode?: number;
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

/** Per-tab snapshot of workflow + UI state. */
export interface TabState {
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
}

export type AppStore = ProjectSlice &
  WorkflowSlice &
  ExecutionSlice &
  UISlice &
  PreviewSlice &
  PaletteSlice &
  TabSlice &
  TerminalTabsSlice;
