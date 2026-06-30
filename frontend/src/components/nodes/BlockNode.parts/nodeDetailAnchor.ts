// Canvas node hover-detail popover geometry (#1887).
//
// The palette anchors its hover detail to the right of a fixed-position tile.
// On the canvas a node can sit anywhere in the viewport (and the canvas pans /
// zooms), so the anchor is computed from the node's on-screen bounding rect:
// prefer the right side, flip to the left when the popover would overflow the
// right viewport edge, and clamp the top so the card stays on screen.
//
// Spec: docs/specs/frontend-block-palette.md §7 Canvas Node Hover Detail.

import type { PopoverAnchor } from "../../BlockDetailPopover";

/** Gap between the node and the popover, in px (matches the palette). */
export const NODE_DETAIL_POPOVER_GAP = 8;
/** Popover width, in px — mirrors the `w-64` (16rem) card. */
export const NODE_DETAIL_POPOVER_WIDTH = 256;
/** Max popover height used for top clamping, in px (matches the palette). */
export const NODE_DETAIL_POPOVER_MAX_HEIGHT = 240;
/**
 * Dwell before the canvas popover opens, in ms. Longer than the palette's
 * 150ms so it does not flash while the user is wiring or dragging nodes
 * (owner directive, #1887).
 */
export const NODE_DETAIL_OPEN_DELAY_MS = 400;

/** On-screen rectangle of the node, viewport-space (a `DOMRect` subset). */
export interface NodeRect {
  left: number;
  right: number;
  top: number;
}

export interface Viewport {
  width: number;
  height: number;
}

/**
 * Compute the viewport-space anchor for a canvas node's hover-detail popover.
 *
 * Prefers placing the popover to the right of the node with a small gap. When
 * it would overflow the right edge, it flips to the left of the node (clamped
 * so it never runs off the left edge). The top is clamped into
 * `[GAP, viewport.height - MAX_HEIGHT]` so a node near the top or bottom edge
 * still yields a fully visible card.
 */
export function computeNodeDetailAnchor(rect: NodeRect, viewport: Viewport): PopoverAnchor {
  const rightLeft = rect.right + NODE_DETAIL_POPOVER_GAP;
  const fitsRight = rightLeft + NODE_DETAIL_POPOVER_WIDTH <= viewport.width;
  const left = fitsRight
    ? rightLeft
    : Math.max(
        NODE_DETAIL_POPOVER_GAP,
        rect.left - NODE_DETAIL_POPOVER_GAP - NODE_DETAIL_POPOVER_WIDTH,
      );

  const maxTop = Math.max(
    NODE_DETAIL_POPOVER_GAP,
    viewport.height - NODE_DETAIL_POPOVER_MAX_HEIGHT,
  );
  const top = Math.min(Math.max(rect.top, NODE_DETAIL_POPOVER_GAP), maxTop);

  return { left, top };
}
