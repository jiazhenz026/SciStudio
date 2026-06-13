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
  PlotRunRequest,
  PlotRunResponse,
  PreviewEnvelope,
  PreviewResourceResponse,
  PreviewTarget,
} from "../../types/api";
import { JSON_HEADERS, apiFetch } from "./core";

/**
 * ADR-048 SPEC 2 / #1606 — build the routed `plot_artifact` {@link PreviewTarget}
 * for a successful {@link PlotRunResponse}.
 *
 * This is the frontend production trigger that closes the runtime dead-wire:
 * after {@link dataApi.runPlotJob} registers the produced artifact and returns
 * its catalog `data_ref`, a caller passes the target this helper builds to
 * {@link PreviewHost}, which opens a routed preview session that resolves the
 * core PlotPreviewer (`core.plot.basic`) and renders the figure. The end-to-end
 * runtime chain (run route -> catalog registration -> routed preview session ->
 * PlotPreviewer) is proven by `tests/api/test_plot_preview_wiring.py`.
 *
 * Returns `null` when the run did not produce a previewable artifact (failed /
 * cancelled / timed-out, or no `data_ref`) so callers render the failure state
 * instead of an empty preview.
 */
export function plotTargetFromRunResponse(result: PlotRunResponse): PreviewTarget | null {
  if (result.status !== "succeeded" || !result.data_ref) return null;
  return {
    kind: "plot_artifact",
    ref: result.data_ref,
    recorded_type: result.recorded_type || "PlotArtifact",
    type_chain: result.type_chain?.length ? result.type_chain : ["DataObject", "PlotArtifact"],
    source: result.source ?? null,
  };
}

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

  // -- ADR-048 SPEC 2 / #1606: plot-job run + preview wiring ----------------

  /** Run a plot job and register its artifact for routed preview
   *  (`POST /api/plots/run`). On success the response's `data_ref` opens a
   *  `plot_artifact` preview session via {@link plotTargetFromRunResponse} +
   *  {@link createPreviewSession}; the produced figure then renders through the
   *  core PlotPreviewer. */
  runPlotJob: (request: PlotRunRequest) =>
    apiFetch<PlotRunResponse>("/api/plots/run", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request),
    }),
};
