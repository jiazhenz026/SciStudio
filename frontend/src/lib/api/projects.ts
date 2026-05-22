/**
 * Project-scoped REST endpoints.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422). Exposed as a
 * record that the parent `api` object spreads in.
 */

import type { ProjectResponse, TreeResponse } from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const projectsApi = {
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
  getProjectTree: (projectId: string, path = "") =>
    apiFetch<TreeResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/tree?path=${encodeURIComponent(path)}`,
    ),
};
