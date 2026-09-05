import { create } from "zustand";
import { persist } from "zustand/middleware";

import { postActiveWorkflowContext } from "../lib/api/ai";
import { reportWorkspaceFocus } from "../explore/workspaceFocus";

import { createExecutionSlice } from "./executionSlice";
import { createExploreSlice } from "./exploreSlice";
import { createGitSlice } from "./gitSlice";
import { createLearningCenterSlice } from "./learningCenterSlice";
import { createLineageSlice } from "./lineageSlice";
import { createPaletteSlice } from "./paletteSlice";
import { createPreviewSlice } from "./previewSlice";
import { createPanelCatalogSlice } from "./panelCatalogSlice";
import { createProjectSlice } from "./projectSlice";
import { createTabSlice } from "./tabSlice";
import { createTerminalTabsSlice, rehydrateTerminalTabs } from "./terminalTabsSlice";
import { createTypesSlice } from "./typesSlice";
import type { AppStore, ExploreTab, FileTab, TabState } from "./types";
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

/**
 * ADR-054 FR-001 — an Explore tab persists like a file tab: its identity is
 * the notebook path, and everything else is runtime state that must be read
 * back from the runtime rather than trusted from `localStorage`.
 *
 * `sessionId` is dropped because the session it named is gone with the page,
 * and `restoring` is set so the shell knows to re-fetch rather than render an
 * empty session as an empty notebook. A pause tab is not persisted at all
 * (see `partializeTabs`): the run it was paused on did not survive the reload,
 * so restoring the tab would offer a confirm with nothing behind it.
 */
function partializeExploreTab(tab: ExploreTab): ExploreTab {
  return {
    kind: "explore",
    id: tab.id,
    notebookPath: tab.notebookPath,
    sessionId: null,
    displayName: tab.displayName,
    mode: "session",
    boundRunId: null,
    pauseNodeId: null,
    notebookVisible: true,
    restoring: true,
  };
}

function partializeTabs(tabs: TabState[]): TabState[] {
  return (
    tabs
      // #1758: block-source ("View source") tabs are transient — their content
      // comes from the block registry, not a project file, and has no
      // rehydrate-refetch path. Drop them from persistence so a reload does not
      // leave a permanently-empty placeholder.
      //
      // ADR-053 FR-032: user-library tabs are dropped for the same reason.
      // Their file lives outside every project root, so the project-file
      // rehydrate path cannot restore it either.
      //
      // ADR-054 FR-024: panel-source tabs are dropped for the same reason
      // again. A panel is addressed by panel id rather than by project path,
      // so the rehydrate has no path to re-read.
      .filter(
        (tab) =>
          !(
            tab.kind === "file" &&
            (tab.blockSourceType || tab.userLibraryTarget || tab.panelSourceId)
          ),
      )
      .map((tab) =>
        tab.kind === "file"
          ? partializeFileTab(tab)
          : tab.kind === "explore"
            ? partializeExploreTab(tab)
            : tab,
      )
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
      // ADR-053 Learning Center (#2057) — view state only; not persisted.
      ...createLearningCenterSlice(...args),
      ...createWorkflowSlice(...args),
      ...createExecutionSlice(...args),
      ...createUISlice(...args),
      ...createPreviewSlice(...args),
      ...createPaletteSlice(...args),
      // ADR-053 §7 — registered data type catalogue (FR-026 / FR-027).
      ...createTypesSlice(...args),
      // #2113 — registered panel catalogue + per-type choices.
      ...createPanelCatalogSlice(...args),
      ...createTabSlice(...args),
      ...createTerminalTabsSlice(...args),
      // ADR-038 §3.8 — Lineage tab state.
      ...createLineageSlice(...args),
      // ADR-039 §6 Phase 2 — git versioning slice.
      ...createGitSlice(...args),
      // ADR-054 spec 4 FR-033 — the Explore session slice. Not persisted: it
      // holds runtime truth (marks, kernel state, bindings), and FR-034 says
      // the runtime is where that comes from, so a reload re-reads it.
      ...createExploreSlice(...args),
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
        // ADR-053 FR-001 / FR-074 — the four `runFirstWorkflowTutorial*` keys
        // that used to be persisted here are gone. Tutorial progress lives on
        // the backend under `~/.scistudio/`; a browser copy would be a second
        // source of truth that survives a backend which has moved on.
        // ADR-036 §3.11: persist file-tab METADATA only (not content).
        // Workflow tabs are NOT persisted here because their canvas state
        // re-derives from project open + workflow load. #2112 preview tabs
        // are excluded by the same kind filter: they are frozen, ephemeral
        // snapshots with no rehydrate path.
        // ADR-054 FR-001 — Explore tabs persist beside file tabs. A pause tab
        // is excluded: the paused run is gone with the page, so the tab would
        // come back offering a decision on nothing.
        tabs: partializeTabs(
          state.tabs.filter(
            (t) => t.kind === "file" || (t.kind === "explore" && t.mode === "session"),
          ),
        ),
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
        const validTabs = new Set<string>([
          "ai",
          "terminal",
          "config",
          "logs",
          "plots",
          "lineage",
          "git",
        ]);
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
          state.tabs = state.tabs.map((tab) => {
            if (tab.kind === "file") {
              return {
                ...tab,
                content: "",
                contentLoadedAt: 0,
                dirty: false,
                loading: true,
              };
            }
            // ADR-054 FR-001: a rehydrated Explore tab is bound to no session
            // until `restoreExploreTab` reopens its notebook. The shell fires
            // that on mount; marking it here is what tells the shell to.
            if (tab.kind === "explore") {
              return { ...tab, sessionId: null, restoring: true };
            }
            return tab;
          });
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
  /*
   * ADR-054 spec 5 FR-001 - and where the person is, beside what they are
   * editing.
   *
   * The same subscriber rather than a second one: the two are one fact about
   * the workspace, and reporting them from one place is what keeps them from
   * disagreeing across a tab switch. `reportWorkspaceFocus` compares against
   * what it last sent, so this fires on every store change and posts only when
   * the focus actually moved.
   */
  reportWorkspaceFocus(state);
});

// Fire once at module load so the backend's persisted value is
// compared against (or replaced by) whatever the freshly-hydrated
// frontend has. Without this, the very first sync waits until the user
// opens or switches a workflow.
syncActiveWorkflowId(useAppStore.getState().workflowId);
// The focus is reported once at load for the same reason: the backend's
// persisted value predates this page and the agent should be told what is on
// screen now, not what was on screen when the backend last heard.
reportWorkspaceFocus(useAppStore.getState());
