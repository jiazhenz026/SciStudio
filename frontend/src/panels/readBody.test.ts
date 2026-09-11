import { afterEach, describe, expect, it, vi } from "vitest";
import { readPanelBody } from "./readBody";
afterEach(() => vi.useRealTimers());
describe("panel body consumption", () => {
  it("times out and cancels a body that stalls after response headers", async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    const response = new Response(new ReadableStream({ cancel }));
    const body = readPanelBody(response, { limit: 1024, timeoutMs: 10 });
    const rejected = expect(body).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(11);
    await rejected;
    expect(cancel).toHaveBeenCalledOnce();
  });
  it("unmount cancellation interrupts a pending reader.read after headers", async () => {
    const controller = new AbortController();
    const cancel = vi.fn();
    const response = new Response(new ReadableStream({ cancel }));
    const body = readPanelBody(response, { signal: controller.signal, limit: 1024 });
    const rejected = expect(body).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await rejected;
    expect(cancel).toHaveBeenCalledOnce();
  });
  it("rejects oversized numeric chunks even if the server omits a length", async () => {
    const response = new Response(new Uint8Array(9));
    await expect(readPanelBody(response, { limit: 8 })).rejects.toMatchObject({
      code: "size_limit",
    });
  });
});
