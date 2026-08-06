/**
 * Tests for TerminalView. We replace @xterm/xterm and addons with vi.mock so
 * the test does not depend on canvas / DOM measurement in jsdom.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TerminalView } from "../TerminalView";

// --- xterm.js mock state ----------------------------------------------------
const xtermState: {
  lastInstance: FakeTerm | null;
  loadedAddons: unknown[];
  written: string[];
  onDataCb: ((s: string) => void) | null;
  onScrollCb: ((ydisp: number) => void) | null;
  keyHandler: ((ev: KeyboardEvent) => boolean) | null;
} = {
  lastInstance: null,
  loadedAddons: [],
  written: [],
  onDataCb: null,
  onScrollCb: null,
  keyHandler: null,
};

class FakeTerm {
  cols = 80;
  rows = 24;
  refreshCount = 0;
  /** Current buffer selection, set by the clipboard tests. */
  selection = "";
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
  attachCustomKeyEventHandler(handler: (ev: KeyboardEvent) => boolean) {
    xtermState.keyHandler = handler;
  }
  getSelection() {
    return this.selection;
  }
  hasSelection() {
    return this.selection.length > 0;
  }
  /** Real xterm routes paste() into the onData stream; so does the fake. */
  paste(data: string) {
    xtermState.onDataCb?.(data);
  }
  dispose() {}
}

// --- clipboard fake ---------------------------------------------------------
// jsdom ships no navigator.clipboard, so each test installs its own.
interface FakeClipboard {
  writeText?: (text: string) => Promise<void>;
  readText?: () => Promise<string>;
}

function installClipboard(clipboard: FakeClipboard | null) {
  Object.defineProperty(navigator, "clipboard", {
    value: clipboard ?? undefined,
    configurable: true,
    writable: true,
  });
}

/** Build a plain object good enough for the custom key-event handler. */
function keyEvent(key: string, extra: Partial<KeyboardEvent> = {}) {
  const preventDefault = vi.fn();
  const ev = {
    type: "keydown",
    key,
    ctrlKey: true,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    preventDefault,
    ...extra,
  };
  return { ev: ev as unknown as KeyboardEvent, preventDefault };
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
  xtermState.keyHandler = null;
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
  installClipboard(null);
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

  // --- manual refresh button ------------------------------------------------
  // Escape hatch (#1946): when the alt-screen TUI leaves ghost residue the user
  // can force a full host-side repaint (mirrors selecting the text) without
  // tearing down the PTY.
  it("renders a manual refresh button for the tab", async () => {
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
    expect(screen.getByTestId("terminal-refresh-t1")).toBeInTheDocument();
  });

  it("refits and repaints when the manual refresh button is clicked", async () => {
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
    const term = xtermState.lastInstance!;
    const fitsBefore = fitState.fitCalls;
    const refreshesBefore = term.refreshCount;

    fireEvent.click(screen.getByTestId("terminal-refresh-t1"));

    // Refit (layout may have drifted while garbled) + one full host-side repaint.
    expect(fitState.fitCalls).toBe(fitsBefore + 1);
    expect(term.refreshCount).toBe(refreshesBefore + 1);
  });

  // --- clipboard UX (#1994) -------------------------------------------------
  // Owner decision: Ctrl+C copies and Ctrl+V pastes. The terminal loses its
  // interrupt gesture on purpose — closing a session is the tab's X button.
  describe("clipboard", () => {
    const STDIN_INTERRUPT = JSON.stringify({ type: "stdin", data: "\x03" });

    async function mountRunningTerminal() {
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
      await waitFor(() => expect(xtermState.lastInstance).not.toBeNull());
      await waitFor(() => expect(xtermState.keyHandler).not.toBeNull());
      await waitFor(() => expect(FakeWebSocket.instances[0]).toBeDefined());
      const ws = FakeWebSocket.instances[0];
      ws.open();
      return { ws, term: xtermState.lastInstance! };
    }

    it("Ctrl+C copies the current selection instead of interrupting the PTY", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      installClipboard({ writeText, readText: vi.fn() });
      const { ws, term } = await mountRunningTerminal();
      term.selection = "measured peak at 532 nm";
      const sentBefore = ws.sent.length;

      const { ev, preventDefault } = keyEvent("c");
      // Returning false is what stops xterm encoding the key as PTY bytes.
      expect(xtermState.keyHandler!(ev)).toBe(false);
      expect(preventDefault).toHaveBeenCalled();

      await waitFor(() => expect(writeText).toHaveBeenCalledWith("measured peak at 532 nm"));
      // The defining assertion of #1994: no interrupt, in fact no stdin at all.
      expect(ws.sent.length).toBe(sentBefore);
      expect(ws.sent).not.toContain(STDIN_INTERRUPT);
      await waitFor(() =>
        expect(screen.getByTestId("terminal-clipboard-hint-t1")).toHaveTextContent("Copied"),
      );
    });

    it("Ctrl+C with no selection is a hinted no-op, never an interrupt", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      installClipboard({ writeText, readText: vi.fn() });
      const { ws, term } = await mountRunningTerminal();
      term.selection = "";
      const sentBefore = ws.sent.length;

      expect(xtermState.keyHandler!(keyEvent("c").ev)).toBe(false);

      // Nothing is written (we never clobber the clipboard with "") and
      // nothing reaches the PTY — but the user is told why.
      await waitFor(() =>
        expect(screen.getByTestId("terminal-clipboard-hint-t1")).toHaveTextContent(
          "Nothing selected",
        ),
      );
      expect(writeText).not.toHaveBeenCalled();
      expect(ws.sent.length).toBe(sentBefore);
      expect(ws.sent).not.toContain(STDIN_INTERRUPT);
    });

    it("Ctrl+V writes the clipboard text to the PTY stdin", async () => {
      installClipboard({
        writeText: vi.fn(),
        readText: vi.fn().mockResolvedValue("import numpy as np\n"),
      });
      const { ws } = await mountRunningTerminal();

      const { ev, preventDefault } = keyEvent("v");
      expect(xtermState.keyHandler!(ev)).toBe(false);
      expect(preventDefault).toHaveBeenCalled();

      await waitFor(() =>
        expect(ws.sent).toContain(JSON.stringify({ type: "stdin", data: "import numpy as np\n" })),
      );
      // A successful paste is its own feedback; no toast.
      expect(screen.queryByTestId("terminal-clipboard-hint-t1")).toBeNull();
    });

    it("reports a denied clipboard permission instead of failing silently", async () => {
      installClipboard({
        writeText: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
        readText: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      });
      const { ws, term } = await mountRunningTerminal();
      term.selection = "some text";

      xtermState.keyHandler!(keyEvent("c").ev);
      await waitFor(() =>
        expect(screen.getByTestId("terminal-clipboard-hint-t1")).toHaveTextContent(
          "permission denied",
        ),
      );

      xtermState.keyHandler!(keyEvent("v").ev);
      await waitFor(() =>
        expect(screen.getByTestId("terminal-clipboard-hint-t1")).toHaveTextContent(
          "could not paste",
        ),
      );
      expect(ws.sent.some((f) => f.includes('"stdin"'))).toBe(false);
    });

    it("reports an absent Clipboard API (insecure origin) instead of throwing", async () => {
      installClipboard(null);
      const { term } = await mountRunningTerminal();
      term.selection = "some text";

      expect(xtermState.keyHandler!(keyEvent("c").ev)).toBe(false);
      await waitFor(() =>
        expect(screen.getByTestId("terminal-clipboard-hint-t1")).toHaveTextContent("unavailable"),
      );
    });

    it("leaves every other key to xterm, including the tab shortcuts", async () => {
      installClipboard({ writeText: vi.fn(), readText: vi.fn() });
      await mountRunningTerminal();
      const handler = xtermState.keyHandler!;

      // Ctrl+T / Ctrl+W / Ctrl+1 belong to TerminalTabs' window-level listener.
      for (const key of ["t", "w", "1", "9", "a", "d", "l"]) {
        expect(handler(keyEvent(key).ev)).toBe(true);
      }
      // Ctrl+Shift+C / Ctrl+Shift+V keep their conventional terminal meaning.
      expect(handler(keyEvent("c", { shiftKey: true }).ev)).toBe(true);
      expect(handler(keyEvent("v", { shiftKey: true }).ev)).toBe(true);
      // Plain C / V type normally.
      expect(handler(keyEvent("c", { ctrlKey: false }).ev)).toBe(true);
      // keyup/keypress repeats of the same key must not double-fire.
      expect(handler(keyEvent("c", { type: "keyup" } as Partial<KeyboardEvent>).ev)).toBe(true);
    });

    it("opens a context menu on right-click with Copy enabled when text is selected", async () => {
      installClipboard({ writeText: vi.fn().mockResolvedValue(undefined), readText: vi.fn() });
      const { term } = await mountRunningTerminal();
      term.selection = "peak 532 nm";

      expect(screen.queryByTestId("terminal-context-menu-t1")).toBeNull();
      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"), {
        clientX: 40,
        clientY: 60,
      });

      expect(screen.getByTestId("terminal-context-menu-t1")).toBeInTheDocument();
      expect(screen.getByTestId("terminal-context-copy-t1")).toBeEnabled();
      expect(screen.getByTestId("terminal-context-paste-t1")).toBeEnabled();
    });

    it("disables the context-menu Copy item when nothing is selected", async () => {
      installClipboard({ writeText: vi.fn(), readText: vi.fn() });
      const { term } = await mountRunningTerminal();
      term.selection = "";

      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"));

      expect(screen.getByTestId("terminal-context-copy-t1")).toBeDisabled();
      // Paste never depends on the selection.
      expect(screen.getByTestId("terminal-context-paste-t1")).toBeEnabled();
    });

    it("copies from the context menu and closes it", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      installClipboard({ writeText, readText: vi.fn() });
      const { term } = await mountRunningTerminal();
      term.selection = "sample-042";

      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"));
      fireEvent.click(screen.getByTestId("terminal-context-copy-t1"));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith("sample-042"));
      expect(screen.queryByTestId("terminal-context-menu-t1")).toBeNull();
    });

    it("pastes from the context menu into the PTY and closes it", async () => {
      installClipboard({ writeText: vi.fn(), readText: vi.fn().mockResolvedValue("/data/run7") });
      const { ws } = await mountRunningTerminal();

      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"));
      fireEvent.click(screen.getByTestId("terminal-context-paste-t1"));

      await waitFor(() =>
        expect(ws.sent).toContain(JSON.stringify({ type: "stdin", data: "/data/run7" })),
      );
      expect(screen.queryByTestId("terminal-context-menu-t1")).toBeNull();
    });

    it("dismisses the context menu on Escape and on an outside click", async () => {
      installClipboard({ writeText: vi.fn(), readText: vi.fn() });
      await mountRunningTerminal();

      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"));
      expect(screen.getByTestId("terminal-context-menu-t1")).toBeInTheDocument();
      fireEvent.keyDown(window, { key: "Escape" });
      expect(screen.queryByTestId("terminal-context-menu-t1")).toBeNull();

      fireEvent.contextMenu(screen.getByTestId("terminal-view-t1"));
      expect(screen.getByTestId("terminal-context-menu-t1")).toBeInTheDocument();
      fireEvent.mouseDown(document.body);
      expect(screen.queryByTestId("terminal-context-menu-t1")).toBeNull();
    });
  });
});
