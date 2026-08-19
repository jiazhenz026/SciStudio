import { useAppStore } from "./store";

export function resetAppStore() {
  localStorage.clear();
  useAppStore.setState({
    currentProject: null,
    recentProjects: [],
    projectDialogOpen: false,
    projectDialog: { mode: "new", name: "", description: "", path: "" },
    workflowId: null,
    workflowDescription: "",
    workflowVersion: "1.0.0",
    workflowMetadata: {},
    workflowNodes: [],
    workflowEdges: [],
    workflowDirty: false,
    workflowHistory: [],
    workflowFuture: [],
    blockStates: {},
    blockRunStartedAt: {},
    blockOutputs: {},
    executionMessages: [],
    logEntries: [],
    selectedNodeId: null,
    activeBottomTab: "config",
    paletteCollapsed: false,
    previewCollapsed: false,
    bottomPanelCollapsed: false,
    // ADR-053 Learning Center (#2057) — view state only (FR-074 keeps progress
    // on the backend), so a reset is just "closed, nothing fetched yet".
    learningCenterOpen: false,
    learningCenterCatalogue: null,
    learningCenterSession: null,
    learningCenterLoading: false,
    learningCenterError: null,
    learningCenterFirstRunDismissed: false,
    learningCenterWorkImportOffer: false,
    panelSizes: { palette: 15, preview: 22, bottom: 30 },
    minimapVisible: true,
    lastError: null,
    blocks: [],
    blockSchemas: {},
    paletteSearch: "",
    // ADR-053 §7 — the type catalogue starts unloaded, which is the FR-067
    // loading window every colour consumer must render correctly.
    types: [],
    typesLoaded: false,
    declaredTypeColors: undefined,
  });
}
