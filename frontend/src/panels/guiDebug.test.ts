import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { guiDebugHello, handleGuiDebugRequest } from "./guiDebug";

const state = vi.hoisted(() => ({ currentProject: { path: "/project/a" }, activeTabId: "a" }));
const listeners = vi.hoisted(() => new Set<(state: unknown, previous: unknown) => void>());
vi.mock("../store", () => ({
  useAppStore: {
    getState: () => state,
    subscribe: (listener: (state: unknown, previous: unknown) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  },
}));

const capture = vi.fn();
const request = {
  type: "gui.debug.request",
  request_id: "one",
  project: "/project/a",
  action: "screenshot",
  target: "miniapp",
  wait_ms: 0,
};
function pane(panelId = "array", contextId = "context-a") {
  const node = document.createElement("div");
  node.dataset.guiMiniapp = "";
  node.dataset.panelId = panelId;
  node.dataset.contextId = contextId;
  node.dataset.processState = "running";
  node.innerHTML = '<div data-panel-ready="true"><canvas></canvas></div>';
  node.getBoundingClientRect = () =>
    ({ left: 10, top: 20, right: 410, bottom: 320, width: 400, height: 300 }) as DOMRect;
  document.body.append(node);
  return node;
}

beforeEach(() => {
  state.currentProject = { path: "/project/a" };
  capture.mockReset().mockResolvedValue({ png_base64: "pixels", width: 400, height: 300 });
  Object.defineProperty(window, "scistudioDesktop", {
    configurable: true,
    value: { captureGui: capture },
  });
});
afterEach(() => {
  document.body.innerHTML = "";
  delete window.scistudioDesktop;
});

describe("read-only project-bound GUI screenshots", () => {
  it("invalidates tab A to B to A even when final target metadata matches", async () => {
    pane();
    const reply = vi.fn();
    capture.mockImplementation(async () => {
      listeners.forEach((listener) => listener({ ...state, activeTabId: "b" }, state));
      listeners.forEach((listener) => listener(state, { ...state, activeTabId: "b" }));
      return { png_base64: "wrong-tab", width: 400, height: 300 };
    });
    await handleGuiDebugRequest(request, reply);
    expect(reply).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.objectContaining({ code: "gui_changed" }) }),
    );
    expect(listeners.size).toBe(0);
  });
  it("captures the visible MiniApp region and observed readiness", async () => {
    pane();
    const reply = vi.fn();
    await handleGuiDebugRequest(request, reply);
    expect(capture).toHaveBeenCalledWith({ rect: { x: 10, y: 20, width: 400, height: 300 } });
    expect(reply).toHaveBeenCalledWith(
      expect.objectContaining({
        context_id: "context-a",
        panel_id: "array",
        state: "ready",
        process_state: "running",
        png_base64: "pixels",
      }),
    );
  });
  it("rejects old project requests and hidden/unknown tabs without capturing", async () => {
    const hidden = pane();
    hidden.getBoundingClientRect = () => ({ width: 0, height: 0 }) as DOMRect;
    const reply = vi.fn();
    await handleGuiDebugRequest(request, reply);
    expect(reply).toHaveBeenLastCalledWith(
      expect.objectContaining({ error: expect.objectContaining({ code: "target_not_visible" }) }),
    );
    await handleGuiDebugRequest({ ...request, project: "/project/old" }, reply);
    expect(reply).toHaveBeenLastCalledWith(
      expect.objectContaining({ error: expect.objectContaining({ code: "project_changed" }) }),
    );
    expect(capture).not.toHaveBeenCalled();
  });
  it("discards pixels if the project or target switches during compositor capture", async () => {
    const node = pane();
    const reply = vi.fn();
    capture.mockImplementation(async () => {
      node.dataset.contextId = "new-context";
      return { png_base64: "secret", width: 400, height: 300 };
    });
    await handleGuiDebugRequest(request, reply);
    expect(reply).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.objectContaining({ code: "gui_changed" }) }),
    );
    expect(JSON.stringify(reply.mock.calls)).not.toContain("secret");
  });
  it("does not advertise browser-only screenshot capability", async () => {
    delete window.scistudioDesktop;
    expect(guiDebugHello()).toMatchObject({ project: "/project/a", screenshot: false });
    const reply = vi.fn();
    await handleGuiDebugRequest(request, reply);
    expect(reply).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.objectContaining({ code: "unsupported_gui" }) }),
    );
  });
});
