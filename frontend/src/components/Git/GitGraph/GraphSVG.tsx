/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph SVG renderer.
 *
 * D39-2.4b IMPL: renders the commit DAG as a left-aligned SVG of dots +
 * bezier edges, with a sibling DOM column for labels. The labels live
 * OUTSIDE the SVG (Approach B in the skeleton docstring) so HTML text
 * truncation works naturally.
 *
 * Coordinate system + constants are defined in `colorPalette.ts` so the
 * edge router and renderer agree on the same layout grid.
 */
import { useMemo } from "react";
import type { JSX } from "react";

import { useAppStore } from "../../../store";
import type { GitCommit } from "../../../types/api";

import { LANE_PITCH, LANE_X_OFFSET, ROW_HEIGHT, resolveLaneColor } from "./colorPalette";
import type { GraphEdge } from "./edgeRouter";
import { GraphDots } from "./GraphSVG.parts/GraphDots";
import { GraphLabels } from "./GraphSVG.parts/GraphLabels";
import { maxLane, type LaneAssignment } from "./laneAssign";

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
   * Optional click handler. Wired by the panel to `loadDiff(sha)` against
   * `gitSlice` and opening `GitDiffModal`.
   */
  onCommitClick?: (sha: string) => void;
  /**
   * Optional virtualization window. When supplied, only edges and dots
   * that intersect [start, end) are rendered. Labels use the same range.
   * Default: render everything (suitable for repos < 1000 commits).
   */
  visibleRange?: [number, number];
  /**
   * Optional currently-hovered row (for a faint highlight). Drives styling
   * only — the tooltip itself lives in the parent panel.
   */
  hoveredIdx?: number | null;
  /** Optional focused row index for keyboard navigation. */
  focusedIdx?: number | null;
}

function EmptyGraph() {
  return (
    <div
      data-testid="git-graph-empty"
      className="flex h-full w-full items-center justify-center text-xs text-stone-400"
    >
      No commits to display.
    </div>
  );
}

interface EdgeLayerProps {
  edges: GraphEdge[];
}

function EdgeLayer({ edges }: EdgeLayerProps) {
  return (
    <g data-testid="git-graph-edges">
      {edges.map((e, ei) => (
        <path
          key={`${e.child_sha}-${e.parent_sha}-${ei}`}
          data-testid={`git-graph-edge-${e.child_sha}-${e.parent_sha}`}
          d={e.path}
          fill="none"
          stroke={resolveLaneColor(e.color_index, false)}
          strokeWidth={2}
          opacity={e.dangling ? 0.4 : 1}
        />
      ))}
    </g>
  );
}

/**
 * Branch graph renderer. Pure renderer; user-input handling lives in
 * `interactions.ts` and is passed in via props.
 */
export function GraphSVG(props: GraphSVGProps): JSX.Element {
  const { assignments, edges, commits, onCommitClick, visibleRange, hoveredIdx, focusedIdx } =
    props;

  // Pull historyFilter so we re-render when it changes (the bool itself
  // is derived in integration.ts but tooltip text references it).
  void useAppStore((s) => s.historyFilter);

  const totalRows = assignments.length;
  const width = useMemo(() => {
    const m = maxLane(assignments);
    return Math.max(LANE_X_OFFSET * 2, LANE_X_OFFSET + (m + 1) * LANE_PITCH + 4);
  }, [assignments]);
  const height = totalRows * ROW_HEIGHT;

  const [start, end] = visibleRange ?? [0, totalRows];
  const visibleStart = Math.max(0, start);
  const visibleEnd = Math.min(totalRows, end);

  // Filter edges that have at least one endpoint in the visible range.
  // We keep edges fully even if one endpoint is just outside so the
  // path doesn't get clipped at the boundary.
  const visibleEdges = useMemo(() => {
    if (visibleRange === undefined) return edges;
    return edges.filter((e) => {
      const minIdx = Math.min(e.child_idx, e.parent_idx >= 0 ? e.parent_idx : e.child_idx);
      const maxIdx = Math.max(e.child_idx, e.parent_idx >= 0 ? e.parent_idx : e.child_idx);
      return maxIdx >= visibleStart - 1 && minIdx <= visibleEnd;
    });
  }, [edges, visibleRange, visibleStart, visibleEnd]);

  if (totalRows === 0) {
    return <EmptyGraph />;
  }

  return (
    <div data-testid="git-graph-svg-root" className="flex h-full min-h-0 w-full">
      <div className="shrink-0" style={{ width: `${width}px`, position: "relative" }}>
        <svg
          data-testid="git-graph-svg"
          role="img"
          aria-label={`Branch graph: ${totalRows} commits`}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Edges first so dots paint on top. */}
          <EdgeLayer edges={visibleEdges} />
          <GraphDots
            assignments={assignments}
            commits={commits}
            visibleStart={visibleStart}
            visibleEnd={visibleEnd}
            hoveredIdx={hoveredIdx}
            focusedIdx={focusedIdx}
          />
        </svg>
      </div>
      {/*
        Hotfix #1004: the UL spans the full `height` ( totalRows * ROW_HEIGHT)
        but renders only the virtualization window's slice of LIs. Pre-fix,
        those LIs were flow-laid-out at the UL's TOP (y=0..offsetPx),
        leaving the rest of the UL blank — when the user scrolled past
        offsetPx the right side went blank even though the SVG (which uses
        absolute y-positioning per dot) correctly showed commits.

        Push the slice down with a top spacer (height = visibleStart * ROW_HEIGHT)
        so the visible LIs align vertically with their SVG dots.
      */}
      <GraphLabels
        assignments={assignments}
        commits={commits}
        visibleStart={visibleStart}
        visibleEnd={visibleEnd}
        height={height}
        focusedIdx={focusedIdx}
        onCommitClick={onCommitClick}
      />
    </div>
  );
}

export default GraphSVG;
