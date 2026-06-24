import { create } from "zustand";
import { persist } from "zustand/middleware";

import { postActiveWorkflowContext } from "../lib/api/ai";

import { createExecutionSlice } from "./executionSlice";
import { createGitSlice } from "./gitSlice";
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
  return (
    tabs
      // #1758: block-source ("View source") tabs are transient — their content
      // comes from the block registry, not a project file, and has no
      // rehydrate-refetch path. Drop them from persistence so a reload does not
      // leave a permanently-empty placeholder.
      .filter((tab) => !(tab.kind === "file" && tab.blockSourceType))
      .map((tab) => (tab.kind === "file" ? partializeFileTab(tab) : tab))
  );
}

// ADR-040 Addendum 5 / #1488: sentinel for the active-workflow sync
// subscriber. Tracks the workflowId last POSTed to ``/api/ai/active-context``
// so an unrelated slice change does not re-emit the same id, and so the
// first call (after store creation + rehydration) always fires exactly one
// POST. ``undefined`` is used as the "never synced" marker because the
// store value itself is ``string | null`` — neither of which collides.
let lastSyncedActiveWorkflowId: string | null | undefined;

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
      // ADR-038 §3.8 — Lineage tab state.
      ...createLineageSlice(...args),
      // ADR-039 §6 Phase 2 — git versioning slice.
      ...createGitSlice(...args),
    }),
    {
      name: "scistudio-studio-ui",
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
        // ADR-038 §3.8 + ADR-039 §3.5 — `activeBottomTab` valid values
        // after integration are exactly the BottomTab union members
        // ("ai", "terminal", "config", "logs", "lineage", "git"). The historical
        // "jobs" placeholder was removed by ADR-038 §3.8 (run history
        // now lives in Lineage). Older persisted snapshots may still
        // carry "jobs", "problems", or other retired values; coerce
        // anything not in the current union back to "lineage" — the
        // semantic replacement for the run-history surface Jobs used
        // to occupy. This also covers any future tab removals.
        const validTabs = new Set<string>(["ai", "terminal", "config", "logs", "lineage", "git"]);
        if (typeof state.activeBottomTab !== "string" || !validTabs.has(state.activeBottomTab)) {
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

// ADR-040 Addendum 5 / #1488: surface the editor's active workflow id to
// the backend so the chat agent's ``get_active_workflow_context`` MCP
// tool reflects the same workflow the GUI is showing. We subscribe to
// the workflowId selector and POST whenever it transitions. The first
// call (sentinel == undefined) always fires so the backend's
// freshly-loaded persistence value can be confirmed or replaced.
function syncActiveWorkflowId(workflowId: string | null): void {
  if (lastSyncedActiveWorkflowId === workflowId) return;
  lastSyncedActiveWorkflowId = workflowId;
  void postActiveWorkflowContext(workflowId).catch((err) => {
    // Best-effort: a failed sync MUST NOT block the editor. The chat
    // agent simply won't see the latest id this turn — the next
    // workflowId change re-emits.
    console.warn("[ai-context] active workflow sync failed", err);
  });
}

useAppStore.subscribe((state) => {
  syncActiveWorkflowId(state.workflowId);
});

// Fire once at module load so the backend's persisted value is
// compared against (or replaced by) whatever the freshly-hydrated
// frontend has. Without this, the very first sync waits until the user
// opens or switches a workflow.
syncActiveWorkflowId(useAppStore.getState().workflowId);
