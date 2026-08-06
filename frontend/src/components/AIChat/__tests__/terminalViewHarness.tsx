/**
 * Shared test doubles for the TerminalView suites.
 *
 * Not a test file itself (the name does not match vitest's `include`), so it is
 * imported by TerminalView.test.tsx and TerminalView.scrollHint.test.tsx rather
 * than duplicated. The `vi.mock()` calls stay in the test files: vitest hoists
 * them per-file, and each suite decides which modules it wants faked.
 *
 * jsdom provides none of what xterm needs — no canvas measurement, no
 * ResizeObserver / IntersectionObserver, no clipboard — so everything the
 * component touches is faked here with manually-fired callbacks.
 */
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// --- xterm.js mock state ----------------------------------------------------
export const xtermState: {
  lastInstance: FakeTerm | null;
  loadedAddons: unknown[];
  written: string[];
  onDataCb: ((s: string) => void) | null;
  // Real xterm supports many listeners per event and TerminalView registers two
  // onScroll handlers (repaint + scrolled-up hint), so the fake keeps lists.
  onScrollCbs: ((ydisp: number) => void)[];
  onRenderCbs: ((range: { start: number; end: number }) => void)[];
  keyHandler: ((ev: KeyboardEvent) => boolean) | null;
} = {
  lastInstance: null,
  loadedAddons: [],
  written: [],
  onDataCb: null,
  onScrollCbs: [],
  onRenderCbs: [],
  keyHandler: null,
};

/** Fire every registered listener, the way the real terminal would. */
export function fireScroll(ydisp = 0) {
  for (const cb of [...xtermState.onScrollCbs]) cb(ydisp);
}

export function fireRender() {
  for (const cb of [...xtermState.onRenderCbs]) cb({ start: 0, end: 23 });
}

export class FakeTerm {
  cols = 80;
  rows = 24;
  refreshCount = 0;
  /** Current buffer selection, set by the clipboard tests. */
  selection = "";
  /** Viewport position, set by the scrolled-up hint tests. */
  viewportY = 0;
  baseY = 0;
  constructor(public opts: unknown) {
    xtermState.lastInstance = this;
  }
  get buffer() {
    return { active: { viewportY: this.viewportY, baseY: this.baseY } };
  }
  /** Move the viewport off the bottom, as scrolling up in history would. */
  scrollUp(rowsOfHistory = 10) {
    this.baseY = rowsOfHistory;
    this.viewportY = 0;
  }
  /** Return the viewport to the live bottom. */
  scrollToBottom() {
    this.viewportY = this.baseY;
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
    xtermState.onScrollCbs.push(cb);
    return {
      dispose: () => {
        xtermState.onScrollCbs = xtermState.onScrollCbs.filter((c) => c !== cb);
      },
    };
  }
  onRender(cb: (range: { start: number; end: number }) => void) {
    xtermState.onRenderCbs.push(cb);
    return {
      dispose: () => {
        xtermState.onRenderCbs = xtermState.onRenderCbs.filter((c) => c !== cb);
      },
    };
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

/** Counts fit() calls so the resize tests can assert refit timing. */
export const fitState = { fitCalls: 0 };

export class FakeFitAddon {
  fit() {
    fitState.fitCalls += 1;
  }
}

// --- clipboard fake ---------------------------------------------------------
export interface FakeClipboard {
  writeText?: (text: string) => Promise<void>;
  readText?: () => Promise<string>;
}

export function installClipboard(clipboard: FakeClipboard | null) {
  Object.defineProperty(navigator, "clipboard", {
    value: clipboard ?? undefined,
    configurable: true,
    writable: true,
  });
}

/** Build a plain object good enough for the custom key-event handler. */
export function keyEvent(key: string, extra: Partial<KeyboardEvent> = {}) {
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

// --- WebSocket fake ---------------------------------------------------------
export class FakeWebSocket {
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

// --- ResizeObserver + IntersectionObserver fakes ----------------------------
export class FakeResizeObserver {
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

export class FakeIntersectionObserver {
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

export function waitForDebounce(): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, RESIZE_DEBOUNCE_WAIT_MS));
}

/**
 * Register the shared beforeEach/afterEach. Call once at the top level of a
 * suite file; the hooks attach to that file's root suite.
 */
export function installHarnessLifecycle() {
  const originalWs = global.WebSocket;

  beforeEach(() => {
    xtermState.lastInstance = null;
    xtermState.loadedAddons = [];
    xtermState.written = [];
    xtermState.onDataCb = null;
    xtermState.onScrollCbs = [];
    xtermState.onRenderCbs = [];
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
}
