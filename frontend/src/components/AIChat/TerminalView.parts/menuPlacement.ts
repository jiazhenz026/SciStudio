/**
 * Edge-aware placement for the terminal's right-click menu (#1994 follow-up).
 *
 * Right-clicking near the bottom of the PTY used to render the menu below the
 * visible area, where it could not be clicked at all. The frame clips its
 * children (`overflow-hidden`), so anything past an edge is simply gone.
 *
 * Kept as a pure function so both axes and every corner are directly testable
 * without a layout engine — jsdom reports every element as 0×0, so a
 * DOM-level test could not exercise this at all.
 */
export interface MenuPlacementInput {
  /** Requested position, relative to the frame — where the user right-clicked. */
  x: number;
  y: number;
  /** Measured menu size. */
  menuWidth: number;
  menuHeight: number;
  /** Inner size of the frame the menu is positioned inside. */
  frameWidth: number;
  frameHeight: number;
}

export interface MenuPlacement {
  left: number;
  top: number;
  /** True when the menu was flipped to the other side of the cursor. */
  flippedX: boolean;
  flippedY: boolean;
}

/**
 * Resolve the menu's position so it stays fully inside the frame.
 *
 * Preference order per axis: the requested side, then the opposite side of the
 * cursor (a flip, which is what a native context menu does), then clamped to
 * the edge. The final clamp matters when the menu is larger than the frame — a
 * short PTY pane is not hypothetical — where flipping alone cannot fit it and
 * showing the top-left corner beats showing nothing.
 */
export function resolveMenuPlacement({
  x,
  y,
  menuWidth,
  menuHeight,
  frameWidth,
  frameHeight,
}: MenuPlacementInput): MenuPlacement {
  const place = (
    requested: number,
    size: number,
    frameSize: number,
  ): { value: number; flipped: boolean } => {
    // Fits as requested.
    if (requested + size <= frameSize) return { value: Math.max(0, requested), flipped: false };
    // Flip to the other side of the cursor, if that fits.
    const flipped = requested - size;
    if (flipped >= 0) return { value: flipped, flipped: true };
    // Neither side fits (menu taller/wider than the frame): clamp.
    return { value: Math.max(0, frameSize - size), flipped: false };
  };

  const horizontal = place(x, menuWidth, frameWidth);
  const vertical = place(y, menuHeight, frameHeight);

  return {
    left: horizontal.value,
    top: vertical.value,
    flippedX: horizontal.flipped,
    flippedY: vertical.flipped,
  };
}
