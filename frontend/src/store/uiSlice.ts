import type { StateCreator } from "zustand";

import type { AppStore, UISlice } from "./types";

export const createUISlice: StateCreator<AppStore, [], [], UISlice> = (set, get) => ({
  selectedNodeId: null,
  // #1799 — transient picker highlight, separate from selectedNodeId.
  highlightedNodeId: null,
  // #1799 — bottom Plots panel content mode; null = card grid.
  plotPicker: null,
  activeBottomTab: "config",
  // ADR-050 §3.1 — focus mode is frontend-only view state, off by default.
  focusMode: { enabled: false, selectedIds: [], depth: 1 },
  // Live hotfix batch: palette starts collapsed so opening a project shows
  // the canvas first; the value is persisted, so a later user toggle sticks.
  paletteCollapsed: true,
  previewCollapsed: false,
  bottomPanelCollapsed: false,
  bottomPanelPinned: false,
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
  blockCatalogRefreshCounter: 0,
  setSelectedNodeId: (nodeId) => set({ selectedNodeId: nodeId }),
  // #1799 — picker hover/select highlight. Cleared on picker close.
  setHighlightedNodeId: (nodeId) => set({ highlightedNodeId: nodeId }),
  // #1799 — toolbar / Plots-tab "New plot" entry point. Expanding the panel and
  // switching to the Plots tab are required so the picker (which lives in the
  // Plots tab content) is actually on screen when triggered from the toolbar.
  openNewPlotPicker: () =>
    set({
      bottomPanelCollapsed: false,
      activeBottomTab: "plots",
      plotPicker: { mode: "new" },
      highlightedNodeId: null,
    }),
  // #1799 — relink is triggered from a plot card, so the panel is already open;
  // still normalize panel/tab state for safety.
  openRelinkPlotPicker: (plotId) =>
    set({
      bottomPanelCollapsed: false,
      activeBottomTab: "plots",
      plotPicker: { mode: "relink", plotId },
      highlightedNodeId: null,
    }),
  closePlotPicker: () => set({ plotPicker: null, highlightedNodeId: null }),
  // ADR-050 §3.1 — enter/exit focus mode. Pure view state: these actions never
  // touch workflow nodes, edges, config, or the dirty flag (FR-018).
  enterFocusMode: (selectedIds, depth) =>
    set((state) => {
      if (selectedIds.length === 0) return {};
      return {
        focusMode: {
          enabled: true,
          selectedIds: [...selectedIds],
          depth: depth ?? state.focusMode.depth,
        },
      };
    }),
  exitFocusMode: () =>
    set((state) => ({
      focusMode: { enabled: false, selectedIds: [], depth: state.focusMode.depth },
    })),
  setFocusDepth: (depth) =>
    set((state) => ({
      focusMode: { ...state.focusMode, depth: Math.max(0, depth) },
    })),
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
  // #9: bumped on a ``blocks.reloaded`` WS event (e.g. the agent scaffolded +
  // reloaded a custom block) so App re-fetches the block catalog.
  bumpBlockCatalogRefresh: () =>
    set((state) => ({ blockCatalogRefreshCounter: state.blockCatalogRefreshCounter + 1 })),
  togglePalette: () => set((state) => ({ paletteCollapsed: !state.paletteCollapsed })),
  togglePreview: () => set((state) => ({ previewCollapsed: !state.previewCollapsed })),
  toggleBottomPanel: () => set((state) => ({ bottomPanelCollapsed: !state.bottomPanelCollapsed })),
  toggleBottomPanelPinned: () => set((state) => ({ bottomPanelPinned: !state.bottomPanelPinned })),
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
