/**
 * Tests for the terminal context menu's edge-aware placement (#1994 follow-up).
 *
 * The reported bug: right-clicking near the bottom of the PTY rendered the menu
 * below the visible area, where it could not be clicked. The frame is
 * `overflow-hidden`, so anything past an edge is gone, not merely awkward.
 *
 * The maths is a pure function precisely so it can be tested — jsdom reports
 * every element as 0×0, so a DOM-only test can never exercise a flip.
 */
import { describe, expect, it } from "vitest";

import { resolveMenuPlacement } from "../TerminalView.parts/menuPlacement";

// A representative menu (two items) inside a representative PTY pane.
const MENU = { menuWidth: 128, menuHeight: 64 };
const FRAME = { frameWidth: 800, frameHeight: 400 };

describe("resolveMenuPlacement", () => {
  it("leaves a menu with room alone", () => {
    const p = resolveMenuPlacement({ x: 100, y: 100, ...MENU, ...FRAME });
    expect(p).toEqual({ left: 100, top: 100, flippedX: false, flippedY: false });
  });

  it("flips upward when the menu would overflow the bottom edge", () => {
    // The reported bug: right-click 20px from the bottom of a 400px pane.
    const p = resolveMenuPlacement({ x: 100, y: 380, ...MENU, ...FRAME });
    expect(p.top).toBe(380 - 64);
    expect(p.flippedY).toBe(true);
    // Fully inside the frame, which is the whole point.
    expect(p.top + MENU.menuHeight).toBeLessThanOrEqual(FRAME.frameHeight);
  });

  it("flips leftward when the menu would overflow the right edge", () => {
    const p = resolveMenuPlacement({ x: 780, y: 100, ...MENU, ...FRAME });
    expect(p.left).toBe(780 - 128);
    expect(p.flippedX).toBe(true);
    expect(p.left + MENU.menuWidth).toBeLessThanOrEqual(FRAME.frameWidth);
  });

  it("flips both axes in the bottom-right corner", () => {
    const p = resolveMenuPlacement({ x: 795, y: 395, ...MENU, ...FRAME });
    expect(p).toEqual({ left: 795 - 128, top: 395 - 64, flippedX: true, flippedY: true });
  });

  it("does not flip when the click is exactly at the fitting boundary", () => {
    const p = resolveMenuPlacement({
      x: FRAME.frameWidth - MENU.menuWidth,
      y: FRAME.frameHeight - MENU.menuHeight,
      ...MENU,
      ...FRAME,
    });
    expect(p.flippedX).toBe(false);
    expect(p.flippedY).toBe(false);
    expect(p.left).toBe(672);
    expect(p.top).toBe(336);
  });

  it("clamps instead of flipping off the top when the pane is shorter than the menu", () => {
    // A collapsed bottom panel: neither side fits. Showing the top of the menu
    // beats showing none of it.
    const p = resolveMenuPlacement({
      x: 10,
      y: 30,
      ...MENU,
      frameWidth: 800,
      frameHeight: 40,
    });
    expect(p.top).toBe(0);
    expect(p.flippedY).toBe(false);
  });

  it("clamps instead of flipping off the left when the pane is narrower than the menu", () => {
    const p = resolveMenuPlacement({
      x: 60,
      y: 10,
      ...MENU,
      frameWidth: 100,
      frameHeight: 400,
    });
    expect(p.left).toBe(0);
    expect(p.flippedX).toBe(false);
  });

  it("never returns a negative offset", () => {
    for (const [frameWidth, frameHeight] of [
      [0, 0],
      [10, 10],
      [800, 400],
    ]) {
      for (const [x, y] of [
        [0, 0],
        [5, 5],
        [799, 399],
      ]) {
        const p = resolveMenuPlacement({ x, y, ...MENU, frameWidth, frameHeight });
        expect(p.left).toBeGreaterThanOrEqual(0);
        expect(p.top).toBeGreaterThanOrEqual(0);
      }
    }
  });
});
