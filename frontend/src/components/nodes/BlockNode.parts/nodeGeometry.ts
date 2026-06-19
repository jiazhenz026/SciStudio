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
 * Vertical offset (CSS px) of the FIRST port handle — the top quarter of the
 * square (NODE_SIZE / 4). Ports march downward from here (see
 * `portRailOffset`), so a node's first port is always at the same height.
 */
export const PORT_RAIL_TOP_INSET = 26;

/**
 * Y offset (CSS px, node-local coordinates) of the port handle at `index` on a
 * rail, given the total number of ports on that rail.
 *
 * Top-anchored: the first handle sits at the top-quarter inset
 * (`PORT_RAIL_TOP_INSET` = NODE_SIZE / 4) and handles march downward at a fixed
 * stride — no vertical centring, so a node's first port is always at the same
 * height regardless of port count. The rail may extend below the square for
 * many ports (ADR-050 §2.4 — the body stays fixed, the rail overflows). Both
 * rails share this helper so input and output handles stay aligned.
 */
export function portRailOffset(index: number, portCount: number): number {
  if (portCount <= 0) return PORT_RAIL_TOP_INSET;
  return PORT_RAIL_TOP_INSET + index * PORT_RAIL_STRIDE;
}

/**
 * Y offset (CSS px) of the trailing `+` add-port control on a rail. It sits
 * exactly one full `PORT_RAIL_STRIDE` past the LAST port on the rail, computed
 * from the SAME `portCount` centring the ports use, so the `+` never overlaps
 * the last handle.
 *
 * The earlier form `portRailOffset(portCount, portCount + 1)` re-centred the
 * rail as if it had `portCount + 1` elements, which shifted the rail start and
 * left the `+` only ~half a stride below the last port (visual overlap, #1698
 * canvas polish). Anchoring off the last port's own offset keeps the gap equal
 * to the port-to-port spacing.
 */
export function addPortRailOffset(portCount: number): number {
  if (portCount <= 0) return portRailOffset(0, 1);
  return portRailOffset(portCount - 1, portCount) + PORT_RAIL_STRIDE;
}
