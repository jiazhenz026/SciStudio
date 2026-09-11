import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";
const source = readFileSync(new URL("../../../src/scistudio/panels/sdk/1/scistudio-panel.js", import.meta.url), "utf8");
function boot(standalone = false, sample = {}) {
  const listeners: Record<string, (event: unknown) => void> = {};
  const win: Record<string, unknown> = { location: { href: "https://example.test/panel/index.html" } };
  win.parent = standalone ? win : {};
  win.addEventListener = (type: string, cb: (event: unknown) => void) => { listeners[type] = cb; };
  win.removeEventListener = (type: string) => { delete listeners[type]; };
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => sample });
  const style = { setProperty: vi.fn() };
  const root = { style, dataset: {} };
  runInNewContext(source, { window: win, document: { documentElement: root }, fetch, URL, Map, Set, Promise, ArrayBuffer, setTimeout, clearTimeout });
  const api = win.scistudio as Record<string, (...args: unknown[]) => Promise<unknown>>;
  const port = { onmessage: null as null | ((event: unknown) => void), postMessage: vi.fn(), start: vi.fn(), close: vi.fn() };
  const init = (kind = "preview", sender = win.parent) => listeners.message?.({ source: sender, ports: [port], data: { v: 1, type: "init", payload: { context: kind, input: { ref: "data-1" }, operations: kind === "preview" ? ["read"] : ["writeBack"], services: ["open", "save"], theme: { mode: "dark", tokens: { "--ss-ink": "255 255 255" } } } });
  const response = (payload: unknown = null) => { const call = port.postMessage.mock.lastCall![0]; port.onmessage?.({ data: { v: 1, type: "result", id: call.id, payload } }); };
  return { win, api, port, init, response, listeners, fetch, root };
}
describe("dependency-free SDK", () => {
  it("accepts one parent init and ignores all later window replies", async () => {
    const { api, port, init, response, listeners, root } = boot();
    init("preview", {}); expect(port.start).not.toHaveBeenCalled();
    init(); expect(port.start).toHaveBeenCalledOnce();
    expect(listeners.message).toBeUndefined();
    expect(api.call).toBeUndefined(); expect(api.sync).toBeUndefined(); expect(api.writeBack).toBeUndefined();
    const ready = api.ready(); await Promise.resolve(); response(); await ready;
    const reading = api.read("array.plane", { format: "binary" });
    const bytes = new ArrayBuffer(8); response({ data: bytes });
    expect(await reading).toEqual({ data: bytes });
    expect(root.style.setProperty).toHaveBeenCalledWith("--ss-ink", "255 255 255");
  });
  it("applies themes and rejects pending requests on disposal", async () => {
    const { api, port, init, response, root } = boot(); init();
    const ready = api.ready(); await Promise.resolve(); response(); await ready;
    const pending = api.read("metadata");
    const rejected = expect(pending).rejects.toMatchObject({ code: "disposed" });
    port.onmessage?.({ data: { v: 1, type: "theme", payload: { mode: "light", tokens: { "--ss-ink": "0 0 0" } } } });
    expect(root.style.setProperty).toHaveBeenLastCalledWith("--ss-ink", "0 0 0");
    port.onmessage?.({ data: { v: 1, type: "dispose" } }); await rejected;
    expect(port.close).toHaveBeenCalledOnce();
  });
  it("exposes only writeBack in interactive mode and transfers save buffers", async () => {
    const { api, port, init, response } = boot(); init("interactive");
    const ready = api.ready(); await Promise.resolve(); response(); await ready;
    expect(api.read).toBeUndefined(); expect(api.open).toBeUndefined();
    const data = new ArrayBuffer(4); const saving = api.save({ name: "x", mime: "application/octet-stream", data });
    expect(port.postMessage.mock.lastCall![1]).toEqual([data]); response(); await saving;
  });
  it("loads panel.sample.json and answers read fixtures without any host", async () => {
    const { api, fetch } = boot(true, { context: "preview", input: { ref: "example" }, reads: { metadata: { type_name: "Image", complete: true } } });
    await api.ready();
    expect(String(fetch.mock.calls[0][0])).toBe("https://example.test/panel/panel.sample.json");
    expect(await api.read("metadata")).toEqual({ type_name: "Image", complete: true });
    await expect(api.read("table.page")).rejects.toMatchObject({ code: "not_found" });
  });
});
