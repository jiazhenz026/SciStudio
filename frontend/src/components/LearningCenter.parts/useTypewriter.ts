/**
 * ADR-053 Learning Center (#2135) — a beat arrives a character at a time.
 *
 * The reason is pacing, not decoration. A whole paragraph appearing at once is
 * read at whatever speed the reader is already going, which on a tutorial they
 * are half-skimming is "not at all"; text that arrives at a speaking pace is
 * read at a speaking pace, and the ▼ that appears when it stops is the signal
 * that the line is finished and the click is theirs to make. It is the same
 * device a visual novel uses, for the same reason.
 *
 * **A click while it is typing finishes the line; it does not skip it.** This
 * is the one rule that keeps the mechanism from costing the reader anything: a
 * reader who does not want to wait presses once and has the whole line, presses
 * again and moves on. Without it, an impatient click would advance past a
 * sentence they never saw, and the pacing would have taken text away rather
 * than given it a rhythm.
 *
 * **Nothing moves while it types.** The full line is in the DOM from the first
 * frame and the untyped tail is drawn transparent, so wrapping is decided once.
 * Growing the text instead would reflow the panel on nearly every character —
 * a scrollbar appearing mid-sentence in a fixed-height box, and words jumping
 * lines as the one before them fills up.
 *
 * `prefers-reduced-motion` turns the whole thing off, which is also what a test
 * environment reports: `vitest.setup.ts` answers "reduce", so every existing
 * assertion about what a step says still reads a finished line.
 */

import { useEffect, useRef, useState } from "react";

/**
 * Milliseconds per character.
 *
 * ~60 characters a second, which is a brisk speaking pace: fast enough that a
 * two-line beat is finished in about a second and a half, slow enough that the
 * arrival is legible as arrival rather than as a flicker.
 */
export const TYPEWRITER_MS_PER_CHAR = 16;

/**
 * Whether the reader has asked for less motion — and "cannot tell" counts as
 * yes.
 *
 * A host with no `matchMedia` is not a browser with a reader in front of it; it
 * is a renderer, a test, or a snapshot. Animating there is at best wasted and
 * at worst the reason an assertion reads half a sentence.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

export interface Typewriter {
  /** How many characters of the beat are visible. */
  shown: number;
  /** Whether the whole beat is on screen — the click is the reader's again. */
  done: boolean;
  /** Put the rest of the beat up now. Idempotent. */
  reveal: () => void;
}

/**
 * Type out `total` characters of the beat identified by `beat`.
 *
 * `beat` is the reset key rather than the text to render: this hook counts, and
 * what those characters are is the caller's business — which is what lets the
 * caller split the line into emphasized runs first and still reveal it as one
 * sentence.
 */
export function useTypewriter(beat: string, total: number): Typewriter {
  const instant = prefersReducedMotion();
  /*
   * The count and the beat it belongs to, held together.
   *
   * They are one piece of state because the reset has to happen *during* the
   * render the beat changes on, not in an effect afterwards. An effect runs
   * after commit and paint, so a beat shorter than the one before it was
   * painted once at the previous beat's count — which is to say complete, and
   * `done` — before the reset landed. The reader saw the next line flash whole
   * and start over, and a click in that frame advanced the step instead of
   * revealing the line, skipping a beat outright.
   */
  const [typed, setTyped] = useState(() => ({ beat, shown: instant ? total : 0 }));
  /*
   * Set the moment the beat is complete, by either route. The interval reads it
   * on every tick so that a `reveal()` mid-line stops the typing instead of
   * letting the next tick overwrite the finished line with a shorter prefix.
   */
  const finished = useRef(false);

  // Setting state during render is React's own answer to state derived from a
  // prop: the render is discarded and re-run at once, so nothing is painted
  // holding the old beat's count.
  if (typed.beat !== beat) setTyped({ beat, shown: instant ? total : 0 });
  const shown = typed.beat === beat ? typed.shown : instant ? total : 0;

  useEffect(() => {
    finished.current = false;

    if (instant || total === 0) {
      finished.current = true;
      setTyped({ beat, shown: total });
      return;
    }

    let count = 0;
    const timer = window.setInterval(() => {
      if (finished.current) {
        window.clearInterval(timer);
        return;
      }
      count += 1;
      setTyped({ beat, shown: count });
      if (count >= total) {
        finished.current = true;
        window.clearInterval(timer);
      }
    }, TYPEWRITER_MS_PER_CHAR);

    return () => window.clearInterval(timer);
  }, [beat, total, instant]);

  return {
    shown: Math.min(shown, total),
    done: shown >= total,
    reveal: () => {
      finished.current = true;
      setTyped({ beat, shown: total });
    },
  };
}
