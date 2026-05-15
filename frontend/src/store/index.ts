import { create } from "zustand";
import { persist } from "zustand/middleware";

import { createExecutionSlice } from "./executionSlice";
import { createLineageSlice } from "./lineageSlice";
import { createPaletteSlice } from "./paletteSlice";
import { createPreviewSlice } from "./previewSlice";
import { createProjectSlice } from "./projectSlice";
import { createTabSlice } from "./tabSlice";
import { createTerminalTabsSlice, rehydrateTerminalTabs } from "./terminalTabsSlice";
import type { AppStore, FileTab, TabState } from "./types";
import { createUISlice } from "./uiSlice";
import { createWorkflowSlice } from "./workflowSlice";

/**
 * ADR-036 §3.11 — file tab persistence whitelist.
 *
 * Only metadata is persisted; ``content`` is re-fetched on rehydrate
 * (the FileTab is restored with ``loading: true`` so the editor renders
 * a placeholder until the GET resolves).
 */
function partializeFileTab(tab: FileTab): FileTab {
  return {
    kind: "file",
    id: tab.id,
    filePath: tab.filePath,
    displayName: tab.displayName,
    language: tab.language,
    readOnly: tab.readOnly,
    // Reset volatile fields; CodeEditor refetches content on mount.
    content: "",
    contentLoadedAt: 0,
    dirty: false,
    loading: true,
  };
}

function partializeTabs(tabs: TabState[]): TabState[] {
  return tabs.map((tab) => (tab.kind === "file" ? partializeFileTab(tab) : tab));
}

export const useAppStore = create<AppStore>()(
  persist(
    (...args) => ({
      ...createProjectSlice(...args),
      ...createWorkflowSlice(...args),
      ...createExecutionSlice(...args),
      ...createUISlice(...args),
      ...createPreviewSlice(...args),
      ...createPaletteSlice(...args),
      ...createTabSlice(...args),
      ...createTerminalTabsSlice(...args),
      // ADR-038 §3.8 — Lineage tab state (D38-2.4b skeleton).
      ...createLineageSlice(...args),
    }),
    {
      name: "scieasy-studio-ui",
      partialize: (state) => ({
        activeBottomTab: state.activeBottomTab,
        paletteCollapsed: state.paletteCollapsed,
        previewCollapsed: state.previewCollapsed,
        bottomPanelCollapsed: state.bottomPanelCollapsed,
        panelSizes: state.panelSizes,
        // ADR-034 Phase 1.3: persist terminal tab metadata (NOT subprocess
        // state). On rehydrate, any `running` tab is downgraded to `closed`
        // with synthetic exit code -1 so the user sees the Reopen button.
        terminalTabs: state.terminalTabs,
        activeTerminalTabId: state.activeTerminalTabId,
        // ADR-036 §3.11: persist file-tab METADATA only (not content).
        // Workflow tabs are NOT persisted here because their canvas state
        // re-derives from project open + workflow load.
        tabs: partializeTabs(state.tabs.filter((t) => t.kind === "file")),
        activeTabId: state.activeTabId,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        // ADR-038 §3.8 / Codex P2 (PR #937): the "jobs" bottom tab was
        // removed in this PR. Users with persisted state from before
        // the upgrade may rehydrate into `activeBottomTab="jobs"`, which
        // is no longer a valid BottomTab value. Normalize stale values
        // to "lineage" (the closest semantic replacement — Jobs was a
        // placeholder for the run-history surface that Lineage now owns).
        // This guard is cheap; it also covers any future tab removals.
        const validTabs = new Set(["ai", "config", "logs", "lineage"]);
        if (state.activeBottomTab && !validTabs.has(state.activeBottomTab)) {
          state.activeBottomTab = "lineage";
        }
        const defaults = { palette: 15, preview: 22, bottom: 30 };
        const mins = { palette: 4, preview: 4, bottom: 10 };
        const sizes = state.panelSizes;
        if (sizes) {
          const fixed = { ...sizes };
          let needsFix = false;
          for (const key of ["palette", "preview", "bottom"] as const) {
            if (sizes[key] < mins[key]) {
              fixed[key] = defaults[key];
              needsFix = true;
            }
          }
          if (needsFix) {
            state.panelSizes = fixed;
          }
        }
        // Downgrade any "running" terminal tabs to "closed" — the PTY died
        // when the page unloaded.
        if (Array.isArray(state.terminalTabs)) {
          state.terminalTabs = rehydrateTerminalTabs(state.terminalTabs);
        }
        // ADR-036 §3.11: rehydrated file tabs come back with stripped
        // ``content`` and ``loading: true``. CodeEditor mounts will
        // re-fetch via ``openFileTab`` flow when the tab is activated.
        if (Array.isArray(state.tabs)) {
          state.tabs = state.tabs.map((tab) =>
            tab.kind === "file"
              ? {
                  ...tab,
                  content: "",
                  contentLoadedAt: 0,
                  dirty: false,
                  loading: true,
                }
              : tab,
          );
        }
      },
    },
  ),
);
