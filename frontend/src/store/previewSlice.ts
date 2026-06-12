import type { StateCreator } from "zustand";

import type { PreviewTarget } from "../types/api";

import type { AppStore, PreviewSlice } from "./types";

/**
 * ADR-048 SPEC 1 — build the routed-preview cache key (FR-021).
 *
 * Keys the session-envelope cache by data/collection reference, previewer id
 * (when known), session id (when known), the query parameters that change the
 * rendered envelope (slice/page/sort/slot/item), and the data version when the
 * caller can provide one. Private `_`-prefixed enrichment keys (`_storage`,
 * `_record_metadata`, ...) are excluded so they never widen the key.
 */
export function buildPreviewCacheKey(
  target: PreviewTarget,
  query: Record<string, unknown>,
  opts?: { previewerId?: string; sessionId?: string; dataVersion?: string },
): string {
  const QUERY_KEYS = ["slice_index", "page", "page_size", "sort_by", "sort_dir", "slot", "item"];
  const queryParts = QUERY_KEYS.filter((k) => query[k] !== undefined && query[k] !== null)
    .sort()
    .map((k) => `${k}=${String(query[k])}`);
  return [
    target.ref,
    target.kind,
    opts?.previewerId ?? "",
    opts?.sessionId ?? "",
    opts?.dataVersion ?? "",
    ...queryParts,
  ].join("|");
}

export const createPreviewSlice: StateCreator<AppStore, [], [], PreviewSlice> = (set) => ({
  previewEnvelopeCache: {},
  cachePreviewEnvelope: (key, envelope) =>
    set((state) => ({
      previewEnvelopeCache: {
        ...state.previewEnvelopeCache,
        [key]: envelope,
      },
    })),
  clearPreviewEnvelopeCache: () => set(() => ({ previewEnvelopeCache: {} })),
});
