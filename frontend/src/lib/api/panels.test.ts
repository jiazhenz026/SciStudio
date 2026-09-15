import { afterEach, describe, expect, it, vi } from "vitest";
import { panelsApi } from "./panels";
import { PanelError } from "../../panels/types";
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
  /*
   * ADR-054 FR-016 / FR-011 — the call route answers three ways on HTTP 200:
   * a JSON result, a JSON author exception, and a binary NumPy array. Only the
   * first is a resolved promise.
   */
  it("resolves a JSON call result", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ result: { count: 3 } }),
    });
    vi.stubGlobal("fetch", fetch);
    expect(await panelsApi.call("pc-1", "threshold", { t: 0.4 })).toEqual({ count: 3 });
    expect(fetch.mock.lastCall![0]).toBe("/api/panels/contexts/pc-1/call");
    expect(JSON.parse(fetch.mock.lastCall![1].body)).toEqual({
      fn: "threshold",
      args: { t: 0.4 },
    });
  });

  it("rejects the HTTP-200 body a raising panel.py function returns", async () => {
    // US2 acceptance 3: the page receives the exception type and message, and
    // the process keeps running — so the backend answers 200, not an error
    // status, and `apiFetch` hands the body back as a success.
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({
        error: { type: "ValueError", message: "t must be finite", traceback: "…" },
      }),
    });
    vi.stubGlobal("fetch", fetch);
    await expect(panelsApi.call("pc-1", "threshold", {})).rejects.toMatchObject({
      name: "PanelError",
      code: "call_failed",
      message: "ValueError: t must be finite",
    });
  });

  it("returns a binary call result above the 8 MiB read cap", async () => {
    // US2 acceptance 2, and the hazard the read helper's cap creates: a call
    // result is budgeted at 64 MiB, so a 12 MiB array must not be refused.
    const binary = new ArrayBuffer(12 * 1024 * 1024);
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        "Content-Type": "application/octet-stream",
        "X-Panel-Dtype": "<f8",
        "X-Panel-Shape": "[512,3072]",
        "X-Panel-Metadata": '{"dtype":"<f8"}',
      }),
      body: new Response(binary).body,
    });
    vi.stubGlobal("fetch", fetch);
    const result = (await panelsApi.call("pc-1", "plane", {})) as Record<string, unknown>;
    expect(result.dtype).toBe("<f8");
    expect(result.shape).toEqual([512, 3072]);
    expect((result.data as ArrayBuffer).byteLength).toBe(binary.byteLength);
    expect(result).not.toBeInstanceOf(PanelError);
  });

  it("asks the process route for the status the toolbar shows", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ state: "running", pid: 42, resident_memory: 1048576 }),
    });
    vi.stubGlobal("fetch", fetch);
    expect(await panelsApi.processStatus("pc-1")).toEqual({
      state: "running",
      pid: 42,
      resident_memory: 1048576,
    });
    expect(fetch.mock.lastCall![0]).toBe("/api/panels/contexts/pc-1/process");
  });
});
