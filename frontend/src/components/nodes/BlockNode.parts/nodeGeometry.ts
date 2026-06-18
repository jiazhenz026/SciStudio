// ADR-050 §2.1 / FR-001-FR-002 — fixed square canvas node geometry.
//
// The canvas block node is a fixed-size square topology glyph. Its body never
// grows for config, ports, status, errors, or actions. This module is the
// single source of truth for the square's CSS pixel dimensions and for the
// vertical placement of port handles on the left/right rails.
//
// Decoupling note (checklist §4.1): FE-2 owns
// `WorkflowCanvas.parts/layoutConstants.ts`, which declares its OWN
// `NODE_SIZE = 104` for graph spacing. The two constants MUST stay equal but
// are intentionally NOT cross-imported, so each agent worktree type-checks in
// isolation. The manager reconciles the seam at integration. Do not import
// layoutConstants.ts from here or vice versa.

/** Square body edge length in CSS pixels (ADR-050 §2.1 default density). */
export const NODE_SIZE = 104;

/** Square body border radius in CSS pixels (ADR-050 §2.1 "≤ 8px"). */
export const NODE_BORDER_RADIUS = 8;

/**
 * Vertical stride between adjacent port handles on a rail, in CSS pixels.
 * Ports are spaced far enough apart to remain individually clickable while
 * still letting a handful fit beside the 104px square.
 */
export const PORT_RAIL_STRIDE = 22;

/**
 * Vertical inset from the top of the square to the FIRST port handle, in CSS
 * pixels. Keeps port row 1 clear of the rounded top corner and the block-kind
 * mark.
 */
export const PORT_RAIL_TOP_INSET = 26;

/**
 * Y offset (CSS px, node-local coordinates) of the port handle at `index` on a
 * rail, given the total number of ports on that rail.
 *
 * The rail is centred vertically on the square when the ports fit within the
 * body height; when there are more ports than fit, the rail extends below the
 * square (ADR-050 §2.4 — the body stays fixed, the rail may overflow). Both
 * rails use the same helper so input and output handles stay aligned.
 */
export function portRailOffset(index: number, portCount: number): number {
  if (portCount <= 0) return NODE_SIZE / 2;
  const railHeight = (portCount - 1) * PORT_RAIL_STRIDE;
  // Centre the rail in the available vertical space below the top inset when
  // it fits; otherwise anchor at the top inset and let it overflow downward.
  const available = NODE_SIZE - PORT_RAIL_TOP_INSET;
  const start =
    railHeight <= available
      ? PORT_RAIL_TOP_INSET + (available - railHeight) / 2
      : PORT_RAIL_TOP_INSET;
  return start + index * PORT_RAIL_STRIDE;
}

/**
 * Y offset (CSS px) of the trailing `+` add-port control on a rail. It sits one
 * stride past the last port so it reads as "append to this rail".
 */
export function addPortRailOffset(portCount: number): number {
  return portRailOffset(portCount, portCount + 1);
}
