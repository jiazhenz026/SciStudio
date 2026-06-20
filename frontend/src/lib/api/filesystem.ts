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
  openNativeDialog: (mode: "file" | "directory", initialDir?: string) =>
    apiFetch<{ paths: string[] }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ mode, initial_dir: initialDir }),
    }),
  openNativeSaveDialog: (options: {
    initialDir?: string;
    defaultFilename?: string;
    fileFilter?: string;
  }) =>
    apiFetch<{ paths: string[]; available?: boolean }>("/api/filesystem/native-dialog", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        mode: "save_file",
        initial_dir: options.initialDir,
        default_filename: options.defaultFilename,
        file_filter: options.fileFilter,
      }),
    }),
};
