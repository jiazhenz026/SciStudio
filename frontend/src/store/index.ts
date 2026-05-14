import { create } from "zustand";
import { persist } from "zustand/middleware";

import { createExecutionSlice } from "./executionSlice";
import { createPaletteSlice } from "./paletteSlice";
import { createPreviewSlice } from "./previewSlice";
import { createProjectSlice } from "./projectSlice";
import { createTabSlice } from "./tabSlice";
import { createTerminalTabsSlice, rehydrateTerminalTabs } from "./terminalTabsSlice";
import type { AppStore } from "./types";
import { createUISlice } from "./uiSlice";
import { createWorkflowSlice } from "./workflowSlice";

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
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) return;
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
      },
    },
  ),
);
