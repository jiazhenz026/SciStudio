/**
 * ADR-053 Learning Center (#2135) — a beat arriving a character at a time.
 *
 * Two behaviors are being protected here and they pull in opposite
 * directions. In a browser the line has to arrive at a speaking pace, because
 * text that appears all at once on a tutorial somebody is half-skimming is
 * read at whatever speed they were already going. Under the runner it has to
 * not animate at all, because every existing assertion about what a step says
 * would otherwise be racing an interval — which is why `vitest.setup.ts`
 * answers "reduce" to the motion query for the whole suite.
 *
 * That default is the reason this file installs its own `matchMedia` for the
 * animated cases and puts the suite's back afterwards. Leaving a non-reduced
 * stub behind would hand every later file a typewriter that types, and the
 * failures would land in tests that have nothing to do with this one. The
 * pattern is `xtermPasteContract.test.ts`'s.
 *
 * The case that matters most is `reveal()` followed by another tick. A reader
 * who does not want to wait clicks once and gets the whole line; if the next
 * interval tick then wrote its own shorter prefix back over it, the line would
 * visibly retreat and the click would have cost them text instead of saving
 * them time.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TYPEWRITER_MS_PER_CHAR, prefersReducedMotion, useTypewriter } from "../useTypewriter";

/** The suite-wide stub from `vitest.setup.ts`, which answers "reduce". */
const REDUCED_MOTION = window.matchMedia;

/**
 * Answer the motion query the way a browser with a reader in front of it does.
 *
 * Assigned rather than mocked because `prefersReducedMotion` reads
 * `window.matchMedia` at call time and nothing else — there is no module seam
 * to intercept, and inventing one would be a seam that exists only for tests.
 */
function withMotion(): void {
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
}

afterEach(() => {
  window.matchMedia = REDUCED_MOTION;
  vi.useRealTimers();
});

describe("a reader who has asked for less motion", () => {
  it("is given the whole beat on the first paint", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 26));

    expect(result.current.shown).toBe(26);
    expect(result.current.done).toBe(true);
  });

  it("has nothing scheduled against them at all", () => {
    /*
     * Not merely "finishes instantly". An interval that ran and then set the
     * same number over and over would satisfy the assertion above while still
     * waking the browser sixty times a second on a panel that is not changing,
     * and would keep doing it for as long as the step is on screen.
     */
    vi.useFakeTimers();
    renderHook(() => useTypewriter("first-beat", 26));

    expect(vi.getTimerCount()).toBe(0);
  });

  it("is what a host with no media queries at all is treated as", () => {
    /*
     * A renderer, a snapshot, or a test environment is not a reader. "Cannot
     * tell" has to mean "do not animate", because the alternative is an
     * assertion somewhere reading half a sentence and nobody being able to say
     * which half it will be.
     */
    // Installed and then removed rather than simply left out, so the query
    // that would have answered "animate" is demonstrably gone: without the
    // removal this reads `false` and the case proves nothing.
    withMotion();
    Reflect.deleteProperty(window, "matchMedia");

    expect(prefersReducedMotion()).toBe(true);
  });

  it("is what a host whose media query throws is treated as", () => {
    window.matchMedia = (() => {
      throw new Error("matchMedia is not available in this context");
    }) as unknown as typeof window.matchMedia;

    expect(prefersReducedMotion()).toBe(true);
  });
});

describe("a beat arriving at a speaking pace", () => {
  it("starts from nothing rather than flashing the line first", () => {
    /*
     * The whole line for one frame and then nothing is worse than either
     * behavior on its own: the reader sees the sentence, loses it, and reads
     * it again as it types. The initial state has to be empty on the render
     * before the effect runs, not corrected by it.
     */
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 3));

    expect(result.current.shown).toBe(0);
    expect(result.current.done).toBe(false);
  });

  it("adds one character per tick and reports itself finished on the last one", () => {
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 3));

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR);
    });
    expect(result.current.shown).toBe(1);
    expect(result.current.done).toBe(false);

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR);
    });
    expect(result.current.shown).toBe(2);
    expect(result.current.done).toBe(false);

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR);
    });
    expect(result.current.shown).toBe(3);
    expect(result.current.done).toBe(true);
  });

  it("stops waking up once the beat is on screen", () => {
    // The interval clears itself on the character that completes the line, so
    // a step the reader sits on costs nothing while they read it.
    withMotion();
    vi.useFakeTimers();
    renderHook(() => useTypewriter("first-beat", 2));

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR * 2);
    });

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("a reader who does not want to wait", () => {
  it("gets the rest of the beat the moment they ask for it", () => {
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 8));

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR * 2);
    });
    expect(result.current.shown).toBe(2);

    act(() => {
      result.current.reveal();
    });

    expect(result.current.shown).toBe(8);
    expect(result.current.done).toBe(true);
  });

  it("does not watch the line retreat on the tick after they asked", () => {
    /*
     * The failure this exists for. The interval counts in a closure of its
     * own, so a tick arriving after `reveal()` would write its own prefix back
     * over the finished line — the reader would see the sentence complete and
     * then shorten under them, and the click that was meant to save them time
     * would have taken text away instead.
     */
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 8));

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR * 2);
    });
    act(() => {
      result.current.reveal();
    });

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR * 5);
    });

    expect(result.current.shown).toBe(8);
    expect(result.current.done).toBe(true);
  });

  it("is asking for the same thing twice when they ask twice", () => {
    // Clicking through a step at speed lands more than one reveal on the same
    // beat before the next one arrives; the second must be a no-op, not a
    // reset.
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("first-beat", 5));

    act(() => {
      result.current.reveal();
      result.current.reveal();
    });

    expect(result.current.shown).toBe(5);
    expect(result.current.done).toBe(true);
  });
});

describe("moving on to the next beat", () => {
  it("types the new line out from nothing instead of inheriting the last one's count", () => {
    /*
     * `beat` is the reset key, and it has to reset both the count and the
     * finished flag. Carrying either across would open the next beat already
     * complete — which is the pacing gone, silently, from the second line of
     * every step onward.
     */
    withMotion();
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ beat, total }: { beat: string; total: number }) => useTypewriter(beat, total),
      { initialProps: { beat: "first-beat", total: 4 } },
    );

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR * 4);
    });
    expect(result.current.done).toBe(true);

    rerender({ beat: "second-beat", total: 6 });

    expect(result.current.shown).toBe(0);
    expect(result.current.done).toBe(false);

    act(() => {
      vi.advanceTimersByTime(TYPEWRITER_MS_PER_CHAR);
    });
    expect(result.current.shown).toBe(1);
  });
});

describe("a beat with nothing in it", () => {
  it("is finished before it starts, and waits on no timer to say so", () => {
    /*
     * A step that says nothing, and the problem banner, both arrive here with
     * a length of zero. Waiting for a tick that will never move the count
     * would leave the panel's advance prompt hidden on a line that has already
     * finished — a step nobody can see their way out of.
     */
    withMotion();
    vi.useFakeTimers();
    const { result } = renderHook(() => useTypewriter("empty-beat", 0));

    expect(result.current.shown).toBe(0);
    expect(result.current.done).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
