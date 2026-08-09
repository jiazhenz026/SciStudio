/**
 * Embedded code-editor endpoints: project file R/W, ruff lint, block
 * template scaffold (ADR-036).
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 * ADR-045 version-vector source-id headers added during main-merge (#1410).
 */

import type { TypeListResponse, TypeSourceResponse, TypeTemplateResponse } from "../../types/api";

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
  // ADR-053 FR-026 — the registered data type listing. The single source of
  // type colour for the product (FR-050): both the Data types tab and canvas
  // port colour read declared colours from here, so the two surfaces cannot
  // disagree (FR-066). Independent of the block listing (FR-027) — refreshing
  // types never means refreshing the palette.
  listTypes: () => apiFetch<TypeListResponse>("/api/types/"),
  // ADR-053 FR-062 — a real backend re-scan, the Data types tab's counterpart
  // of `POST /api/blocks/reload`. `listTypes` answers from the in-memory
  // registry and costs no scan, so without this the tab's Reload button could
  // not show a type the user had just written to `{project}/types/`.
  reloadTypes: () =>
    apiFetch<{ reloaded: number; added: string[]; removed: string[] }>("/api/types/reload", {
      method: "POST",
    }),
  // ADR-053 FR-068 — read-only source for a core or packaged type, the type-side
  // twin of `getBlockSource`. A project or user-library type does NOT come
  // through here: it opens through its own tier's editable path, because this
  // response carries an absolute path and no save route accepts one.
  getTypeSource: (typeName: string) =>
    apiFetch<TypeSourceResponse>(`/api/types/${encodeURIComponent(typeName)}/source`),
  // ADR-053 FR-028 — data type template scaffold, byte-identical in shape to
  // `getBlockTemplate` so the new-block and new-data-type flows share their
  // fetch/write/open steps (FR-033).
  getTypeTemplate: (kind: string = "basic") =>
    apiFetch<TypeTemplateResponse>(`/api/types/template?kind=${encodeURIComponent(kind)}`),
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
