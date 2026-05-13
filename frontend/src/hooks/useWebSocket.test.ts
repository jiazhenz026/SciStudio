/**
 * Regression tests for useWorkflowWebSocket (#793).
 *
 * Verifies that engine events do NOT force the bottom panel onto the Logs
 * tab — they should only bump the unread counter, leaving the user's chosen
 * tab in place.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { useWorkflowWebSocket } from "./useWebSocket";

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
  // @ts-expect-error - install our mock globally
  global.WebSocket = MockWebSocket;
  // @ts-expect-error
  global.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error
  global.WebSocket.CLOSED = MockWebSocket.CLOSED;
  // Reset only the bits that matter to this test.
  useAppStore.setState({
    activeBottomTab: "ai",
    unreadLogsCount: 0,
    unreadProblemsCount: 0,
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

  it("bumps unreadLogsCount on block_/workflow_ events while another tab is active", () => {
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

    expect(useAppStore.getState().unreadLogsCount).toBe(2);
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("bumps unreadProblemsCount on block_error events", () => {
    renderHook(() => useWorkflowWebSocket(true));
    useAppStore.setState({ activeBottomTab: "ai" });

    pushMessage({
      type: "block_error",
      block_id: "n1",
      workflow_id: "wf",
      timestamp: "2026-05-13T00:00:00Z",
      data: { error: "boom" },
    });

    expect(useAppStore.getState().unreadProblemsCount).toBe(1);
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
