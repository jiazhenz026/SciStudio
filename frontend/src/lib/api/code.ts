/**
 * Embedded code-editor endpoints: project file R/W, ruff lint, block
 * template scaffold (ADR-036).
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 * ADR-045 version-vector source-id headers added during main-merge (#1410).
 */

import { apiFetch, JSON_HEADERS } from "./core";
import {
  createClientSourceId,
  type ProjectFileResponse,
  type ProjectFileWriteResponse,
  type VersionedWriteOptions,
} from "./version";

export const codeApi = {
  // ADR-036 §3.2 — embedded code editor file R/W endpoints.
  getProjectFile: (projectId: string, path: string) =>
    apiFetch<ProjectFileResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
    ),
  putProjectFile: (
    projectId: string,
    path: string,
    content: string,
    options?: VersionedWriteOptions,
  ) => {
    const sourceId = options?.sourceId ?? createClientSourceId("file");
    return apiFetch<ProjectFileWriteResponse>(
      `/api/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`,
      {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({
          content,
          source: options?.source ?? "canvas",
          source_id: sourceId,
          create_parent_dirs: options?.createParentDirs ?? false,
        }),
      },
    );
  },
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
