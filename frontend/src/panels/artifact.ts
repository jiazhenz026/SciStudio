import { apiFetch } from "../lib/api/core";
import { apiUrl } from "../lib/api/base-path";
import { PanelError } from "./types";

export const DEFAULT_PANEL_ARTIFACT_LIMIT = 100 * 1024 * 1024;

/** Host-only hydration: opaque panel frames cannot fetch under connect-src none. */
export async function materializePanelArtifact(
  metadata: Record<string, unknown>,
  signal?: AbortSignal,
  limit = DEFAULT_PANEL_ARTIFACT_LIMIT,
): Promise<Record<string, unknown>> {
  if (typeof metadata.url !== "string")
    throw new PanelError("invalid_response", "Artifact response has no grant URL");
  const raw = metadata.url;
  if (!raw.startsWith("/") || raw.startsWith("//"))
    throw new PanelError("forbidden", "Artifact grant must be a local route");
  const url = new URL(apiUrl(raw), window.location.origin);
  const prefix = apiUrl("/api/panels/t/");
  const suffix = url.pathname.startsWith(prefix) ? url.pathname.slice(prefix.length) : "";
  if (
    url.origin !== window.location.origin ||
    url.search ||
    url.hash ||
    !/^[A-Za-z0-9_-]+\/artifact\/[a-f0-9]+$/.test(suffix)
  ) {
    throw new PanelError("forbidden", "Artifact grant is outside the panel artifact route");
  }
  if (typeof metadata.size === "number" && metadata.size > limit)
    throw new PanelError("size_limit", `Artifact exceeds the ${limit} byte limit`);
  const response = await apiFetch<Response>(url.pathname, {
    responseType: "response",
    signal,
    redirect: "error",
    timeoutMs: 30000,
  });
  if (Number(response.headers.get("Content-Length")) > limit) {
    await response.body?.cancel();
    throw new PanelError("size_limit", `Artifact exceeds the ${limit} byte limit`);
  }
  if (!response.body) throw new PanelError("invalid_response", "Artifact response has no body");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      signal?.throwIfAborted();
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new PanelError("size_limit", `Artifact exceeds the ${limit} byte limit`);
      }
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  signal?.throwIfAborted();
  const data = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    data.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const { url: _grant, ...info } = metadata;
  return {
    ...info,
    mime_type:
      metadata.mime_type ?? response.headers.get("Content-Type") ?? "application/octet-stream",
    data: data.buffer,
  };
}
