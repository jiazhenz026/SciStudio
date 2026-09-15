import { describe, expect, it, vi } from "vitest";
import { createPanelBridge } from "./bridge";
import type { PanelContext } from "./types";

export const context: PanelContext = {
  context_id: "pc-1",
  bootstrap_proof: "proof",
  panel: { id: "lab.image", api_version: "1.0" },
  kind: "preview",
  operations: ["read"],
  services: ["open", "save"],
  input: { ref: "data-1" },
  token: "secret",
  expires_at: 9999999999,
  entry_url: "/api/panels/t/secret/assets/lab.image/index.html",
  sdk_url: "/api/panels/t/secret/sdk/1/scistudio-panel.js",
  lib_base_url: "/api/panels/t/secret/lib/",
};
export function fakePort() {
  return {
    postMessage: vi.fn(),
    start: vi.fn(),
    close: vi.fn(),
    onmessage: null,
    onmessageerror: null,
  } as unknown as MessagePort;
}
/** What `PanelContext.provides()` grants each kind (contexts.py:68-75). */
const PROVIDES = {
  preview: { operations: ["read"], services: ["open", "save"] },
  interactive: { operations: ["writeBack"], services: ["save"] },
  // ADR-054 FR-004 — a miniapp reads AND calls, and has no `open`.
  miniapp: { operations: ["read", "call"], services: ["save"] },
} as const;

function setup(kind: "preview" | "interactive" | "miniapp" = "preview") {
  const port = fakePort();
  const handlers = {
    read: vi.fn().mockResolvedValue({ complete: true }),
    open: vi.fn().mockResolvedValue(null),
    writeBack: vi.fn().mockResolvedValue(null),
    call: vi.fn().mockResolvedValue({ ok: true }),
    save: vi.fn().mockResolvedValue(null),
    viewState: vi.fn(),
    resize: vi.fn(),
    ready: vi.fn(),
    failure: vi.fn(),
  };
  const bridge = createPanelBridge(
    port,
    {
      ...context,
      kind,
      operations: [...PROVIDES[kind].operations],
      services: [...PROVIDES[kind].services],
    },
    handlers,
  );
  const send = async (type: string, payload: unknown = null, id = type) => {
    await port.onmessage?.({ data: { v: 1, id, type, payload } } as MessageEvent);
  };
  return { port, handlers, bridge, send };
}
describe("panel port bridge", () => {
  it("provides preview reads only after ready and refuses unsupported operations", async () => {
    const { send, port, handlers } = setup();
    await send("read", { op: "metadata", params: {} });
    expect(handlers.read).not.toHaveBeenCalled();
    await send("ready");
    await send("read", { op: "metadata", params: {} });
    expect(handlers.read).toHaveBeenCalledWith("data-1", "metadata", {});
    // ADR-054 FR-016 — a preview context is granted `["read"]` only, so `call`
    // is refused here even though the host wires a call handler.
    for (const type of ["writeBack", "call", "sync"]) {
      await send(type, {});
      expect(port.postMessage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          type: "error",
          payload: expect.objectContaining({ code: "unsupported" }),
        }),
        [],
      );
    }
  });
  it("provides miniapp read and call, and still denies open and writeBack", async () => {
    // ADR-054 FR-004 / FR-016 — the backend grants a miniapp context
    // `["read","call"]`, so the host must honour both; `open` and `writeBack`
    // are not granted and stay refused.
    const { send, port, handlers } = setup("miniapp");
    await send("ready");
    await send("read", { op: "metadata", params: {} });
    expect(handlers.read).toHaveBeenCalledWith("data-1", "metadata", {});
    await send("call", { fn: "threshold", args: { t: 0.4 } });
    expect(handlers.call).toHaveBeenCalledWith("threshold", { t: 0.4 });
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: "result", payload: { ok: true } }),
      [],
    );
    for (const type of ["open", "writeBack", "sync"]) {
      await send(type, { ref: "child" });
      expect(port.postMessage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          type: "error",
          payload: expect.objectContaining({ code: "unsupported" }),
        }),
        [],
      );
    }
    expect(handlers.open).not.toHaveBeenCalled();
    expect(handlers.writeBack).not.toHaveBeenCalled();
  });
  it("refuses a call without a function name", async () => {
    const { send, port, handlers } = setup("miniapp");
    await send("ready");
    await send("call", { fn: "", args: {} });
    expect(handlers.call).not.toHaveBeenCalled();
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "error",
        payload: expect.objectContaining({ code: "invalid_request" }),
      }),
      [],
    );
  });
  it("claims interactive decisions once and denies read/open/call/sync", async () => {
    const { send, port, handlers } = setup("interactive");
    await send("ready");
    await send("writeBack", { selected: [1] });
    await send("writeBack", { selected: [2] });
    expect(handlers.writeBack).toHaveBeenCalledTimes(1);
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ payload: expect.objectContaining({ code: "already_used" }) }),
      [],
    );
    for (const type of ["read", "open", "call", "sync"]) await send(type, {});
    expect(handlers.read).not.toHaveBeenCalled();
    expect(handlers.open).not.toHaveBeenCalled();
    // ADR-054 FR-016 — `call` belongs to miniapp contexts alone. The handler
    // is wired here, so this asserts the gate, not a missing handler.
    expect(handlers.call).not.toHaveBeenCalled();
  });
  it("transfers binary buffers and ignores window messages", async () => {
    const { send, port, handlers } = setup();
    const data = new ArrayBuffer(8);
    handlers.read.mockResolvedValue({ data, dtype: "float32", shape: [2] });
    window.dispatchEvent(
      new MessageEvent("message", { data: { v: 1, id: "rogue", type: "read", payload: {} } }),
    );
    expect(handlers.read).not.toHaveBeenCalled();
    await send("ready");
    await send("read", { op: "array.plane", params: { format: "binary" } });
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ payload: expect.objectContaining({ data }) }),
      [data],
    );
  });
  it("drops in-flight replies after disposal and closes the port once", async () => {
    const { send, port, handlers, bridge } = setup();
    let resolve!: (value: unknown) => void;
    handlers.read.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    await send("ready");
    const reading = send("read", { op: "metadata", params: {} });
    bridge.dispose();
    bridge.dispose();
    resolve({ complete: true });
    await reading;
    expect(port.close).toHaveBeenCalledTimes(1);
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: "dispose" }),
      [],
    );
  });
  it("validates JSON state and clamps requested height", async () => {
    const { send, handlers, port } = setup();
    await send("ready");
    await send("viewState", { zoom: Infinity });
    expect(handlers.viewState).not.toHaveBeenCalled();
    await send("viewState", { zoom: 2 });
    expect(handlers.viewState).toHaveBeenCalledWith({ zoom: 2 });
    await send("resize", { height: 999999 });
    expect(handlers.resize).toHaveBeenCalledWith(4096);
    await send("read", { op: "filesystem.read", params: {} });
    expect(port.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ payload: expect.objectContaining({ code: "invalid_request" }) }),
      [],
    );
  });
});
