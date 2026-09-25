import { filesystemApi } from "../lib/api/filesystem";
import { panelsApi } from "../lib/api/panels";
import { isRecord, PanelError } from "./types";

export const DEFAULT_PANEL_SAVE_LIMIT = 100 * 1024 * 1024;

/** The native dialog's type filter for a file name, by its extension. */
export function saveFileFilter(filename: string): string {
  const match = /\.([A-Za-z0-9]+)$/.exec(filename);
  if (!match) return "All files (*.*)|*.*";
  const extension = match[1].toLowerCase();
  return `${extension.toUpperCase()} (*.${extension})|*.${extension}|All files (*.*)|*.*`;
}

/**
 * Save a panel's file for the user.
 *
 * The native save dialog runs first; it opens in the project root. The bytes
 * go to the path it returned. A cancelled dialog saves nothing. Only when no
 * native dialog is available (a remote browser session) does the file fall
 * back to a browser download, which always targets the user's computer.
 */
export async function savePanelBytes(
  payload: unknown,
  contextId?: string,
  limit = DEFAULT_PANEL_SAVE_LIMIT,
) {
  if (!isRecord(payload) || typeof payload.name !== "string" || typeof payload.mime !== "string") {
    throw new PanelError("invalid_request", "Save requires name, mime and bytes");
  }
  const data = payload.data;
  if (!(data instanceof ArrayBuffer) && !ArrayBuffer.isView(data) && typeof data !== "string") {
    throw new PanelError("invalid_request", "Save data must be text or bytes");
  }
  const blob = new Blob([data as BlobPart], { type: payload.mime });
  if (blob.size > limit) throw new PanelError("size_limit", `Save exceeds the ${limit} byte limit`);
  const name = payload.name.split(/[\\/]/).pop() || "panel-export";

  if (contextId) {
    const dialog = await filesystemApi
      .openNativeSaveDialog({ defaultFilename: name, fileFilter: saveFileFilter(name) })
      .catch(() => ({ paths: [] as string[], available: false }));
    const path = dialog.paths[0];
    if (path) {
      const written = await panelsApi.save(contextId, path, blob);
      return { saved: true, destination: "file", path: written.path };
    }
    if (dialog.available !== false) return { saved: false, destination: "cancelled" };
  }

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Downloads consume blob URLs asynchronously; retain briefly, then release.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { saved: true, destination: "download" };
}
