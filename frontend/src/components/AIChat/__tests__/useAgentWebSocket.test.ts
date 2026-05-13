/**
 * Vitest unit tests for the agent WS hook.
 *
 * Uses a controllable MockWebSocket so we can drive open/message/close
 * without touching the network. Exercises:
 *   - inbound `agent_event` → slice updated
 *   - inbound `permission_request` → pendingPermissions populated
 *   - inbound `session_ended` → session marked ended
 *   - inbound `error` → appended as synthetic error event
 *   - reconnect after unexpected close
 *   - clean teardown on hook unmount
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { useAgentWebSocket } from "../../../hooks/useAgentWebSocket";

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
  // @ts-expect-error - keep the constants exposed on the constructor
  global.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error
  global.WebSocket.CLOSED = MockWebSocket.CLOSED;
  useAppStore.setState({
    eventsByChat: {},
    pendingPermissions: {},
    sessions: [],
  });
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useAgentWebSocket", () => {
  it("opens a socket and dispatches agent_event into the slice", () => {
    renderHook(() => useAgentWebSocket("chat-1", "/tmp/proj"));
    const ws = createdSockets[0];
    expect(ws).toBeDefined();

    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.({} as Event);
      ws.onmessage?.({
        data: JSON.stringify({
          type: "agent_event",
          event: { kind: "done", raw: {} },
        }),
      } as MessageEvent);
    });
    expect(useAppStore.getState().eventsByChat["chat-1"]).toHaveLength(1);
  });

  it("routes permission_request to pendingPermissions", () => {
    renderHook(() => useAgentWebSocket("chat-2", "/tmp/proj"));
    const ws = createdSockets[0];
    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.({} as Event);
      ws.onmessage?.({
        data: JSON.stringify({
          type: "permission_request",
          request_id: "req-1",
          tool: { name: "Edit", input: { file_path: "/x" } },
        }),
      } as MessageEvent);
    });
    const pending = useAppStore.getState().pendingPermissions["chat-2"];
    expect(pending?.requestId).toBe("req-1");
    expect(pending?.toolName).toBe("Edit");
  });

  it("marks session ended on session_ended frame", () => {
    useAppStore.getState().createSession("chat-3");
    renderHook(() => useAgentWebSocket("chat-3", "/tmp/proj"));
    const ws = createdSockets[0];
    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.({} as Event);
      ws.onmessage?.({
        data: JSON.stringify({ type: "session_ended", reason: "boom" }),
      } as MessageEvent);
    });
    expect(
      useAppStore.getState().sessions.find((s) => s.id === "chat-3")?.ended,
    ).toBe(true);
  });

  it("appends error envelopes as synthetic error events", () => {
    renderHook(() => useAgentWebSocket("chat-4", "/tmp/proj"));
    const ws = createdSockets[0];
    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.({} as Event);
      ws.onmessage?.({
        data: JSON.stringify({ type: "error", message: "kaboom" }),
      } as MessageEvent);
    });
    const events = useAppStore.getState().eventsByChat["chat-4"];
    expect(events).toHaveLength(1);
    expect(events?.[0]?.kind).toBe("error");
  });

  it("reconnects after an unexpected close with exponential backoff", () => {
    renderHook(() => useAgentWebSocket("chat-5", "/tmp/proj"));
    const ws1 = createdSockets[0];

    // Open succeeds, then the server drops the connection.
    act(() => {
      ws1.readyState = MockWebSocket.OPEN;
      ws1.onopen?.({} as Event);
    });
    act(() => {
      ws1.readyState = MockWebSocket.CLOSED;
      ws1.onclose?.({} as CloseEvent);
    });
    expect(createdSockets).toHaveLength(1);

    // Advance past the initial backoff window — hook should reconnect.
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(createdSockets.length).toBeGreaterThanOrEqual(2);
  });

  it("ignores stale onclose after chatId switch (no reconnect to old chat)", () => {
    // Codex P1 regression test (PR #745 discussion_r3231068587):
    // When chatId changes, the previous socket's close event may fire
    // after the effect cleanup but before/around the new effect resets
    // intentionalCloseRef. The stale onclose must NOT schedule a
    // reconnect for the now-defunct chat.
    const { rerender } = renderHook(
      ({ chatId }: { chatId: string }) => useAgentWebSocket(chatId, "/tmp/proj"),
      { initialProps: { chatId: "chat-old" } },
    );
    const ws1 = createdSockets[0];
    act(() => {
      ws1.readyState = MockWebSocket.OPEN;
      ws1.onopen?.({} as Event);
    });

    // Switch to a new chat — cleanup fires, new effect creates new socket.
    rerender({ chatId: "chat-new" });
    const socketCountAfterSwitch = createdSockets.length;
    expect(socketCountAfterSwitch).toBe(2);

    // Now fire the OLD socket's onclose (delayed delivery from browser).
    act(() => {
      ws1.readyState = MockWebSocket.CLOSED;
      ws1.onclose?.({} as CloseEvent);
    });
    // Advance past initial backoff — the stale onclose must NOT schedule
    // a reconnect.
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(createdSockets).toHaveLength(socketCountAfterSwitch);
  });

  it("does not reconnect on intentional close (unmount)", () => {
    const { unmount } = renderHook(() => useAgentWebSocket("chat-6", "/tmp/proj"));
    const ws = createdSockets[0];
    act(() => {
      ws.readyState = MockWebSocket.OPEN;
      ws.onopen?.({} as Event);
    });
    unmount();
    // After unmount the cleanup sets intentionalCloseRef = true and
    // closes the socket. No further sockets should be created even
    // after a long delay.
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(createdSockets).toHaveLength(1);
  });
});
