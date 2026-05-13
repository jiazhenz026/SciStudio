import { create } from "zustand";
import { persist } from "zustand/middleware";

import { createChatSlice } from "./chatSlice";
import { createExecutionSlice } from "./executionSlice";
import { createPaletteSlice } from "./paletteSlice";
import { createPreviewSlice } from "./previewSlice";
import { createProjectSlice } from "./projectSlice";
import { createTabSlice } from "./tabSlice";
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
      ...createChatSlice(...args),
      ...createTabSlice(...args),
    }),
    {
      name: "scieasy-studio-ui",
      partialize: (state) => ({
        activeBottomTab: state.activeBottomTab,
        paletteCollapsed: state.paletteCollapsed,
        previewCollapsed: state.previewCollapsed,
        bottomPanelCollapsed: state.bottomPanelCollapsed,
        panelSizes: state.panelSizes,
        chatMessages: state.chatMessages,
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
      },
    },
  ),
);
