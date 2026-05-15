import type {
  BlockListResponse,
  BlockSchemaResponse,
  CancelPropagationResponse,
  ConnectionValidationResponse,
  DataMetadataResponse,
  DataPreviewResponse,
  DataUploadResponse,
  ExecuteFromResponse,
  FilesystemBrowseResponse,
  ProjectResponse,
  TreeResponse,
  WorkflowExecutionResponse,
  WorkflowResponse,
} from "../types/api";
import type {
  LineageGetRunsParams,
  LineageGetRunsResponse,
  LineageMethodsResponse,
  LineageRerunResponse,
  LineageRerunValidation,
  LineageRunDetail,
} from "../types/lineage";

const JSON_HEADERS = {
  "Content-Type": "application/json",
};

/**
 * Error thrown by `apiFetch` for non-2xx responses. Exposes the HTTP status
 * code so callers can branch on it (e.g. fall back on 500 but not on 504).
 * See issue #678.
 */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({ detail: response.statusText }))) as {
      detail?: string | { message?: string; errors?: unknown };
    };
    // ``detail`` can be a plain string (legacy + FastAPI default) OR a
    // structured object like ``{message, errors}`` (used by the workflow
    // GET route when a YAML fails pydantic validation — surfaces the
    // exact field/reason list for the agent / GUI to display).
    let message: string;
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (payload.detail && typeof payload.detail.message === "string") {
      message = payload.detail.message;
    } else {
      message = `Request failed with ${response.status}`;
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects: () => apiFetch<ProjectResponse[]>("/api/projects/"),
  createProject: (body: { name: string; description: string; path: string }) =>
    apiFetch<ProjectResponse>("/api/projects/", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  openProject: (projectIdOrPath: string) =>
    apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(projectIdOrPath)}`),
  updateProject: (projectId: string, body: { name?: string; description?: string }) =>
    apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  deleteProject: (projectId: string) =>
    apiFetch<void>(`/api/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    }),
  listBlocks: () => apiFetch<BlockListResponse>("/api/blocks/"),
  getBlockSchema: (blockType: string) =>
    apiFetch<BlockSchemaResponse>(`/api/blocks/${encodeURIComponent(blockType)}/schema`),
  validateConnection: (body: {
    source_block: string;
    source_port: string;
    target_block: string;
    target_port: string;
  }) =>
    apiFetch<ConnectionValidationResponse>("/api/blocks/validate-connection", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  listWorkflows: () => apiFetch<string[]>("/api/workflows/list"),
  importWorkflowFile: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<WorkflowResponse>("/api/workflows/import", {
      method: "POST",
      body: formData,
    });
  },
  importWorkflowFromPath: async (filePath: string) => {
    // Read the file via fetch from the backend browse result, then re-upload
    // For now, use a dedicated endpoint that accepts a path
    // TODO: replace the dedicated /api/workflows/import-path endpoint with a fetch-then-import flow that reuses /api/projects/{id}/file.
    return apiFetch<WorkflowResponse>("/api/workflows/import-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path: filePath }),
    });
  },
  createWorkflow: (body: WorkflowResponse) =>
    apiFetch<WorkflowResponse>("/api/workflows/", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  getWorkflow: (workflowId: string) => apiFetch<WorkflowResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`),
  updateWorkflow: (workflowId: string, body: WorkflowResponse) =>
    apiFetch<WorkflowResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  deleteWorkflow: (workflowId: string) =>
    apiFetch<void>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
      method: "DELETE",
    }),
  executeWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/execute`, {
      method: "POST",
    }),
  pauseWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/pause`, {
      method: "POST",
    }),
  resumeWorkflow: (workflowId: string) =>
    apiFetch<WorkflowExecutionResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/resume`, {
      method: "POST",
    }),
  cancelWorkflow: (workflowId: string) =>
    apiFetch<CancelPropagationResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/cancel`, {
      method: "POST",
    }),
  cancelBlock: (workflowId: string, blockId: string) =>
    apiFetch<CancelPropagationResponse>(
      `/api/workflows/${encodeURIComponent(workflowId)}/blocks/${encodeURIComponent(blockId)}/cancel`,
      { method: "POST" },
    ),
  executeFrom: (workflowId: string, blockId: string) =>
    apiFetch<ExecuteFromResponse>(`/api/workflows/${encodeURIComponent(workflowId)}/execute-from`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ block_id: blockId }),
    }),
  uploadData: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DataUploadResponse>("/api/data/upload", {
      method: "POST",
      body: formData,
    });
  },
  getDataMetadata: (dataRef: string) => apiFetch<DataMetadataResponse>(`/api/data/${encodeURIComponent(dataRef)}`),
  getDataPreview: (dataRef: string, slice?: number) => {
    // #899 — optional ``slice`` query param selects the index along the
    // backend-detected slider axis for 3-D images. Out-of-range values are
    // clamped server-side; 2-D images ignore the param.
    const qs = slice === undefined ? "" : `?slice=${encodeURIComponent(slice)}`;
    return apiFetch<DataPreviewResponse>(`/api/data/${encodeURIComponent(dataRef)}/preview${qs}`);
  },
  browseFilesystem: (path: string) =>
    apiFetch<FilesystemBrowseResponse>(
      `/api/filesystem/browse?path=${encodeURIComponent(path)}`,
    ),
  getProjectTree: (projectId: string, path = "") =>
    apiFetch<TreeResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/tree?path=${encodeURIComponent(path)}`,
    ),
  revealInExplorer: (path: string) =>
    apiFetch<{ status: string }>("/api/filesystem/reveal", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path }),
    }),
  openNativeDialog: (mode: "file" | "directory", initialDir?: string) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ mode, initial_dir: initialDir }),
    }),
  openNativeSaveDialog: (options: { initialDir?: string; defaultFilename?: string; fileFilter?: string }) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        mode: "save_file",
        initial_dir: options.initialDir,
        default_filename: options.defaultFilename,
        file_filter: options.fileFilter,
      }),
    }),
  exportWorkflowToPath: (workflowId: string, path: string) =>
    apiFetch<{ status: string; path: string }>("/api/workflows/export-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ workflow_id: workflowId, path }),
    }),
  // ADR-036 §3.2 — embedded code editor file R/W endpoints.
  getProjectFile: (projectId: string, path: string) =>
    apiFetch<{ content: string; mtime: number; size: number; encoding: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
    ),
  putProjectFile: (projectId: string, path: string, content: string) =>
    apiFetch<{ mtime: number; size: number }>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
      {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ content }),
      },
    ),
  // ADR-036 §3.12 — block template scaffold endpoint (I36c).
  getBlockTemplate: (kind: string = "basic") =>
    apiFetch<{ kind: string; content: string; suggested_filename: string }>(
      `/api/blocks/template?kind=${encodeURIComponent(kind)}`,
    ),
  // ADR-036 §3.3 — server-side ruff lint endpoint.
  lintPython: (content: string, filename: string) =>
    apiFetch<{
      diagnostics: Array<{
        line: number;
        column: number;
        end_line: number;
        end_column: number;
        code: string;
        severity: string;
        message: string;
      }>;
      note?: string;
    }>("/api/lint/python", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ content, filename }),
    }),

  // ---------------------------------------------------------------------
  // ADR-038 §3.8 — Lineage REST surface (D38-2.4b skeleton).
  //
  // Function bodies throw new Error("TODO: D38-2.4c — ...") so the
  // skeleton compiles + tests can mock these directly while the IMPL
  // agent (D38-2.4c) wires them to real fetch calls.
  //
  // URL shapes match the backend stubs declared by D38-2.4a in
  // `src/scieasy/api/routes/runs.py`. Both PRs target tracking branch
  // `track/adr-038/lineage-db`; if either PR refines a path the other
  // updates here.
  //
  // The namespace pattern (`api.lineage.getRuns(...)`) groups Lineage
  // calls so callers do not collide with `api.list*` / `api.get*` from
  // the existing surface. Mirrors how a future `api.git.*` namespace
  // will land for ADR-039 in D39-2.3a (sibling tracking branch — out of
  // scope here, mentioned only to avoid future merge surprises).
  // ---------------------------------------------------------------------
  lineage: {
    /**
     * GET /api/runs?workflow_id=...&limit=...
     *
     * IMPL D38-2.4c: build the querystring from params (omit absent
     * fields), call apiFetch<LineageGetRunsResponse>, return runs.
     */
    getRuns: (_params?: LineageGetRunsParams): Promise<LineageGetRunsResponse> => {
      throw new Error("TODO: D38-2.4c — implement api.lineage.getRuns");
    },

    /**
     * GET /api/runs/{run_id}
     *
     * IMPL D38-2.4c: call apiFetch<LineageRunDetail>, surface 404 as
     * ApiError(status=404). The lineageSlice fetchRunDetail handler maps
     * 404 to "Run not found" per the slice contract.
     */
    getRun: (_runId: string): Promise<LineageRunDetail> => {
      throw new Error("TODO: D38-2.4c — implement api.lineage.getRun");
    },

    /**
     * GET /api/runs/{run_id}/methods
     *
     * IMPL D38-2.4c: returns rendered markdown for the methods section
     * (server-side template owned by D38-2.4a in
     * `core/lineage/methods_export.py`).
     */
    getRunMethods: (_runId: string): Promise<LineageMethodsResponse> => {
      throw new Error("TODO: D38-2.4c — implement api.lineage.getRunMethods");
    },

    /**
     * GET /api/runs/{run_id}/validate-rerun
     *
     * IMPL D38-2.4c: returns input + environment drift warnings per
     * ADR-038 §3.6. Both lists may be empty (no drift detected).
     */
    validateRerun: (_runId: string): Promise<LineageRerunValidation> => {
      throw new Error(
        "TODO: D38-2.4c — implement api.lineage.validateRerun",
      );
    },

    /**
     * POST /api/runs/{run_id}/rerun
     *
     * IMPL D38-2.4c: triggers re-execution; returns the new run_id. The
     * frontend caller (RerunDialog.handleConfirm) closes the dialog and
     * refreshes the runs list on success.
     */
    rerunRun: (_runId: string): Promise<LineageRerunResponse> => {
      throw new Error("TODO: D38-2.4c — implement api.lineage.rerunRun");
    },
  },
};
