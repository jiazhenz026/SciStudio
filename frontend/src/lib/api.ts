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
};
