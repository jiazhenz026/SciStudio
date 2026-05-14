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
  // Logs unread badge. Coupled to ``appendLog`` / ``consumeEvent`` in
  // executionSlice — bumps iff a row is actually added AND the user isn't
  // already viewing Logs. Cleared when the Logs tab is opened.
  unreadLogsCount: 0,
  projectTreeRefreshCounter: 0,
  setSelectedNodeId: (nodeId) => set({ selectedNodeId: nodeId }),
  setActiveBottomTab: (tab) => {
    const patch: Record<string, unknown> = { activeBottomTab: tab };
    if (tab === "logs") patch.unreadLogsCount = 0;
    set(patch);
  },
  bumpUnreadLogs: () => {
    if (get().activeBottomTab === "logs") return;
    set((state) => ({ unreadLogsCount: state.unreadLogsCount + 1 }));
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
