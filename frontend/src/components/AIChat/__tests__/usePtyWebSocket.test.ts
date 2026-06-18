/**
 * Tests for usePtyWebSocket hook + buildPtyUrl helper.
 *
 * We never spin up a real WebSocket; instead we replace the global
 * `WebSocket` with a fake constructor that records the URL and exposes
 * onmessage/onopen/onclose triggers.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildPtyUrl, usePtyWebSocket, type PtyServerFrame } from "../hooks/usePtyWebSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  url: string;
  readyState: number = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  message(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
  send(payload: string) {
    this.sent.push(payload);
  }
  close() {
    if (this.closed) return;
    this.closed = true;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({} as CloseEvent);
  }
  failClose(code = 1006, reason = "") {
    if (this.closed) return;
    this.closed = true;
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

const originalWs = global.WebSocket;

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.instances = [];
  (global as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket;
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  (global as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWs;
});

function flushConnectTimer() {
  act(() => {
    vi.runOnlyPendingTimers();
  });
}

describe("buildPtyUrl", () => {
  it("encodes project_dir, provider, dangerous, and tab_id", () => {
    const url = buildPtyUrl({
      tabId: "tab abc",
      projectDir: "C:\\Users\\me\\proj",
      provider: "claude-code",
      dangerous: true,
      baseOrigin: "ws://localhost:8000",
    });
    expect(url).toMatch(/^ws:\/\/localhost:8000\/api\/ai\/pty\/tab%20abc\?/);
    // URLSearchParams may emit params in any order; check membership.
    const qs = new URL(url.replace("ws://", "http://")).searchParams;
    expect(qs.get("project_dir")).toBe("C:\\Users\\me\\proj");
    expect(qs.get("provider")).toBe("claude-code");
    expect(qs.get("dangerous")).toBe("true");
  });

  it("emits dangerous=false when flag is false", () => {
    const url = buildPtyUrl({
      tabId: "t1",
      projectDir: "/p",
      provider: "codex",
      dangerous: false,
      cols: 101,
      rows: 33,
      baseOrigin: "ws://h",
    });
    expect(url).toContain("dangerous=false");
    expect(url).toContain("provider=codex");
    expect(url).toContain("cols=101");
    expect(url).toContain("rows=33");
  });
});

describe("usePtyWebSocket", () => {
  it("opens a WebSocket with the correct URL on mount", () => {
    const onMessage = vi.fn<(_: PtyServerFrame) => void>();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/proj",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    expect(FakeWebSocket.instances).toHaveLength(1);
    const ws = FakeWebSocket.instances[0];
    expect(ws.url).toContain("/api/ai/pty/t1");
    expect(ws.url).toContain("project_dir=%2Fproj");
    expect(ws.url).toContain("provider=claude-code");
    expect(ws.url).toContain("dangerous=false");
  });

  it("does not open a socket when projectDir is null", () => {
    const onMessage = vi.fn();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: null,
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("does not open a socket while disabled", () => {
    const onMessage = vi.fn();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        enabled: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("parses server JSON frames and invokes onMessage", () => {
    const onMessage = vi.fn<(_: PtyServerFrame) => void>();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    const ws = FakeWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.message(JSON.stringify({ type: "stdout", data: "hello" })));
    expect(onMessage).toHaveBeenCalledWith({ type: "stdout", data: "hello" });
    act(() => ws.message(JSON.stringify({ type: "exit", code: 0 })));
    expect(onMessage).toHaveBeenLastCalledWith({ type: "exit", code: 0 });
  });

  it("surfaces malformed frames as error frames instead of throwing", () => {
    const onMessage = vi.fn<(_: PtyServerFrame) => void>();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    const ws = FakeWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.message("not json"));
    const calls = onMessage.mock.calls;
    const last = calls[calls.length - 1]?.[0];
    expect(last?.type).toBe("error");
  });

  it("does not replace opaque browser socket errors with fake PTY errors", () => {
    const onMessage = vi.fn<(_: PtyServerFrame) => void>();
    const onClose = vi.fn<(_: CloseEvent) => void>();
    renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
        onClose,
      }),
    );
    flushConnectTimer();
    const ws = FakeWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.onerror?.());
    expect(onMessage).not.toHaveBeenCalledWith({ type: "error", message: "WebSocket error" });
    act(() => ws.failClose(1006));
    expect(onClose).toHaveBeenCalled();
  });

  it("send() JSON-encodes frames once the socket is OPEN", () => {
    const onMessage = vi.fn();
    const { result } = renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    const ws = FakeWebSocket.instances[0];
    // Before open, send is dropped silently.
    act(() => result.current.send({ type: "stdin", data: "x" }));
    expect(ws.sent).toEqual([]);
    act(() => ws.open());
    act(() => result.current.send({ type: "stdin", data: "abc" }));
    act(() => result.current.send({ type: "resize", cols: 80, rows: 24 }));
    expect(ws.sent).toEqual([
      JSON.stringify({ type: "stdin", data: "abc" }),
      JSON.stringify({ type: "resize", cols: 80, rows: 24 }),
    ]);
  });

  it("closes the socket on unmount", () => {
    const onMessage = vi.fn();
    const { unmount } = renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );
    flushConnectTimer();
    const ws = FakeWebSocket.instances[0];
    expect(ws.closed).toBe(false);
    unmount();
    expect(ws.closed).toBe(true);
  });

  it("cancels a pending socket open when unmounted before the next tick", () => {
    const onMessage = vi.fn();
    const { unmount } = renderHook(() =>
      usePtyWebSocket({
        tabId: "t1",
        projectDir: "/p",
        provider: "claude-code",
        dangerous: false,
        onMessage,
      }),
    );

    unmount();
    flushConnectTimer();

    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});
