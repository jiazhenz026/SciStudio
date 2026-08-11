/**
 * ADR-053 Learning Center (#2057) — where the step card lands.
 *
 * FR-089's one hard rule is that the card must not cover the element the step
 * is telling the reader to act on. The strip kept that by taking its own row;
 * a following card keeps it by geometry, so the geometry is what is tested —
 * every case below is a placement that would have broken the rule if the
 * fallback order were wrong.
 */

import { describe, expect, it } from "vitest";

import { CARD_WIDTH, placeCard, type CardPlacement } from "../placeCard";
import type { HighlightRect } from "../useHighlightRect";

const VIEWPORT = { width: 1400, height: 900 };

function topOf(placement: CardPlacement, viewport = VIEWPORT): number {
  // A docked card hangs from the bottom, so its top is only knowable once its
  // height is; the ceiling is the worst case and the one worth testing against.
  if (placement.top !== null) return placement.top;
  return viewport.height - (placement.bottom ?? 0) - placement.maxHeight;
}

function overlaps(placement: CardPlacement, rect: HighlightRect): boolean {
  // The card's height is unknown until it renders; 400 is far taller than it
  // ever is, so an overlap here is a real one rather than a measurement artifact.
  const top = topOf(placement);
  const card = {
    top,
    left: placement.left,
    right: placement.left + CARD_WIDTH,
    bottom: top + 400,
  };
  return (
    card.left < rect.left + rect.width &&
    card.right > rect.left &&
    card.top < rect.top + rect.height &&
    card.bottom > rect.top
  );
}

describe("placeCard", () => {
  it("docks to the bottom-right when the step points at nothing", () => {
    /*
     * A step with no target is prose to read, not an instruction to act on.
     * Centering it drops a wall of text into the middle of the user's own
     * workspace; the corner leaves the canvas and both panels readable behind
     * it, which is what a reader describing the workspace needs.
     */
    const placement = placeCard(null, VIEWPORT);

    expect(placement.side).toBeNull();
    expect(placement.left + CARD_WIDTH).toBeLessThanOrEqual(VIEWPORT.width);
    expect(placement.left).toBeGreaterThan(VIEWPORT.width / 2);
  });

  it("anchors a docked card by its bottom edge, not its top", () => {
    /*
     * The bug this prevents: a step with five sentences of prose is taller than
     * any estimate, so positioning by `top` pushed the card's lower half — with
     * Continue in it — off the bottom of the window, and the step could not be
     * finished at all. Anchored by the bottom, the card grows upward and the
     * buttons stay where they are.
     */
    const placement = placeCard(null, VIEWPORT);

    expect(placement.top).toBeNull();
    expect(placement.bottom).toBeGreaterThan(0);
  });

  it("keeps a docked card on screen in a window smaller than the card", () => {
    const placement = placeCard(null, { width: 300, height: 150 });

    expect(placement.left).toBeGreaterThanOrEqual(0);
    expect(placement.bottom).toBeGreaterThanOrEqual(0);
  });

  it("sits to the right of a target with room beside it", () => {
    // The palette case: a narrow target hard against the left edge.
    const rect = { top: 300, left: 20, width: 90, height: 90 };

    const placement = placeCard(rect, VIEWPORT);

    expect(placement.side).toBe("right");
    expect(placement.left).toBeGreaterThanOrEqual(rect.left + rect.width);
    expect(overlaps(placement, rect)).toBe(false);
  });

  it("flips to the left when the target is against the right edge", () => {
    const rect = { top: 300, left: 1300, width: 80, height: 40 };

    const placement = placeCard(rect, VIEWPORT);

    expect(placement.side).toBe("left");
    expect(placement.left + CARD_WIDTH).toBeLessThanOrEqual(rect.left);
    expect(overlaps(placement, rect)).toBe(false);
  });

  it("goes below a target too wide for either side", () => {
    // The bottom-panel case: a full-width element with nothing beside it.
    const rect = { top: 40, left: 10, width: 1380, height: 60 };

    const placement = placeCard(rect, VIEWPORT);

    expect(placement.side).toBe("bottom");
    expect(placement.top).toBeGreaterThanOrEqual(rect.top + rect.height);
  });

  it("goes above a full-width target sitting at the bottom of the window", () => {
    const rect = { top: 700, left: 10, width: 1380, height: 180 };

    const placement = placeCard(rect, VIEWPORT);

    expect(placement.side).toBe("top");
    expect(placement.top).toBeLessThan(rect.top);
  });

  it("keeps the card on screen when the target fills the window", () => {
    /*
     * Nothing fits beside a target this size, and the rule still holds: cover
     * as little of it as possible rather than centering on top of it. The card
     * must stay within the viewport, because a card pushed off the edge is
     * guidance the reader cannot read at all.
     */
    const rect = { top: 0, left: 0, width: VIEWPORT.width, height: VIEWPORT.height };

    const placement = placeCard(rect, VIEWPORT);

    expect(placement.left).toBeGreaterThanOrEqual(0);
    expect(placement.left + CARD_WIDTH).toBeLessThanOrEqual(VIEWPORT.width);
    expect(topOf(placement)).toBeGreaterThanOrEqual(0);
  });

  it("keeps the card on screen in a window narrower than the card", () => {
    const narrow = { width: 320, height: 600 };

    const placement = placeCard({ top: 100, left: 10, width: 60, height: 60 }, narrow);

    expect(placement.left).toBeGreaterThanOrEqual(0);
    expect(topOf(placement, narrow)).toBeGreaterThanOrEqual(0);
  });

  it("levels the card with a target's middle rather than its top edge", () => {
    // What makes a card beside a target read as pointing at it.
    const rect = { top: 400, left: 20, width: 90, height: 200 };

    const placement = placeCard(rect, VIEWPORT);

    expect(topOf(placement)).toBeLessThan(rect.top + rect.height);
    expect(topOf(placement) + 400).toBeGreaterThan(rect.top);
  });
  /*
   * The card is never clipped by the window's edges.
   *
   * The defect: `maxHeight` was the whole window less both margins, whatever
   * the card's own offset was, so a card placed low with more text than
   * `CARD_HEIGHT_ESTIMATE` ran off the bottom edge and took its Continue
   * button with it. The ceiling is measured from where the card starts, so
   * "as tall as it is allowed to be" and "on screen" are the same statement.
   */
  it.each([
    ["a target near the bottom", { top: 820, left: 300, width: 120, height: 40 }],
    ["a target near the top", { top: 20, left: 300, width: 120, height: 40 }],
    ["a target hard against the right edge", { top: 400, left: 1330, width: 60, height: 40 }],
    ["a target taller than the window", { top: -100, left: 200, width: 100, height: 1200 }],
    ["a target filling the width", { top: 300, left: 0, width: 1400, height: 100 }],
  ])("fits inside the window for %s", (_name, rect) => {
    const placement = placeCard(rect, VIEWPORT);

    const top = placement.top ?? VIEWPORT.height - (placement.bottom ?? 0) - placement.maxHeight;
    expect(top).toBeGreaterThanOrEqual(0);
    expect(top + placement.maxHeight).toBeLessThanOrEqual(VIEWPORT.height);
    expect(placement.left).toBeGreaterThanOrEqual(0);
    expect(placement.left + CARD_WIDTH).toBeLessThanOrEqual(VIEWPORT.width);
  });

  it("shrinks the ceiling for a card placed low rather than letting it overflow", () => {
    const high = placeCard({ top: 40, left: 300, width: 100, height: 40 }, VIEWPORT);
    const low = placeCard({ top: 780, left: 300, width: 100, height: 40 }, VIEWPORT);

    expect(low.maxHeight).toBeLessThan(high.maxHeight);
    expect((low.top ?? 0) + low.maxHeight).toBeLessThanOrEqual(VIEWPORT.height);
  });

  it("keeps a docked card clear of the top edge too", () => {
    const short = { width: 1400, height: 400 };

    const placement = placeCard(null, short);

    const top = short.height - (placement.bottom ?? 0) - placement.maxHeight;
    expect(top).toBeGreaterThanOrEqual(0);
  });
});
