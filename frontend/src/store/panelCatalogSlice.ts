// The registered panel catalogue plus the person's per-type panel
// choices (#2113, over the #2095 discovery/reload and #2049 choice APIs).
//
// One store-held copy of `GET /api/previews/previewers` and one of
// `GET /api/previews/choices` serve every surface that needs them — the
// Panels tab renders them, the websocket `blocks.reloaded` invalidation
// re-reads them, and `panelChoiceVersion` is what tells an open preview
// its routing inputs changed. Holding them here rather than fetching per
// surface is what keeps those three readers on the same answer.
//
// `panelChoiceVersion` is a plain counter rather than derived state: a
// choice change is an *event* (the person clicked), and the preview host's
// session-creation effect needs exactly one new dependency value per event,
// not a recomputed object identity per render.

import type { StateCreator } from "zustand";

import type { AppStore, PanelCatalogSlice } from "./types";

export const createPanelCatalogSlice: StateCreator<AppStore, [], [], PanelCatalogSlice> = (
  set,
) => ({
  panels: [],
  panelsLoaded: false,
  panelDiagnostics: [],
  panelChoices: [],
  panelChoicesLoaded: false,
  panelChoiceVersion: 0,
  setPanels: (panels, diagnostics) =>
    set({ panels, panelsLoaded: true, panelDiagnostics: diagnostics }),
  setPanelChoices: (choices) => set({ panelChoices: choices, panelChoicesLoaded: true }),
  bumpPanelChoiceVersion: () =>
    set((state) => ({ panelChoiceVersion: state.panelChoiceVersion + 1 })),
});
