/**
 * ADR-053 Learning Center (#2136) — where the dialogue group stands.
 *
 * FR-089 is the same obligation `placeCard` answers. The dialogue group answers
 * it twice over.
 *
 * **It stands in the main editing area, not on the window.** Anchoring to the
 * viewport put it over whatever happened to be at that corner — the icon rail,
 * the preview panel, the bottom panel's tabs and the settings under them. The
 * main area is the one surface a tutorial can cover without covering a control,
 * so the group is laid out inside its box and its floor is that box's floor,
 * which is the top edge of the tab strip. Everything the product puts around it
 * stays reachable by construction rather than by choosing corners carefully.
 *
 * The *main area* rather than the canvas, because the canvas is only sometimes
 * what is in it: a code editor opened over it — by this tutorial, at the step
 * that writes a block's source — used to drop her into the corner of the window
 * instead, standing over the left panel and talking about code she was nowhere
 * near.
 *
 * **Inside that box it takes the corner the target is not in.** That is only
 * possible because the group is small: a strip across the window has nowhere to
 * go, while a character and a fixed panel leave three corners free. The width
 * below is exact, since the panel no longer resizes itself; the height is an
 * estimate, and deliberately generous, because the cost of overestimating is
 * standing somewhere slightly better than necessary.
 *
 * Pure geometry, in its own module, for the reason `placeCard` gives: the cases
 * worth testing are a target in each corner, one filling the canvas, and none —
 * and none of those need a DOM.
 */

import { TUTORIAL_STAGE_TARGET } from "./targets";
import type { HighlightRect } from "./useHighlightRect";

/**
 * The main editing area, as a target the group is laid out inside.
 *
 * Not the canvas element: a step can be delivered while a code editor is open
 * over the canvas — core tutorial 1 opens one itself, and then talks about the
 * code in it — and anchoring to the canvas left her standing in the corner of
 * the *window*, over the left panel, whenever it was not on screen.
 */
export const STAGE_TARGET = { target: TUTORIAL_STAGE_TARGET, args: {} } as const;

/** How tall the character stands, in pixels. The panel is laid out against her. */
export const SPRITE_HEIGHT = 225;

/**
 * The panel's width. Fixed, not a ceiling.
 *
 * A panel sized to its line changes width on every beat, so the reader's eye
 * has to find the text again each time they click — and the two controls in the
 * footer slide with it. A visual novel's box is the same box all evening; only
 * the words inside it change. The height is fixed for the same reason and in
 * the same place: the line area scrolls rather than growing.
 */
export const PANEL_WIDTH = 460;

/** Clear space between her outline and the panel's edge. */
export const PANEL_GAP = 20;

/** Clearance between the group and the stage's side edges. */
const MARGIN = 24;

/** Assumed panel height when deciding what the group would cover. */
const PANEL_HEIGHT_ESTIMATE = 220;

export type DialogueSide = "left" | "right";
export type DialogueEdge = "bottom" | "top";

export interface Viewport {
  width: number;
  height: number;
}

export interface DialoguePlacement {
  side: DialogueSide;
  edge: DialogueEdge;
}

/**
 * The default corner.
 *
 * Bottom-left, because that is where a reader of a scene expects the speaker,
 * and because it is the corner of the canvas furthest from the preview panel.
 * Exported so the one opinion in this module is in one place, and changing it
 * is one edit.
 */
export const DEFAULT_PLACEMENT: DialoguePlacement = { side: "left", edge: "bottom" };

/**
 * The box the group is laid out in: the canvas when it is on screen, the window
 * when it is not.
 *
 * The fallback is not decoration. A tutorial step can be readable on a surface
 * that has no canvas at all, and a group positioned against a box of zeroes
 * would sit in the top-left corner at nothing.
 */
export function stageBox(canvas: HighlightRect | null, viewport: Viewport): HighlightRect {
  if (canvas && canvas.width > 0 && canvas.height > 0) return canvas;
  return { top: 0, left: 0, width: viewport.width, height: viewport.height };
}

function footprint(placement: DialoguePlacement, stage: HighlightRect) {
  const width = Math.min(PANEL_WIDTH + PANEL_GAP + SPRITE_HEIGHT * 0.7, stage.width - MARGIN * 2);
  const height = Math.min(Math.max(SPRITE_HEIGHT, PANEL_HEIGHT_ESTIMATE), stage.height);
  const left =
    placement.side === "left" ? stage.left + MARGIN : stage.left + stage.width - MARGIN - width;
  const top = placement.edge === "bottom" ? stage.top + stage.height - height : stage.top;
  return { left, right: left + width, top, bottom: top + height };
}

function overlaps(rect: HighlightRect, box: ReturnType<typeof footprint>): boolean {
  return (
    rect.left < box.right &&
    rect.left + rect.width > box.left &&
    rect.top < box.bottom &&
    rect.top + rect.height > box.top
  );
}

/**
 * Which corner of the stage the group takes, given what the step points at.
 *
 * The default corner unless the lit target is in it, and then the first corner
 * that is free, tried in the order a reader would least mind: the other side of
 * the same edge first, because moving sideways keeps the dialogue at the height
 * the eye is already at, and only then the opposite edge.
 *
 * A target that covers every corner — a highlighted panel filling the canvas —
 * leaves nothing to choose, and the default is returned. Standing in the
 * expected place while covering part of something beats standing somewhere
 * arbitrary while covering a different part of it.
 */
export function placeDialogue(
  rect: HighlightRect | null,
  stage: HighlightRect,
  preferred: DialoguePlacement = DEFAULT_PLACEMENT,
): DialoguePlacement {
  if (rect === null) return preferred;

  const other = (side: DialogueSide): DialogueSide => (side === "left" ? "right" : "left");
  const flip = (edge: DialogueEdge): DialogueEdge => (edge === "bottom" ? "top" : "bottom");

  const candidates: DialoguePlacement[] = [
    preferred,
    { ...preferred, side: other(preferred.side) },
    { ...preferred, edge: flip(preferred.edge) },
    { side: other(preferred.side), edge: flip(preferred.edge) },
  ];

  for (const candidate of candidates) {
    if (!overlaps(rect, footprint(candidate, stage))) return candidate;
  }
  return preferred;
}
