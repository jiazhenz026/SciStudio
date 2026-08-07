/**
 * ADR-034 — "you are scrolled up, press ↓" hint for the embedded PTY (#1994).
 *
 * Why this exists. Some CLIs intermittently fail to paint their bottom input
 * box: the PTY is created at exactly the size the client asked for, so the
 * frontend's ResizeObserver never fires and a CLI that painted early is never
 * told to repaint. A backend-side post-spawn column jiggle reduced it but the
 * owner still sees it occasionally. The recovery is trivial — press ↓ — and the
 * owner's point is that the user has no way to know that. So we surface the
 * recovery rather than keep chasing the defect.
 *
 * What this hook does NOT do, deliberately: it does not touch the ↓ key.
 * xterm already scrolls the viewport to the bottom on user input
 * (`scrollOnUserInput`, default true; CoreService.triggerDataEvent fires
 * onRequestScrollToBottom, which CoreTerminal wires to scrollToBottom), AND it
 * still delivers the keystroke to the PTY as ESC[B / ESCOB. Both halves matter:
 * the scroll is what the user sees, and the delivery is what makes the CLI
 * repaint its input box — that repaint IS the fix. Intercepting ↓ ourselves
 * would be redundant at best and, if we swallowed the key, would break the very
 * recovery we are advertising. The upstream contract we depend on is pinned by
 * __tests__/xtermScrollContract.test.ts against the real xterm build.
 *
 * Alt-screen TUIs have no scrollback (baseY stays 0), so the hint never appears
 * there — correct, because scrolling is not a thing in that mode.
 */
import { useCallback, useRef, useState } from "react";

/** The slice of the xterm API this hook reads. */
export interface ScrollAwareTerm {
  buffer?: { active?: { viewportY?: number; baseY?: number } };
  onScroll?: (cb: (ydisp: number) => void) => { dispose: () => void };
  onRender?: (cb: (range: { start: number; end: number }) => void) => { dispose: () => void };
}

/**
 * True when the viewport is showing history rather than the live bottom.
 *
 * `baseY` is the buffer row of the top of the bottom page; `viewportY` is the
 * buffer row currently at the top of the viewport. They are equal exactly when
 * the user is at the bottom.
 */
export function isScrolledUp(term: ScrollAwareTerm | null): boolean {
  const active = term?.buffer?.active;
  if (!active) return false;
  const viewportY = active.viewportY;
  const baseY = active.baseY;
  if (typeof viewportY !== "number" || typeof baseY !== "number") return false;
  return viewportY < baseY;
}

export interface UseTerminalScrollHintResult {
  /** True while the viewport is scrolled up; drives the floating hint. */
  scrolledUp: boolean;
  /**
   * Subscribe to a live terminal. Call from the xterm mount effect and invoke
   * the returned disposer during its cleanup. Stable across renders.
   */
  attachScrollHint: (term: ScrollAwareTerm) => () => void;
}

export function useTerminalScrollHint(): UseTerminalScrollHintResult {
  const [scrolledUp, setScrolledUp] = useState(false);
  // Mirror of the state so a firehose of output does not call setState on every
  // rendered frame just to set the same value.
  const lastRef = useRef(false);

  const attachScrollHint = useCallback((term: ScrollAwareTerm) => {
    const sync = () => {
      const next = isScrolledUp(term);
      if (next === lastRef.current) return;
      lastRef.current = next;
      setScrolledUp(next);
    };

    // onScroll covers the user moving the viewport (wheel, scrollbar, keys).
    // onRender covers the other direction: output arriving, which moves baseY
    // out from under a viewport that is standing still. Neither alone is
    // sufficient to keep the flag honest.
    const subscriptions = [term.onScroll?.(sync), term.onRender?.(sync)].filter(
      (d): d is { dispose: () => void } => Boolean(d),
    );
    sync();

    return () => {
      for (const subscription of subscriptions) {
        try {
          subscription.dispose();
        } catch {
          /* already disposed with the terminal */
        }
      }
      lastRef.current = false;
      setScrolledUp(false);
    };
  }, []);

  return { scrolledUp, attachScrollHint };
}
