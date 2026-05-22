/**
 * Workflow CRUD + execution + export endpoints.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type {
  CancelPropagationResponse,
  ExecuteFromResponse,
  WorkflowExecutionResponse,
  WorkflowResponse,
} from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const workflowsApi = {
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
  getWorkflow: (workflowId: string) =>
    apiFetch<WorkflowResponse>(`/api/workflows/${encodeURIComponent(workflowId)}`),
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
    apiFetch<WorkflowExecutionResponse>(
      `/api/workflows/${encodeURIComponent(workflowId)}/execute`,
      {
        method: "POST",
      },
    ),
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
  exportWorkflowToPath: (workflowId: string, path: string) =>
    apiFetch<{ status: string; path: string }>("/api/workflows/export-path", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ workflow_id: workflowId, path }),
    }),
};
