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
    blockOutputs: {},
    executionMessages: [],
    logEntries: [],
    selectedNodeId: null,
    activeBottomTab: "config",
    paletteCollapsed: false,
    previewCollapsed: false,
    bottomPanelCollapsed: false,
    panelSizes: { palette: 15, preview: 22, bottom: 30 },
    minimapVisible: true,
    lastError: null,
    previewCache: {},
    previewLoading: {},
    blocks: [],
    blockSchemas: {},
    paletteSearch: "",
  });
}
