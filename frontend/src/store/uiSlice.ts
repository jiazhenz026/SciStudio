import type { StateCreator } from "zustand";

import type { AppStore, UISlice } from "./types";

export const createUISlice: StateCreator<AppStore, [], [], UISlice> = (set, get) => ({
  selectedNodeId: null,
  activeBottomTab: "config",
  paletteCollapsed: false,
  previewCollapsed: false,
  bottomPanelCollapsed: false,
  minimapVisible: true,
  panelSizes: {
    palette: 15,
    preview: 22,
    bottom: 30,
  },
  lastError: null,
  // #793: unread badges on the bottom-panel tabs. Incremented when an event
  // arrives while the matching tab is hidden; cleared when the user opens it.
  unreadLogsCount: 0,
  unreadProblemsCount: 0,
  projectTreeRefreshCounter: 0,
  setSelectedNodeId: (nodeId) => set({ selectedNodeId: nodeId }),
  setActiveBottomTab: (tab) => {
    // Clear the unread counter for whichever tab the user just opened.
    const patch: Record<string, unknown> = { activeBottomTab: tab };
    if (tab === "logs") patch.unreadLogsCount = 0;
    if (tab === "problems") patch.unreadProblemsCount = 0;
    set(patch);
  },
  bumpUnreadLogs: () => {
    // Don't increment while the user is already viewing the logs tab.
    if (get().activeBottomTab === "logs") return;
    set((state) => ({ unreadLogsCount: state.unreadLogsCount + 1 }));
  },
  bumpUnreadProblems: () => {
    if (get().activeBottomTab === "problems") return;
    set((state) => ({ unreadProblemsCount: state.unreadProblemsCount + 1 }));
  },
  bumpProjectTreeRefresh: () =>
    set((state) => ({ projectTreeRefreshCounter: state.projectTreeRefreshCounter + 1 })),
  togglePalette: () => set((state) => ({ paletteCollapsed: !state.paletteCollapsed })),
  togglePreview: () => set((state) => ({ previewCollapsed: !state.previewCollapsed })),
  toggleBottomPanel: () => set((state) => ({ bottomPanelCollapsed: !state.bottomPanelCollapsed })),
  toggleMinimap: () => set((state) => ({ minimapVisible: !state.minimapVisible })),
  setPanelSize: (panel, size) =>
    set((state) => ({
      panelSizes: {
        ...state.panelSizes,
        [panel]: size,
      },
    })),
  setLastError: (message) => set({ lastError: message }),
});
