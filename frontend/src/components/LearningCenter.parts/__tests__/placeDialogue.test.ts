/**
 * ADR-053 Learning Center (#2136) — the dialogue group's placement, as geometry.
 *
 * FR-089's obligation reduced to arithmetic: given where the lit target is,
 * which corner of the canvas does the group take, and when does it give up and
 * shrink. No DOM, for the reason `placeCard.test.ts` gives — the cases worth
 * testing are corners and a target that covers everything.
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_PLACEMENT, placeDialogue, stageBox } from "../placeDialogue";

/** A canvas occupying most of a 1600x900 window, the way the product lays out. */
const STAGE = { top: 70, left: 290, width: 960, height: 540 };
const VIEWPORT = { width: 1600, height: 900 };

/** A small target sitting in one corner of the stage. */
function inCorner(side: "left" | "right", edge: "bottom" | "top") {
  const width = 120;
  const height = 90;
  return {
    left: side === "left" ? STAGE.left + 10 : STAGE.left + STAGE.width - 10 - width,
    top: edge === "top" ? STAGE.top + 10 : STAGE.top + STAGE.height - 10 - height,
    width,
    height,
  };
}

describe("the stage the group is laid out in", () => {
  it("is the canvas when the canvas is on screen", () => {
    expect(stageBox(STAGE, VIEWPORT)).toEqual(STAGE);
  });

  it("falls back to the window when there is no canvas", () => {
    /*
     * Not decoration: a step can be readable on a surface with no canvas at
     * all, and a group positioned against a box of zeroes sits in the top-left
     * corner at nothing.
     */
    expect(stageBox(null, VIEWPORT)).toEqual({ top: 0, left: 0, ...VIEWPORT });
    expect(stageBox({ top: 0, left: 0, width: 0, height: 0 }, VIEWPORT)).toEqual({
      top: 0,
      left: 0,
      ...VIEWPORT,
    });
  });
});

describe("which corner the group takes", () => {
  it("takes its default corner when the step points at nothing", () => {
    expect(placeDialogue(null, STAGE)).toEqual(DEFAULT_PLACEMENT);
  });

  it("steps sideways before it steps across", () => {
    /*
     * The lit target is in the default corner, so the group has to move. It
     * goes to the other side of the same edge rather than to the far corner:
     * moving sideways keeps the dialogue at the height the eye is already at.
     */
    const placement = placeDialogue(inCorner("left", "bottom"), STAGE);
    expect(placement.side).toBe("right");
    expect(placement.edge).toBe("bottom");
  });

  it("crosses to the other edge when both sides of this one are taken", () => {
    const bothBottomCorners = {
      left: STAGE.left + 10,
      top: STAGE.top + STAGE.height - 100,
      width: STAGE.width - 20,
      height: 90,
    };
    expect(placeDialogue(bothBottomCorners, STAGE).edge).toBe("top");
  });

  it("stays in the expected corner when every corner is taken", () => {
    /*
     * A highlight covering the whole canvas — a lit panel, say. There is
     * nothing to choose between, and the default corner wins: hunting for the
     * dialogue somewhere new every time is worse than one predictable overlap.
     *
     * It does *not* switch to the compact form here. Which steps are compact is
     * the author's declaration (FR-011e), not something geometry infers.
     */
    const everything = {
      left: STAGE.left,
      top: STAGE.top,
      width: STAGE.width,
      height: STAGE.height,
    };
    expect(placeDialogue(everything, STAGE)).toEqual(DEFAULT_PLACEMENT);
  });

  it("always finds a corner for a target that blocks only one", () => {
    for (const side of ["left", "right"] as const) {
      for (const edge of ["bottom", "top"] as const) {
        const placement = placeDialogue(inCorner(side, edge), STAGE);
        expect(placement).not.toEqual({ side, edge });
      }
    }
  });
});
