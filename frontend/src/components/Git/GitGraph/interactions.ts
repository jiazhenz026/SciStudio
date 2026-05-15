/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph interactions (SKELETON).
 *
 * Status: SKELETON. All non-pure helpers throw
 * `Error("TODO: D39-2.4b — ...")`. D39-2.4b fills in the hover preview,
 * click handling, and virtualization hooks.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Encapsulate the user-input layer of the branch graph so `GraphSVG.tsx`
 * stays a pure renderer. This module owns:
 *
 *   - HOVER PREVIEW — when the pointer is over a commit dot, show a
 *     floating tooltip with the full commit subject + author + relative
 *     date. Tooltip positioning uses the row's center coordinates.
 *
 *   - CLICK → DIFF — clicking a commit dot dispatches `loadDiff(sha)`
 *     against `gitSlice` and opens `GitDiffModal`. Clicking a row's
 *     label is the same.
 *
 *   - CLICK → CHECKOUT — Shift+Click on a commit dot offers "Checkout
 *     this commit" in a context menu, dispatching `switchBranch` /
 *     `restore` as appropriate. D39-2.4b: confirm the UX choice with
 *     the user before wiring (per ADR §3.6 "soft restore is the
 *     prominent default"); skeleton documents the slot.
 *
 *   - KEYBOARD NAV — Arrow keys move a "focused row" cursor up/down,
 *     Enter triggers click-equivalent. Focus state lives in this
 *     module's hook and is exposed via aria-activedescendant on the
 *     SVG group.
 *
 *   - VIRTUALIZATION — for repos > 1000 commits, derive a `visibleRange`
 *     [start, end] from the scroll position using `@tanstack/react-virtual`
 *     (already available in package.json) and pass it to `GraphSVG.tsx`.
 *
 * ============================================================================
 * INPUT / OUTPUT
 * ============================================================================
 *
 * Exposed as a single `useGraphInteractions(...)` hook so the panel can
 * compose it once. Returns:
 *
 *   {
 *     visibleRange:     [number, number];                  // [start_idx, end_idx)
 *     focusedRow:       number | null;                     // for kbd nav
 *     setFocusedRow:    (idx: number | null) => void;
 *     hoveredSha:       string | null;                     // for tooltip
 *     setHoveredSha:    (sha: string | null) => void;
 *     onCommitClick:    (sha: string) => void;             // wired to gitSlice
 *     onCommitDotKeyDown: (e: React.KeyboardEvent) => void; // arrow + enter
 *   }
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. EMPTY COMMITS → visibleRange [0,0], focusedRow null, all
 *      handlers no-op.
 *   2. HOVER LEAVES SVG VIEWPORT → setHoveredSha(null) so the tooltip
 *      unmounts. Without this the tooltip can stick.
 *   3. CLICK WHILE A DIFF MODAL IS OPEN → close existing first, then
 *      open new. Handled at the panel level (this hook only emits
 *      "user wants diff of sha X").
 *   4. KEYBOARD NAV WITH FILTER ACTIVE → arrows still walk EVERY row
 *      (dimmed grey-dot rows included). Skipping filtered rows would
 *      surprise users who toggle filters mid-navigation.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - Consumes `gitSlice` via `useAppStore()` for loadDiff / switchBranch.
 *   - Drives `GraphSVG.tsx` purely through props (no direct DOM mutation).
 *   - Lives alongside `integration.ts` which owns the "slice → memoised
 *     assignment+edges" transform.
 *
 * ============================================================================
 */

/**
 * Hook return shape. Exported as a type so consumers and tests share it.
 */
export interface GraphInteractionsApi {
  /** Inclusive-exclusive row window driven by scroll position. */
  visibleRange: [number, number];
  /** Currently focused row index (keyboard navigation), null if none. */
  focusedRow: number | null;
  setFocusedRow: (idx: number | null) => void;
  /** Currently hovered commit SHA (for the floating tooltip), null if none. */
  hoveredSha: string | null;
  setHoveredSha: (sha: string | null) => void;
  /** Wired by D39-2.4b to `gitSlice.loadDiff` + open `GitDiffModal`. */
  onCommitClick: (sha: string) => void;
  /**
   * Arrow-up / arrow-down moves focusedRow. Enter triggers
   * `onCommitClick(commits[focusedRow].sha)`.
   */
  onCommitDotKeyDown: (event: React.KeyboardEvent<Element>) => void;
}

/**
 * Hook factory. D39-2.4a SKELETON: throws on first call so accidental
 * mounts surface loudly during development. D39-2.4b: implement using
 * `useState` + `useCallback` + a small reducer for the keyboard state.
 *
 * @param totalRows - The number of rows the graph would render if
 *                    nothing were virtualized.
 */
export function useGraphInteractions(totalRows: number): GraphInteractionsApi {
  void totalRows;
  throw new Error(
    "TODO: D39-2.4b — implement useGraphInteractions per the docstring " +
      "above. Wire to gitSlice.loadDiff + GitDiffModal. Implement keyboard " +
      "navigation + virtualization with @tanstack/react-virtual.",
  );
}
