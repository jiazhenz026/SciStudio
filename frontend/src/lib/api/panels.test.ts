import { afterEach, describe, expect, it, vi } from "vitest";
import { panelsApi } from "./panels";
import { resetBasePathCacheForTests } from "./base-path";
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__SCISTUDIO_BASE_PATH__;
  resetBasePathCacheForTests();
});
describe("guarded panel client", () => {
  it.each(["", "/user/alice/scistudio"])(
    "keeps JSON and binary operations behind the shared prefix/auth client at %s",
    async (prefix) => {
      window.__SCISTUDIO_BASE_PATH__ = prefix;
      resetBasePathCacheForTests();
      const binary = new ArrayBuffer(8);
      const fetch = vi
        .fn()
        .mockResolvedValue({ ok: true, status: 200, json: async () => ({ context_id: "pc-1" }) });
      vi.stubGlobal("fetch", fetch);
      await panelsApi.create({ kind: "preview", target: { kind: "data_ref", ref: "data-1" } });
      expect(fetch.mock.calls[0][0]).toBe(`${prefix}/api/panels/contexts`);
      expect(fetch.mock.calls[0][1].headers.get("X-Request-ID")).toBeTruthy();
      await panelsApi.open("pc-1", "composite#slot");
      expect(fetch.mock.lastCall![0]).toBe(`${prefix}/api/panels/contexts/pc-1/open`);
      expect(fetch.mock.lastCall![1].headers.get("X-Request-ID")).toBeTruthy();
      expect(JSON.parse(fetch.mock.lastCall![1].body)).toEqual({ ref: "composite#slot" });
      fetch.mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({
          "Content-Type": "application/octet-stream",
          "X-Panel-Dtype": "float32",
          "X-Panel-Shape": "[2]",
          "X-Panel-Metadata": '{"complete":true}',
        }),
        body: new Response(binary).body,
      });
      expect(await panelsApi.read("pc-1", "data-1", "array.plane", { format: "binary" })).toEqual({
        data: binary,
        dtype: "float32",
        shape: [2],
        complete: true,
      });
      expect(fetch.mock.lastCall![0]).toBe(`${prefix}/api/panels/contexts/pc-1/read`);
      expect(fetch.mock.lastCall![1].headers.get("X-Request-ID")).toBeTruthy();
    },
  );
});
