/**
 * Data-artifact REST endpoints (uploads, metadata) and the routed panel
 * session API. The legacy one-shot `getDataPreview` was removed under ADR-048
 * no-compat (#1604); previews flow through the session helpers below.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  DataMetadataResponse,
  DataOpenAsCandidatesResponse,
  DataOpenAsListResponse,
  DataRegisterPathResponse,
  DataUploadResponse,
  PlotCreateRequest,
  PlotCreateResponse,
  PlotListResponse,
  PlotRelinkRequest,
  PlotRelinkResponse,
  PlotRunRequest,
  PlotRunResponse,
  PlotTargetListResponse,
  PreviewEnvelope,
  PreviewResourceResponse,
  PreviewResourceSaveRequest,
  PreviewResourceSaveResponse,
  PreviewTarget,
  PanelChoiceListResponse,
  PanelChoiceScope,
  PanelListResponse,
  PanelOverrideRevertResponse,
  PanelReloadResponse,
  PanelSourceResponse,
  PanelSourceSaveResponse,
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
 * core PlotPanel (`core.plot.basic`) and renders the figure. The end-to-end
 * runtime chain (run route -> catalog registration -> routed preview session ->
 * PlotPanel) is proven by `tests/api/test_plot_preview_wiring.py`.
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

/**
 * Build the same-origin URL for a panel asset on the merged asset route
 * (`GET /api/panels/assets/{panel_id}/{asset_path}`, ADR-054 FR-021, D-008).
 *
 * This mirrors `scistudio.panels.descriptor.PANEL_ASSET_ROUTE_PREFIX`, which is
 * where the one definition lives; a panel's own entry document and asset base
 * arrive on the descriptor rather than being built here, so this exists only
 * for a caller that has an id and a path and no descriptor.
 */
export function buildPanelAssetUrl(panelId: string, assetPath: string): string {
  const cleaned = assetPath.replace(/^\/+/, "");
  return `/api/panels/assets/${encodeURIComponent(panelId)}/${cleaned}`;
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

  /** Register a project-relative (or project-local absolute) file path with
   *  the data catalog (`POST /api/data/register-path`). #2112: the Data tree
   *  double-click feeds the response into a `data_ref` preview target.
   *
   *  `typeName` opens the file as a specific type and `remember` records that
   *  choice for the extension in the open project; omit both to let the
   *  backend apply the remembered or inferred type. */
  registerDataPath: (request: {
    projectId?: string;
    path: string;
    typeName?: string;
    remember?: boolean;
  }) =>
    apiFetch<DataRegisterPathResponse>("/api/data/register-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        project_id: request.projectId,
        path: request.path,
        type_name: request.typeName,
        remember: request.remember ?? false,
      }),
    }),

  /** The types a file could be opened as, plus any remembered choice
   *  (`GET /api/data/open-as/candidates`, #2112). More than one candidate with
   *  nothing remembered is what raises the picker. */
  getOpenAsCandidates: (request: { projectId?: string; path: string }) => {
    const params = new URLSearchParams({ path: request.path });
    if (request.projectId) params.set("project_id", request.projectId);
    return apiFetch<DataOpenAsCandidatesResponse>(`/api/data/open-as/candidates?${params}`);
  },

  /** The open project's remembered extension -> type choices (#2112). */
  listOpenAsTypes: (projectId?: string) =>
    apiFetch<DataOpenAsListResponse>(
      `/api/data/open-as${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),

  /** Forget the remembered type for one extension (#2112). */
  clearOpenAsType: (request: { projectId?: string; extension: string }) => {
    const query = request.projectId ? `?project_id=${encodeURIComponent(request.projectId)}` : "";
    return apiFetch<DataOpenAsListResponse>(
      `/api/data/open-as/${encodeURIComponent(request.extension)}${query}`,
      { method: "DELETE" },
    );
  },

  // -- ADR-048 SPEC 1: routed panel session API (additive, FR-007) ------

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

  // -- ADR-054 D-020: the panel API surface -------------------------------
  //
  // The listing, the rebuild and the choices moved under the panel naming with
  // their behaviour unchanged (FR-023), and the frontend follows them in the
  // same change. The *session* routes deliberately stay where they are:
  // FR-022 keeps `/api/previews/...` serving its existing clients for the
  // duration of the migration.

  /** List registered panels with the tier each was discovered from, ordered in
   *  routing precedence (`GET /api/panels`). `targetType` is an exact-match
   *  filter, not the router's specificity walk. */
  listPanels: (targetType?: string) =>
    apiFetch<PanelListResponse>(
      `/api/panels${targetType ? `?target_type=${encodeURIComponent(targetType)}` : ""}`,
    ),

  /** Rebuild the panel registry — the one way a panel directory that was
   *  added, changed or removed takes effect (`POST /api/panels/reload`,
   *  FR-023, FR-046). */
  reloadPanels: () => apiFetch<PanelReloadResponse>("/api/panels/reload", { method: "POST" }),

  /** List the effective panel choices, each with the layer it came from and
   *  whether its panel is still registered (`GET /api/panels/choices`). */
  listPanelChoices: () => apiFetch<PanelChoiceListResponse>("/api/panels/choices"),

  /** Record `targetType -> panelId` at `scope` — `project` (this project
   *  only) or `user` (every project). Returns the resulting effective choices
   *  (`PUT /api/panels/choices/{target_type}`). */
  setPanelChoice: (targetType: string, panelId: string, scope: PanelChoiceScope) =>
    apiFetch<PanelChoiceListResponse>(`/api/panels/choices/${encodeURIComponent(targetType)}`, {
      method: "PUT",
      headers: JSON_HEADERS,
      // `panel_id`, not `previewer_id`: `PanelChoiceRequest` was renamed with
      // the subsystem, so the old key leaves the required field missing and
      // the route rejects the body outright.
      body: JSON.stringify({ panel_id: panelId, scope }),
    }),

  /** Clear the choice for `targetType` at `scope`; clearing a type that was
   *  never chosen succeeds (`DELETE /api/panels/choices/{target_type}`). */
  clearPanelChoice: (targetType: string, scope: PanelChoiceScope) =>
    apiFetch<PanelChoiceListResponse>(
      `/api/panels/choices/${encodeURIComponent(targetType)}?scope=${encodeURIComponent(scope)}`,
      { method: "DELETE" },
    ),

  // -- ADR-054 T-010: reading a panel, saving it, reverting (FR-024..FR-029) --
  //
  // The three editing routes. Nothing asks *where* a save goes: FR-025 says the
  // system decides from the tier the panel resolved from, and the response's
  // `copied` says what it decided.

  /** Read any resolved panel's entry document and declaration, whichever tier
   *  it came from (`GET /api/panels/{panel_id}/source`, FR-024). */
  readPanelSource: (panelId: string) =>
    apiFetch<PanelSourceResponse>(`/api/panels/${encodeURIComponent(panelId)}/source`),

  /** Save an edit. A project or user-library panel is written back in place; a
   *  core or package panel is copied into the open project under the same id
   *  and `copied` comes back `true` (`PUT /api/panels/{panel_id}/source`,
   *  FR-025 to FR-027). */
  savePanelSource: (panelId: string, source: string, declaration?: string | null) =>
    apiFetch<PanelSourceSaveResponse>(`/api/panels/${encodeURIComponent(panelId)}/source`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify({ source, declaration: declaration ?? null }),
    }),

  /** Delete the shadowing copy, restoring whatever it shadowed. A panel that
   *  shadows nothing is refused with 409 rather than deleted — that would be a
   *  delete, a different request (`DELETE /api/panels/{panel_id}/override`,
   *  FR-029). */
  revertPanelOverride: (panelId: string) =>
    apiFetch<PanelOverrideRevertResponse>(`/api/panels/${encodeURIComponent(panelId)}/override`, {
      method: "DELETE",
    }),

  /** Save a bounded provider resource to a user-selected absolute file path
   *  (`POST /api/previews/sessions/{id}/resources/{resource_id}/save`). */
  savePreviewResource: (
    sessionId: string,
    resourceId: string,
    request: PreviewResourceSaveRequest,
  ) =>
    apiFetch<PreviewResourceSaveResponse>(
      `/api/previews/sessions/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(
        resourceId,
      )}/save`,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(request),
      },
    ),

  // -- ADR-048 SPEC 2 / #1606: plot-job run + preview wiring ----------------

  /** List workflow output targets available for a new plot scaffold. */
  listPlotTargets: (params?: {
    workflowId?: string | null;
    workflowPath?: string | null;
    nodeId?: string | null;
    outputPort?: string | null;
    includeUnavailable?: boolean;
  }) => {
    const search = new URLSearchParams();
    if (params?.workflowId) search.set("workflow_id", params.workflowId);
    if (params?.workflowPath) search.set("workflow_path", params.workflowPath);
    if (params?.nodeId) search.set("node_id", params.nodeId);
    if (params?.outputPort) search.set("output_port", params.outputPort);
    if (params?.includeUnavailable === false) search.set("include_unavailable", "false");
    const suffix = search.toString();
    return apiFetch<PlotTargetListResponse>(`/api/plots/targets${suffix ? `?${suffix}` : ""}`);
  },

  /** Create plots/<id>/plot.yaml plus a render script from the plot template. */
  createPlot: (request: PlotCreateRequest) =>
    apiFetch<PlotCreateResponse>("/api/plots", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request),
    }),

  /** Delete a plot's manifest and render script directory. */
  deletePlot: (plotId: string) =>
    apiFetch<void>(`/api/plots/${encodeURIComponent(plotId)}`, {
      method: "DELETE",
    }),

  /** Re-point an existing plot at a new workflow output target (bug#7).
   *  `POST /api/plots/{plot_id}/relink` rewrites only the manifest target block
   *  (strict 1:1) and re-validates, so a previously broken target becomes valid
   *  without recreating the plot or its render script. */
  relinkPlot: (plotId: string, request: PlotRelinkRequest) =>
    apiFetch<PlotRelinkResponse>(`/api/plots/${encodeURIComponent(plotId)}/relink`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request),
    }),

  /** Run a plot job and register its artifact for routed preview
   *  (`POST /api/plots/run`). On success the response's `data_ref` opens a
   *  `plot_artifact` preview session via {@link plotTargetFromRunResponse} +
   *  {@link createPreviewSession}; the produced figure then renders through the
   *  core PlotPanel. */
  runPlotJob: (request: PlotRunRequest) =>
    apiFetch<PlotRunResponse>("/api/plots/run", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request),
    }),

  /** List project-local plot manifests, optionally scoped to a workflow block. */
  listPlots: (params?: {
    workflowId?: string | null;
    nodeId?: string | null;
    outputPort?: string | null;
  }) => {
    const search = new URLSearchParams();
    if (params?.workflowId) search.set("workflow_id", params.workflowId);
    if (params?.nodeId) search.set("node_id", params.nodeId);
    if (params?.outputPort) search.set("output_port", params.outputPort);
    const suffix = search.toString();
    return apiFetch<PlotListResponse>(`/api/plots${suffix ? `?${suffix}` : ""}`);
  },
};
