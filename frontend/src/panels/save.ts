import { isRecord, PanelError } from "./types";

export const DEFAULT_PANEL_SAVE_LIMIT = 100 * 1024 * 1024;
/** Browser download always targets the user's computer, including remote deployments. */
export async function savePanelBytes(payload: unknown, limit = DEFAULT_PANEL_SAVE_LIMIT) {
  if (!isRecord(payload) || typeof payload.name !== "string" || typeof payload.mime !== "string") {
    throw new PanelError("invalid_request", "Save requires name, mime and bytes");
  }
  const data = payload.data;
  if (!(data instanceof ArrayBuffer) && !ArrayBuffer.isView(data) && typeof data !== "string") {
    throw new PanelError("invalid_request", "Save data must be text or bytes");
  }
  const blob = new Blob([data as BlobPart], { type: payload.mime });
  if (blob.size > limit) throw new PanelError("size_limit", `Save exceeds the ${limit} byte limit`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = payload.name.split(/[\\/]/).pop() || "panel-export";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Downloads consume blob URLs asynchronously; retain briefly, then release.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { saved: true, destination: "download" };
}
