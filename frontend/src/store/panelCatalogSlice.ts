// The registered panel catalogue plus the person's per-type panel
// choices (#2113, over the #2095 discovery/reload and #2049 choice APIs).
//
// One store-held copy of `GET /api/panels` and one of
// `GET /api/panels/choices` serve every surface that needs them — the
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
  panelDocumentEpoch: 0,
  panelDocumentVersions: {},
  setPanels: (panels, diagnostics) =>
    set({ panels, panelsLoaded: true, panelDiagnostics: diagnostics }),
  setPanelChoices: (choices) => set({ panelChoices: choices, panelChoicesLoaded: true }),
  bumpPanelChoiceVersion: () =>
    set((state) => ({ panelChoiceVersion: state.panelChoiceVersion + 1 })),
  /*
   * ADR-054 FR-030 — the hot-reload trigger, split two ways on purpose.
   *
   * A named panel bumps only its own counter, so saving one panel remounts
   * that panel and leaves every other mounted panel alone. An unnamed change
   * bumps the epoch, which every mount reads, because "the registry was
   * rebuilt" carries no id and any panel on screen may be the one that moved.
   */
  notePanelDocumentChanged: (panelId) =>
    set((state) =>
      panelId === null
        ? { panelDocumentEpoch: state.panelDocumentEpoch + 1 }
        : {
            panelDocumentVersions: {
              ...state.panelDocumentVersions,
              [panelId]: (state.panelDocumentVersions[panelId] ?? 0) + 1,
            },
          },
    ),
});
