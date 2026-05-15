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
import { classifyPrefix } from "../../../store/gitSlice";
import type { GitCommit } from "../../../types/api";

import {
  COMMIT_RADIUS_FILTERED,
  COMMIT_RADIUS_VISIBLE,
  LANE_PITCH,
  LANE_X_OFFSET,
  ROW_HEIGHT,
  colorForIndex,
  resolveLaneColor,
} from "./colorPalette";
import { centerOf, type GraphEdge } from "./edgeRouter";
import { maxLane, type LaneAssignment } from "./laneAssign";

const PREFIX_ICON: Record<string, string> = {
  auto: "·",
  agent: "🤖",
  user: "👤",
};

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

/**
 * Branch graph renderer. Pure renderer; user-input handling lives in
 * `interactions.ts` and is passed in via props.
 */
export function GraphSVG(props: GraphSVGProps): JSX.Element {
  const {
    assignments,
    edges,
    commits,
    onCommitClick,
    visibleRange,
    hoveredIdx,
    focusedIdx,
  } = props;

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
      const minIdx = Math.min(
        e.child_idx,
        e.parent_idx >= 0 ? e.parent_idx : e.child_idx,
      );
      const maxIdx = Math.max(
        e.child_idx,
        e.parent_idx >= 0 ? e.parent_idx : e.child_idx,
      );
      return maxIdx >= visibleStart - 1 && minIdx <= visibleEnd;
    });
  }, [edges, visibleRange, visibleStart, visibleEnd]);

  if (totalRows === 0) {
    return (
      <div
        data-testid="git-graph-empty"
        className="flex h-full w-full items-center justify-center text-xs text-stone-400"
      >
        No commits to display.
      </div>
    );
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
          <g data-testid="git-graph-edges">
            {visibleEdges.map((e, ei) => (
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
          <g data-testid="git-graph-dots">
            {assignments.slice(visibleStart, visibleEnd).map((a, offset) => {
              const idx = visibleStart + offset;
              const c = centerOf(idx, a.lane);
              const r = a.filtered_out
                ? COMMIT_RADIUS_FILTERED
                : COMMIT_RADIUS_VISIBLE;
              const fill = a.filtered_out
                ? "#a1a1aa"
                : colorForIndex(a.color_index);
              const commit = commits[idx];
              const isHovered = hoveredIdx === idx;
              const isFocused = focusedIdx === idx;
              return (
                <circle
                  key={a.sha}
                  data-testid={`git-graph-dot-${commit?.short_sha ?? a.sha.slice(0, 7)}`}
                  data-filtered={a.filtered_out ? "true" : "false"}
                  cx={c.x}
                  cy={c.y}
                  r={isHovered || isFocused ? r + 1 : r}
                  fill={fill}
                  stroke={isFocused ? "#000" : "none"}
                  strokeWidth={isFocused ? 1 : 0}
                >
                  <title>
                    {commit
                      ? `${commit.short_sha}  ${commit.subject}`
                      : a.sha}
                  </title>
                </circle>
              );
            })}
          </g>
        </svg>
      </div>
      <ul
        data-testid="git-graph-labels"
        role="list"
        className="min-h-0 flex-1 overflow-hidden"
        style={{ height: `${height}px` }}
      >
        {assignments.slice(visibleStart, visibleEnd).map((a, offset) => {
          const idx = visibleStart + offset;
          const commit = commits[idx];
          if (!commit) return null;
          const prefix = classifyPrefix(commit.subject);
          const isFocused = focusedIdx === idx;
          return (
            <li
              key={a.sha}
              data-testid={`git-graph-label-${commit.short_sha}`}
              data-commit-prefix={prefix}
              role="button"
              tabIndex={0}
              aria-selected={isFocused || undefined}
              onClick={() => onCommitClick?.(commit.sha)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onCommitClick?.(commit.sha);
                }
              }}
              className={`flex items-center gap-2 border-b border-stone-100 px-3 text-xs hover:bg-stone-50 focus:bg-stone-100 focus:outline-none ${
                isFocused ? "bg-stone-100" : ""
              } ${a.filtered_out ? "opacity-50" : ""}`}
              style={{ height: `${ROW_HEIGHT}px` }}
            >
              <span aria-hidden>{PREFIX_ICON[prefix] ?? "·"}</span>
              <code className="font-mono text-stone-500">{commit.short_sha}</code>
              <span className="flex-1 truncate text-ink" title={commit.subject}>
                {commit.subject}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default GraphSVG;
