/**
 * Pins the xterm.js paste behaviour TerminalView's Ctrl+V handling depends on.
 *
 * This file exists because the first implementation of Ctrl+V passed its unit
 * tests and still did nothing for the user. Those tests asserted against a
 * FakeTerm that recorded `paste()` being called — which proves a call happened,
 * not that anything arrived. The real failure was one layer down: the handler
 * called preventDefault (killing the browser's native paste) and then relied on
 * `navigator.clipboard.readText()`, which rejects with NotAllowedError until the
 * `clipboard-read` permission is granted. Copy kept working because
 * `writeText()` only needs transient user activation. Hence: copy fine, paste
 * dead.
 *
 * The fix is to claim the key (so xterm does not encode it as \x16) but NOT
 * preventDefault, letting the browser's own paste event fire — xterm listens
 * for it and converts it to a data event. That path needs no permission.
 *
 * Verified in real Chromium via Playwright against http://127.0.0.1:5173 before
 * being written up here:
 *
 *   stock xterm, no permission        -> "\x16"        (SYN, no paste)
 *   previous implementation, no perm  -> nothing       (readText NotAllowedError)
 *   fixed handler, no permission      -> "PASTED-TEXT" (native paste)
 *   fixed handler, permission granted -> "PASTED-TEXT"
 *   bracketed paste on, native path   -> "\x1b[200~line1\rline2\x1b[201~"
 *
 * These tests use the REAL xterm build so the two halves of that chain stay
 * pinned in the suite that CI runs: what xterm does with Ctrl+V when we do not
 * claim it, and what it does with a paste event when we let one through.
 */
import { beforeAll, describe, expect, it } from "vitest";

import { Terminal } from "@xterm/xterm";

const ESC = String.fromCharCode(27);
const SYN = String.fromCharCode(22);

beforeAll(() => {
  // jsdom ships neither, and xterm's CoreBrowserService needs both to open().
  window.matchMedia = ((query: string) => ({
    media: query,
    matches: false,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  HTMLCanvasElement.prototype.getContext = (() => ({
    measureText: () => ({ width: 8 }),
    fillRect() {},
    clearRect() {},
    getImageData: () => ({ data: [] }),
    setTransform() {},
    save() {},
    restore() {},
    createLinearGradient: () => ({ addColorStop() {} }),
  })) as unknown as typeof HTMLCanvasElement.prototype.getContext;
});

interface Harness {
  term: Terminal;
  /** Everything xterm handed to the PTY. */
  sent: string[];
  host: HTMLDivElement;
  dispose: () => void;
}

function openTerminal(): Harness {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const term = new Terminal({ cols: 40, rows: 8 });
  term.open(host);
  const sent: string[] = [];
  term.onData((d) => sent.push(d));
  return {
    term,
    sent,
    host,
    dispose: () => {
      term.dispose();
      host.remove();
    },
  };
}

function ctrlV(): KeyboardEvent {
  return new KeyboardEvent("keydown", {
    key: "v",
    code: "KeyV",
    keyCode: 86,
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
}

/**
 * Dispatch a paste event carrying `text`, the way a browser does after a real
 * Ctrl+V. jsdom has no ClipboardEvent with a populated clipboardData, so the
 * payload is attached to a plain Event — xterm only ever calls
 * `ev.clipboardData.getData("text/plain")`.
 */
function dispatchPaste(target: EventTarget, text: string) {
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  (ev as Event & { clipboardData: { getData: () => string } }).clipboardData = {
    getData: () => text,
  };
  target.dispatchEvent(ev);
}

describe("xterm paste contract (#1994 follow-up)", () => {
  it("encodes an unclaimed Ctrl+V as \\x16, which is why we must claim it", () => {
    // Ctrl+V is SYN in a terminal. If our handler returned true, this is what
    // the PTY would receive instead of the user's clipboard — and xterm also
    // cancels the event, so the browser's native paste never runs either.
    const h = openTerminal();
    try {
      h.term.textarea!.dispatchEvent(ctrlV());
      expect(h.sent.join("")).toBe(SYN);
    } finally {
      h.dispose();
    }
  });

  it("does not send \\x16 when the custom handler claims Ctrl+V", () => {
    const h = openTerminal();
    try {
      // Exactly what useTerminalClipboard does for Ctrl+V: claim, no preventDefault.
      h.term.attachCustomKeyEventHandler((ev) => {
        if (ev.type !== "keydown") return true;
        if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.shiftKey) return true;
        return ev.key.toLowerCase() !== "v";
      });

      const ev = ctrlV();
      h.term.textarea!.dispatchEvent(ev);

      expect(h.sent.join("")).toBe("");
      // Not cancelled -> the browser goes on to perform its native paste.
      expect(ev.defaultPrevented).toBe(false);
    } finally {
      h.dispose();
    }
  });

  it("turns a native paste event into PTY input", () => {
    // This is the delivery the fix relies on, and the half a mocked terminal
    // could never have proven.
    const h = openTerminal();
    try {
      dispatchPaste(h.term.textarea!, "import numpy as np");
      expect(h.sent.join("")).toBe("import numpy as np");
    } finally {
      h.dispose();
    }
  });

  it("applies bracketed-paste framing on the native path", () => {
    // The reason the original implementation routed through term.paste(). The
    // native path does it too, so nothing was lost by dropping term.paste().
    const h = openTerminal();
    try {
      h.term.write(`${ESC}[?2004h`); // the CLI enables bracketed paste
      // write() is async; the mode is applied on the parse tick.
      return new Promise<void>((resolve) => {
        h.term.write("", () => {
          dispatchPaste(h.term.textarea!, "line1\nline2");
          expect(h.sent.join("")).toBe(`${ESC}[200~line1\rline2${ESC}[201~`);
          h.dispose();
          resolve();
        });
      });
    } catch (err) {
      h.dispose();
      throw err;
    }
  });

  it("normalises newlines so a multi-line paste is not half-executed", () => {
    const h = openTerminal();
    try {
      dispatchPaste(h.term.textarea!, "a\r\nb\nc");
      expect(h.sent.join("")).toBe("a\rb\rc");
    } finally {
      h.dispose();
    }
  });
});
