/**
 * ADR-053 Learning Center (#2057) — where the step card goes.
 *
 * FR-089's one hard rule survives the redesign: the card must not cover the
 * element the step is telling the reader to act on. The strip satisfied that by
 * never overlapping anything; a following card satisfies it by being placed on
 * whichever side of the target has room.
 *
 * Pure geometry, in its own module, because it is the part with edges worth
 * testing directly — a target hard against the right edge of the window, one
 * taller than the viewport, one at the bottom — and none of those need a DOM.
 */

import type { HighlightRect } from "./useHighlightRect";

/** The card's fixed footprint, in pixels. Width is exact; height is an estimate. */
export const CARD_WIDTH = 380;
const CARD_HEIGHT_ESTIMATE = 180;

/** Clearance between the card and the lit region. */
const GAP = 16;

/** Clearance between the card and the window's edges. */
const MARGIN = 12;

/**
 * Clearance for the docked corner.
 *
 * Larger than `MARGIN` because a docked card is read rather than glanced at,
 * and because the bottom-right corner is where the bottom panel's own chrome
 * ends — sitting flush against it reads as part of that panel.
 */
const DOCK_MARGIN = 20;

/**
 * The floor under the card's height ceiling.
 *
 * In a window too short for the margins the ceiling would otherwise come out
 * near zero or negative, collapsing the card to nothing. Better to overflow a
 * very short window than to render a card with no visible content in it.
 */
const MIN_USABLE_HEIGHT = 160;

export interface CardPlacement {
  /**
   * Distance from the top of the window, or `null` when the card hangs from
   * its bottom edge instead.
   *
   * A docked card is anchored by its bottom, because its height is whatever its
   * text turns out to need and only the anchored edge is knowable in advance.
   * Positioning it by `top` means computing `height - estimate`, and a step
   * whose prose runs past the estimate then extends *below* the window, taking
   * the Continue button with it — which is a step the reader cannot complete.
   */
  top: number | null;
  /** Distance from the bottom of the window; `null` when positioned by `top`. */
  bottom: number | null;
  left: number;
  /**
   * The tallest the card may be, so a long step still shows its buttons.
   *
   * The card scrolls its text inside this rather than growing past the window.
   */
  maxHeight: number;
  /** Which side of the target the card sits on; `null` when it is docked. */
  side: "top" | "right" | "bottom" | "left" | null;
}

export interface Viewport {
  width: number;
  height: number;
}

function clamp(value: number, low: number, high: number): number {
  /*
   * `high` can fall below `low` when the viewport is narrower than the card
   * plus its margins. Ordering the bounds this way keeps the card's near edge
   * on screen instead of pushing it off the far one, which is the half a user
   * reads first.
   */
  if (high < low) return low;
  return Math.min(Math.max(value, low), high);
}

/**
 * Place the card against *rect*, or dock it when there is no target.
 *
 * **Docked, not centered.** A step with no `highlight` asks the reader to read
 * rather than to act, and the first step of core tutorial 1 is five sentences
 * of scene-setting. Centering that puts a wall of prose in the middle of the
 * user's own workspace and demands to be dealt with before anything else can
 * happen. The bottom-right corner is where the product's own transient panels
 * live, and it leaves the canvas and both panels readable behind it — the
 * reader can look at what the prose is describing while they read it.
 *
 * Sides are tried in the order right, left, bottom, top. Horizontal first
 * because this product's targets are overwhelmingly in the left palette or on
 * the canvas with panels above and below, so a card beside them displaces less
 * than one under them; and because a card to the side keeps its own vertical
 * midpoint level with the target, which reads as pointing at it.
 *
 * The last resort is the center of the free space rather than an overlap: if
 * nothing fits beside the target, covering it is the one outcome FR-089 rules
 * out, so the card goes as far from it as the viewport allows.
 */
export function placeCard(rect: HighlightRect | null, viewport: Viewport): CardPlacement {
  if (!rect) {
    return {
      top: null,
      bottom: DOCK_MARGIN,
      left: Math.max(MARGIN, viewport.width - CARD_WIDTH - DOCK_MARGIN),
      // Anchored by its bottom edge, so what is left is the window above the
      // dock margin — the same "measure from where the card starts" rule the
      // beside placements use, in the other direction.
      maxHeight: Math.max(MIN_USABLE_HEIGHT, viewport.height - DOCK_MARGIN - MARGIN),
      side: null,
    };
  }

  /*
   * Beside the target, the card must not grow into the window's edges, so its
   * ceiling is what is left *below where it starts* — not the whole window.
   *
   * The whole-window form clipped the card against the bottom edge whenever a
   * step ran past `CARD_HEIGHT_ESTIMATE`: the card is positioned by `top`, the
   * estimate is only an estimate, and a ceiling that ignores the offset let the
   * real height run off screen, taking the Continue button with it. Measuring
   * from the offset means a card placed low is short and scrolls its text,
   * which is the outcome this ceiling exists to produce. It is the *ceiling*,
   * not the height: a short step is short.
   */
  const beside = (top: number, left: number, side: CardPlacement["side"]): CardPlacement => ({
    top,
    bottom: null,
    left,
    maxHeight: Math.max(MIN_USABLE_HEIGHT, viewport.height - top - MARGIN),
    side,
  });

  const verticallyLevel = clamp(
    rect.top + rect.height / 2 - CARD_HEIGHT_ESTIMATE / 2,
    MARGIN,
    viewport.height - CARD_HEIGHT_ESTIMATE - MARGIN,
  );
  const horizontallyLevel = clamp(
    rect.left + rect.width / 2 - CARD_WIDTH / 2,
    MARGIN,
    viewport.width - CARD_WIDTH - MARGIN,
  );

  const rightEdge = rect.left + rect.width + GAP;
  if (rightEdge + CARD_WIDTH + MARGIN <= viewport.width) {
    return beside(verticallyLevel, rightEdge, "right");
  }

  const leftEdge = rect.left - GAP - CARD_WIDTH;
  if (leftEdge >= MARGIN) {
    return beside(verticallyLevel, leftEdge, "left");
  }

  const bottomEdge = rect.top + rect.height + GAP;
  if (bottomEdge + CARD_HEIGHT_ESTIMATE + MARGIN <= viewport.height) {
    return beside(bottomEdge, horizontallyLevel, "bottom");
  }

  const topEdge = rect.top - GAP - CARD_HEIGHT_ESTIMATE;
  if (topEdge >= MARGIN) {
    return beside(topEdge, horizontallyLevel, "top");
  }

  /*
   * Nothing fits beside it. Put the card in the larger of the two horizontal
   * bands the target leaves, which is the most room available anywhere, and
   * accept that it may be tight rather than accept covering the target.
   */
  const roomLeft = rect.left;
  const roomRight = viewport.width - (rect.left + rect.width);
  const left = roomRight >= roomLeft ? viewport.width - CARD_WIDTH - MARGIN : MARGIN;
  return beside(verticallyLevel, left, roomRight >= roomLeft ? "right" : "left");
}
