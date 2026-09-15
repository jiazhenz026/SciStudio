// The registered previewer catalogue plus the person's per-type previewer
// choices (#2113, over the #2095 discovery/reload and #2049 choice APIs).
//
// One store-held copy of `GET /api/previews/previewers` and one of
// `GET /api/previews/choices` serve every surface that needs them — the
// Previewers tab renders them and the websocket panel-catalog and choice
// events re-read them. Holding them here rather than fetching per surface is
// what keeps those readers on the same answer. Which open previews re-route
// is not store state: the panel service names the affected types and each
// `PreviewHost` decides for itself (#2465, `panels/panelEvents`).

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
  setPreviewers: (previewers, diagnostics) =>
    set({ previewers, previewersLoaded: true, previewerDiagnostics: diagnostics }),
  setPreviewerChoices: (choices) =>
    set({ previewerChoices: choices, previewerChoicesLoaded: true }),
});
