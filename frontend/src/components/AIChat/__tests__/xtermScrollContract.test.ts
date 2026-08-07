/**
 * Pins the xterm.js behaviour TerminalView deliberately does NOT reimplement.
 *
 * The owner asked for "↓ jumps to the bottom" as part of the #1994 missing-
 * input-box recovery. Investigation showed xterm already does it: with
 * `scrollOnUserInput` (default true), CoreService.triggerDataEvent fires
 * onRequestScrollToBottom, which CoreTerminal wires to scrollToBottom — and the
 * keystroke is STILL delivered to the PTY, which is what makes the CLI repaint
 * its input box. So TerminalView adds only the hint and leaves ↓ alone.
 *
 * That makes this file load-bearing: it is the evidence for a decision not to
 * write code. If an xterm upgrade or an options change breaks the assumption,
 * these tests fail loudly instead of the assumption silently rotting.
 *
 * Unlike TerminalView.test.tsx this suite uses the REAL xterm build, so it must
 * not sit in a file that vi.mock()s the module.
 */
import { beforeAll, describe, expect, it } from "vitest";

import { Terminal } from "@xterm/xterm";

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

const ESC = String.fromCharCode(27);

interface Harness {
  term: Terminal;
  /** Everything xterm handed to the PTY. */
  sent: string[];
  dispose: () => void;
}

async function openTerminalWithScrollback(): Promise<Harness> {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const term = new Terminal({ cols: 40, rows: 5, scrollback: 200 });
  term.open(host);
  const sent: string[] = [];
  term.onData((d) => sent.push(d));
  // Enough lines to push content into the scrollback.
  await new Promise<void>((resolve) => term.write("line\r\n".repeat(60), resolve));
  return {
    term,
    sent,
    dispose: () => {
      term.dispose();
      host.remove();
    },
  };
}

function pressArrowDown(term: Terminal) {
  term.textarea!.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "ArrowDown",
      code: "ArrowDown",
      keyCode: 40,
      bubbles: true,
      cancelable: true,
    }),
  );
}

describe("xterm scroll contract (#1994)", () => {
  it("enables scrollOnUserInput by default, and TerminalView never overrides it", async () => {
    const h = await openTerminalWithScrollback();
    try {
      expect(h.term.options.scrollOnUserInput).toBe(true);
    } finally {
      h.dispose();
    }
  });

  it("↓ jumps the viewport to the bottom with no code of ours involved", async () => {
    const h = await openTerminalWithScrollback();
    try {
      h.term.scrollToTop();
      const baseY = h.term.buffer.active.baseY;
      expect(baseY).toBeGreaterThan(0);
      expect(h.term.buffer.active.viewportY).toBe(0);

      pressArrowDown(h.term);

      expect(h.term.buffer.active.viewportY).toBe(baseY);
    } finally {
      h.dispose();
    }
  });

  it("↓ still reaches the PTY — that delivery is what repaints the CLI", async () => {
    const h = await openTerminalWithScrollback();
    try {
      h.term.scrollToTop();
      pressArrowDown(h.term);

      // ESC[B (normal) or ESCOB (application cursor keys). If a future change
      // starts swallowing ↓ to "scroll to bottom", this assertion fails — and
      // it should, because swallowing it removes the actual recovery.
      // ESC is spelled out rather than written into the pattern so the regex
      // stays free of control characters (eslint no-control-regex), and the
      // failure message shows something a human can read.
      const readable = h.sent.join("").split(ESC).join("<ESC>");
      expect(readable).toMatch(/<ESC>(\[|O)B/);
    } finally {
      h.dispose();
    }
  });

  it("keeps the viewport pinned to the bottom as new output arrives", async () => {
    const h = await openTerminalWithScrollback();
    try {
      expect(h.term.buffer.active.viewportY).toBe(h.term.buffer.active.baseY);
      await new Promise<void>((r) => h.term.write("more\r\n".repeat(20), r));
      // Still at the bottom -> the hint must stay hidden.
      expect(h.term.buffer.active.viewportY).toBe(h.term.buffer.active.baseY);
    } finally {
      h.dispose();
    }
  });

  it("leaves the viewport behind when output arrives while scrolled up", async () => {
    const h = await openTerminalWithScrollback();
    try {
      h.term.scrollToTop();
      await new Promise<void>((r) => h.term.write("more\r\n".repeat(20), r));
      // baseY moved, viewportY did not -> still "scrolled up", hint stays up.
      expect(h.term.buffer.active.viewportY).toBeLessThan(h.term.buffer.active.baseY);
    } finally {
      h.dispose();
    }
  });
});
