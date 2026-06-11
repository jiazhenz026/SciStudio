/**
 * Data-artifact REST endpoints (uploads, metadata, preview slices).
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  DataMetadataResponse,
  DataPreviewQuery,
  DataPreviewResponse,
  DataUploadResponse,
  PreviewEnvelope,
  PreviewResourceResponse,
  PreviewTarget,
} from "../../types/api";
import { JSON_HEADERS, apiFetch } from "./core";

/** Build the same-origin URL for a validated previewer asset
 *  (`GET /api/previews/assets/{previewer_id}/{asset_path}`). This is the ONLY
 *  origin a dynamic previewer module is permitted to load from (FR-022). */
export function buildPreviewAssetUrl(previewerId: string, assetPath: string): string {
  const cleaned = assetPath.replace(/^\/+/, "");
  return `/api/previews/assets/${encodeURIComponent(previewerId)}/${cleaned}`;
}

export const dataApi = {
  uploadData: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DataUploadResponse>("/api/data/upload", {
      method: "POST",
      body: formData,
    });
  },
  getDataMetadata: (dataRef: string) =>
    apiFetch<DataMetadataResponse>(`/api/data/${encodeURIComponent(dataRef)}`),
  getDataPreview: (dataRef: string, opts?: number | DataPreviewQuery) => {
    // Backwards-compat: a bare number is interpreted as ``slice`` (image flow).
    // Object form covers slice + DataFrame paging (page/page_size/sort_by/sort_dir).
    const o: DataPreviewQuery = typeof opts === "number" ? { slice: opts } : (opts ?? {});
    const params = new URLSearchParams();
    if (o.slice !== undefined) params.set("slice", String(o.slice));
    if (o.page !== undefined) params.set("page", String(o.page));
    if (o.pageSize !== undefined) params.set("page_size", String(o.pageSize));
    if (o.sortBy) params.set("sort_by", o.sortBy);
    if (o.sortDir) params.set("sort_dir", o.sortDir);
    const qs = params.toString();
    const url = `/api/data/${encodeURIComponent(dataRef)}/preview${qs ? `?${qs}` : ""}`;
    return apiFetch<DataPreviewResponse>(url);
  },

  // -- ADR-048 SPEC 1: routed previewer session API (additive, FR-007) ------

  /** Create a routed preview session for a target and return the first
   *  envelope (`POST /api/previews/sessions`). */
  createPreviewSession: (target: PreviewTarget, query: Record<string, unknown> = {}) =>
    apiFetch<PreviewEnvelope>("/api/previews/sessions", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ target, query }),
    }),

  /** Read the current envelope for a session
   *  (`GET /api/previews/sessions/{session_id}`). */
  getPreviewSession: (sessionId: string) =>
    apiFetch<PreviewEnvelope>(`/api/previews/sessions/${encodeURIComponent(sessionId)}`),

  /** Update query state (slice/page/sort/slot/item) and re-render the envelope
   *  (`PATCH /api/previews/sessions/{session_id}`). */
  patchPreviewSession: (sessionId: string, query: Record<string, unknown>) =>
    apiFetch<PreviewEnvelope>(`/api/previews/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({ query }),
    }),

  /** Fetch a bounded provider resource — an array tile or a child preview
   *  envelope (`GET /api/previews/sessions/{id}/resources/{resource_id}`). */
  getPreviewResource: (sessionId: string, resourceId: string) =>
    apiFetch<PreviewResourceResponse>(
      `/api/previews/sessions/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(
        resourceId,
      )}`,
    ),
};
