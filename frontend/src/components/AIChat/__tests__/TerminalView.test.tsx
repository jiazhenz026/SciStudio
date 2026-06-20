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
  onScrollCb: ((ydisp: number) => void) | null;
} = { lastInstance: null, loadedAddons: [], written: [], onDataCb: null, onScrollCb: null };

class FakeTerm {
  cols = 80;
  rows = 24;
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
  onScroll(cb: (ydisp: number) => void) {
    xtermState.onScrollCb = cb;
    return { dispose: () => {} };
  }
  refresh(_start: number, _end: number) {
    void _start;
    void _end;
    this.refreshCount += 1;
  }
  dispose() {}
}

vi.mock("@xterm/xterm", () => ({ Terminal: FakeTerm }));
// Count fit() calls so the resize tests can assert refit timing.
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

// --- ResizeObserver + IntersectionObserver fakes ----------------------------
// jsdom ships neither, so we stub both with manually-fired callbacks.
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

// The component freezes the terminal during a drag and refits via setTimeout
// once it settles (RESIZE_DEBOUNCE_MS=100). Tests use real timers and wait just
// past that window for the deferred fit.
const RESIZE_DEBOUNCE_WAIT_MS = 180;
function waitForDebounce(): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, RESIZE_DEBOUNCE_WAIT_MS));
}

beforeEach(() => {
  xtermState.lastInstance = null;
  xtermState.loadedAddons = [];
  xtermState.written = [];
  xtermState.onDataCb = null;
  xtermState.onScrollCb = null;
  FakeWebSocket.instances = [];
  fitState.fitCalls = 0;
  FakeResizeObserver.instances = [];
  FakeIntersectionObserver.instances = [];
  (global as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket;
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
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
    expect(xtermState.lastInstance?.opts).toMatchObject({ convertEol: false });
    // fit + search + web-links only. The canvas renderer (#1320) was reverted —
    // it did not repaint cleanly on resize — so we are back on xterm's default
    // DOM renderer with no extra renderer addon.
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
  // Freeze during a drag, refit ONCE when it settles. No refresh() at resize
  // time (the buffer is mid-update); the TUI repaints itself via SIGWINCH.
  async function waitForResizeObserver() {
    await waitFor(() => expect(FakeResizeObserver.instances.length).toBe(1));
  }

  it("refits once after the drag settles, without repainting", async () => {
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

    FakeResizeObserver.instances[0].trigger();
    // Frozen until the drag settles.
    expect(fitState.fitCalls).toBe(fitsBeforeResize);
    await waitForDebounce();

    expect(fitState.fitCalls).toBe(fitsBeforeResize + 1);
    // No manual repaint on resize — the TUI redraws itself via SIGWINCH.
    expect(term.refreshCount).toBe(0);
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
    const fitsBeforeResize = fitState.fitCalls;
    const observer = FakeResizeObserver.instances[0];

    // Simulate the rapid burst emitted while the splitter is dragged.
    observer.trigger();
    observer.trigger();
    observer.trigger();
    observer.trigger();
    observer.trigger();
    expect(fitState.fitCalls).toBe(fitsBeforeResize);
    await waitForDebounce();

    // Only the settled layout is fitted — not every intermediate drag frame.
    expect(fitState.fitCalls).toBe(fitsBeforeResize + 1);
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
    const fitsBeforeResize = fitState.fitCalls;

    FakeResizeObserver.instances[0].trigger(); // schedules a debounced fit
    unmount(); // cleanup must clear the timer before it fires
    await waitForDebounce();

    expect(fitState.fitCalls).toBe(fitsBeforeResize);
  });

  // --- visibility repaint ---------------------------------------------------
  // Switching the bottom panel away (display:none) and back left the DOM
  // renderer showing a stale/blank frame (bug#8). On return-to-view we refit
  // and force a full repaint.
  async function waitForIntersectionObserver() {
    await waitFor(() => expect(FakeIntersectionObserver.instances.length).toBe(1));
  }

  it("repaints when the terminal returns to view", async () => {
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

  // --- scroll repaint -------------------------------------------------------
  // The DOM renderer only repaints dirty cells, so scrolling leaves ghosted
  // glyphs. We force a full repaint on every scroll (replaces what the canvas
  // renderer gave us for free).
  it("repaints visible rows on scroll to avoid DOM-renderer ghosting", async () => {
    // Run the rAF-coalesced repaint synchronously for a deterministic assert.
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
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
    await waitFor(() => expect(xtermState.onScrollCb).not.toBeNull());
    const term = xtermState.lastInstance!;
    const refreshesBefore = term.refreshCount;

    xtermState.onScrollCb?.(5);

    expect(term.refreshCount).toBe(refreshesBefore + 1);
  });
});
