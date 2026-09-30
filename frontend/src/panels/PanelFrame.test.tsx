import { bootstrapFrame } from "./testUtils";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, reply, type MockBackend } from "../__tests__/contract/mockBackend";
import { resetBasePathCacheForTests } from "../lib/api/base-path";
import { PANEL_RELOAD_DEBOUNCE_MS, PanelFrame } from "./PanelFrame";
import { notifyPanelContextsRevoked, notifyPanelFilesChanged } from "./panelEvents";
import type { PanelContext } from "./types";
import { useAppStore } from "../store";

const savePanelBytes = vi.hoisted(() => vi.fn());
vi.mock("./save", () => ({ savePanelBytes }));

const context: PanelContext = {
  context_id: "pc-1",
  bootstrap_proof: "a".repeat(64),
  panel: { id: "lab.image", api_version: "1.0", name: "lab.image" },
  kind: "preview",
  operations: ["read"],
  services: ["open", "save"],
  input: { ref: "data-1" },
  token: "secret",
  expires_at: 0,
  entry_url: "/api/panels/t/secret/assets/lab.image/index.html",
  sdk_url: "/api/panels/t/secret/sdk/1/scistudio-panel.js",
  lib_base_url: "/api/panels/t/secret/lib/",
};
let backend: MockBackend;
let createResult: () => unknown;
const channels: { port1: MessagePort; port2: MessagePort }[] = [];
beforeEach(() => {
  createResult = () => context;
  backend = mockBackend({
    "POST /api/panels/contexts": () => createResult(),
    "DELETE /api/panels/contexts/{context_id}": reply(204),
  });
  channels.length = 0;
  vi.stubGlobal(
    "MessageChannel",
    class {
      port1 = {
        onmessage: null,
        postMessage: vi.fn(),
        start: vi.fn(),
        close: vi.fn(),
      } as unknown as MessagePort;
      port2 = { close: vi.fn() } as unknown as MessagePort;
      constructor() {
        channels.push(this);
      }
    },
  );
});
afterEach(() => {
  cleanup();
  backend?.restore();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  delete window.__SCISTUDIO_BASE_PATH__;
  resetBasePathCacheForTests();
});
const request = {
  kind: "preview" as const,
  panel_id: "lab.image",
  target: { kind: "data_ref" as const, ref: "data-1" },
};
describe("PanelFrame", () => {
  it.each([
    [{ saved: true, destination: "file" }, 1],
    [{ saved: false, destination: "cancelled" }, 0],
  ])("reports plot_exported after a plot save (%o)", async (result, reports) => {
    createResult = () => ({ ...context, input: { ref: "plot-1", kind: "plot_artifact" } });
    savePanelBytes.mockResolvedValue(result);
    const report = vi.fn().mockResolvedValue(undefined);
    useAppStore.setState({ reportTutorialUiEvent: report });
    render(<PanelFrame request={request} />);
    const iframe = (await screen.findByTitle("lab.image")) as HTMLIFrameElement;
    bootstrapFrame(iframe);
    fireEvent.load(iframe);
    const port = channels[channels.length - 1].port1;
    await act(async () => {
      await port.onmessage?.({
        data: { v: 1, id: "r", type: "ready", payload: null },
      } as MessageEvent);
      await port.onmessage?.({
        data: {
          v: 1,
          id: "s",
          type: "save",
          payload: { name: "a.png", mime: "image/png", data: "x" },
        },
      } as MessageEvent);
    });
    expect(savePanelBytes).toHaveBeenCalledWith(expect.anything(), "pc-1");
    await waitFor(() => expect(report).toHaveBeenCalledTimes(reports));
    if (reports) expect(report).toHaveBeenCalledWith("plot_exported");
  });
  it("uses exact sandbox and prefix and transfers one intended port, then revokes on navigation", async () => {
    render(<PanelFrame request={request} />);
    const iframe = (await screen.findByTitle("lab.image")) as HTMLIFrameElement;
    expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
    expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(iframe.getAttribute("src")).toBe(context.entry_url);
    const post = vi.spyOn(iframe.contentWindow!, "postMessage");
    const bootstrap = bootstrapFrame(iframe);
    fireEvent.load(iframe);
    expect(post).not.toHaveBeenCalled();
    expect(bootstrap.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: "init", payload: expect.objectContaining({ basePath: "" }) }),
      [channels[0].port2],
    );
    fireEvent.load(iframe);
    expect(await screen.findByRole("alert")).toHaveTextContent("navigated");
    await waitFor(() =>
      expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}")).toHaveLength(1),
    );
    expect(channels[0].port1.close).toHaveBeenCalledTimes(1);
  });
  it("revokes a context whose create finishes after unmount", async () => {
    let resolve!: (value: PanelContext) => void;
    createResult = () =>
      new Promise((done) => {
        resolve = done;
      });
    const view = render(<PanelFrame request={request} />);
    view.unmount();
    await act(async () => {
      resolve(context);
    });
    await waitFor(() =>
      expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}")).toHaveLength(1),
    );
  });
  it("times out, offers explicit remount and core fallback", async () => {
    const fallback = vi.fn();
    render(<PanelFrame request={request} onFallback={fallback} />);
    const iframe = (await screen.findByTitle("lab.image")) as HTMLIFrameElement;
    bootstrapFrame(iframe);
    fireEvent.load(iframe);
    await act(async () => {
      channels[0].port1.onmessage?.({
        data: { v: 1, id: "e", type: "reportError", payload: "broken plot" },
      } as MessageEvent);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("lab.image: broken plot");
    fireEvent.click(screen.getByText("Use core preview"));
    expect(fallback).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Remount panel"));
    await waitFor(() => expect(backend.callsTo("POST /api/panels/contexts")).toHaveLength(2));
  });
  it("shows a ready timeout without requiring a frame load", async () => {
    vi.useFakeTimers();
    render(<PanelFrame request={request} />);
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(10001);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("10 seconds");
  });
});

it("never transfers input to a document without the first context-bound bootstrap", async () => {
  render(<PanelFrame request={request} />);
  const iframe = (await screen.findByTitle("lab.image")) as HTMLIFrameElement;
  const wrong = bootstrapFrame(iframe, "wrong-document-proof");
  const windowPost = vi.spyOn(iframe.contentWindow!, "postMessage");
  fireEvent.load(iframe);
  expect(channels).toHaveLength(0);
  expect(windowPost).not.toHaveBeenCalled();
  expect(wrong.postMessage).not.toHaveBeenCalled();
  const trusted = bootstrapFrame(iframe);
  expect(trusted.postMessage).toHaveBeenCalledOnce();
  const duplicate = bootstrapFrame(iframe);
  expect(duplicate.postMessage).not.toHaveBeenCalled();
  expect(channels).toHaveLength(1);
});

describe("#2465 — backend signals remount only the affected frame", () => {
  const created = () => backend.callsTo("POST /api/panels/contexts");

  it.each(["preview", "interactive"] as const)(
    "reloads a %s frame in place when its panel's page changes, debounced",
    async (kind) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const frameRequest =
        kind === "preview"
          ? request
          : { kind, panel_id: "lab.image", workflow_id: "wf", block_id: "b" };
      render(<PanelFrame request={frameRequest} />);
      await waitFor(() => expect(created()).toHaveLength(1));
      act(() => {
        notifyPanelFilesChanged("lab.image");
        notifyPanelFilesChanged("lab.other");
        notifyPanelFilesChanged("lab.image");
      });
      act(() => {
        vi.advanceTimersByTime(PANEL_RELOAD_DEBOUNCE_MS - 1);
      });
      expect(created()).toHaveLength(1);
      act(() => {
        vi.advanceTimersByTime(2);
      });
      await waitFor(() => expect(created()).toHaveLength(2));
      await waitFor(() =>
        expect(backend.callsTo("DELETE /api/panels/contexts/{context_id}")).toHaveLength(1),
      );
    },
  );

  it("ignores another panel's page change", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PanelFrame request={request} />);
    await waitFor(() => expect(created()).toHaveLength(1));
    act(() => notifyPanelFilesChanged("lab.other"));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(created()).toHaveLength(1);
  });

  it("remounts only when its own context is revoked", async () => {
    render(<PanelFrame request={request} />);
    await waitFor(() => expect(created()).toHaveLength(1));
    await screen.findByTitle("lab.image");
    act(() => notifyPanelContextsRevoked(["pc-other"]));
    expect(created()).toHaveLength(1);
    act(() => notifyPanelContextsRevoked(["pc-1"]));
    await waitFor(() => expect(created()).toHaveLength(2));
  });
});
