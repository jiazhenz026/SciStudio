/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch color rotation (SKELETON).
 *
 * Status: SKELETON for the consumer-facing constants + the palette
 * itself is finalized; only the dynamic lane→color resolver throws
 * `Error("TODO: D39-2.4b — ...")`.
 *
 * The palette is deterministic on lane index (`color_index = lane mod N`)
 * so that branches keep stable colors across re-renders — the user's
 * mental model of "the green branch" persists even after `loadLog`
 * refreshes.
 *
 * Visual style references VS Code / GitLens / JetBrains as design
 * inspiration (functional UI conventions are not copyright-protected
 * per ADR-039 §3.5b).
 *
 * ============================================================================
 * PALETTE DESIGN NOTES
 * ============================================================================
 *
 *   - ~10 colors per ADR §3.5b "approximately 10 branch colors with
 *     deterministic assignment".
 *   - Order chosen to maximize adjacent-lane contrast: colors that are
 *     visually distinct from their neighbors (lane 0 vs lane 1 vs lane 2)
 *     so an S-curve crossing between them is easy to follow.
 *   - All colors pass WCAG AA contrast vs the default light theme
 *     background (#fafafa, stone-50). For dark theme, the renderer
 *     should swap to a parallel `PALETTE_DARK` array — out of scope for
 *     v1 since SciStudio currently uses light theme only.
 *   - Filtered commits get a fixed grey (`FILTERED_COLOR`) instead of
 *     a palette color, per ADR §3.5c.
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. Lane index > palette length → wrap around via modulo.
 *   2. Negative lane index → defensive: clamp to 0 with a console.warn.
 *      Should never happen in practice; documented for paranoia.
 *
 * ============================================================================
 */

/**
 * Deterministic branch palette. Length = 10.
 *
 * D39-2.4b: the palette is final; do not mutate. Add a parallel
 * `PALETTE_DARK` array when dark-theme support lands (post-v1).
 */
export const PALETTE: ReadonlyArray<string> = [
  "#2563eb", // blue-600
  "#16a34a", // green-600
  "#dc2626", // red-600
  "#ca8a04", // yellow-600
  "#9333ea", // purple-600
  "#0891b2", // cyan-600
  "#c2410c", // orange-700
  "#65a30d", // lime-600
  "#db2777", // pink-600
  "#475569", // slate-600
];

/**
 * Color used for filtered-out commits (small grey dots per ADR §3.5c).
 */
export const FILTERED_COLOR = "#a1a1aa"; // zinc-400

/**
 * Layout constants. Co-located here so `edgeRouter.ts` and `GraphSVG.tsx`
 * agree on the same coordinate system. D39-2.4b: if these need to move
 * out (e.g. into a dedicated `layoutConstants.ts`), do so consistently.
 */
export const ROW_HEIGHT = 22;
export const LANE_PITCH = 16;
export const LANE_X_OFFSET = 12;
export const COMMIT_RADIUS_VISIBLE = 4;
export const COMMIT_RADIUS_FILTERED = 2;

/**
 * Resolve a palette index to its hex color string. Pure helper, kept
 * implemented because it has no dependency on the unimplemented graph
 * algorithm and is independently useful in tests.
 *
 * @param colorIndex - 0-based palette index. Wraps via modulo if too
 *                     large.
 * @returns a "#rrggbb" color string from {@link PALETTE}.
 */
export function colorForIndex(colorIndex: number): string {
  if (!Number.isFinite(colorIndex)) return PALETTE[0];
  // Defensive: handle negative inputs.
  const i = ((colorIndex % PALETTE.length) + PALETTE.length) % PALETTE.length;
  return PALETTE[i];
}

/**
 * Resolve a {@link LaneAssignment} to a stroke color. Convenience over
 * {@link colorForIndex} that applies the "filtered → grey" rule from
 * §3.5c without callers having to remember it.
 *
 * D39-2.4a SKELETON: throws — body trivially `filtered_out ?
 * FILTERED_COLOR : colorForIndex(color_index)` but kept as a TODO so
 * D39-2.4b owns the wiring decision (the impl agent may want a
 * different signature once they've written GraphSVG.tsx).
 */
export function resolveLaneColor(
  /** From a `LaneAssignment` row. */ colorIndex: number,
  /** From the same row. */ filteredOut: boolean,
): string {
  // D39-2.4b: applies the §3.5c filtered-grey rule. The signature is
  // kept as-is from the skeleton; the simple `(colorIndex, filteredOut)`
  // pair is sufficient because both fields live on every `LaneAssignment`
  // row and edge rendering passes them independently.
  if (filteredOut) return FILTERED_COLOR;
  return colorForIndex(colorIndex);
}
