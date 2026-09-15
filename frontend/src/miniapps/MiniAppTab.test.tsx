/**
 * ADR-054 Phase D — the MiniApp tab's lifetime rules.
 *
 * The acceptance scenarios these cover:
 *  - US2/1 and FR-002: opening the tab creates a `miniapp` context on the
 *    chosen block output, bound to this workspace's `/ws` client (FR-013).
 *  - US6/3 and FR-019: switching to another tab leaves the MiniApp tab open
 *    and its process running; closing it closes the context.
 *  - US2/4 and FR-019: the tab going away ends the process — including the
 *    wholesale tab wipe a project switch performs.
 *  - FR-015: the state and memory are refreshed at least every five seconds,
 *    and a MiniApp with no `panel.py` is not treated as a failure.
 *  - FR-020: the preview column collapses and comes back at its old width.
 *  - FR-022: a `panel.files_changed` event reloads the MiniApp on a NEW
 *    context, debounced by 500 ms.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockBackend, reply, type MockBackend } from "../__tests__/contract/mockBackend";
import { resetBasePathCacheForTests } from "../lib/api/base-path";
import { bootstrapFrame } from "../panels/testUtils";
import { useAppStore } from "../store";
import type { MiniAppTab as MiniAppTabState } from "../store/types";
import { MiniAppTabLayer, useMiniAppPreviewColumn, usePreviewColumnState } from "./MiniAppTab";

const TAB: MiniAppTabState = {
  kind: "miniapp",
  id: "miniapp:lab.threshold:wf:seg:image",
  panelId: "lab.threshold",
  source: { workflow_id: "wf", block_id: "seg", port: "image" },
  displayName: "Threshold explorer",
};

function contextResponse(id: string, process: Record<string, unknown> | null) {
  return {
    context_id: id,
    panel: { id: "lab.threshold", api_version: "1.0", name: "Threshold explorer" },
    kind: "miniapp",
    operations: ["read", "call"],
    services: ["save"],
    input: { ref: "data-1", type: "Image" },
    token: "secret",
    bootstrap_proof: "a".repeat(64),
    expires_at: 9_999_999_999,
    entry_url: "/api/panels/t/secret/assets/lab.threshold/index.html",
    sdk_url: "/api/panels/t/secret/sdk/1/scistudio-panel.js",
    lib_base_url: "/api/panels/t/secret/lib/",
    process,
  };
}

let backend: MockBackend;
let contexts: number;
let processBody: () => unknown;

beforeEach(() => {
  contexts = 0;
  processBody = () => ({ state: "running", pid: 4242, resident_memory: 12 * 1024 * 1024 });
  backend = mockBackend({
    "POST /api/panels/contexts": () => {
      contexts += 1;
      return contextResponse(`pc-${contexts}`, {
        state: "starting",
        pid: 4242,
        resident_memory: null,
      });
    },
    "GET /api/panels/contexts/{context_id}/process": () => processBody(),
    "POST /api/panels/contexts/{context_id}/process/restart": () =>
      contextResponse("pc-1", { state: "starting", pid: 5151, resident_memory: null }),
    "POST /api/panels/contexts/{context_id}/process/stop": () =>
      contextResponse("pc-1", { state: "stopped", pid: 4242, exit_code: 0 }),
    "POST /api/panels/contexts/{context_id}/renew": () =>
      contextResponse("pc-1", { state: "running", pid: 4242, resident_memory: 1024 }),
    "DELETE /api/panels/contexts/{context_id}": reply(204),
  });
  useAppStore.setState({ wsClientId: "ws-abc123", panelFilesChangedSeq: {} });
});

afterEach(() => {
  cleanup();
  backend.restore();
  resetBasePathCacheForTests();
  useAppStore.setState({ wsClientId: null, panelFilesChangedSeq: {} });
  vi.useRealTimers();
});

const created = () => backend.callsTo("POST /api/panels/contexts");
const closed = () => backend.callsTo("DELETE /api/panels/contexts/{context_id}");

describe("MiniApp tab lifetime (ADR-054 FR-018 / FR-019)", () => {
  it("creates a miniapp context on its source, bound to the ws client", async () => {
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));
    expect(created()[0].body).toEqual({
      kind: "miniapp",
      panel_id: "lab.threshold",
      source: { workflow_id: "wf", block_id: "seg", port: "image" },
      ws_client_id: "ws-abc123",
    });
  });

  it("keeps the tab open and its process running when another tab becomes active", async () => {
    // US6 acceptance 3. The context is what owns the process, so "the process
    // keeps running" means exactly "no DELETE was sent and no second context
    // was created".
    const view = render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));
    expect(screen.getByTestId("miniapp-tab-pane")).toBeTruthy();

    view.rerender(<MiniAppTabLayer tabs={[TAB]} activeTabId="tab-workflow" onConvert={vi.fn()} />);
    await Promise.resolve();

    expect(screen.getByTestId("miniapp-tab-pane")).toBeTruthy();
    expect(closed()).toHaveLength(0);
    expect(created()).toHaveLength(1);

    // ...and coming back does not restart anything either.
    view.rerender(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await Promise.resolve();
    expect(created()).toHaveLength(1);
    expect(closed()).toHaveLength(0);
  });

  it("closes the context when the tab is closed, and when the tab list is wiped", async () => {
    // US2 acceptance 4 / FR-019. A project switch empties the tab list
    // wholesale with no per-tab hook, so teardown has to be unmount-driven.
    const view = render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));

    view.rerender(<MiniAppTabLayer tabs={[]} activeTabId={null} onConvert={vi.fn()} />);
    await waitFor(() => expect(closed()).toHaveLength(1));
    expect(closed()[0].path).toBe("/api/panels/contexts/pc-1");
  });

  it("shows usable process state without memory metrics, and tolerates a MiniApp with no process", async () => {
    // FR-015. The 404 `no_process` answer is a legitimate MiniApp (no
    // panel.py), not a failure, so it must not surface as an error.
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId("miniapp-process-state").textContent).toBe("Running"),
    );
    expect(screen.queryByTestId("miniapp-process-memory")).toBeNull();
    expect(screen.queryByText(/MiB|GiB/)).toBeNull();

    cleanup();
    processBody = () => reply(404, { detail: { code: "no_process", message: "no process" } });
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId("miniapp-process-absent")).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("restarts and stops the process from the tab toolbar", async () => {
    // FR-021 / FR-014. Both routes answer with a full context, so the toolbar
    // shows the refreshed state without waiting for the next poll.
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() =>
      expect(backend.callsTo("POST /api/panels/contexts/{context_id}/process/stop")).toHaveLength(
        1,
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId("miniapp-process-state").textContent).toBe("Stopped"),
    );
    expect(screen.getByTestId("miniapp-process-exit").textContent).toBe("exit 0");

    fireEvent.click(screen.getByRole("button", { name: "Restart" }));
    await waitFor(() =>
      expect(
        backend.callsTo("POST /api/panels/contexts/{context_id}/process/restart"),
      ).toHaveLength(1),
    );
  });

  it("renews its context so a long-lived tab outlives the 600 s expiry", async () => {
    // FR-013 / the 600 s context TTL. A MiniApp tab is long-lived by design
    // and its process lives exactly as long as its context does, so the host's
    // 240 s renewal heartbeat has to keep running for as long as the tab is
    // open — including while a tab of another kind is the active one.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const channels: { port1: MessagePort; port2: MessagePort }[] = [];
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
    const view = render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    const iframe = (await screen.findByTitle("Threshold explorer")) as HTMLIFrameElement;

    // The page reaches ready() before the host's 10 s deadline, which is what
    // leaves the renewal heartbeat as the only long timer still running.
    bootstrapFrame(iframe);
    fireEvent.load(iframe);
    await act(async () => {
      channels[0].port1.onmessage?.({
        data: { v: 1, id: "ready", type: "ready", payload: null },
      } as MessageEvent);
    });

    view.rerender(<MiniAppTabLayer tabs={[TAB]} activeTabId="tab-workflow" onConvert={vi.fn()} />);
    await act(async () => {
      vi.advanceTimersByTime(240_000);
    });
    await waitFor(() =>
      expect(
        backend.callsTo("POST /api/panels/contexts/{context_id}/renew").length,
      ).toBeGreaterThan(0),
    );
    expect(closed()).toHaveLength(0);
    vi.unstubAllGlobals();
  });

  it("opens the Convert dialog for this MiniApp", () => {
    // FR-021 / FR-036 — the dialog is mounted by the workspace, so the tab
    // only reports which MiniApp is being converted.
    const onConvert = vi.fn();
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={onConvert} />);
    fireEvent.click(screen.getByRole("button", { name: "Convert to interactive block" }));
    expect(onConvert).toHaveBeenCalledWith("lab.threshold");
  });

  it("reloads on panel.files_changed with a new context, debounced", async () => {
    // FR-022. The entry handshake is one-shot, so a reload must replace the
    // frame — a new context, a new process — rather than re-navigate it.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));

    act(() => {
      useAppStore.getState().notifyPanelFilesChanged("lab.threshold");
      useAppStore.getState().notifyPanelFilesChanged("lab.threshold");
    });
    act(() => {
      vi.advanceTimersByTime(499);
    });
    expect(created()).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(2);
    });
    await waitFor(() => expect(created()).toHaveLength(2));
    // One reload for the burst, and the old context was closed.
    await waitFor(() => expect(closed()).toHaveLength(1));
  });

  it("ignores a files_changed event for another panel", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
    await waitFor(() => expect(created()).toHaveLength(1));
    act(() => useAppStore.getState().notifyPanelFilesChanged("lab.other"));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(created()).toHaveLength(1);
  });
});

/** A stand-in for the `workspace-preview` panel's imperative handle. */
function fakePanel(percentage: number, collapsed = false) {
  const state = { percentage, collapsed };
  const panel: PanelImperativeHandle = {
    collapse: vi.fn(() => {
      state.collapsed = true;
    }),
    expand: vi.fn(() => {
      state.collapsed = false;
    }),
    getSize: vi.fn(() => ({ asPercentage: state.percentage, inPixels: 0 })),
    isCollapsed: vi.fn(() => state.collapsed),
    resize: vi.fn((size: number | string) => {
      state.percentage = typeof size === "number" ? size : parseFloat(size);
    }),
  };
  return { panel, state };
}

describe("the preview column while a MiniApp is active (ADR-054 FR-020)", () => {
  it("collapses on activation and returns to the width it had", () => {
    const { panel, state } = fakePanel(26);
    const ref = { current: panel };
    const view = renderHook(({ active }) => useMiniAppPreviewColumn(ref, active), {
      initialProps: { active: false },
    });
    expect(panel.collapse).not.toHaveBeenCalled();

    view.rerender({ active: true });
    expect(panel.collapse).toHaveBeenCalledTimes(1);
    expect(state.collapsed).toBe(true);

    view.rerender({ active: false });
    expect(panel.expand).toHaveBeenCalledTimes(1);
    expect(panel.resize).toHaveBeenCalledWith("26%");
    expect(state.percentage).toBe(26);
  });

  it("leaves a column the user had already collapsed alone", () => {
    const { panel } = fakePanel(0, true);
    const ref = { current: panel };
    const view = renderHook(({ active }) => useMiniAppPreviewColumn(ref, active), {
      initialProps: { active: false },
    });
    view.rerender({ active: true });
    expect(panel.collapse).not.toHaveBeenCalled();

    view.rerender({ active: false });
    expect(panel.expand).not.toHaveBeenCalled();
    expect(panel.resize).not.toHaveBeenCalled();
  });

  it("keeps a width the user dragged open while the MiniApp was active", () => {
    const { panel, state } = fakePanel(26);
    const ref = { current: panel };
    const view = renderHook(({ active }) => useMiniAppPreviewColumn(ref, active), {
      initialProps: { active: false },
    });
    view.rerender({ active: true });
    expect(state.collapsed).toBe(true);

    // The user drags the column open again, without leaving the MiniApp.
    state.collapsed = false;
    state.percentage = 38;

    view.rerender({ active: false });
    expect(panel.expand).not.toHaveBeenCalled();
    expect(panel.resize).not.toHaveBeenCalled();
    expect(state.percentage).toBe(38);
  });

  it("collapses nothing in the AI host, which renders no right column", () => {
    const ref: { current: PanelImperativeHandle | null } = { current: null };
    const view = renderHook(({ active }) => useMiniAppPreviewColumn(ref, active), {
      initialProps: { active: false },
    });
    expect(() => view.rerender({ active: true })).not.toThrow();
  });
});

it("does not reload a newly mounted tab for historical file changes", async () => {
  useAppStore.setState({ panelFilesChangedSeq: { [TAB.panelId]: 12 } });
  render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
  await waitFor(() => expect(created()).toHaveLength(1));
  await act(() => new Promise((resolve) => setTimeout(resolve, 650)));
  expect(created()).toHaveLength(1);
  expect(closed()).toHaveLength(0);
});

it("waits for a workspace identity before creating a process context", async () => {
  useAppStore.setState({ wsClientId: null });
  render(<MiniAppTabLayer tabs={[TAB]} activeTabId={TAB.id} onConvert={vi.fn()} />);
  expect(created()).toHaveLength(0);
  act(() => useAppStore.setState({ wsClientId: "ws-reconnected" }));
  await waitFor(() => expect(created()).toHaveLength(1));
  expect(created()[0].body).toMatchObject({ ws_client_id: "ws-reconnected" });
});

it("expands the actual preview panel when a visibility request opens it", () => {
  useAppStore.setState({ previewCollapsed: true });
  const { panel, state } = fakePanel(0, true);
  const ref = { current: panel };
  renderHook(() => usePreviewColumnState(ref));
  expect(state.collapsed).toBe(true);
  act(() => useAppStore.setState({ previewCollapsed: false }));
  expect(panel.expand).toHaveBeenCalledTimes(1);
  expect(panel.isCollapsed()).toBe(false);
});
