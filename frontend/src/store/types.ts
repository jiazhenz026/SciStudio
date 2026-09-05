import type {
  BlockSchemaResponse,
  BlockSummary,
  ExploreBindingsResponse,
  ExploreBoundRun,
  ExploreCell,
  ExploreCommitRecordedPayload,
  ExploreEdge,
  ExploreGraphResponse,
  ExploreKernelListItem,
  ExploreMarksResponse,
  ExploreOutOfOrderRead,
  ExploreOutput,
  ExplorePackagedPayload,
  ExploreOpenSessionRequest,
  ExplorePackagingCheckResponse,
  ExploreRequest,
  ExploreSessionEventMessage,
  ExploreSessionResponse,
  ExploreUnresolvedRead,
  PanelDescriptorResponse,
  PreviewEnvelope,
  GitBranch,
  GitCommit,
  GitHistoryFilter,
  GitStatus,
  LogEntry,
  PreviewTarget,
  PanelChoice,
  PanelSpecSummary,
  ProjectResponse,
  ResolvedSubworkflowPorts,
  TypeSummary,
  UserLibraryTarget,
  WorkflowEdge,
  WorkflowEventMessage,
  WorkflowNode,
  WorkflowResponse,
} from "../types/api";
import type { DeclaredTypeColors } from "../config/typeColorMap";
import type {
  TutorialCatalogueResponse,
  TutorialSessionResponse,
  TutorialStartRequest,
} from "../lib/api/learningCenter";
import type { LineageRunDetail, LineageRunSummary } from "../types/lineage";
import type {
  BottomTab,
  ExploreCellMarkKind,
  ExploreCellRunState,
  ExploreKernelDisplayState,
  ExploreShellState,
  ExploreTabMode,
} from "../types/ui";

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

/**
 * How the user resolves a workflow version conflict surfaced by the canvas
 * conflict dialog (#1891):
 * - ``keepLocal``: keep the unsaved local edits and let autosave persist them,
 *   overwriting the remote write (now a user-chosen last-write-wins).
 * - ``loadRemote``: discard local edits and adopt the remote version as the
 *   new base.
 */
export type WorkflowConflictResolution = "keepLocal" | "loadRemote";

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

/**
 * ADR-053 Learning Center (#2057) — session view state, and nothing else.
 *
 * Spec §4.1 keeps every judgment on the backend, so this slice holds copies of
 * backend answers plus two facts about the panel itself. It replaced
 * `TutorialSlice`, whose eight hardcoded step ids and per-tutorial instance
 * fields were the frontend-as-judge assumption FR-001 removes.
 */
export interface LearningCenterSlice {
  learningCenterOpen: boolean;
  learningCenterCatalogue: TutorialCatalogueResponse | null;
  learningCenterSession: TutorialSessionResponse | null;
  learningCenterLoading: boolean;
  learningCenterError: string | null;
  /**
   * FR-086 — half of the toolbar dot's condition.
   *
   * Session-lifetime only, and deliberately so: it is a fact about this run of
   * the surface, not progress. Progress lives on the backend (FR-074), and a
   * persisted copy of anything tutorial-shaped is what FR-001 removed.
   */
  learningCenterFirstRunDismissed: boolean;
  /**
   * The start request the backend answered with 409 because another tutorial
   * is running. Held rather than discarded so the surface can say that one
   * tutorial runs at a time and offer to leave the current one — the spec's
   * edge case — and then retry this exact request.
   */
  learningCenterStartConflict: TutorialStartRequest | null;
  /**
   * FR-079 — whether the product should volunteer the work-import offer.
   *
   * The backend's answer held for rendering, never the frontend's own record
   * of what it has already shown. `GET /unlock` is the single place that knows
   * whether the offer is still owed.
   */
  learningCenterWorkImportOffer: boolean;
  /**
   * #2061 — why the last trigger press failed, or null.
   *
   * Held apart from `learningCenterError` because it belongs on the step card
   * beside the button that failed, and it clears the moment a session
   * response is adopted — a retry that worked, an advance, a leave.
   */
  learningCenterTriggerError: string | null;
  /**
   * #2135 — which of the last step's two endings the reader picked.
   *
   * `true` means finish and stay in the project; `false`, the default and
   * the behavior finishing has always had, means open the Learning Center
   * and close the project behind it. Held in the store rather than passed to
   * the continue call because the reaction to a finished session lives in
   * `useLearningCenter`, which never sees the click.
   */
  learningCenterStayOnFinish: boolean;
  setLearningCenterStayOnFinish: (stay: boolean) => void;
  openLearningCenter: () => void;
  /**
   * A page of the user guide the reader has asked for, or null (#2083).
   *
   * A field rather than a call because opening one is three things owned by
   * three places: the project has to close (App owns that), the Learning
   * Center has to show its reading tab (`LearningCenter` owns that), and the
   * browser has to load the page (`DocsBrowser` owns that). Each watches this
   * and does its own part; `DocsBrowser` clears it once the page is up.
   */
  pendingUserGuidePage: string | null;
  /** Ask for a user-guide page — from a `[text](doc:page)` run in a beat. */
  requestUserGuidePage: (path: string) => void;
  /** Called by whoever finally showed the page. */
  clearUserGuidePage: () => void;
  closeLearningCenter: () => void;
  setLearningCenterCatalogue: (catalogue: TutorialCatalogueResponse | null) => void;
  setLearningCenterSession: (session: TutorialSessionResponse | null) => void;
  setLearningCenterLoading: (loading: boolean) => void;
  setLearningCenterError: (error: string | null) => void;
  clearLearningCenterStartConflict: () => void;
  refreshLearningCenter: () => Promise<void>;
  refreshActiveTutorialSession: () => Promise<void>;
  /**
   * React to an engine event by asking the backend where the step stands.
   *
   * A no-op when no tutorial is running, and coalesced so a burst of
   * `workflow.changed` during a drag becomes one request plus one trailing
   * catch-up rather than a queue of them.
   */
  syncActiveTutorialSession: () => Promise<void>;
  startTutorial: (request: TutorialStartRequest) => Promise<void>;
  evaluateActiveTutorialStep: () => Promise<void>;
  continueActiveTutorialStep: () => Promise<void>;
  /** #2138 — go back to the step before this one. */
  backActiveTutorialStep: () => Promise<void>;
  /** #2061 — run the current step's user-triggered action. */
  triggerActiveTutorialStep: () => Promise<void>;
  /**
   * #2083 — report that a scripted reply has finished playing, landing the
   * files the replay held back. A no-op when nothing is pending.
   */
  settleActiveTutorialReplay: () => Promise<void>;
  reportTutorialUiEvent: (name: string, target?: string) => Promise<void>;
  leaveActiveTutorial: () => Promise<void>;
  /** Resolves to the directories the backend reports it deleted. */
  clearTutorialData: () => Promise<string[]>;
  checkWorkImportOffer: () => Promise<void>;
  dismissWorkImportOffer: () => Promise<void>;
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
  resolveWorkflowConflict: (resolution: WorkflowConflictResolution) => void;
  undoWorkflow: () => void;
  redoWorkflow: () => void;
}

/** ADR-051: descriptor for a block-owned interactive panel component. */
export interface PanelManifestDescriptor {
  panel_id: string;
  module_url?: string;
  export_name?: string;
  css?: string[];
  version?: string;
  api_version?: string;
}

/** #591/#594 + ADR-051: Data for an interactive block prompt (DataRouter, PairEditor). */
export interface InteractivePrompt {
  blockId: string;
  blockType: string;
  /**
   * ADR-051: the workflow id the prompt belongs to, carried by the prompt event.
   * Confirm/cancel MUST use this (not the store's active workflow id), so the
   * response is run-scoped to the right run even if the user switches tabs while
   * the prompt is open.
   */
  workflowId: string;
  /**
   * ADR-051: the block's panel manifest. Kept because it names the panel and
   * because the ADR-048 compatibility shim still reads its `module_url`; the
   * host no longer mounts from it (ADR-054 FR-007, FR-037).
   */
  panelManifest: PanelManifestDescriptor | null;
  /**
   * ADR-054 D-020 — the descriptor for the panel the *backend* resolved for
   * this block, carried on the `interactive_prompt` event as
   * `panel_descriptor`. A paused interactive block is mounted from this, on
   * exactly the terms a preview panel is: the frontend keeps no registry
   * mapping a panel id to a compiled React component (FR-037).
   *
   * `null` when the event did not carry one, which the host reports as the
   * backend defect it is — with Cancel still reachable, because a person must
   * never be stuck on a paused block with no exit (#2195).
   */
  panelDescriptor: PanelDescriptorResponse | null;
  /** ADR-051: the block-built, window-sized JSON view (nested, not spread). */
  panelPayload: Record<string, unknown>;
  /**
   * ADR-051 interaction memory: the generic input fingerprint for this run,
   * echoed by the engine so the frontend can persist it alongside the decision
   * when the user enables "remember and skip the dialog".
   */
  inputSignature: Record<string, string[]>;
  /** Full event-data envelope (back-compat). */
  data: Record<string, unknown>;
}

export interface ExecutionSlice {
  blockStates: Record<string, string>;
  /**
   * #1974 — epoch-ms instant at which each block entered the running state,
   * taken from the `block_running` event's engine timestamp. An entry exists
   * ONLY while the block is running (any later event for that block drops it),
   * so the node's elapsed counter vanishes when the run ends and no previous
   * run's duration is retained.
   */
  blockRunStartedAt: Record<string, number>;
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

/**
 * #1799 — which content the bottom Plots panel is showing. `null` = the normal
 * plot-card grid. `{ mode: "new" }` = the new-plot target picker. `{ mode:
 * "relink", plotId }` = the relink picker for an existing plot. The picker is
 * an in-place content mode of the Plots panel (no full-screen modal), so the
 * canvas stays visible above it for the hover/select → highlight + auto-center
 * interaction.
 */
export type PlotPickerState = { mode: "new" } | { mode: "relink"; plotId: string };

export interface UISlice {
  selectedNodeId: string | null;
  /**
   * #1799 — transient highlight target driven by the plot target picker (hover
   * or select a row). Distinct from `selectedNodeId` so hovering a picker row
   * does not change the Config/Preview selection. The canvas draws a ring on
   * this node and auto-centers it; plot cards bound to it also highlight.
   */
  highlightedNodeId: string | null;
  /** #1799 — bottom Plots panel content mode (cards vs. target picker). */
  plotPicker: PlotPickerState | null;
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
   * the Reload button.
   */
  projectTreeRefreshCounter: number;
  /** Fit-the-view requests raised by something that rewrote the graph. */
  canvasFitRequestCounter: number;
  /**
   * #9 — bumped on a ``blocks.reloaded`` WS event so the app re-fetches the
   * block catalog (palette summaries + per-block schemas) without a manual
   * palette reload.
   */
  blockCatalogRefreshCounter: number;
  setSelectedNodeId: (nodeId: string | null) => void;
  /** #1799 — set/clear the transient picker highlight target. */
  setHighlightedNodeId: (nodeId: string | null) => void;
  /**
   * #1799 — open the new-plot target picker in the bottom Plots panel: ensure
   * the panel is expanded, switch to the Plots tab, and enter picker mode.
   */
  openNewPlotPicker: () => void;
  /** #1799 — open the relink picker for an existing plot (panel already open). */
  openRelinkPlotPicker: (plotId: string) => void;
  /** #1799 — leave picker mode and return the Plots panel to the card grid. */
  closePlotPicker: () => void;
  setActiveBottomTab: (tab: BottomTab) => void;
  /**
   * ADR-053 spec 2 (#2001) — bring a bottom-panel tab into view.
   *
   * `setActiveBottomTab` alone is not enough when the panel is collapsed: the
   * work-import session would start, the tab would be created, and the user
   * would see nothing happen. This expands the panel and selects the tab in one
   * action, mirroring `openNewPlotPicker`'s existing treatment of the same
   * problem.
   */
  openBottomTab: (tab: BottomTab) => void;
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
  /**
   * Bumped when something other than the person rewrote the graph they are
   * looking at — a tutorial step writing a workflow file. The canvas keeps its
   * own pan and zoom, so a reader who dragged the view somewhere is left
   * staring at empty space while the nodes sit off screen. The canvas fits the
   * view to the graph when this changes.
   */
  bumpCanvasFitRequest: () => void;
  bumpBlockCatalogRefresh: () => void;
  togglePalette: () => void;
  togglePreview: () => void;
  toggleBottomPanel: () => void;
  toggleBottomPanelPinned: () => void;
  toggleMinimap: () => void;
  setPanelSize: (panel: "palette" | "preview" | "bottom", size: number) => void;
  setLastError: (message: string | null) => void;
  /**
   * Desktop application menu (desktop/menu.js) opens these dialogs from
   * outside the toolbar, so the open state lives in the store instead of
   * Toolbar-local useState. Not persisted: a reopened app never starts with a
   * dialog already up.
   */
  packageManagerOpen: boolean;
  /** See `packageManagerOpen`; the dialog mounts only while open. */
  bringInMyWorkOpen: boolean;
  setPackageManagerOpen: (open: boolean) => void;
  setBringInMyWorkOpen: (open: boolean) => void;
}

export interface PreviewSlice {
  // ADR-048 SPEC 1 — routed session-envelope cache (FR-021). Keyed by the
  // composite key built from data/collection ref + panel id + session id +
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
 * ADR-053 §7 — the registered data type catalogue.
 *
 * Separate from `PaletteSlice` because FR-027 makes the types listing
 * independent of the block listing: the Data types tab must not have to fetch
 * blocks to draw types, and refreshing types must not mean refreshing the
 * palette. Loading is driven by `store/useTypeCatalog.ts`.
 */
export interface TypesSlice {
  types: TypeSummary[];
  /** True once `GET /api/types/` has landed at least once. */
  typesLoaded: boolean;
  /**
   * FR-051 step 1 — `name → declared colors`, derived from `types` at set
   * time. `undefined` until the listing lands (FR-067), which the color
   * resolvers read as "declares nothing" and answer with the pre-ADR-053
   * fallback.
   */
  declaredTypeColors: DeclaredTypeColors | undefined;
  setTypes: (types: TypeSummary[]) => void;
}

/**
 * #2113 — the registered panel catalogue and the person's per-type
 * panel choices, one store-held copy each so the Panels tab, the
 * websocket invalidation, and the preview re-route all read the same answer.
 *
 * Same independence argument as {@link TypesSlice} (ADR-053 FR-027, applied
 * one tier over by #2095): the Panels tab must not have to fetch blocks
 * to draw panels. Loading is driven by `store/usePanelCatalog.ts`.
 */
export interface PanelCatalogSlice {
  panels: PanelSpecSummary[];
  /** True once `GET /api/panels` has landed at least once. */
  panelsLoaded: boolean;
  /** Registry discovery diagnostics reported alongside the listing (#2095). */
  panelDiagnostics: string[];
  panelChoices: PanelChoice[];
  /** True once `GET /api/panels/choices` has landed at least once. */
  panelChoicesLoaded: boolean;
  /**
   * Bumped on every choice mutation. `DataPreview` feeds it to `PreviewHost`
   * as the routing epoch so an open preview re-creates its session — and thus
   * re-routes through the new choice — instead of sitting on the envelope the
   * old choice produced.
   */
  panelChoiceVersion: number;
  /**
   * ADR-054 FR-030 — bumped when *some* panel's document changed but nothing
   * said which one: a registry rebuild, a package install, a branch switch.
   * Every mounted panel remounts, because any of them may be the one that
   * moved.
   */
  panelDocumentEpoch: number;
  /**
   * ADR-054 FR-030/FR-032 — per-panel-id reload counter, bumped when a file
   * inside one panel's directory changed and the event named it. Only that
   * panel's mounts remount, so saving one panel does not blink every other one
   * on screen.
   */
  panelDocumentVersions: Record<string, number>;
  setPanels: (panels: PanelSpecSummary[], diagnostics: string[]) => void;
  setPanelChoices: (choices: PanelChoice[]) => void;
  bumpPanelChoiceVersion: () => void;
  /**
   * Record that a panel's document changed on disk. `null` means "some panel
   * did"; a panel id means that one. Both are ordinary events rather than
   * derived state, which is why they are counters: a mount needs exactly one
   * new value per event, not a recomputed identity per render.
   */
  notePanelDocumentChanged: (panelId: string | null) => void;
}

/**
 * ADR-034 Phase 1.3: one PTY-backed terminal tab.
 *
 * State machine:
 *   setup   — user picks provider + permission mode, no subprocess yet
 *   running — subprocess + WebSocket alive
 *   closed  — subprocess exited (real or synthesized after reload)
 *
 * On launch: provider + permissionMode are filled in.
 * On exit: state -> closed, exitCode set (-1 means synthesized after reload
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

/**
 * ADR-034 FR-020 / FR-020a — the single frontend declaration of a provider key.
 *
 * Every consumer imports from here. `SetupScreen.parts/types.ts` re-exports
 * these names; nothing redeclares them.
 *
 * Agent provider keys (`claude-code`, `codex`, `kimi-code`, `qoder`, `qoder-cn`,
 * …) are deliberately NOT a hand-maintained TypeScript literal union. The
 * backend provider registry is the only place the supported set is declared; a
 * literal union here would have to be edited for every new provider, which
 * reintroduces exactly the duplication FR-001 removes and breaks the
 * registry-only extension path of User Story 7 (ADR-034 §4.1). Agent keys are
 * therefore opaque strings, validated at runtime against the
 * `GET /api/ai/status` payload — see `isKnownAgentProvider`. The accepted
 * tradeoff, recorded in the spec, is that agent keys lose compile-time
 * exhaustiveness checking in TypeScript.
 *
 * For the same reason there is no frontend label map: display labels arrive on
 * the status payload as `ProviderStatus.label` (FR-020b).
 *
 * `user-terminal` is the one exception and keeps a named literal type, because
 * the frontend branches on it to route between the chat surface and the
 * terminal surface. Branch sites compare against `USER_TERMINAL_PROVIDER` (or
 * call `isUserTerminalProvider`) so a misspelling is a compile error rather
 * than a silently dead branch.
 */
export const USER_TERMINAL_PROVIDER = "user-terminal";

/** The pseudo-provider the frontend branches on for surface routing. */
export type UserTerminalProvider = typeof USER_TERMINAL_PROVIDER;

/**
 * An agent provider key. Opaque by design (FR-020a) — validate at runtime with
 * `isKnownAgentProvider` against the status payload rather than reaching for a
 * literal union.
 */
export type AgentProviderKey = string;

/** Any provider key a terminal tab can carry: an agent key or `user-terminal`. */
export type TerminalProvider = UserTerminalProvider | AgentProviderKey;

/**
 * ADR-034 FR-020b — a single `GET /api/ai/status` entry.
 *
 * The backend emits one entry per agent provider, in registry order.
 * `user-terminal` is not an agent provider and never appears here.
 */
export interface ProviderStatus {
  name: TerminalProvider;
  available: boolean;
  version: string | null;
  logged_in: boolean;
  /** Backend-supplied display label. The frontend never maps keys to labels. */
  label: string;
}

export interface AiStatusResponse {
  providers: ProviderStatus[];
}

/** Type guard for the `user-terminal` pseudo-provider. */
export function isUserTerminalProvider(value: unknown): value is UserTerminalProvider {
  return value === USER_TERMINAL_PROVIDER;
}

/**
 * Shape validation for a provider key that arrived over the wire.
 *
 * Used where no status payload is on hand (e.g. the `block_pty_opened` frame).
 * A key that fails this check is an error at the call site — never a reason to
 * substitute a default provider (FR-020c).
 */
export function isTerminalProviderKey(value: unknown): value is TerminalProvider {
  return typeof value === "string" && value.length > 0;
}

/**
 * ADR-034 FR-020a — runtime membership validation of an agent provider key
 * against the `GET /api/ai/status` payload.
 *
 * This is the replacement for the literal union: the authoritative set of agent
 * keys is whatever the backend registry reported, so adding a provider needs no
 * frontend edit. `user-terminal` is rejected because it is not an agent
 * provider and is never listed by the status endpoint.
 */
export function isKnownAgentProvider(
  value: unknown,
  providers: readonly Pick<ProviderStatus, "name">[] | null | undefined,
): value is AgentProviderKey {
  if (!isTerminalProviderKey(value) || isUserTerminalProvider(value)) return false;
  return (providers ?? []).some((p) => p.name === value);
}

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
   *   - "user"            (default) — user clicked the `+` button or Ctrl+T
   *   - "ai-block"        — engine spawned the tab on behalf of an AI Block worker
   *   - "tutorial-replay" — the Learning Center adopted a scripted replay tab
   *     (ADR-053 FR-061a, #2083). Distinct from "ai-block" so it carries no
   *     Mark-done or block-cancel affordances, and distinct from "user" so the
   *     replay lifecycle (torn down with the tutorial session) is recognizable.
   * Optional for backwards-compat with persisted tabs from before ADR-035.
   */
  source?: "user" | "ai-block" | "tutorial-replay";
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
    /**
     * ADR-034 FR-020c / FR-022 — the provider the engine actually spawned,
     * forwarded from the `block_pty_opened` frame. Required: the store must
     * never guess or default a provider onto an engine-initiated tab.
     */
    provider: TerminalProvider;
  }) => void;
  /**
   * ADR-053 spec 2 (#2001) / FR-022, FR-025 — attach a Bring In My Work
   * session tab.
   *
   * `POST /api/work-import/sessions` has already composed the brief, written it
   * to disk in full, and spawned the PTY (FR-024) by the time this is called,
   * so the tab goes straight to `running`: there is no SetupScreen to show and
   * no second launch to perform. Mounting it opens
   * `WS /api/ai/pty/{tabId}` with the existing query parameters, which joins
   * the already-spawned session rather than starting another one.
   *
   * `source` stays `"user"` on purpose. FR-025 requires an ORDINARY chat
   * session the user can talk to, redirect, and end like any other — an
   * `"ai-block"` tab would carry a Mark-done affordance and block-run cancel
   * semantics that have no meaning here.
   *
   * Idempotent on `tabId`, matching `addAiBlockTerminalTab`.
   */
  addWorkImportTerminalTab: (args: {
    tabId: string;
    title: string;
    /** ADR-034 FR-020c — the provider the backend actually spawned. Never defaulted. */
    provider: TerminalProvider;
    permissionMode: "safe" | "dangerous";
  }) => void;
  /**
   * ADR-053 FR-061a (#2083) — adopt a tutorial replay tab.
   *
   * The tutorial runtime opened a scripted PTY-shaped byte source and named
   * its tab id in the session response (`session.replay.tab_id`); mounting
   * the tab opens `WS /api/ai/pty/{tabId}`, which joins that prespawned
   * session exactly as a Bring In My Work tab joins its own. The provider is
   * the `user-terminal` pseudo-provider: it is a valid WebSocket query value,
   * and the join branch never spawns it because the scripted session is
   * already registered under the tab id. The replay discards keystrokes on
   * the backend (FR-061a), so the tab is a real tab that ignores typing.
   *
   * Idempotent on `tabId`, matching the other two adopters.
   */
  adoptTutorialReplayTab: (args: { tabId: string; title: string }) => void;
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
  /**
   * ADR-044 — tab dedup identity. Defaults to `workflowId`, so normal opens
   * (project tree, load-by-id, new workflow) dedup exactly as before. A
   * subworkflow opened by double-click passes its project-relative `ref.path`,
   * so each referenced copy gets its own tab even though several copies share
   * the same internal `workflow.id` (which would otherwise collide into one
   * tab). `workflowId` is unchanged, so save/run keep using the real id.
   */
  tabKey?: string;
  /**
   * ADR-044 — run-scope prefix when this tab is the expanded child of a
   * subworkflow node. At run start the parser flattens each subworkflow, so its
   * inner blocks emit status/output events keyed `<parentNodeId>__<innerId>`
   * (composed for nesting). A child tab opened by double-clicking a subworkflow
   * node carries the parent's prefix so the canvas can map each inner node to
   * its flattened run id. Absent/`""` for a top-level workflow opened directly.
   */
  runPrefix?: string;
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
  language: "python" | "r" | "yaml" | "json" | "text" | "markdown" | "html";
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
  /**
   * #1758: set when this is a read-only "View source" tab for a registered
   * block type (core / package / custom). Its ``content`` comes from
   * ``GET /api/blocks/{blockType}/source`` rather than a project file, so the
   * tab is not persisted across reload (see ``partializeTabs``).
   */
  blockSourceType?: string;
  /**
   * ADR-053 FR-032 — set when this tab edits a file in the user-wide library
   * (``~/.scistudio/blocks`` or ``~/.scistudio/types``) rather than a project
   * file.
   *
   * The new-file flow may write into either destination (FR-030), and FR-032
   * requires the created file to open **for editing** in both cases — so the
   * tab needs to know which door to read and write through. ``filePath`` holds
   * the absolute library path for display; the target plus the basename is
   * what the endpoint takes. Like a block-source tab, it is not persisted
   * across reload (see ``partializeTabs``): it lives outside every project, so
   * the project-file rehydrate path cannot restore it.
   */
  userLibraryTarget?: UserLibraryTarget;
  /**
   * ADR-054 T-010 — set when this tab edits a *panel's* entry document
   * (FR-024, FR-025). Holds the panel id, which is the only address the
   * editing routes take.
   *
   * Editable for every tier, and that is the point rather than an oversight:
   * FR-025 says the system is never asked where a save goes, and FR-026 says a
   * save to a core or package panel copies it into the open project under the
   * same id. Making a core panel's tab read-only would remove the one action
   * that performs the copy — SC-004's "copy a built-in panel into a project,
   * edit, save" would have no affordance at all.
   *
   * Not persisted across reload (see ``partializeTabs``): a panel directory is
   * addressed by panel id rather than by project path, so the project-file
   * rehydrate path cannot restore it — the same reason a block-source tab and
   * a library tab are excluded.
   */
  panelSourceId?: string;
}

/**
 * #2112 — transient preview tab.
 *
 * Opened by the DataPreview panel's maximize button: instead of restyling the
 * right-sidebar preview into a floating overlay, the frozen {@link PreviewTarget}
 * (a snapshot taken at click time) opens as a tab beside the file/workflow tabs
 * and renders through the same `PreviewHost`.
 *
 * The tab is deliberately ephemeral:
 *   - it is removed from `tabs` the moment focus moves to any other tab
 *     (see `dropInactivePreviewTabs` in `tabHelpers.ts`);
 *   - it carries no dirty state, so `closeTab` never prompts;
 *   - it is never persisted (the `partialize` whitelist keeps file tabs only).
 *
 * The id convention is `preview:<ref>` so re-maximizing the same target
 * focuses the existing tab instead of piling up duplicates (mirrors
 * `openFileTab`'s id-keyed dedup).
 */
/**
 * How a data-tree file was opened, so the preview tab can say which type it
 * chose and offer to change it (#2112). Absent on tabs opened by maximizing
 * the sidebar preview, which have no file path behind them.
 */
export interface PreviewTabOpenAs {
  /** Project-relative path the tab was opened from. */
  path: string;
  /** Normalized extension the remembered choice is keyed on (".tif"). */
  extension: string;
  /** The type the file was recorded as. */
  typeName: string;
  /** Whether that type is the project's remembered choice for the extension. */
  remembered: boolean;
}

export interface PreviewTab {
  /** Discriminator. Always "preview". */
  kind: "preview";
  id: string;
  /** Frozen preview target captured when the tab was opened. */
  target: PreviewTarget;
  displayName: string;
  /** Set when the tab came from a Data-tree double-click (#2112). */
  openAs?: PreviewTabOpenAs;
  /**
   * Collection targets carry their item snapshot through the session query
   * (see `refEntries.ts`), so the initial query must freeze alongside the
   * target; a bare ref would resolve to an empty collection.
   */
  initialQuery?: Record<string, unknown>;
  /** Epoch-ms open time; diagnostic only. */
  openedAt?: number;
}

/**
 * ADR-036 §3.10 — discriminated union of all tab kinds.
 *
 * Phase 2A (I36a) migration: ``TabState`` is now ``WorkflowTab | FileTab``.
 * ``AnyTab`` is retained as an alias for backward compatibility with any
 * code that imported it during the transition; new code should use
 * ``TabState`` directly.
 */
// ADR-054 FR-001 — the Explore member joins the union. Every existing
// consumer type-guards on `tab.kind`, so widening it here is what makes the
// centre switch and the right-column condition in `ProjectWorkspace` legal.
export type TabState = WorkflowTab | FileTab | PreviewTab | ExploreTab;
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
  openTab: (
    workflow: WorkflowResponse,
    displayName?: string,
    runPrefix?: string,
    tabKey?: string,
  ) => void;
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
   * #1758 — open a read-only tab showing a registered block's source code
   * (core / package / custom). Fetches ``GET /api/blocks/{blockType}/source``
   * and renders the returned source inline (the file lives outside the
   * project, so it cannot use the project-file fetch path).
   */
  openBlockSourceTab: (blockType: string) => void;
  /**
   * ADR-053 FR-068 — open a read-only tab on a core or packaged type's source.
   *
   * Reads ``GET /api/types/{type_name}/source``. Read-only structurally: that
   * response carries an absolute path and no save route accepts one. A project
   * or user-library type is opened through `openFileTab` /
   * `openUserLibraryFileTab` instead, which produce genuinely editable tabs.
   */
  openTypeSourceTab: (typeName: string) => void;
  /**
   * ADR-053 FR-032 — open (or focus) an editable tab on a user-library file.
   *
   * The library sits outside every project root, so the project-file fetch
   * path cannot reach it; this reads ``GET /api/user-library/file`` and saves
   * through the matching PUT. Used by the new-file flow when the user chose
   * the library destination (FR-029/FR-030) — without it, choosing the library
   * would write a template the user could not then edit.
   */
  openUserLibraryFileTab: (target: UserLibraryTarget, filename: string) => void;
  /**
   * ADR-054 FR-024, FR-025 — open (or focus) an editable tab on a panel's
   * entry document, whichever tier the panel resolved from.
   *
   * Reads ``GET /api/panels/{panel_id}/source`` and saves through the matching
   * PUT. Editable for every tier because that is what FR-026 asks of a save on
   * a read-only panel: it copies the panel into the open project under the same
   * id and writes the copy. Nothing here asks the person where it should go.
   */
  openPanelSourceTab: (panelId: string) => void;
  /**
   * #2112 — open (or focus) a transient preview tab on a frozen
   * {@link PreviewTarget}.
   *
   * Opened by the DataPreview maximize button. De-duplicates on the tab id
   * (``preview:<ref>``): re-maximizing the same ref focuses the existing tab.
   * The tab is removed as soon as any other tab becomes active, carries no
   * dirty state, and is never persisted.
   */
  openPreviewTab: (
    target: PreviewTarget,
    displayName?: string,
    initialQuery?: Record<string, unknown>,
    openAs?: PreviewTabOpenAs,
  ) => void;
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
  /**
   * ADR-054 FR-001 / FR-002 — open a session and put it in an Explore tab.
   *
   * Asynchronous because the tab's identity is the session's notebook path,
   * and only `POST /api/explore/sessions` knows it. Resolves with the tab that
   * is now active, whether it was created or activated; rejects with the
   * backend's refusal, which the caller shows (a block with no outputs, a
   * packaged block that is not one).
   */
  openExploreTab: (
    request: ExploreOpenSessionRequest,
    options?: {
      mode?: ExploreTabMode;
      pauseNodeId?: string | null;
      displayName?: string;
    },
  ) => Promise<ExploreTab | null>;
  /**
   * ADR-054 FR-001 — re-fetch a rehydrated Explore tab's session state.
   *
   * A persisted tab comes back with its notebook path and no session id; this
   * reopens the notebook and binds the tab to the session it gets.
   */
  restoreExploreTab: (notebookPath: string) => Promise<void>;
  /** ADR-054 FR-026 — show or hide the notebook pane of a pause tab. */
  setExploreNotebookVisible: (tabId: string, visible: boolean) => void;
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
  /**
   * Keys whose last load failed, so the auto-fetch guards stop asking.
   *
   * `GitHistoryList` and `useGraphData` both auto-fetch on
   * `commits === null && !loading`. A failed load leaves the cache undefined
   * and clears the loading flag, so that guard reads "never attempted" and the
   * `set()` that recorded the failure re-renders the consumer, which asks
   * again. Deleting the open project — which is what clearing tutorial data
   * does — turned that into 159,353 requests and a frozen window.
   *
   * Cleared by `invalidateHistory`, so anything that genuinely changes git
   * state retries, and bypassed by an explicit refresh.
   */
  logFailed: Record<string, boolean>;
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
  loadLog: (branch?: string, options?: { force?: boolean }) => Promise<void>;
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
  // ADR-038 Addendum 1 (#2033): `rerunDialogRunId` / `openRerunDialog` /
  // `closeRerunDialog` are gone with the Re-run affordance. The restore
  // dialog is owned locally by whichever tab opened it, so it needs no
  // store state.
  // actions
  fetchRuns: (opts?: { workflowId?: string; limit?: number }) => Promise<void>;
  fetchRunDetail: (runId: string) => Promise<void>;
  selectRun: (runId: string | null) => void;
  toggleBlockExecutionExpanded: (blockExecutionId: string) => void;
  openMethodsDialog: (runId: string) => void;
  closeMethodsDialog: () => void;
  clearLineage: () => void;
}

// ---------------------------------------------------------------------------
// ADR-054 spec 4 (T-001) — the Explore tab and the session slice.
//
// The Key Entities of `docs/specs/adr-054-explore-frontend.md` §3, named as
// the spec names them because three sibling components code against them:
// `ExploreTab`, `ExploreSliceState`, `CellView`, `VariableEntry`, `PanelSlot`.
//
// FR-034 is the rule that shapes all of it: **nothing here is derived**. Every
// mark, kernel state and binding is copied out of a runtime event or a route
// response. There is no local computation of a mark, no optimistic advance of
// a cell out of `queued`, and no place a command's effect is recorded before
// its event arrives.
// ---------------------------------------------------------------------------

/**
 * ADR-054 FR-001 — the Explore member of the centre-area tab union.
 *
 * Keyed by the session's **notebook path**, not by its session id: a session
 * that is closed and reopened is the same notebook to the person, and the
 * existing id-keyed dedup in `switchTab` then serves FR-001's "opening a
 * session whose tab exists activates that tab" for free.
 *
 * Persisted like a file tab (see `partializeTabs` in `store/index.ts`), which
 * is why `sessionId` is nullable: a rehydrated tab carries the path only, and
 * the shell re-fetches its session state on mount.
 */
export interface ExploreTab {
  /** Discriminator. Always "explore". */
  kind: "explore";
  /** `explore:<notebookPath>` — the dedup identity of FR-001. */
  id: string;
  /** Project-relative notebook path; the slice key and the tab key. */
  notebookPath: string;
  /** The open session's id, or `null` before the open lands / after a reload. */
  sessionId: string | null;
  /** Tab label. The notebook's basename unless the opener supplied one. */
  displayName: string;
  /** FR-024 — `"pause"` renders the same host with no notebook pane. */
  mode: ExploreTabMode;
  /** The run the session is bound to, when it was opened over one. */
  boundRunId: string | null;
  /** The paused block's node id, in pause mode. */
  pauseNodeId: string | null;
  /**
   * FR-026 — whether the notebook pane is shown. `true` for a session tab;
   * `false` for a pause tab until the person opens a notebook over the same
   * inputs.
   */
  notebookVisible: boolean;
  /**
   * FR-001 — set on a rehydrated tab so the shell knows to re-fetch rather
   * than render an empty session as an empty notebook.
   */
  restoring?: boolean;
  /** Epoch-ms open time; diagnostic only. */
  openedAt?: number;
}

/**
 * One cell as rendered (spec §3 `CellView`).
 *
 * `marks` and `outOfOrderReads` are copied verbatim from the runtime; the
 * shell draws them and never computes them (FR-012, FR-034).
 */
export interface CellView {
  cellId: string;
  cellType: string;
  source: string;
  enabled: boolean;
  /** From `explore.cell_output`; empty until a run reports outputs. */
  outputs: ExploreOutput[];
  /** From `CellModel.marks` and the `marks` map on `explore.cell_state`. */
  marks: ExploreCellMarkKind[];
  /** From `MarksResponse`, or the `out_of_order` names on a starting run. */
  outOfOrderReads: ExploreOutOfOrderRead[];
  /** From `explore.cell_state` / `explore.cell_output` only (FR-034). */
  runState: ExploreCellRunState;
  executionCount: number | null;
  /** Names the last run of this cell changed, from `explore.changed_names`. */
  changedNames: string[];
  /**
   * ISO timestamp of the most recent event applied to this cell.
   *
   * This is what makes FR-033's ordering requirement true rather than hoped
   * for: two events for one cell can arrive in either order, and the later
   * timestamp wins whichever arrives second.
   */
  lastEventAt: string | null;
}

/**
 * One strip item (spec §3 `VariableEntry`).
 *
 * Derived from the bindings response and the analysis event — which is the
 * only sense in which anything here is derived: the *values* are the
 * runtime's, and `live` is `exists_in_kernel` copied, never guessed.
 */
export interface VariableEntry {
  name: string;
  /** The SciStudio type a packaged port would carry, when the kernel holds it. */
  typeName: string | null;
  /** `type(value).__name__`, when the kernel holds it. */
  nativeTypeName: string | null;
  summary: string | null;
  /** `BindingModel.exists_in_kernel`. A name that is not live is greyed. */
  live: boolean;
  /** FR-020 — a declared output pins itself when it becomes live. */
  pinned: boolean;
  /** The panel mounted for this name, when one is. */
  openPanelId: string | null;
  lastBoundBy: string | null;
}

/** One mounted panel in the centre (spec §3 `PanelSlot`). */
export interface PanelSlot {
  panelId: string;
  boundName: string;
  pinned: boolean;
  /** FR-023 — submissions are refused while a run changes the bound name. */
  frozen: boolean;
}

/** The dependency graph as the slice holds it, for FR-032's view. */
export interface ExploreGraphState {
  cells: string[];
  edges: ExploreEdge[];
  unresolvedReads: ExploreUnresolvedRead[];
  unknownBindingCells: string[];
  changedSets: Record<string, string[]>;
}

/** The kernel as the slice holds it, written only from events and responses. */
export interface ExploreKernelView {
  state: ExploreKernelDisplayState;
  pid: number | null;
  memoryBytes: number | null;
  needsRestart: boolean;
  /** Timestamp of the last kernel event applied, for the same ordering rule. */
  lastEventAt: string | null;
}

/** One session's whole state, keyed in the slice by its notebook path. */
export interface ExploreSessionState {
  sessionId: string;
  notebookPath: string;
  shellState: ExploreShellState;
  /** The refusal that failed the open or restore, when `shellState` is failed. */
  error: string | null;
  boundRun: ExploreBoundRun | null;
  openedOver: string | null;
  notebookCommit: string | null;
  currentCell: string | null;
  cells: CellView[];
  kernel: ExploreKernelView;
  bindings: VariableEntry[];
  /** FR-020 — the names pinned, kept beside `bindings` so a pin survives a
   *  bindings refresh that drops the name for a moment. */
  pinnedNames: string[];
  panels: PanelSlot[];
  graph: ExploreGraphState | null;
  /** FR-028 — the last packaging check report rendered for this session. */
  lastReport: ExplorePackagingCheckResponse | null;
  /** The last `explore.commit_recorded` payload. */
  lastCommit: ExploreCommitRecordedPayload | null;
  /** The last `explore.packaged` payload; FR-029's palette refresh reads it. */
  lastPackaged: ExplorePackagedPayload | null;
  /** Names the runtime said it could not observe on the last run. */
  unobservableNames: string[];
  /** The reason of the last `explore.analysis_updated`, for the graph view. */
  lastAnalysisReason: string | null;
  /**
   * Timestamp of the last whole-session marks map applied from an event.
   *
   * Marks arrive as one complete map rather than per cell, so the per-cell
   * `lastEventAt` cannot order them; this is the guard that makes two
   * `cell_state` events converge on the later map whichever order they land in.
   * A marks *response* resets it to `null`, because a response is a fresh read
   * and anything after it should win.
   */
  lastMarksAt: string | null;
}

/**
 * The store slice (spec §3 `ExploreSliceState`).
 *
 * `sessions` is keyed by notebook path, as the spec says. Events are keyed by
 * *session id*, so `sessionPathById` is the index that joins the two, and
 * `pendingEvents` holds the events that arrive for a session id the slice has
 * not been told the path of yet — which is not a theoretical case: the
 * `session_opened` event is published inside the open call, so it can reach
 * the socket before the POST response reaches the caller.
 */
export interface ExploreSliceState {
  sessions: Record<string, ExploreSessionState>;
  sessionPathById: Record<string, string>;
  /** FR-015 — every live kernel in the project, from `listExploreKernels`. */
  exploreKernels: ExploreKernelListItem[];
  /** Session id to buffered events, drained when the session becomes known. */
  pendingExploreEvents: Record<string, ExploreSessionEventMessage[]>;
}

export interface ExploreSlice extends ExploreSliceState {
  /**
   * Write a session from a route response (`SessionModel`).
   *
   * Idempotent: applying the same response twice leaves the same state, and
   * applying it after events have already landed keeps the events' cell run
   * states rather than resetting them, because the response says nothing
   * about a run in flight.
   */
  applyExploreSession: (session: ExploreSessionResponse) => void;
  /** Route one WebSocket session event into the slice (FR-033). */
  applyExploreSessionEvent: (message: ExploreSessionEventMessage) => void;
  /** Write the cells from `CellsResponse` after an edit, insert, or toggle. */
  applyExploreCells: (sessionId: string, cells: ExploreCell[]) => void;
  /** Write the marks from `MarksResponse` (FR-012). */
  applyExploreMarks: (sessionId: string, marks: ExploreMarksResponse) => void;
  /** Write the bindings from `BindingsResponse` (FR-018). */
  applyExploreBindings: (sessionId: string, bindings: ExploreBindingsResponse) => void;
  /** Write the graph from `GraphResponse` (FR-032). */
  applyExploreGraph: (sessionId: string, graph: ExploreGraphResponse) => void;
  /** Write the packaging report from `PackagingCheckResponse` (FR-028). */
  applyExplorePackagingReport: (sessionId: string, report: ExplorePackagingCheckResponse) => void;
  /**
   * Write the queued requests a run control's `RunResponse` reported.
   *
   * The only door through which a cell reaches `queued`: the runtime publishes
   * no event for a request that is merely waiting, and FR-034 admits responses
   * alongside events. It never demotes a cell the runtime already called
   * running, so a race between the response and the event cannot go backwards.
   */
  applyExploreRunRequests: (sessionId: string, requests: ExploreRequest[]) => void;
  /** Write the kernel list from `KernelListResponse` (FR-015). */
  applyExploreKernelList: (kernels: ExploreKernelListItem[]) => void;
  /** Record that a session's open or restore is in flight, keyed by path. */
  noteExploreSessionOpening: (notebookPath: string) => void;
  /** Record that a session's open or restore was refused. */
  noteExploreSessionFailed: (notebookPath: string, error: string) => void;
  /** FR-019 — a panel was mounted in the centre for a name. */
  noteExplorePanelOpened: (sessionId: string, slot: PanelSlot) => void;
  /** FR-019 — a panel was unmounted. */
  noteExplorePanelClosed: (sessionId: string, panelId: string) => void;
  /** FR-020 — pin or unpin a mounted panel and its strip entry. */
  setExplorePanelPinned: (sessionId: string, panelId: string, pinned: boolean) => void;
  /** Drop a session from the slice; the tab is closed separately. */
  forgetExploreSession: (notebookPath: string) => void;
}

export type AppStore = ProjectSlice &
  // ADR-053 Learning Center (#2057) — replaces the removed TutorialSlice.
  LearningCenterSlice &
  WorkflowSlice &
  ExecutionSlice &
  UISlice &
  PreviewSlice &
  PaletteSlice &
  // ADR-053 §7 — the registered data type catalogue.
  TypesSlice &
  // #2113 — the registered panel catalogue + per-type choices.
  PanelCatalogSlice &
  TabSlice &
  TerminalTabsSlice &
  // ADR-038 §3.8 — Lineage tab client state.
  LineageSlice &
  // ADR-039 §6 Phase 2 — git versioning slice.
  GitSlice &
  // ADR-054 spec 4 FR-033 — the Explore session slice.
  ExploreSlice;
