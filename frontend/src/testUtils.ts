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
    runFirstWorkflowTutorialActive: false,
    runFirstWorkflowTutorialStep: "inspect-data",
    runFirstWorkflowTutorialInstance: null,
    runFirstWorkflowTutorialPrefs: {},
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
