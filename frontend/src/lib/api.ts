import type {
  AIGenerateBlockResponse,
  AIOptimizeParamsResponse,
  AISuggestWorkflowResponse,
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
      detail?: string;
    };
    throw new ApiError(
      payload.detail ?? `Request failed with ${response.status}`,
      response.status,
    );
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
  getDataPreview: (dataRef: string) =>
    apiFetch<DataPreviewResponse>(`/api/data/${encodeURIComponent(dataRef)}/preview`),
  generateBlock: (body: { description: string; block_category?: string }) =>
    apiFetch<AIGenerateBlockResponse>("/api/ai/generate-block", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  suggestWorkflow: (body: { data_description: string; goal: string }) =>
    apiFetch<AISuggestWorkflowResponse>("/api/ai/suggest-workflow", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  optimizeParams: (body: { block_id: string; intermediate_results: Record<string, unknown> }) =>
    apiFetch<AIOptimizeParamsResponse>("/api/ai/optimize-params", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
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
};
