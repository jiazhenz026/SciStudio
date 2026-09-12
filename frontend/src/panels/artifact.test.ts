import { afterEach, describe, expect, it, vi } from "vitest";
import { materializePanelArtifact } from "./artifact";
import { resetBasePathCacheForTests } from "../lib/api/base-path";
import { panelsApi } from "../lib/api/panels";
const grant = "/api/panels/t/authorized-token/artifact/0123456789abcdef0123456789abcdef";
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__SCISTUDIO_BASE_PATH__;
  resetBasePathCacheForTests();
});
describe("host-mediated artifacts under connect-src none", () => {
  it.each(["", "/user/alice/scistudio"])(
    "fetches only the exact authorized grant through the host client at %s",
    async (prefix) => {
      window.__SCISTUDIO_BASE_PATH__ = prefix;
      resetBasePathCacheForTests();
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              url: prefix + grant,
              name: "image.png",
              mime_type: "image/png",
              size: 3,
              complete: true,
            }),
            { headers: { "Content-Type": "application/json" } },
          ),
        )
        .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3])));
      vi.stubGlobal("fetch", fetch);
      const result = await panelsApi.read("pc-1", "image-1", "artifact.file", {});
      expect(result).toMatchObject({ name: "image.png", mime_type: "image/png", complete: true });
      expect(new Uint8Array(result.data as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
      expect(result.url).toBeUndefined();
      expect(fetch.mock.lastCall![0]).toBe(prefix + grant);
      expect(fetch.mock.lastCall![1].headers.get("X-Request-ID")).toBeTruthy();
      expect(fetch.mock.lastCall![1].redirect).toBe("error");
    },
  );
  it.each([
    "https://attacker.test/file",
    "//attacker.test/file",
    "/api/filesystem/read",
    "/api/panels/t/token/assets/panel/file",
    grant + "?path=/secret",
  ])("refuses a non-grant URL %s", async (url) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(materializePanelArtifact({ url })).rejects.toMatchObject({ code: "forbidden" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("caps actual streamed bytes when Content-Length is absent and cancels the stream", async () => {
    const cancel = vi.fn();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array(9));
      },
      cancel,
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    await expect(materializePanelArtifact({ url: grant }, undefined, 8)).rejects.toMatchObject({
      code: "size_limit",
    });
    expect(cancel).toHaveBeenCalled();
  });
  it("does not start an oversized metadata request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      materializePanelArtifact({ url: grant, size: 9 }, undefined, 8),
    ).rejects.toMatchObject({ code: "size_limit" });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("passes mount cancellation through the shared authenticated fetch", async () => {
    const controller = new AbortController();
    const fetch = vi.fn(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const reading = materializePanelArtifact({ url: grant }, controller.signal);
    const rejected = expect(reading).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await rejected;
  });
});
