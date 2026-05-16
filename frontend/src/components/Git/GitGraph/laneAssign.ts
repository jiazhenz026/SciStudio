/**
 * ADR-039 §3.5b — Branch-graph lane assignment.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Given a topologically-ordered list of git commits (each carrying its own
 * SHA and the SHAs of its parents), assign every commit to a horizontal
 * "lane" so that the resulting drawing of commits-as-dots + edges-as-lines
 * looks like the VS Code / GitLens / JetBrains git graphs:
 *
 *   lane 0 ●─────────●─────●           main
 *               ╲         ╲╱
 *   lane 1       ●─────────●           feat/X
 *                          ╱
 *   lane 2                ●             stash@{0}
 *
 * ============================================================================
 * ALGORITHM — DFS chain + per-color row-recycle (#1002 hotfix)
 * ============================================================================
 *
 * The original §3.5b sketch used a row-indexed `active_lanes: (sha|null)[]`
 * array where every active lane slot stayed open until the lane's "waiting"
 * SHA was processed. In a deep history with many already-deleted feature
 * branches (e.g. SciEasy dev repo: ~60 merged-and-deleted feature branches)
 * those slots could remain open all the way to repo root, producing max
 * lane index = 148 and SVG width = 2400px.
 *
 * Hotfix #1002 replaces that with the DFS-chain + per-color-recycle
 * invariant used by every modern git GUI (vscode-git-graph `web/graph.ts`,
 * JetBrains `PrintElementGenerator`, GitLens):
 *
 *   1. Maintain `availableColours[c]` = the LAST row index at which color
 *      slot `c` was used. A color is reusable starting from `startAt` when
 *      `startAt > availableColours[c]`.
 *
 *   2. For each unprocessed parent of each commit, walk a DFS chain along
 *      first-parent edges. Every vertex on the chain joins the chain's
 *      branch (gets the branch's color/lane).
 *
 *   3. The chain BREAKS the moment we hit a vertex that already belongs to
 *      a different branch. The current branch records its end at the
 *      previous row; its color slot becomes available for reuse by any
 *      LATER commit (row > end).
 *
 * Net effect: max simultaneously-allocated color count = max number of
 * *temporally overlapping* unfinished side branches, not the count of
 * historical branches. For SciEasy dev repo this drops max lane from 148
 * to roughly the count of branches alive in any one row's neighbourhood
 * (typically <= 10).
 *
 * Reference: mhutchie/vscode-git-graph `web/graph.ts` — `determinePath`
 * (lines 643-750 in develop branch), `getAvailableColour` (lines 719-726).
 * Clean-room reimplementation per CLAUDE.md §2.4 — same invariant, fresh
 * TypeScript, no code copied. ADR-039 §3.5b addendum documents the
 * algorithm change.
 *
 * ============================================================================
 * INPUT / OUTPUT
 * ============================================================================
 *
 *   commits: GitCommit[]   — already in topological order (children first,
 *                            parents later). `git log --topo-order` gives
 *                            us this for free.
 *
 *   returns LaneAssignment[]   — parallel array; result[i] describes
 *                                commits[i]. See {@link LaneAssignment}
 *                                for field semantics.
 *
 * Pure function: does NOT mutate its input.
 *
 * ============================================================================
 * COMPLEXITY
 * ============================================================================
 *
 *   Time:  O(C * L_active)  where C = #commits, L_active = max number of
 *          concurrently-alive branches. The inner findIndex over
 *          `availableColours` is L_active long. In practice L_active is
 *          small (<= 20 for typical scientific projects), so this is
 *          effectively O(C).
 *   Space: O(L_active) for `availableColours` + O(C) for output. The input
 *          is not mutated.
 *
 * Performance target (ADR §3.5b): 1000 commits without virtualization,
 * 10000+ commits with virtualization.
 */

import type { GitCommit } from "../../../types/api";

import { PALETTE } from "./colorPalette";

/**
 * Per-commit lane assignment produced by {@link assignLanes}.
 *
 * The renderer (`GraphSVG.tsx`) reads this directly; the edge router
 * (`edgeRouter.ts`) reads {@link LaneAssignment.lane} and
 * {@link LaneAssignment.merge_lanes} to compute connector paths.
 */
export interface LaneAssignment {
  sha: string;
  /**
   * Primary lane (column) the commit dot lives on. Zero-based; the SVG
   * layer multiplies by the lane-pitch constant.
   */
  lane: number;
  /**
   * For merge commits (parents.length >= 2), the lane each extra parent
   * comes in on. `merge_lanes[i]` is the lane for `parents[i+1]`
   * (parents[0] always continues `lane`). Empty for non-merge commits.
   */
  merge_lanes: number[];
  /**
   * Deterministic palette index. Computed as `lane % palette.length` in
   * the impl. Renderer maps to actual color via `colorPalette.ts`.
   */
  color_index: number;
  /**
   * Hint for the renderer: `true` when the active history filter would
   * hide this commit from the History list, so the graph dims it to a
   * small grey dot (per ADR §3.5c). Computed by `integration.ts` from
   * `gitSlice.historyFilter` BEFORE calling the renderer; this function
   * itself does NOT apply filtering.
   */
  filtered_out: boolean;
}

/**
 * Internal: per-vertex bookkeeping during traversal.
 *
 * `nextParentIdx` tracks which of this vertex's parents has been consumed
 * by the outer loop. When a vertex is first visited via `determinePath`,
 * its first parent is consumed; on a re-entry (merge commit with multiple
 * parents), the next un-consumed parent is consumed.
 *
 * `branch` is the {@link Branch} the vertex was assigned to (or null if
 * not yet assigned — only true mid-traversal).
 */
interface VertexState {
  nextParentIdx: number;
  branch: Branch | null;
}

/**
 * Internal: an active or completed branch in the lane allocator. Holds
 * its color/lane number and the row at which its last vertex sits, so the
 * recycle test (`startAt > end`) is O(1).
 */
interface Branch {
  /**
   * Lane index (x-position slot). Recycled when the branch ends — many
   * short-lived branches in a dense PR-ladder repo can end up sharing the
   * same slot over time.
   */
  colour: number;
  /**
   * Palette index for stroke color. Hotfix #1010: assigned at allocation
   * time from a monotonic counter (modulo palette length), NOT from the
   * lane index. Decoupling color from lane means every newly-allocated
   * branch gets the next color in the palette — so when a lane is recycled
   * the new branch picks a different color than the one that just ended.
   * Pre-#1010 this was always `lane % PALETTE.length`, which meant a
   * PR-merge-heavy history with many short feature branches all recycling
   * lane 3 rendered as a wall of yellow lines.
   */
  colorIndex: number;
  /**
   * Row index of the last vertex on this branch. Updated as the DFS
   * extends; used as the lower-bound when checking whether the lane slot
   * can be recycled for a later branch.
   */
  end: number;
}

/**
 * Assign every commit to a graph lane per ADR-039 §3.5b (hotfix #1002
 * algorithm). Pure function: does NOT mutate its input.
 *
 * @param commits - Commits in topological order (children first).
 * @returns A parallel array of lane assignments; `result[i]` describes
 *          `commits[i]`.
 */
export function assignLanes(commits: GitCommit[]): LaneAssignment[] {
  if (commits.length === 0) return [];

  const n = commits.length;

  // Per-vertex traversal state. nextParentIdx starts at 0; bumped each
  // time the outer loop "consumes" a parent edge into the DFS.
  const state: VertexState[] = new Array(n);
  for (let i = 0; i < n; i++) {
    state[i] = { nextParentIdx: 0, branch: null };
  }

  // SHA → row index, for fast parent lookup.
  const shaToIdx = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    shaToIdx.set(commits[i].sha, i);
  }

  // Per-vertex merge_lanes accumulator (only populated for merge commits).
  const mergeLanes: number[][] = new Array(n);
  for (let i = 0; i < n; i++) mergeLanes[i] = [];

  // availableColours[c] = last row index where lane slot c was used.
  // Lane c is reusable starting at row r when r > availableColours[c].
  const availableColours: number[] = [];
  const branches: Branch[] = [];

  // Hotfix #1010: monotonic counter for stroke-color assignment.
  // Each newly-allocated branch gets `colorSeq % PALETTE.length`. The lane
  // slot is recycled separately by `getAvailableColour`, so dense
  // PR-ladder histories no longer collapse onto the same palette colour
  // every time the slot gets reused.
  let colorSeq = 0;

  /**
   * Allocate a lane slot for a new branch starting at `startAt`. Returns
   * both the lane (x-position) and a fresh palette colour drawn from the
   * monotonic `colorSeq` counter.
   */
  function allocateBranchSlot(startAt: number): {
    lane: number;
    colorIndex: number;
  } {
    let lane = -1;
    for (let c = 0; c < availableColours.length; c++) {
      if (startAt > availableColours[c]) {
        lane = c;
        break;
      }
    }
    if (lane < 0) {
      availableColours.push(0);
      lane = availableColours.length - 1;
    }
    const colorIndex = colorSeq % PALETTE.length;
    colorSeq++;
    return { lane, colorIndex };
  }

  /**
   * Look up the parent's row index for the p-th parent of vertex `i`. The
   * parent may be missing from the input (truncated `git log`), in which
   * case we return -1 — the caller treats it as a chain termination.
   */
  function parentRow(i: number, p: number): number {
    const parents = commits[i].parents;
    if (p < 0 || p >= parents.length) return -1;
    const idx = shaToIdx.get(parents[p]);
    return idx === undefined ? -1 : idx;
  }

  /**
   * The DFS-chain extension. Called when the outer loop wants vertex
   * `startAt` to receive a branch (because it has no branch yet) or to
   * have its next unprocessed parent consumed (merge case).
   *
   * If `startAt` itself has no branch, we allocate one with a recycled
   * color slot. Then we follow first-parent edges down the chain, extending
   * the branch to each parent vertex UNTIL we hit a vertex already
   * assigned to a different branch — at that point the chain breaks
   * (the parent keeps its own branch; we just record an end-of-chain).
   */
  function determinePath(startAt: number): void {
    // 1. Make sure the start vertex itself is on a branch.
    let branch = state[startAt].branch;
    if (branch === null) {
      const slot = allocateBranchSlot(startAt);
      branch = { colour: slot.lane, colorIndex: slot.colorIndex, end: startAt };
      branches.push(branch);
      state[startAt].branch = branch;
    }

    // 2. Consume the next un-consumed parent of `startAt`.
    const startParentP = state[startAt].nextParentIdx;
    if (startParentP >= commits[startAt].parents.length) {
      // No parents to consume (root commit, or we've exhausted them).
      branch.end = startAt;
      availableColours[branch.colour] = startAt;
      return;
    }
    state[startAt].nextParentIdx++;

    // For an extra parent of a merge commit (startParentP > 0), allocate
    // a SEPARATE branch and slot for the fold-in. The fold-in branch
    // starts at the parent's row, not at the merge commit's row.
    let curIdx = startAt;
    let curBranch: Branch;

    if (startParentP === 0) {
      // First-parent edge continues `startAt`'s branch.
      curBranch = branch;
    } else {
      // Extra parent: allocate a new branch starting from the parent's row.
      const parentIdx = parentRow(startAt, startParentP);
      if (parentIdx < 0) {
        // Dangling parent for a merge fold-in: allocate a fresh lane
        // anchored at the merge commit's row so the renderer can still
        // draw a stub. The fold-in branch immediately ends.
        const slot = allocateBranchSlot(startAt);
        const foldBranch: Branch = {
          colour: slot.lane,
          colorIndex: slot.colorIndex,
          end: startAt,
        };
        branches.push(foldBranch);
        mergeLanes[startAt].push(slot.lane);
        availableColours[slot.lane] = startAt;
        return;
      }

      // If the parent is already on a branch, the fold-in just records a
      // merge_lanes entry pointing at that existing branch's lane. No new
      // allocation, no chain extension — the edge router will draw the
      // bezier from this merge commit straight to the parent's existing
      // lane.
      if (state[parentIdx].branch !== null) {
        mergeLanes[startAt].push(state[parentIdx].branch!.colour);
        return;
      }

      // Parent is not yet on a branch — allocate a new lane slot for the
      // fold-in branch and assign the parent to it. The chain then walks
      // down from the parent. The slot is allocated against `startAt`
      // (the merge commit's row), not the parent's row, because the
      // fold-in lane occupies the column from the merge commit DOWN to
      // wherever the fold-in branch ends — so the column is "in use"
      // starting at startAt.
      const slot = allocateBranchSlot(startAt);
      const foldBranch: Branch = {
        colour: slot.lane,
        colorIndex: slot.colorIndex,
        end: parentIdx,
      };
      branches.push(foldBranch);
      mergeLanes[startAt].push(slot.lane);
      state[parentIdx].branch = foldBranch;
      // The parent's first-parent edge is now consumed by this fold-in
      // chain (we're walking down through it). Bump nextParentIdx.
      state[parentIdx].nextParentIdx++;
      curIdx = parentIdx;
      curBranch = foldBranch;
      curBranch.end = parentIdx;
      availableColours[curBranch.colour] = parentIdx;
    }

    if (startParentP === 0) {
      // Walk down first-parent edges from startAt.
      const firstParentIdx = parentRow(startAt, 0);
      if (firstParentIdx < 0) {
        // Root commit (or dangling first-parent) — branch ends here.
        curBranch.end = startAt;
        availableColours[curBranch.colour] = startAt;
        return;
      }

      let parentIdx = firstParentIdx;
      while (parentIdx >= 0 && parentIdx < n) {
        if (state[parentIdx].branch !== null) {
          // Chain break: parent already belongs to a different branch.
          // We don't claim this parent for our branch. The renderer's
          // edge will still be drawn from curIdx to parentIdx because
          // commits[curIdx].parents[0] === commits[parentIdx].sha.
          curBranch.end = curIdx;
          availableColours[curBranch.colour] = curIdx;
          return;
        }
        // Extend our branch onto parentIdx.
        state[parentIdx].branch = curBranch;
        state[parentIdx].nextParentIdx++;
        curIdx = parentIdx;
        curBranch.end = curIdx;
        availableColours[curBranch.colour] = curIdx;

        // Advance to the parent's first parent (if any).
        const next = parentRow(parentIdx, 0);
        if (next < 0) {
          // Root or dangling.
          return;
        }
        parentIdx = next;
      }
    } else {
      // We've already advanced curIdx to the fold-in's parent row above
      // and consumed its first-parent slot. Now continue walking down
      // first-parent edges from curIdx.
      let parentIdx = parentRow(curIdx, 0);
      while (parentIdx >= 0 && parentIdx < n) {
        if (state[parentIdx].branch !== null) {
          curBranch.end = curIdx;
          availableColours[curBranch.colour] = curIdx;
          return;
        }
        state[parentIdx].branch = curBranch;
        state[parentIdx].nextParentIdx++;
        curIdx = parentIdx;
        curBranch.end = curIdx;
        availableColours[curBranch.colour] = curIdx;
        const next = parentRow(parentIdx, 0);
        if (next < 0) return;
        parentIdx = next;
      }
    }
  }

  // Outer loop. Re-enters merge vertices until all parents are consumed.
  let i = 0;
  while (i < n) {
    const hasMoreParents =
      state[i].nextParentIdx < commits[i].parents.length;
    if (state[i].branch === null || hasMoreParents) {
      determinePath(i);
      // Do NOT advance i: a merge commit with multiple parents needs to
      // be re-entered. We advance only when the vertex has both a branch
      // AND all its parents consumed.
      if (state[i].nextParentIdx >= commits[i].parents.length) {
        i++;
      }
    } else {
      i++;
    }
  }

  // Build the LaneAssignment output array.
  const out: LaneAssignment[] = new Array(n);
  for (let r = 0; r < n; r++) {
    const branch = state[r].branch;
    // A vertex always has a branch by this point — determinePath ensures
    // it. Defensive fallback: lane 0 with a fresh color slot.
    const lane = branch !== null ? branch.colour : 0;
    // Hotfix #1010: color_index follows the branch (allocation order)
    // rather than the lane number. Defensive fallback uses lane 0's
    // palette colour when no branch is recorded.
    const colorIndex =
      branch !== null ? branch.colorIndex : 0 % PALETTE.length;
    out[r] = {
      sha: commits[r].sha,
      lane,
      merge_lanes: mergeLanes[r],
      color_index: colorIndex,
      filtered_out: false,
    };
  }

  // Hotfix #1006 (Plan B): pin the "trunk" to lane 0 by following
  // merge-parent continuations when the first-parent chain breaks.
  //
  // The DFS+recycle algorithm (per #1002) walks first-parent edges
  // from commits[0] (HEAD). In a complex history HEAD's first-parent
  // chain may end mid-log: e.g. `git checkout feature; git merge main`
  // makes the merge commit's first parent the feature tip, not main,
  // so the first-parent chain follows feature back to its origin
  // (which is a root commit somewhere shallow), not the actual trunk.
  // The actual trunk continues through the merge's SECOND parent.
  //
  // Detection: find the deepest-row commit on lane 0. If it's already
  // the last row, no work to do. Else inspect its non-first parents
  // (`parents[1..]`). If any of those parents lives in the log and is
  // on a different lane, that lane is the "true trunk continuation"
  // — swap it with lane 0.
  //
  // This protects octopus / disconnected-history fixtures where the
  // deepest-lane-0 commit's parents are all unrooted (no continuation
  // possible) — the swap is a no-op for them. Edge colors recompute
  // downstream via `max(child_lane, parent_lane)` (#994). merge_lanes
  // references swap with the lane numbers.
  if (out.length >= 2) {
    let laneZeroDeepestRow = -1;
    for (let r = out.length - 1; r >= 0; r--) {
      if (out[r].lane === 0) {
        laneZeroDeepestRow = r;
        break;
      }
    }
    if (
      laneZeroDeepestRow >= 0 &&
      laneZeroDeepestRow < out.length - 1
    ) {
      const lane0Tail = commits[laneZeroDeepestRow];
      // Build a sha-to-row map once.
      const shaToIdx = new Map<string, number>();
      for (let i = 0; i < commits.length; i++) shaToIdx.set(commits[i].sha, i);
      let trueTrunkLane: number | null = null;
      for (let p = 1; p < lane0Tail.parents.length; p++) {
        const pi = shaToIdx.get(lane0Tail.parents[p]);
        if (
          pi !== undefined &&
          pi > laneZeroDeepestRow &&
          out[pi].lane !== 0
        ) {
          trueTrunkLane = out[pi].lane;
          break;
        }
      }
      if (trueTrunkLane !== null) {
        const target = trueTrunkLane;
        // Hotfix #1010: color_index is per-branch (allocation order),
        // not per-lane. Swap lane numbers but leave color_index alone —
        // each branch carries its colour across the swap.
        for (const a of out) {
          if (a.lane === 0) a.lane = target;
          else if (a.lane === target) a.lane = 0;
          if (a.merge_lanes.length > 0) {
            a.merge_lanes = a.merge_lanes.map((c) =>
              c === 0 ? target : c === target ? 0 : c,
            );
          }
        }
      }
    }
  }

  return out;
}

/**
 * Helper exposed for unit tests and the renderer: given a
 * `LaneAssignment[]` result, return the maximum lane index used (i.e. the
 * graph width in lanes). Pure.
 *
 * Returns -1 for an empty input so the renderer can short-circuit.
 */
export function maxLane(assignments: LaneAssignment[]): number {
  if (assignments.length === 0) return -1;
  let m = 0;
  for (const a of assignments) {
    if (a.lane > m) m = a.lane;
    for (const ml of a.merge_lanes) {
      if (ml > m) m = ml;
    }
  }
  return m;
}
