import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { panelsApi } from "../lib/api/panels";
import { resetBasePathCacheForTests } from "../lib/api/base-path";
import { PanelFrame } from "./PanelFrame";
import type { PanelContext } from "./types";
vi.mock("../lib/api/panels", () => ({ panelsApi: { create: vi.fn(), close: vi.fn(), read: vi.fn(), renew: vi.fn() } }));
const context: PanelContext = { context_id: "pc-1", panel: { id: "lab.image", api_version: "1.0" }, kind: "preview", operations: ["read"], services: ["open", "save"], input: { ref: "data-1" }, token: "secret", expires_at: 0, entry_url: "/api/panels/t/secret/assets/lab.image/index.html", sdk_url: "/api/panels/t/secret/sdk/1/scistudio-panel.js", lib_base_url: "/api/panels/t/secret/lib/" };
const channels: { port1: MessagePort; port2: MessagePort }[] = [];
beforeEach(() => {
  vi.mocked(panelsApi.create).mockResolvedValue(context);
  vi.mocked(panelsApi.close).mockResolvedValue(undefined);
  channels.length = 0;
  vi.stubGlobal("MessageChannel", class {
    port1 = { onmessage: null, postMessage: vi.fn(), start: vi.fn(), close: vi.fn() } as unknown as MessagePort;
    port2 = { close: vi.fn() } as unknown as MessagePort;
    constructor() { channels.push(this); }
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); delete window.__SCISTUDIO_BASE_PATH__; resetBasePathCacheForTests(); });
const request = { kind: "preview" as const, panel_id: "lab.image", target: { kind: "data_ref" as const, ref: "data-1" } };
describe("PanelFrame", () => {
  it("uses exact sandbox and prefix and transfers one intended port, then revokes on navigation", async () => {
    window.__SCISTUDIO_BASE_PATH__ = "/user/alice/scistudio"; resetBasePathCacheForTests();
    render(<PanelFrame request={request} />);
    const iframe = await screen.findByTitle("lab.image") as HTMLIFrameElement;
    expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
    expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(iframe.getAttribute("src")).toBe("/user/alice/scistudio" + context.entry_url);
    const post = vi.spyOn(iframe.contentWindow!, "postMessage");
    fireEvent.load(iframe);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(expect.objectContaining({ type: "init", payload: expect.objectContaining({ basePath: "/user/alice/scistudio" }) }), "*", [channels[0].port2]);
    fireEvent.load(iframe);
    expect(await screen.findByRole("alert")).toHaveTextContent("navigated");
    expect(panelsApi.close).toHaveBeenCalledWith("pc-1");
    expect(channels[0].port1.close).toHaveBeenCalledTimes(1);
  });
  it("revokes a context whose create finishes after unmount", async () => {
    let resolve!: (value: PanelContext) => void;
    vi.mocked(panelsApi.create).mockReturnValue(new Promise((done) => { resolve = done; }));
    const view = render(<PanelFrame request={request} />); view.unmount();
    await act(async () => { resolve(context); });
    expect(panelsApi.close).toHaveBeenCalledWith("pc-1");
  });
  it("times out, offers explicit remount and core fallback", async () => {
    const fallback = vi.fn(); render(<PanelFrame request={request} onFallback={fallback} />);
    const iframe = await screen.findByTitle("lab.image");
    fireEvent.load(iframe);
    await act(async () => { channels[0].port1.onmessage?.({ data: { v: 1, id: "e", type: "reportError", payload: "broken plot" } } as MessageEvent); });
    expect(screen.getByRole("alert")).toHaveTextContent("lab.image: broken plot");
    fireEvent.click(screen.getByText("Use core preview")); expect(fallback).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Remount panel"));
    await waitFor(() => expect(panelsApi.create).toHaveBeenCalledTimes(2));
  });
  it("shows a ready timeout without requiring a frame load", async () => {
    vi.useFakeTimers(); render(<PanelFrame request={request} />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(10001); });
    expect(screen.getByRole("alert")).toHaveTextContent("10 seconds");
  });
});
