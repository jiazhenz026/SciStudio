/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph SVG renderer (SKELETON).
 *
 * Status: SKELETON. Returns a stub that says "Branch graph (TODO:
 * D39-2.4b)" so the parent panel can mount the component without
 * crashing. The full SVG render is deferred to D39-2.4b.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Render the per-row commit dots + per-link bezier edges into a single
 * `<svg>`. Mirrors the VS Code / GitLens / JetBrains branch-graph
 * visual conventions:
 *
 *   - One row per commit, top = newest, bottom = oldest.
 *   - Each row: a colored dot at (lane_x, row_y) + the commit's
 *     short_sha + subject as DOM text (rendered OUTSIDE the SVG via
 *     foreignObject or via a sibling DOM column in the parent panel —
 *     see "Text layout" below).
 *   - Edges drawn as `<path d={...}/>` elements, color picked by the
 *     edge color_index.
 *   - Filtered commits dim to a small grey dot (per ADR §3.5c) but
 *     stay on the topology — the connecting edges still flow through.
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   props:
 *     assignments: LaneAssignment[]   from `assignLanes(commits)`
 *     edges:       GraphEdge[]        from `routeEdges(assignments, commits)`
 *     commits:     GitCommit[]        parallel array; we read short_sha /
 *                                     subject / author_date for labels
 *     onCommitClick?:  (sha) => void  optional, opens diff modal (passed
 *                                     down from the panel's `gitSlice`
 *                                     binding)
 *
 * ============================================================================
 * TEXT LAYOUT — open question for D39-2.4b
 * ============================================================================
 *
 * Two viable approaches:
 *
 *   (A) Pure SVG with `<text>` elements — simplest, but no native text
 *       wrapping. Long subjects truncate or overflow.
 *
 *   (B) Mixed SVG + DOM: the `<svg>` holds dots + edges; a sibling
 *       `<div>` column (right of the SVG) holds the row labels using
 *       normal HTML. Rows align by sharing ROW_HEIGHT.
 *
 * Approach (B) is the GitLens / JetBrains convention and what VS Code
 * uses. D39-2.4b should pick (B). This skeleton presumes (B): the SVG
 * is only ~`(maxLane+1) * LANE_PITCH + 24` pixels wide; the rest is
 * label DOM.
 *
 * ============================================================================
 * VIRTUALIZATION
 * ============================================================================
 *
 * For repos with > 1000 commits, `@tanstack/react-virtual` (already
 * available via React-style hooks; see ADR-039 §3.5b performance target)
 * windows the visible row range and the SVG renders only those rows
 * with a vertical offset transform. D39-2.4b: implement virtualization
 * in `interactions.ts` and pass a `visibleRange: [start, end]` prop
 * here.
 *
 * ============================================================================
 * ACCESSIBILITY
 * ============================================================================
 *
 *   - The SVG has `role="img"` and an `aria-label` describing the graph
 *     scope ("Branch graph: 87 commits across 4 branches").
 *   - Each commit dot is a `<circle>` with a `<title>` child holding
 *     short_sha + subject for hover tooltips and screen-reader access.
 *   - Keyboard navigation lives in `interactions.ts`; this component
 *     only renders.
 *
 * ============================================================================
 * THEMING
 * ============================================================================
 *
 * Light theme only for v1. The stroke colors come from
 * `colorPalette.ts:PALETTE`; dark-theme support post-v1 swaps to a
 * `PALETTE_DARK` (already documented in `colorPalette.ts`).
 *
 * ============================================================================
 */

import type { GitCommit } from "../../../types/api";

import type { GraphEdge } from "./edgeRouter";
import type { LaneAssignment } from "./laneAssign";

export interface GraphSVGProps {
  /** Lane assignments from `assignLanes(commits)`. */
  assignments: LaneAssignment[];
  /** Edges from `routeEdges(assignments, commits)`. */
  edges: GraphEdge[];
  /**
   * The same commit array passed to `assignLanes` (parallel order). Used
   * to render labels alongside the dots.
   */
  commits: GitCommit[];
  /**
   * Optional click handler. D39-2.4b wiring: dispatches a
   * `loadDiff(sha)` against `gitSlice` and opens `GitDiffModal`.
   */
  onCommitClick?: (sha: string) => void;
}

/**
 * Branch graph renderer (SKELETON).
 *
 * D39-2.4a: returns a stub div so the panel mounts. D39-2.4b: implement
 * the full SVG layout per the docstring above.
 */
export function GraphSVG(props: GraphSVGProps): JSX.Element {
  // Touch every prop so unused-vars lint stays quiet on the skeleton.
  void props.assignments;
  void props.edges;
  void props.commits;
  void props.onCommitClick;

  return (
    <div
      data-testid="git-graph-svg-skeleton"
      role="img"
      aria-label="Branch graph (not yet implemented — D39-2.4b)"
      className="flex h-full w-full items-center justify-center text-xs text-stone-400"
    >
      Branch graph (TODO: D39-2.4b)
    </div>
  );
}

export default GraphSVG;
