/**
 * Commit-dot layer for GraphSVG. Extracted in #1413 to reduce parent
 * function size and complexity.
 */
import type { GitCommit } from "../../../../types/api";
import { COMMIT_RADIUS_FILTERED, COMMIT_RADIUS_VISIBLE, colorForIndex } from "../colorPalette";
import { centerOf } from "../edgeRouter";
import type { LaneAssignment } from "../laneAssign";

export interface GraphDotsProps {
  assignments: LaneAssignment[];
  commits: GitCommit[];
  visibleStart: number;
  visibleEnd: number;
  hoveredIdx?: number | null;
  focusedIdx?: number | null;
}

interface DotProps {
  idx: number;
  a: LaneAssignment;
  commit: GitCommit | undefined;
  hoveredIdx: number | null | undefined;
  focusedIdx: number | null | undefined;
}

interface DotGeometry {
  cx: number;
  cy: number;
  r: number;
  fill: string;
  isFocused: boolean;
  isMerge: boolean;
}

function computeDotGeometry(props: DotProps): DotGeometry {
  const { idx, a, commit, hoveredIdx, focusedIdx } = props;
  const c = centerOf(idx, a.lane);
  const r = a.filtered_out ? COMMIT_RADIUS_FILTERED : COMMIT_RADIUS_VISIBLE;
  const fill = a.filtered_out ? "#a1a1aa" : colorForIndex(a.color_index);
  const isHovered = hoveredIdx === idx;
  const isFocused = focusedIdx === idx;
  const effectiveR = isHovered || isFocused ? r + 1 : r;
  // Hotfix #1008: merge commits render as double-ring (filled outer + inner white).
  const isMerge = (commit?.parents.length ?? 0) > 1;
  return { cx: c.x, cy: c.y, r: effectiveR, fill, isFocused, isMerge };
}

function DotBadge(props: DotProps) {
  const { a, commit } = props;
  const geom = computeDotGeometry(props);
  const titleText = commit ? `${commit.short_sha}  ${commit.subject}` : a.sha;
  const testId = `git-graph-dot-${commit?.short_sha ?? a.sha.slice(0, 7)}`;
  return (
    <g key={a.sha}>
      <circle
        data-testid={testId}
        data-filtered={a.filtered_out ? "true" : "false"}
        data-merge={geom.isMerge ? "true" : "false"}
        cx={geom.cx}
        cy={geom.cy}
        r={geom.r}
        fill={geom.fill}
        stroke={geom.isFocused ? "#000" : "none"}
        strokeWidth={geom.isFocused ? 1 : 0}
      >
        <title>{titleText}</title>
      </circle>
      {geom.isMerge && !a.filtered_out && (
        <circle
          cx={geom.cx}
          cy={geom.cy}
          r={Math.max(1, geom.r - 2)}
          fill="#ffffff"
          pointerEvents="none"
          aria-hidden="true"
        />
      )}
    </g>
  );
}

export function GraphDots({
  assignments,
  commits,
  visibleStart,
  visibleEnd,
  hoveredIdx,
  focusedIdx,
}: GraphDotsProps) {
  return (
    <g data-testid="git-graph-dots">
      {assignments.slice(visibleStart, visibleEnd).map((a, offset) => {
        const idx = visibleStart + offset;
        return (
          <DotBadge
            key={a.sha}
            idx={idx}
            a={a}
            commit={commits[idx]}
            hoveredIdx={hoveredIdx}
            focusedIdx={focusedIdx}
          />
        );
      })}
    </g>
  );
}
