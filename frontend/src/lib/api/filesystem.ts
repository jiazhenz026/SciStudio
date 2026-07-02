/**
 * Filesystem browsing + native-dialog endpoints.
 *
 * Extracted from `frontend/src/lib/api.ts` (#1422).
 */

import type { FilesystemBrowseResponse, FilesystemStatResponse } from "../../types/api";
import { apiFetch, JSON_HEADERS } from "./core";

export const filesystemApi = {
  browseFilesystem: (path: string) =>
    apiFetch<FilesystemBrowseResponse>(`/api/filesystem/browse?path=${encodeURIComponent(path)}`),
  statFilesystem: (path: string) =>
    apiFetch<FilesystemStatResponse>(`/api/filesystem/stat?path=${encodeURIComponent(path)}`),
  revealInExplorer: (path: string) =>
    apiFetch<{ status: string }>("/api/filesystem/reveal", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ path }),
    }),
  // `preferHome` opens the dialog at the last-used location / user home instead
  // of the active project root (#1915) — used only by the create/open-project
  // and diagnostic-export dialogs, which pick a location outside any project.
  openNativeDialog: (mode: "file" | "directory", initialDir?: string, preferHome?: boolean) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ mode, initial_dir: initialDir, prefer_home: preferHome }),
    }),
  openNativeSaveDialog: (options: {
    initialDir?: string;
    defaultFilename?: string;
    fileFilter?: string;
    preferHome?: boolean;
  }) =>
    apiFetch<{ paths: string[]; available?: boolean }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        mode: "save_file",
        initial_dir: options.initialDir,
        default_filename: options.defaultFilename,
        file_filter: options.fileFilter,
        prefer_home: options.preferHome,
      }),
    }),
};
