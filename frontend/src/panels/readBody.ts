import { PanelError } from "./types";

/** Bound the body itself: the shared HTTP client's deadline ends at headers. */
export async function readPanelBody(
  response: Response,
  { signal, limit, timeoutMs = 30000 }: { signal?: AbortSignal; limit: number; timeoutMs?: number },
): Promise<ArrayBuffer> {
  signal?.throwIfAborted();
  if (Number(response.headers.get("Content-Length")) > limit) {
    await response.body?.cancel();
    throw new PanelError("size_limit", `Panel response exceeds the ${limit} byte limit`);
  }
  if (!response.body) throw new PanelError("invalid_response", "Panel response has no body");
  const reader = response.body.getReader();
  let failure: unknown;
  const abort = (reason: unknown) => {
    failure = reason;
    void reader.cancel().catch(() => {});
  };
  const onAbort = () => abort(signal?.reason ?? new DOMException("Aborted", "AbortError"));
  signal?.addEventListener("abort", onAbort, { once: true });
  const timer = setTimeout(
    () => abort(new PanelError("timeout", "Panel response body timed out")),
    timeoutMs,
  );
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      if (failure) throw failure;
      const { done, value } = await reader.read();
      if (failure) throw failure;
      if (done) break;
      length += value.byteLength;
      if (length > limit)
        throw new PanelError("size_limit", `Panel response exceeds the ${limit} byte limit`);
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
    reader.releaseLock();
  }
  signal?.throwIfAborted();
  const data = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    data.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return data.buffer;
}
