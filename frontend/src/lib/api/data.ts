/**
 * Data-artifact REST endpoints (uploads, metadata) and the routed previewer
 * session API. The legacy one-shot `getDataPreview` was removed under ADR-048
 * no-compat (#1604); previews flow through the session helpers below.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  DataMetadataResponse,
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
