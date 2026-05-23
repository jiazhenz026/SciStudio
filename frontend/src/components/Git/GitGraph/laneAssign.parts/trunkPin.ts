/**
 * Hotfix #1006 (Plan B) — pin the "trunk" to lane 0 by following merge-parent
 * continuations when the first-parent chain breaks.
 *
 * Extracted in #1413 from `laneAssign.ts` to reduce the parent function's
 * size + complexity.
 *
 * The DFS+recycle algorithm (per #1002) walks first-parent edges from
 * commits[0] (HEAD). In a complex history HEAD's first-parent chain may
 * end mid-log: e.g. `git checkout feature; git merge main` makes the merge
 * commit's first parent the feature tip, not main, so the first-parent
 * chain follows feature back to its origin (which is a root commit
 * somewhere shallow), not the actual trunk. The actual trunk continues
 * through the merge's SECOND parent.
 *
 * Detection: find the deepest-row commit on lane 0. If it's already the
 * last row, no work to do. Else inspect its non-first parents
 * (`parents[1..]`). If any of those parents lives in the log and is on a
 * different lane, that lane is the "true trunk continuation" — swap it
 * with lane 0.
 *
 * This protects octopus / disconnected-history fixtures where the
 * deepest-lane-0 commit's parents are all unrooted (no continuation
 * possible) — the swap is a no-op for them. Edge colors recompute
 * downstream via `max(child_lane, parent_lane)` (#994). merge_lanes
 * references swap with the lane numbers.
 *
 * Hotfix #1010: color_index is per-branch (allocation order), not per-lane.
 * Swap lane numbers but leave color_index alone — each branch carries its
 * colour across the swap.
 *
 * Mutates `out` in place.
 */
import type { GitCommit } from "../../../../types/api";
import type { LaneAssignment } from "../laneAssign";

function findDeepestLaneZeroRow(out: LaneAssignment[]): number {
  for (let r = out.length - 1; r >= 0; r--) {
    if (out[r].lane === 0) return r;
  }
  return -1;
}

function findTrueTrunkLane(
  lane0Tail: GitCommit,
  laneZeroDeepestRow: number,
  shaToIdx: Map<string, number>,
  out: LaneAssignment[],
): number | null {
  for (let p = 1; p < lane0Tail.parents.length; p++) {
    const pi = shaToIdx.get(lane0Tail.parents[p]);
    if (pi !== undefined && pi > laneZeroDeepestRow && out[pi].lane !== 0) {
      return out[pi].lane;
    }
  }
  return null;
}

function swapLanes(out: LaneAssignment[], target: number): void {
  for (const a of out) {
    if (a.lane === 0) a.lane = target;
    else if (a.lane === target) a.lane = 0;
    if (a.merge_lanes.length > 0) {
      a.merge_lanes = a.merge_lanes.map((c) => (c === 0 ? target : c === target ? 0 : c));
    }
  }
}

export function pinTrunkToLaneZero(out: LaneAssignment[], commits: GitCommit[]): void {
  if (out.length < 2) return;
  const laneZeroDeepestRow = findDeepestLaneZeroRow(out);
  if (laneZeroDeepestRow < 0 || laneZeroDeepestRow >= out.length - 1) return;

  const lane0Tail = commits[laneZeroDeepestRow];
  const shaToIdx = new Map<string, number>();
  for (let i = 0; i < commits.length; i++) shaToIdx.set(commits[i].sha, i);

  const trueTrunkLane = findTrueTrunkLane(lane0Tail, laneZeroDeepestRow, shaToIdx, out);
  if (trueTrunkLane === null) return;
  swapLanes(out, trueTrunkLane);
}
