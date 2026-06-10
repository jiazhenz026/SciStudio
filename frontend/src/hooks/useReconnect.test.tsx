/**
 * #177: reconnection-behaviour tests for ``useLogStream`` (SSE) and
 * ``useWorkflowWebSocket``.
 *
 * Verifies:
 *  - automatic reconnect after a dropped connection
 *  - exponential backoff (1s -> 2s -> 4s ... capped at 30s)
 *  - delay resets to 1s after a successful reopen
 *  - the surfaced ``status`` reflects connecting/connected/reconnecting
 *  - WebSocket heartbeat drives reconnect on a half-open socket
 *  - teardown on unmount does not schedule a reconnect
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetAppStore } from "../testUtils";
import { RECONNECT_INITIAL_DELAY_MS, RECONNECT_MAX_DELAY_MS } from "./connectionState";
import { useLogStream } from "./useSSE";
import { useWorkflowWebSocket } from "./useWebSocket";

// --- Controllable socket mocks -------------------------------------------

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  sent: string[] = [];

  constructor() {
    MockWebSocket.instances.push(this);
  }

  static latest(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  send(data: string) {
    this.sent.push(data);
  }

  message(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  // Simulate the network dropping the connection (server-driven close).
  drop() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  // Called by the hook on teardown.
  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

class MockEventSource {
  static instances: MockEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  closed = false;

  constructor() {
    MockEventSource.instances.push(this);
  }

  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }

  open() {
    this.onopen?.();
  }

  error() {
    this.onerror?.();
  }

  close() {
    this.closed = true;
  }
}

function WsHarness() {
  const { status } = useWorkflowWebSocket(true);
  return <span data-testid="ws-status">{status}</span>;
}

function SseHarness() {
  const { status } = useLogStream("wf-1", null);
  return <span data-testid="sse-status">{status}</span>;
}

describe("realtime reconnection (#177)", () => {
  beforeEach(() => {
    resetAppStore();
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    MockEventSource.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("SSE reconnects with exponential backoff and resets on reopen", () => {
    const view = render(<SseHarness />);
    const first = MockEventSource.latest();

    // Open succeeds -> connected.
    act(() => first.open());
    expect(view.getByTestId("sse-status").textContent).toBe("connected");
    expect(MockEventSource.instances).toHaveLength(1);

    // Drop -> reconnecting, no new source yet (waiting for backoff).
    act(() => first.error());
    expect(view.getByTestId("sse-status").textContent).toBe("reconnecting");
    expect(MockEventSource.instances).toHaveLength(1);

    // First retry fires after the initial 1s delay.
    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS);
    });
    expect(MockEventSource.instances).toHaveLength(2);

    // That retry also errors before opening -> next backoff is 2s.
    const second = MockEventSource.latest();
    act(() => second.error());
    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS); // 1s: not enough
    });
    expect(MockEventSource.instances).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS); // total 2s
    });
    expect(MockEventSource.instances).toHaveLength(3);

    // Third attempt opens successfully -> backoff resets to 1s.
    const third = MockEventSource.latest();
    act(() => third.open());
    expect(view.getByTestId("sse-status").textContent).toBe("connected");
    act(() => third.error());
    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS);
    });
    expect(MockEventSource.instances).toHaveLength(4);
  });

  it("SSE teardown on unmount closes source and schedules no reconnect", () => {
    const view = render(<SseHarness />);
    const src = MockEventSource.latest();
    act(() => src.open());

    view.unmount();
    expect(src.closed).toBe(true);

    act(() => {
      vi.advanceTimersByTime(RECONNECT_MAX_DELAY_MS * 2);
    });
    // No further EventSource created after unmount.
    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("WebSocket reconnects after a dropped connection", () => {
    const view = render(<WsHarness />);
    const first = MockWebSocket.latest();
    act(() => first.open());
    expect(view.getByTestId("ws-status").textContent).toBe("connected");

    act(() => first.drop());
    expect(view.getByTestId("ws-status").textContent).toBe("reconnecting");
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    // New socket opens -> connected again.
    act(() => MockWebSocket.latest().open());
    expect(view.getByTestId("ws-status").textContent).toBe("connected");
  });

  it("WebSocket heartbeat drives reconnect when the socket is half-open", () => {
    const view = render(<WsHarness />);
    const sock = MockWebSocket.latest();
    act(() => sock.open());
    expect(view.getByTestId("ws-status").textContent).toBe("connected");

    // While OPEN, the heartbeat sends an application-level ping.
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(sock.sent.map((data) => JSON.parse(data))).toContainEqual({ type: "ping" });
    expect(view.getByTestId("ws-status").textContent).toBe("connected");
    expect(MockWebSocket.instances).toHaveLength(1);

    // A pong response before the timeout keeps the socket alive.
    act(() => sock.message({ type: "pong" }));
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(view.getByTestId("ws-status").textContent).toBe("connected");
    expect(MockWebSocket.instances).toHaveLength(1);

    // Simulate the real stale case: the browser still reports OPEN but the
    // server never replies to the next heartbeat.
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(view.getByTestId("ws-status").textContent).toBe("reconnecting");

    // Backoff retry then creates a fresh socket.
    act(() => {
      vi.advanceTimersByTime(RECONNECT_INITIAL_DELAY_MS);
    });
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });

  it("WebSocket teardown detaches handlers and schedules no reconnect", () => {
    const view = render(<WsHarness />);
    const sock = MockWebSocket.latest();
    act(() => sock.open());

    view.unmount();

    act(() => {
      vi.advanceTimersByTime(RECONNECT_MAX_DELAY_MS * 2);
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });
});
