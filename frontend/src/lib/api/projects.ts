/**
 * Project-scoped REST endpoints.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422). Exposed as a
 * record that the parent `api` object spreads in.
 */

import type { ProjectResponse, TreeResponse } from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

/**
 * #2019 — client-side deadline for the two project-switch calls.
 *
 * Both rebind server-side state (block/type registries, lineage + metadata
 * stores, git init, agent provisioning, MCP transport), so they are the
 * slowest calls in the app and legitimately take seconds on a large project;
 * the bound is generous enough never to trip on real work. What it buys is
 * the guarantee that the promise *settles*. These two calls gate a modal and
 * the global busy flag, and both are only cleared from a `finally` — so a
 * request that never returns leaves the whole GUI wedged with no way out.
 */
const PROJECT_SWITCH_TIMEOUT_MS = 60_000;

export const projectsApi = {
  listProjects: () => apiFetch<ProjectResponse[]>("/api/projects/"),
  createProject: (body: { name: string; description: string; path: string }) =>
    apiFetch<ProjectResponse>("/api/projects/", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
      timeoutMs: PROJECT_SWITCH_TIMEOUT_MS,
    }),
  openProject: (projectIdOrPath: string) =>
    apiFetch<ProjectResponse>(`/api/projects/${encodeURIComponent(projectIdOrPath)}`, {
      timeoutMs: PROJECT_SWITCH_TIMEOUT_MS,
    }),
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
