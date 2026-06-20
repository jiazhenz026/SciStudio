import type { StateCreator } from "zustand";

import type { PreviewTarget } from "../types/api";

import type { AppStore, PreviewSlice } from "./types";

export interface PreviewCacheKeyOptions {
  previewerId?: string | null;
  sessionId?: string | null;
  dataVersion?: string | number | null;
}

function stablePreviewCacheValue(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stablePreviewCacheValue(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .filter((key) => record[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stablePreviewCacheValue(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

/**
 * ADR-048 SPEC 1 cache key construction (FR-021).
 *
 * Keys the session-envelope cache by data/collection reference, previewer id
 * (when known), session id (when known), every public query parameter that
 * can change the rendered envelope, and the data version when the caller can
 * provide one. Private `_`-prefixed enrichment keys (`_storage`,
 * `_record_metadata`, ...) are excluded so they never widen the key.
 */
export function buildPreviewCacheKey(
  target: PreviewTarget,
  query: Record<string, unknown>,
  opts?: PreviewCacheKeyOptions,
): string {
  const queryParts = Object.keys(query)
    .filter((k) => !k.startsWith("_") && query[k] !== undefined && query[k] !== null)
    .sort()
    .map((k) => `${k}=${stablePreviewCacheValue(query[k])}`);
  return [
    `ref=${target.ref}`,
    `kind=${target.kind}`,
    opts?.previewerId ? `previewer=${opts.previewerId}` : "",
    opts?.sessionId ? `session=${opts.sessionId}` : "",
    opts?.dataVersion !== undefined && opts.dataVersion !== null
      ? `version=${opts.dataVersion}`
      : "",
    ...queryParts,
  ]
    .filter(Boolean)
    .join("|");
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
  // #1713 — plot Run result shared between the Plots tab (producer) and the
  // Preview panel (renderer).
  plotPreviewTarget: null,
  setPlotPreviewTarget: (target) => set(() => ({ plotPreviewTarget: target })),
});
