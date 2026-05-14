import type { StateCreator } from "zustand";

import type { AppStore, TabSlice, TabState } from "./types";

/**
 * Capture the current workflow + UI state into a TabState snapshot.
 */
function captureTab(state: AppStore): TabState {
  return {
    id: state.activeTabId ?? state.workflowId ?? "main",
    workflowId: state.workflowId ?? "main",
    workflowName: state.workflowName,
    workflowDescription: state.workflowDescription,
    workflowVersion: state.workflowVersion,
    workflowMetadata: state.workflowMetadata,
    workflowNodes: state.workflowNodes,
    workflowEdges: state.workflowEdges,
    workflowDirty: state.workflowDirty,
    workflowHistory: state.workflowHistory,
    workflowFuture: state.workflowFuture,
    selectedNodeId: state.selectedNodeId,
  };
}

/**
 * Restore a tab snapshot into the main workflow + UI state fields.
 */
function restoreTab(tab: TabState): Partial<AppStore> {
  return {
    workflowId: tab.workflowId,
    workflowName: tab.workflowName,
    workflowDescription: tab.workflowDescription,
    workflowVersion: tab.workflowVersion,
    workflowMetadata: tab.workflowMetadata,
    workflowNodes: tab.workflowNodes,
    workflowEdges: tab.workflowEdges,
    workflowDirty: tab.workflowDirty,
    workflowHistory: tab.workflowHistory,
    workflowFuture: tab.workflowFuture,
    selectedNodeId: tab.selectedNodeId,
    activeTabId: tab.id,
  };
}

export const createTabSlice: StateCreator<AppStore, [], [], TabSlice> = (set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: (workflow, displayName) => {
    const state = get();
    // #796: pick a non-empty display name. The backend's WorkflowModel.id has a
    // default of "" — if a YAML omits the id field, workflow.id arrives empty
    // and the tab label + top-left title render blank. Fall back to the caller-
    // supplied displayName (typically the filename stem), then "Untitled".
    const effectiveName = workflow.id || displayName || "Untitled";

    // Use workflow.id when present for tab-de-duplication; otherwise fall back
    // to the display name so two opens of the same blank-id file still de-dupe.
    const dedupeKey = workflow.id || displayName || "";
    const existing = dedupeKey
      ? state.tabs.find((t) => t.workflowId === dedupeKey)
      : undefined;
    if (existing) {
      // Switch to it instead of opening a duplicate
      state.switchTab(existing.id);
      return;
    }

    // Guard: enforce maximum tab limit (#598)
    if (state.tabs.length >= 50) {
      window.alert("Maximum 50 tabs reached.");
      return;
    }

    // Save current tab state before switching
    const updatedTabs = state.activeTabId
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureTab(state) : t))
      : [...state.tabs];

    // Create new tab. Use the effective name as the workflowId fallback so
    // downstream API calls (save/run) have something to address.
    const idForTab = workflow.id || displayName || "main";
    const tabId = `tab-${idForTab}-${Date.now()}`;
    const newTab: TabState = {
      id: tabId,
      workflowId: idForTab,
      workflowName: effectiveName,
      workflowDescription: workflow.description,
      workflowVersion: workflow.version,
      workflowMetadata: workflow.metadata,
      workflowNodes: workflow.nodes,
      workflowEdges: workflow.edges,
      workflowDirty: false,
      workflowHistory: [],
      workflowFuture: [],
      selectedNodeId: null,
    };

    set({
      tabs: [...updatedTabs, newTab],
      ...restoreTab(newTab),
    });
  },

  switchTab: (tabId) => {
    const state = get();
    if (tabId === state.activeTabId) return;

    const target = state.tabs.find((t) => t.id === tabId);
    if (!target) return;

    // Save current tab state
    const updatedTabs = state.activeTabId
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureTab(state) : t))
      : state.tabs;

    set({
      tabs: updatedTabs,
      ...restoreTab(target),
    });
  },

  closeTab: (tabId) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === tabId);
    if (!tab) return true;

    // If this is the active tab, check for the latest dirty state
    const isDirty = tabId === state.activeTabId ? state.workflowDirty : tab.workflowDirty;

    if (isDirty) {
      const confirmed = window.confirm(
        `"${tab.workflowName}" has unsaved changes. Close anyway?`,
      );
      if (!confirmed) return false;
    }

    const remaining = state.tabs.filter((t) => t.id !== tabId);

    if (tabId === state.activeTabId) {
      // Need to switch to another tab or clear
      if (remaining.length > 0) {
        // Switch to the tab that was next to this one
        const closedIndex = state.tabs.findIndex((t) => t.id === tabId);
        const nextTab = remaining[Math.min(closedIndex, remaining.length - 1)];
        set({
          tabs: remaining,
          ...restoreTab(nextTab),
        });
      } else {
        // No tabs left — reset to empty state
        set({
          tabs: [],
          activeTabId: null,
          workflowId: null,
          workflowName: "Untitled",
          workflowDescription: "",
          workflowVersion: "1.0.0",
          workflowMetadata: {},
          workflowNodes: [],
          workflowEdges: [],
          workflowDirty: false,
          workflowHistory: [],
          workflowFuture: [],
          selectedNodeId: null,
        });
      }
    } else {
      set({ tabs: remaining });
    }
    return true;
  },

  syncActiveTab: () => {
    const state = get();
    if (!state.activeTabId) return;
    set({
      tabs: state.tabs.map((t) =>
        t.id === state.activeTabId ? captureTab(state) : t,
      ),
    });
  },

  /**
   * ADR-036 §3.10 — open (or focus) a file editor tab.
   *
   * SKELETON (S36): throws. See ``TabSlice.openFileTab`` docstring in
   * ``types.ts`` for the implementation plan and test plan that
   * Phase 2A (I36a) must execute.
   */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  openFileTab: (_filePath: string, _opts?: { readOnly?: boolean }) => {
    throw new Error(
      "ADR-036 skeleton — openFileTab not implemented (see TabSlice.openFileTab docstring)",
    );
  },

  /**
   * ADR-036 §3.10 — save a file tab to disk via PUT /api/projects/{id}/file.
   *
   * SKELETON (S36): throws. See ``TabSlice.saveFileTab`` docstring in
   * ``types.ts`` for the implementation plan.
   */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  saveFileTab: async (_id: string) => {
    throw new Error(
      "ADR-036 skeleton — saveFileTab not implemented (see TabSlice.saveFileTab docstring)",
    );
  },

  /**
   * ADR-036 §3.10 — update a file tab's in-memory content + dirty flag.
   *
   * SKELETON (S36): throws. See ``TabSlice.updateFileTabContent`` docstring
   * in ``types.ts`` for the implementation plan.
   */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  updateFileTabContent: (_id: string, _content: string) => {
    throw new Error(
      "ADR-036 skeleton — updateFileTabContent not implemented (see TabSlice.updateFileTabContent docstring)",
    );
  },
});
