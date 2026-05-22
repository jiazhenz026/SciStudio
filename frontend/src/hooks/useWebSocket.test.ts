/**
 * Regression tests for useWorkflowWebSocket (#793).
 *
 * Verifies that engine events do NOT force the bottom panel onto the Logs
 * tab — they should only bump the unread counter, leaving the user's chosen
 * tab in place.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../lib/api";
import type * as ApiModule from "../lib/api";
import { useAppStore } from "../store";
import { useWorkflowWebSocket } from "./useWebSocket";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getWorkflow: vi.fn(),
    },
  };
});

interface MockSocket {
  readyState: number;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: () => void;
  url: string;
}

const createdSockets: MockSocket[] = [];

class MockWebSocket implements MockSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send = vi.fn();
  url: string;

  constructor(url: string) {
    this.url = url;
    createdSockets.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({} as CloseEvent);
  }
}

beforeEach(() => {
  createdSockets.length = 0;
  // @ts-expect-error -- MockWebSocket is a minimal stand-in and does not implement the full WebSocket structural type expected by lib.dom.
  global.WebSocket = MockWebSocket;
  // @ts-expect-error -- WebSocket.OPEN is declared readonly in lib.dom; we overwrite it on the mock so production code sees the same numeric constant.
  global.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error -- WebSocket.CLOSED is declared readonly in lib.dom; we overwrite it on the mock so production code sees the same numeric constant.
  global.WebSocket.CLOSED = MockWebSocket.CLOSED;
  // Reset only the bits that matter to this test.
  useAppStore.setState({
    activeBottomTab: "ai",
    unreadLogsCount: 0,
    logEntries: [],
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

function pushMessage(message: object): void {
  const sock = createdSockets[0];
  expect(sock).toBeDefined();
  act(() => {
    sock.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  });
}

describe("useWorkflowWebSocket (#793)", () => {
  it("does NOT switch the active bottom tab when a block_started event arrives", () => {
    renderHook(() => useWorkflowWebSocket(true));
    useAppStore.setState({ activeBottomTab: "ai" });

    pushMessage({
      type: "block_started",
      block_id: "node-1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: {},
    });

    // The active tab MUST remain on "ai" — this is the whole point of #793.
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("bumps unreadLogsCount only when a Logs-panel row is actually added", () => {
    // Coupled-badge contract (fix for "8 unread but Logs empty" mismatch):
    // ``unreadLogsCount`` tracks the number of unseen rows in the Logs
    // panel, NOT the number of engine events seen. block_started /
    // workflow_started don't produce a Logs row, so they don't bump.
    // Only events that ``consumeEvent`` / ``appendLog`` actually
    // materialise into ``logEntries`` (e.g. block_error) bump the badge.
    renderHook(() => useWorkflowWebSocket(true));
    useAppStore.setState({ activeBottomTab: "ai" });

    pushMessage({
      type: "block_started",
      block_id: "n1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: {},
    });
    pushMessage({
      type: "workflow_started",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: {},
    });

    expect(useAppStore.getState().unreadLogsCount).toBe(0);
    expect(useAppStore.getState().logEntries).toHaveLength(0);

    // A block_error DOES add a Logs row → badge bumps.
    pushMessage({
      type: "block_error",
      block_id: "n1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: { error: "boom" },
    });

    expect(useAppStore.getState().unreadLogsCount).toBe(1);
    expect(useAppStore.getState().logEntries).toHaveLength(1);
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("block_error events surface as Logs rows (Problems tab was removed)", () => {
    // The Problems tab was collapsed into the Logs panel's error filter.
    // block_error events therefore land in ``logEntries`` (level=error)
    // and bump the Logs unread badge — the only badge that remains.
    renderHook(() => useWorkflowWebSocket(true));
    useAppStore.setState({ activeBottomTab: "ai" });

    pushMessage({
      type: "block_error",
      block_id: "n1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: { error: "boom" },
    });

    expect(useAppStore.getState().logEntries).toHaveLength(1);
    expect(useAppStore.getState().logEntries[0].level).toBe("error");
    expect(useAppStore.getState().unreadLogsCount).toBe(1);
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("does NOT bump unreadLogsCount while the user is already viewing Logs", () => {
    renderHook(() => useWorkflowWebSocket(true));
    useAppStore.setState({ activeBottomTab: "logs" });

    pushMessage({
      type: "block_started",
      block_id: "n1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: {},
    });

    expect(useAppStore.getState().unreadLogsCount).toBe(0);
  });
});

describe("useWorkflowWebSocket — workflow.changed routing (ADR-034 Phase 2)", () => {
  beforeEach(() => {
    vi.mocked(api.getWorkflow).mockReset();
  });

  it("refetches and replaces the workflow when the changed id matches", async () => {
    // Seed the store with a currently-loaded workflow id.
    useAppStore.setState({ workflowId: "demo", workflowName: "Demo" });
    vi.mocked(api.getWorkflow).mockResolvedValueOnce({
      id: "demo",
      version: "1.0.0",
      description: "refreshed",
      nodes: [],
      edges: [],
      metadata: {},
    } as never);

    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-13T00:00:00Z",
      data: {
        workflow_id: "demo",
        path: "workflows/demo.yaml",
        kind: "modified",
        changed_by: "watcher",
      },
    });

    // Allow the awaited promise to flush.
    await new Promise((r) => setTimeout(r, 0));
    expect(vi.mocked(api.getWorkflow)).toHaveBeenCalledWith("demo");
    expect(useAppStore.getState().workflowDescription).toBe("refreshed");
  });

  it("auto-opens the workflow tab when an MCP-driven run emits workflow_started for an unopened workflow", async () => {
    // Hotfix scope: when an agent calls MCP run_workflow on a yaml that the
    // user has not opened in the canvas, the scheduler emits
    // ``workflow_started`` — no ``workflow.changed`` fires because the yaml
    // was not mutated. The hook must mirror the ``workflow.changed
    // kind=created`` auto-open path so the user can watch the run live.
    useAppStore.setState({ workflowId: null, tabs: [] });
    vi.mocked(api.getWorkflow).mockResolvedValueOnce({
      id: "mcp_run_target",
      version: "1.0.0",
      description: "via MCP",
      nodes: [],
      edges: [],
      metadata: {},
    } as never);
    const openTabSpy = vi.fn();
    useAppStore.setState({ openTab: openTabSpy });

    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow_started",
      workflow_id: "mcp_run_target",
      timestamp: "2026-05-21T00:00:00Z",
      data: {},
    });

    await new Promise((r) => setTimeout(r, 0));
    expect(vi.mocked(api.getWorkflow)).toHaveBeenCalledWith("mcp_run_target");
    expect(openTabSpy).toHaveBeenCalled();
  });

  it("does NOT auto-open on workflow_started when the workflow is already open", async () => {
    // Idempotency guard: a manual user-click already produced the tab, the
    // run that follows must not double-open or re-fetch.
    useAppStore.setState({
      tabs: [
        // Shape mirrors the workflow-tab variant; only the discriminating
        // fields matter for the hook's lookup.
        {
          id: "t-already-open",
          kind: "workflow",
          workflowId: "already_open",
          title: "Already Open",
        },
      ] as never,
    });
    const openTabSpy = vi.fn();
    useAppStore.setState({ openTab: openTabSpy });

    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow_started",
      workflow_id: "already_open",
      timestamp: "2026-05-21T00:00:00Z",
      data: {},
    });

    await new Promise((r) => setTimeout(r, 0));
    expect(vi.mocked(api.getWorkflow)).not.toHaveBeenCalled();
    expect(openTabSpy).not.toHaveBeenCalled();
  });

  it("ignores workflow.changed for a workflow that is not currently loaded", async () => {
    useAppStore.setState({ workflowId: "alpha" });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "beta",
      timestamp: "2026-05-13T00:00:00Z",
      data: {
        workflow_id: "beta",
        path: "workflows/beta.yaml",
        kind: "modified",
        changed_by: "watcher",
      },
    });

    await new Promise((r) => setTimeout(r, 0));
    expect(vi.mocked(api.getWorkflow)).not.toHaveBeenCalled();
    expect(useAppStore.getState().workflowId).toBe("alpha");
  });

  /** Audit P1-D regression: backend emits ``event`` (top level), not
   * ``data.status``/``data.result``. Successful runs were rendering as red ✗. */
  it("maps top-level `event=completed` to AiBlockStatus 'done' (#852 audit P1-D)", () => {
    // Seed a tab so updateAiBlockStatus has a target.
    const setStatus = vi.fn();
    useAppStore.setState({
      updateAiBlockStatus: setStatus,
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "block_pty_closed",
      tab_id: "tab-1",
      block_run_id: "rid-1",
      event: "completed",
      detail: {},
      timestamp: "2026-05-14T00:00:00Z",
    });

    expect(setStatus).toHaveBeenCalledWith("tab-1", "done");
  });

  it("maps top-level `event=cancelled_by_user_close` to 'cancelled'", () => {
    const setStatus = vi.fn();
    useAppStore.setState({
      updateAiBlockStatus: setStatus,
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "block_pty_closed",
      tab_id: "tab-2",
      block_run_id: "rid-2",
      event: "cancelled_by_user_close",
      detail: {},
      timestamp: "2026-05-14T00:00:00Z",
    });

    expect(setStatus).toHaveBeenCalledWith("tab-2", "cancelled");
  });

  it("maps top-level `event=error` to 'error'", () => {
    const setStatus = vi.fn();
    useAppStore.setState({
      updateAiBlockStatus: setStatus,
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "block_pty_closed",
      tab_id: "tab-3",
      block_run_id: "rid-3",
      event: "error",
      detail: { code: 1 },
      timestamp: "2026-05-14T00:00:00Z",
    });

    expect(setStatus).toHaveBeenCalledWith("tab-3", "error");
  });

  /** Audit P2-A: backend emits ``permission_mode`` at top level, not nested. */
  it("reads top-level `permission_mode=bypass` and registers as dangerous (audit P2-A)", () => {
    const addAiBlockTab = vi.fn();
    useAppStore.setState({
      addAiBlockTerminalTab: addAiBlockTab,
    });
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "block_pty_opened",
      tab_id: "tab-bp",
      block_run_id: "rid-bp",
      title: "🤖 demo",
      permission_mode: "bypass",
      timestamp: "2026-05-14T00:00:00Z",
    });

    expect(addAiBlockTab).toHaveBeenCalledWith(
      expect.objectContaining({
        tabId: "tab-bp",
        permissionMode: "dangerous",
      }),
    );
  });

  it("clears the canvas when the loaded workflow is deleted on disk", async () => {
    useAppStore.setState({
      workflowId: "demo",
      workflowName: "Demo",
      workflowNodes: [
        { id: "n", block_type: "Load", config: {}, execution_mode: null, layout: null },
      ],
    });
    // Hotfix #1400 part 3: the deleted-event handler now probes the file
    // first. For a genuine delete the probe fails (404 / network error),
    // and the legacy clear-canvas + warn-log path runs. Mock that.
    vi.mocked(api.getWorkflow).mockRejectedValueOnce(new Error("not found"));
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-13T00:00:00Z",
      data: {
        workflow_id: "demo",
        path: "workflows/demo.yaml",
        kind: "deleted",
        changed_by: "watcher",
      },
    });

    // Wait for the probe promise to reject + the catch block to run.
    await new Promise((r) => setTimeout(r, 0));

    expect(useAppStore.getState().workflowId).toBeNull();
    expect(useAppStore.getState().workflowNodes).toEqual([]);
    // The delete event should also leave a log entry behind.
    const logs = useAppStore.getState().logEntries;
    expect(
      logs.some((entry) => entry.message.includes("demo") && entry.message.includes("deleted")),
    ).toBe(true);
  });

  it("treats a transient delete-then-create (git checkout race) as modification", async () => {
    // Hotfix #1400 part 3: when git-checkout replaces a workflow YAML on
    // Windows, the watchdog sometimes emits a `deleted` event microseconds
    // before the actual content lands. Probing the file proves it's still
    // there with the restored content — the canvas should refresh, not
    // clear.
    useAppStore.setState({
      workflowId: "demo",
      workflowName: "Demo (stale)",
      workflowNodes: [],
    });
    vi.mocked(api.getWorkflow).mockResolvedValueOnce({
      id: "demo",
      name: "Demo (restored)",
      nodes: [
        {
          id: "n",
          block_type: "Load",
          config: { restored: true },
          execution_mode: null,
          layout: null,
        },
      ],
      edges: [],
      schemaVersion: 1,
    } as never);
    renderHook(() => useWorkflowWebSocket(true));

    pushMessage({
      type: "workflow.changed",
      workflow_id: "demo",
      timestamp: "2026-05-13T00:00:00Z",
      data: {
        workflow_id: "demo",
        path: "workflows/demo.yaml",
        kind: "deleted",
        changed_by: "watcher",
      },
    });

    await new Promise((r) => setTimeout(r, 0));

    // Canvas should be refreshed, not cleared — workflowId preserved,
    // nodes replaced with restored content, no scary "deleted" warning.
    expect(useAppStore.getState().workflowId).toBe("demo");
    expect(useAppStore.getState().workflowNodes.length).toBe(1);
    const logs = useAppStore.getState().logEntries;
    expect(logs.some((entry) => entry.message.includes("deleted on disk; canvas cleared"))).toBe(
      false,
    );
  });
});
