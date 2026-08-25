// The registered previewer catalogue plus the person's per-type previewer
// choices (#2113, over the #2095 discovery/reload and #2049 choice APIs).
//
// One store-held copy of `GET /api/previews/previewers` and one of
// `GET /api/previews/choices` serve every surface that needs them — the
// Previewers tab renders them, the websocket `blocks.reloaded` invalidation
// re-reads them, and `previewerChoiceVersion` is what tells an open preview
// its routing inputs changed. Holding them here rather than fetching per
// surface is what keeps those three readers on the same answer.
//
// `previewerChoiceVersion` is a plain counter rather than derived state: a
// choice change is an *event* (the person clicked), and the preview host's
// session-creation effect needs exactly one new dependency value per event,
// not a recomputed object identity per render.

import type { StateCreator } from "zustand";

import type { AppStore, PreviewerCatalogSlice } from "./types";

export const createPreviewerCatalogSlice: StateCreator<AppStore, [], [], PreviewerCatalogSlice> = (
  set,
) => ({
  previewers: [],
  previewersLoaded: false,
  previewerDiagnostics: [],
  previewerChoices: [],
  previewerChoicesLoaded: false,
  previewerChoiceVersion: 0,
  setPreviewers: (previewers, diagnostics) =>
    set({ previewers, previewersLoaded: true, previewerDiagnostics: diagnostics }),
  setPreviewerChoices: (choices) =>
    set({ previewerChoices: choices, previewerChoicesLoaded: true }),
  bumpPreviewerChoiceVersion: () =>
    set((state) => ({ previewerChoiceVersion: state.previewerChoiceVersion + 1 })),
});
