/**
 * The user-wide library file endpoints, `~/.scistudio/` (ADR-053 §4).
 *
 * Spec: docs/specs/adr-053-personal-tool-library.md §4 (FR-006 – FR-010),
 *       §6 (FR-018), §8 (FR-030, FR-031).
 *
 * The backend router (`src/scistudio/api/routes/user_library.py`) deliberately
 * mirrors the project file endpoint's error shapes so one frontend error path
 * serves both destinations: 400 for an empty name, 403 for traversal and
 * escape, 413 over the editor cap, 415 for a non-`.py` extension, 404 when a
 * read finds nothing. The one addition is **409 for a collision** (FR-008),
 * which is what drives the FR-018 overwrite / save-as-new-name prompt — the UI
 * never guesses at a collision it has not been told about.
 *
 * `GET` is the FR-031 existence probe. It is the same 200/404 shape as
 * `GET /api/projects/{id}/file`, which is why `probeUserLibraryFileExistence`
 * in `lib/fileExistence.ts` is `probeProjectFileExistence` with a different
 * call rather than a second probe protocol.
 */

import type {
  UserLibraryFileResponse,
  UserLibraryTarget,
  UserLibraryWriteResponse,
} from "../../types/api";

import { apiFetch, JSON_HEADERS } from "./core";

function fileUrl(target: UserLibraryTarget, filename: string): string {
  return `/api/user-library/file?target=${encodeURIComponent(target)}&filename=${encodeURIComponent(filename)}`;
}

export const userLibraryApi = {
  /**
   * Read one user library file. 404 means "not there" — the FR-031 probe reads
   * exactly that, and nothing else, as "safe to create".
   */
  getUserLibraryFile: (target: UserLibraryTarget, filename: string) =>
    apiFetch<UserLibraryFileResponse>(fileUrl(target, filename)),
  /**
   * Write one user library file.
   *
   * `overwrite` defaults to `false`, so an existing destination comes back as
   * a 409 the caller must resolve with the user (FR-008/FR-018). Passing
   * `true` is the "overwrite" half of that prompt and never a default.
   *
   * `moveFrom` is FR-017: the project file this write replaces. The server
   * removes it *after* the write lands, which is what makes promotion a move.
   * It is a field on this request rather than a separate delete call on
   * purpose — there is then no way to reach the removal except by having
   * successfully written that content somewhere else first, and the product
   * grows no general "delete a project file" endpoint.
   */
  putUserLibraryFile: (
    target: UserLibraryTarget,
    filename: string,
    content: string,
    options?: { overwrite?: boolean; moveFrom?: { projectId: string; path: string } | null },
  ) =>
    apiFetch<UserLibraryWriteResponse>(fileUrl(target, filename), {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        content,
        overwrite: options?.overwrite ?? false,
        move_from: options?.moveFrom
          ? { project_id: options.moveFrom.projectId, path: options.moveFrom.path }
          : null,
      }),
    }),
};
