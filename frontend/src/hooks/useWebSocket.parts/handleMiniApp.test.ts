/**
 * ADR-054 MiniApps (#2354) — the realtime frames a MiniApp lives on.
 *
 * The three cases here are the ones a user feels: an identity that is never
 * read leaves every MiniApp process outliving the tab that opened it; an
 * `open_miniapp` that opens a second tab on a target already open leaves the
 * agent's answer split across two frames; and a reload that is not debounced
 * restarts the process several times for one editor save.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LogEntry, WorkflowEventMessage } from "../../types/api";

import {
  MINIAPP_RELOAD_DEBOUNCE_MS,
  cancelPendingMiniAppReloads,
  handleOpenMiniApp,
  handlePanelFilesChanged,
  handleWsDisconnected,
  handleWsHello,
} from "./handleMiniApp";

function frame(body: Record<string, unknown>): WorkflowEventMessage {
  return {
    data: {},
    timestamp: "2026-09-11T00:00:00Z",
    ...body,
  } as WorkflowEventMessage;
}

describe("the hello frame binds this browser to the backend (CONTRACT §2.1)", () => {
  it("remembers the client id the backend minted", () => {
    const setWsClientId = vi.fn();

    handleWsHello(frame({ type: "hello", client_id: "ws-0123456789abcdef" }), { setWsClientId });

    expect(setWsClientId).toHaveBeenCalledWith("ws-0123456789abcdef");
  });

  it("ignores a hello with no id rather than storing an empty one", () => {
    /*
     * An empty string is a value the store would happily hold and every context
     * create would happily send, binding the MiniApp to a workspace the backend
     * has never heard of. Holding `null` is at least honest about not knowing.
     */
    const setWsClientId = vi.fn();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    handleWsHello(frame({ type: "hello", client_id: "" }), { setWsClientId });

    expect(setWsClientId).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("forgets the id when the socket goes away", () => {
    /*
     * FR-013: the backend retires the id when the socket closes and reaps the
     * MiniApps bound to it after a grace period. A context created with a
     * retired id would open and then die half a minute later, which reads as a
     * crash rather than as a stale identity.
     */
    const setWsClientId = vi.fn();

    handleWsDisconnected({ setWsClientId });

    expect(setWsClientId).toHaveBeenCalledWith(null);
  });
});

describe("panel.open_miniapp opens the tab the agent asked for (FR-030)", () => {
  it("opens the MiniApp on the target the event names", () => {
    const openMiniAppTab = vi.fn();
    const appendLog = vi.fn();

    handleOpenMiniApp(
      frame({
        type: "panel.open_miniapp",
        workflow_id: "wf-1",
        data: {
          panel_id: "peak_explorer",
          workflow_id: "wf-1",
          block_id: "node-a",
          port: "output_1",
        },
      }),
      { openMiniAppTab, appendLog },
    );

    expect(openMiniAppTab).toHaveBeenCalledWith({
      panelId: "peak_explorer",
      name: "peak_explorer",
      target: { workflow_id: "wf-1", block_id: "node-a", port: "output_1" },
    });
  });

  it("reads the target whether it arrives at the top level or inside data", () => {
    // `serialise_event` lifts `workflow_id` onto the frame and leaves the rest
    // inside the envelope, so both levels are real wire shapes.
    const openMiniAppTab = vi.fn();

    handleOpenMiniApp(
      frame({
        type: "panel.open_miniapp",
        panel_id: "peak_explorer",
        workflow_id: "wf-1",
        block_id: "node-a",
        port: "output_1",
        name: "Peak Explorer",
      }),
      { openMiniAppTab, appendLog: vi.fn() },
    );

    expect(openMiniAppTab).toHaveBeenCalledWith({
      panelId: "peak_explorer",
      name: "Peak Explorer",
      target: { workflow_id: "wf-1", block_id: "node-a", port: "output_1" },
    });
  });

  it("opens nothing and says so when the target is incomplete", () => {
    /*
     * A tab opened on half a target is a frame pointed at no data, and the
     * reader has no way to tell that from a MiniApp that simply rendered
     * nothing. The run log is where a frontend refusal is visible.
     */
    const openMiniAppTab = vi.fn();
    const logs: LogEntry[] = [];
    const error = vi.spyOn(console, "error").mockImplementation(() => {});

    handleOpenMiniApp(
      frame({
        type: "panel.open_miniapp",
        data: { panel_id: "peak_explorer", workflow_id: "wf-1", block_id: "node-a" },
      }),
      { openMiniAppTab, appendLog: (entry) => logs.push(entry) },
    );

    expect(openMiniAppTab).not.toHaveBeenCalled();
    expect(logs).toHaveLength(1);
    expect(logs[0].level).toBe("error");
    error.mockRestore();
  });
});

describe("panel.files_changed reloads once per burst (FR-022)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cancelPendingMiniAppReloads();
    vi.useRealTimers();
  });

  it("waits for the writes to settle before reloading", () => {
    /*
     * One save can produce several events — the file, a temporary file renamed
     * over it, an asset written beside it — and each reload is a new frame,
     * context, and process. Three events inside the window are one reload.
     */
    const reloadMiniApp = vi.fn();
    const event = frame({ type: "panel.files_changed", data: { panel_id: "peak_explorer" } });

    handlePanelFilesChanged(event, { reloadMiniApp });
    vi.advanceTimersByTime(MINIAPP_RELOAD_DEBOUNCE_MS - 100);
    handlePanelFilesChanged(event, { reloadMiniApp });
    vi.advanceTimersByTime(MINIAPP_RELOAD_DEBOUNCE_MS - 100);
    handlePanelFilesChanged(event, { reloadMiniApp });

    expect(reloadMiniApp).not.toHaveBeenCalled();

    vi.advanceTimersByTime(MINIAPP_RELOAD_DEBOUNCE_MS);

    expect(reloadMiniApp).toHaveBeenCalledTimes(1);
    expect(reloadMiniApp).toHaveBeenCalledWith("peak_explorer");
  });

  it("keeps one panel's burst from delaying another's reload", () => {
    const reloadMiniApp = vi.fn();

    handlePanelFilesChanged(
      frame({ type: "panel.files_changed", data: { panel_id: "peak_explorer" } }),
      { reloadMiniApp },
    );
    handlePanelFilesChanged(
      frame({ type: "panel.files_changed", data: { panel_id: "spectra_browser" } }),
      { reloadMiniApp },
    );
    vi.advanceTimersByTime(MINIAPP_RELOAD_DEBOUNCE_MS);

    expect(reloadMiniApp.mock.calls.map(([id]) => id).sort()).toEqual([
      "peak_explorer",
      "spectra_browser",
    ]);
  });

  it("ignores a frame with no panel id", () => {
    const reloadMiniApp = vi.fn();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});

    handlePanelFilesChanged(frame({ type: "panel.files_changed", data: {} }), { reloadMiniApp });
    vi.advanceTimersByTime(MINIAPP_RELOAD_DEBOUNCE_MS * 2);

    expect(reloadMiniApp).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
