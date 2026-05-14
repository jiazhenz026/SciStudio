/**
 * Tests for TerminalView. We replace @xterm/xterm and addons with vi.mock so
 * the test does not depend on canvas / DOM measurement in jsdom.
 */
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TerminalView } from "../TerminalView";

// --- xterm.js mock state ----------------------------------------------------
const xtermState: {
  lastInstance: FakeTerm | null;
  loadedAddons: unknown[];
  written: string[];
  onDataCb: ((s: string) => void) | null;
} = { lastInstance: null, loadedAddons: [], written: [], onDataCb: null };

class FakeTerm {
  cols = 80;
  rows = 24;
  constructor(public opts: unknown) {
    xtermState.lastInstance = this;
  }
  loadAddon(addon: unknown) {
    xtermState.loadedAddons.push(addon);
  }
  open(_el: HTMLElement) {
    void _el;
  }
  write(s: string) {
    xtermState.written.push(s);
  }
  onData(cb: (s: string) => void) {
    xtermState.onDataCb = cb;
    return { dispose: () => {} };
  }
  dispose() {}
}

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerm }));
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {}
  },
}));
vi.mock("@xterm/addon-search", () => ({
  SearchAddon: class {},
}));
vi.mock("@xterm/addon-web-links", () => ({
  WebLinksAddon: class {},
}));

// --- WebSocket fake ---------------------------------------------------------
class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = 0;
  sent: string[] = [];
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
  send(s: string) {
    this.sent.push(s);
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }
}

const originalWs = global.WebSocket;

beforeEach(() => {
  xtermState.lastInstance = null;
  xtermState.loadedAddons = [];
  xtermState.written = [];
  xtermState.onDataCb = null;
  FakeWebSocket.instances = [];
  (global as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket;
});

afterEach(() => {
  cleanup();
  (global as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWs;
  vi.restoreAllMocks();
});

describe("TerminalView", () => {
  async function waitForTerm() {
    await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
  }

  it("creates a Terminal and loads fit/search/web-links addons", async () => {
    render(
      <TerminalView
        tabId="t1"
        projectDir="/proj"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitForTerm();
    expect(xtermState.lastInstance).toBeInstanceOf(FakeTerm);
    expect(xtermState.loadedAddons).toHaveLength(3);
  });

  it("opens a PTY WebSocket with the right URL", async () => {
    render(
      <TerminalView
        tabId="abc"
        projectDir="/p"
        provider="claude-code"
        dangerous={true}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    const url = FakeWebSocket.instances[0].url;
    expect(url).toContain("/api/ai/pty/abc");
    expect(url).toContain("dangerous=true");
    expect(url).toContain("provider=claude-code");
  });

  it("writes server stdout into the terminal", async () => {
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(FakeWebSocket.instances[0]).toBeDefined());
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.message(JSON.stringify({ type: "stdout", data: "hello\r\n" }));
    expect(xtermState.written).toContain("hello\r\n");
  });

  it("forwards keystrokes from xterm.onData as stdin frames", async () => {
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(xtermState.onDataCb).not.toBeNull());
    const ws = FakeWebSocket.instances[0];
    ws.open();
    xtermState.onDataCb?.("ls\r");
    expect(ws.sent).toContain(JSON.stringify({ type: "stdin", data: "ls\r" }));
  });

  it("calls onExit when the server sends an exit frame", async () => {
    const onExit = vi.fn();
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={onExit}
        onError={vi.fn()}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(FakeWebSocket.instances[0]).toBeDefined());
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.message(JSON.stringify({ type: "exit", code: 0 }));
    expect(onExit).toHaveBeenCalledWith(0);
  });

  it("calls onError when the server sends an error frame", async () => {
    const onError = vi.fn();
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={vi.fn()}
        onError={onError}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(FakeWebSocket.instances[0]).toBeDefined());
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.message(JSON.stringify({ type: "error", message: "boom" }));
    expect(onError).toHaveBeenCalledWith("boom");
  });
});
