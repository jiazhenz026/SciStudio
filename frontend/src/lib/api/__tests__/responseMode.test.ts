import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, ApiError, ApiTimeoutError } from "../core";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe("apiFetch response mode compatibility", () => {
  it("keeps default JSON and 204 semantics, returning raw Response only when requested", async () => {
    const json = new Response('{"ok":true}', {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const empty = new Response(null, { status: 204 });
    const bytes = new Response(new Uint8Array([1, 2]), { status: 200 });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(json).mockResolvedValueOnce(empty).mockResolvedValueOnce(bytes),
    );
    expect(await apiFetch("/api/version")).toEqual({ ok: true });
    expect(await apiFetch("/api/version")).toBeUndefined();
    const result = await apiFetch<Response>("/api/version", { responseType: "response" });
    expect(result).toBe(bytes);
    expect(new Uint8Array(await result.arrayBuffer())).toEqual(new Uint8Array([1, 2]));
  });
  it("preserves status errors for raw responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"detail":{"message":"Denied"}}', { status: 403 })),
    );
    await expect(apiFetch("/api/version", { responseType: "response" })).rejects.toBeInstanceOf(
      ApiError,
    );
  });
  it("preserves deadline cancellation for raw responses", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, options) =>
          new Promise((_resolve, reject) => {
            options.signal.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      ),
    );
    const result = apiFetch("/api/version", { responseType: "response", timeoutMs: 10 });
    const assertion = expect(result).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(11);
    await assertion;
  });
});
