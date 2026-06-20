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
  scrollToBottomCount = 0;
  refreshCount = 0;
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
  scrollToBottom() {
    this.scrollToBottomCount += 1;
  }
  refresh(_start: number, _end: number) {
    void _start;
    void _end;
    this.refreshCount += 1;
  }
  dispose() {}
}

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerm }));
// Count fit() calls so the resize-coalescing test can assert that a burst of
// ResizeObserver callbacks collapses to a single fit on the settled layout.
const fitState = { fitCalls: 0 };
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: class {
    fit() {
      fitState.fitCalls += 1;
    }
  },
}));
vi.mock("@xterm/addon-search", () => ({
  SearchAddon: class {},
}));
vi.mock("@xterm/addon-web-links", () => ({
  WebLinksAddon: class {},
}));
vi.mock("@xterm/addon-canvas", () => ({
  CanvasAddon: class {},
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
  failClose(code = 1006, reason = "") {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

const originalWs = global.WebSocket;

// --- ResizeObserver + requestAnimationFrame fakes --------------------------
// jsdom ships neither a ResizeObserver nor a frame scheduler we can drive, so
// the resize tests stub both: ResizeObserver callbacks are captured for manual
// firing, and rAF callbacks queue up so the test can flush them deterministically.
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
    FakeResizeObserver.instances.push(this);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  trigger() {
    this.cb([], this as unknown as ResizeObserver);
  }
}

const rafQueue = new Map<number, FrameRequestCallback>();
let rafSeq = 0;
function flushRaf() {
  const callbacks = [...rafQueue.values()];
  rafQueue.clear();
  for (const cb of callbacks) cb(0);
}

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  cb: IntersectionObserverCallback;
  constructor(cb: IntersectionObserverCallback) {
    this.cb = cb;
    FakeIntersectionObserver.instances.push(this);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  trigger(isIntersecting: boolean) {
    this.cb(
      [{ isIntersecting } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
}

beforeEach(() => {
  xtermState.lastInstance = null;
  xtermState.loadedAddons = [];
  xtermState.written = [];
  xtermState.onDataCb = null;
  FakeWebSocket.instances = [];
  fitState.fitCalls = 0;
  FakeResizeObserver.instances = [];
  FakeIntersectionObserver.instances = [];
  rafQueue.clear();
  rafSeq = 0;
  (global as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket;
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    rafSeq += 1;
    rafQueue.set(rafSeq, cb);
    return rafSeq;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    rafQueue.delete(id);
  });
});

afterEach(() => {
  cleanup();
  (global as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWs;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("TerminalView", () => {
  async function waitForTerm() {
    await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
  }

  it("creates a Terminal and loads fit/search/web-links/canvas addons", async () => {
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
    expect(xtermState.lastInstance?.opts).toMatchObject({ convertEol: false });
    // fit + search + web-links + canvas (hotfix #1320: canvas renderer
    // replaces the default DOM renderer to fix alt-screen scroll ghosting).
    expect(xtermState.loadedAddons).toHaveLength(4);
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
    expect(url).toContain("cols=80");
    expect(url).toContain("rows=24");
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

  it("reports a socket close that happens before a PTY exit frame", async () => {
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
    ws.failClose(1006);
    expect(onError).toHaveBeenCalledWith("WebSocket closed before PTY exit (code 1006)");
  });

  it("ignores a socket close that happens after a PTY exit frame", async () => {
    const onExit = vi.fn();
    const onError = vi.fn();
    render(
      <TerminalView
        tabId="t1"
        projectDir="/p"
        provider="claude-code"
        dangerous={false}
        onExit={onExit}
        onError={onError}
      />,
    );
    await waitForTerm();
    await waitFor(() => expect(FakeWebSocket.instances[0]).toBeDefined());
    const ws = FakeWebSocket.instances[0];
    ws.open();
    ws.message(JSON.stringify({ type: "exit", code: 0 }));
    ws.failClose(1000);
    expect(onExit).toHaveBeenCalledWith(0);
    expect(onError).not.toHaveBeenCalled();
  });

  // --- resize behaviour -----------------------------------------------------
  // Regression for the hotfix: dragging the bottom-panel splitter left the PTY
  // content clipped and unscrollable. The fix coalesces the ResizeObserver
  // burst into one fit on the settled layout and snaps the viewport to the
  // newest output afterwards.
  async function waitForResizeObserver() {
    await waitFor(() => expect(FakeResizeObserver.instances.length).toBe(1));
  }

  it("refits and scrolls to the bottom after a container resize", async () => {
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
    await waitForResizeObserver();
    const term = xtermState.lastInstance!;
    const fitsBeforeResize = fitState.fitCalls;
    expect(term.scrollToBottomCount).toBe(0);

    FakeResizeObserver.instances[0].trigger();
    flushRaf();

    expect(fitState.fitCalls).toBe(fitsBeforeResize + 1);
    expect(term.scrollToBottomCount).toBe(1);
  });

  it("coalesces a burst of resize callbacks into a single fit", async () => {
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
    await waitForResizeObserver();
    const term = xtermState.lastInstance!;
    const fitsBeforeResize = fitState.fitCalls;
    const observer = FakeResizeObserver.instances[0];

    // Simulate the rapid burst emitted while the splitter is dragged.
    observer.trigger();
    observer.trigger();
    observer.trigger();
    observer.trigger();
    observer.trigger();
    flushRaf();

    // Only the settled layout is fitted — not every intermediate drag frame.
    expect(fitState.fitCalls).toBe(fitsBeforeResize + 1);
    expect(term.scrollToBottomCount).toBe(1);
  });

  it("cancels a pending resize fit when the view unmounts", async () => {
    const { unmount } = render(
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
    await waitForResizeObserver();
    const term = xtermState.lastInstance!;
    const fitsBeforeResize = fitState.fitCalls;

    FakeResizeObserver.instances[0].trigger(); // schedules a rAF
    unmount(); // cleanup must cancel it before it runs
    flushRaf();

    expect(fitState.fitCalls).toBe(fitsBeforeResize);
    expect(term.scrollToBottomCount).toBe(0);
  });

  // --- visibility repaint ---------------------------------------------------
  // Regression for the hotfix: switching the bottom panel away (display:none)
  // and back left xterm's canvas showing scrambled stale pixels. On
  // return-to-view we refit and force a full canvas repaint.
  async function waitForIntersectionObserver() {
    await waitFor(() => expect(FakeIntersectionObserver.instances.length).toBe(1));
  }

  it("repaints the canvas when the terminal returns to view", async () => {
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
    await waitForIntersectionObserver();
    const term = xtermState.lastInstance!;
    expect(term.refreshCount).toBe(0);

    const io = FakeIntersectionObserver.instances[0];
    io.trigger(false); // hidden (panel collapsed / tab switched away)
    io.trigger(true); // shown again

    expect(term.refreshCount).toBe(1);
    expect(term.scrollToBottomCount).toBeGreaterThanOrEqual(1);
  });

  it("does not repaint on the initial visible observation", async () => {
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
    await waitForIntersectionObserver();
    const term = xtermState.lastInstance!;

    // The first observation reports the element already visible — no repaint.
    FakeIntersectionObserver.instances[0].trigger(true);
    expect(term.refreshCount).toBe(0);
  });
});
