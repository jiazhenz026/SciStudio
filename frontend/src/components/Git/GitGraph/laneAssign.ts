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
 * branches (e.g. SciStudio dev repo: ~60 merged-and-deleted feature branches)
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
import { pinTrunkToLaneZero } from "./laneAssign.parts/trunkPin";

/**
 * Per-commit lane assignment produced by {@link assignLanes}.
 */
export interface LaneAssignment {
  sha: string;
  /** Primary lane (column). Zero-based; renderer multiplies by lane-pitch. */
  lane: number;
  /**
   * For merge commits, the lane each extra parent comes in on.
   * `merge_lanes[i]` is the lane for `parents[i+1]` (parents[0] always
   * continues `lane`). Empty for non-merge commits.
   */
  merge_lanes: number[];
  /** Deterministic palette index. Renderer maps to color via `colorPalette.ts`. */
  color_index: number;
  /**
   * `true` when the active history filter would hide this commit. Computed
   * by `integration.ts` BEFORE calling the renderer; this function does NOT
   * apply filtering.
   */
  filtered_out: boolean;
}

interface VertexState {
  nextParentIdx: number;
  branch: Branch | null;
}

interface Branch {
  /** Lane index (x-position slot). Recycled when the branch ends. */
  colour: number;
  /**
   * Palette index for stroke color. Hotfix #1010: assigned at allocation
   * time from a monotonic counter — decoupled from lane so recycled lanes
   * pick a different colour.
   */
  colorIndex: number;
  /** Row index of the last vertex on this branch. */
  end: number;
}

interface Allocator {
  state: VertexState[];
  branches: Branch[];
  mergeLanes: number[][];
  availableColours: number[];
  shaToIdx: Map<string, number>;
  commits: GitCommit[];
  colorSeq: { value: number };
}

function buildAllocator(commits: GitCommit[]): Allocator {
  const n = commits.length;
  const state: VertexState[] = new Array(n);
  for (let i = 0; i < n; i++) state[i] = { nextParentIdx: 0, branch: null };
  const shaToIdx = new Map<string, number>();
  for (let i = 0; i < n; i++) shaToIdx.set(commits[i].sha, i);
  const mergeLanes: number[][] = new Array(n);
  for (let i = 0; i < n; i++) mergeLanes[i] = [];
  return {
    state,
    branches: [],
    mergeLanes,
    availableColours: [],
    shaToIdx,
    commits,
    colorSeq: { value: 0 },
  };
}

function allocateBranchSlot(
  alloc: Allocator,
  startAt: number,
): { lane: number; colorIndex: number } {
  let lane = -1;
  for (let c = 0; c < alloc.availableColours.length; c++) {
    if (startAt > alloc.availableColours[c]) {
      lane = c;
      break;
    }
  }
  if (lane < 0) {
    alloc.availableColours.push(0);
    lane = alloc.availableColours.length - 1;
  }
  const colorIndex = alloc.colorSeq.value % PALETTE.length;
  alloc.colorSeq.value++;
  return { lane, colorIndex };
}

function parentRow(alloc: Allocator, i: number, p: number): number {
  const parents = alloc.commits[i].parents;
  if (p < 0 || p >= parents.length) return -1;
  const idx = alloc.shaToIdx.get(parents[p]);
  return idx === undefined ? -1 : idx;
}

/** Make sure the start vertex itself is on a branch (allocate if not). */
function ensureBranch(alloc: Allocator, startAt: number): Branch {
  let branch = alloc.state[startAt].branch;
  if (branch === null) {
    const slot = allocateBranchSlot(alloc, startAt);
    branch = { colour: slot.lane, colorIndex: slot.colorIndex, end: startAt };
    alloc.branches.push(branch);
    alloc.state[startAt].branch = branch;
  }
  return branch;
}

/**
 * Handle the fold-in for an extra parent of a merge commit (startParentP > 0).
 * Returns the (curIdx, curBranch) pair from which the caller continues to
 * walk down first-parent edges, or `null` when the fold-in terminates
 * immediately (dangling parent / parent already branched).
 */
function consumeMergeParent(
  alloc: Allocator,
  startAt: number,
  startParentP: number,
): { curIdx: number; curBranch: Branch } | null {
  const parentIdx = parentRow(alloc, startAt, startParentP);
  if (parentIdx < 0) {
    // Dangling parent for a merge fold-in: allocate a fresh lane anchored
    // at the merge commit's row so the renderer can still draw a stub.
    const slot = allocateBranchSlot(alloc, startAt);
    const foldBranch: Branch = { colour: slot.lane, colorIndex: slot.colorIndex, end: startAt };
    alloc.branches.push(foldBranch);
    alloc.mergeLanes[startAt].push(slot.lane);
    alloc.availableColours[slot.lane] = startAt;
    return null;
  }

  // If the parent is already on a branch, the fold-in just records a
  // merge_lanes entry pointing at that existing branch's lane.
  if (alloc.state[parentIdx].branch !== null) {
    alloc.mergeLanes[startAt].push(alloc.state[parentIdx].branch!.colour);
    return null;
  }

  // Parent is not yet on a branch — allocate a new lane slot for the
  // fold-in branch and assign the parent to it. The slot is allocated
  // against `startAt` so the column is "in use" starting at startAt.
  const slot = allocateBranchSlot(alloc, startAt);
  const foldBranch: Branch = { colour: slot.lane, colorIndex: slot.colorIndex, end: parentIdx };
  alloc.branches.push(foldBranch);
  alloc.mergeLanes[startAt].push(slot.lane);
  alloc.state[parentIdx].branch = foldBranch;
  alloc.state[parentIdx].nextParentIdx++;
  foldBranch.end = parentIdx;
  alloc.availableColours[foldBranch.colour] = parentIdx;
  return { curIdx: parentIdx, curBranch: foldBranch };
}

/**
 * Walk first-parent edges starting from `parentIdx`, extending `curBranch`
 * onto each one until we hit a vertex already on a different branch (chain
 * break) or a root commit (parent missing from log).
 */
function walkFirstParentChain(
  alloc: Allocator,
  curBranch: Branch,
  startCurIdx: number,
  firstParentIdx: number,
): void {
  let curIdx = startCurIdx;
  let parentIdx = firstParentIdx;
  while (parentIdx >= 0 && parentIdx < alloc.commits.length) {
    if (alloc.state[parentIdx].branch !== null) {
      // Chain break: parent already belongs to a different branch.
      // Hotfix #1013: hold the lane until parentIdx so the trailing
      // fork-back edge actually ends.
      curBranch.end = curIdx;
      alloc.availableColours[curBranch.colour] = parentIdx;
      return;
    }
    // Extend our branch onto parentIdx.
    alloc.state[parentIdx].branch = curBranch;
    alloc.state[parentIdx].nextParentIdx++;
    curIdx = parentIdx;
    curBranch.end = curIdx;
    alloc.availableColours[curBranch.colour] = curIdx;
    const next = parentRow(alloc, parentIdx, 0);
    if (next < 0) return;
    parentIdx = next;
  }
}

function determinePath(alloc: Allocator, startAt: number): void {
  // 1. Make sure the start vertex itself is on a branch.
  const branch = ensureBranch(alloc, startAt);

  // 2. Consume the next un-consumed parent of `startAt`.
  const startParentP = alloc.state[startAt].nextParentIdx;
  if (startParentP >= alloc.commits[startAt].parents.length) {
    branch.end = startAt;
    alloc.availableColours[branch.colour] = startAt;
    return;
  }
  alloc.state[startAt].nextParentIdx++;

  if (startParentP === 0) {
    // First-parent edge continues `startAt`'s branch.
    const firstParentIdx = parentRow(alloc, startAt, 0);
    if (firstParentIdx < 0) {
      // Root commit (or dangling first-parent) — branch ends here.
      branch.end = startAt;
      alloc.availableColours[branch.colour] = startAt;
      return;
    }
    walkFirstParentChain(alloc, branch, startAt, firstParentIdx);
    return;
  }

  // Extra parent: allocate a SEPARATE branch and slot for the fold-in.
  const foldIn = consumeMergeParent(alloc, startAt, startParentP);
  if (foldIn === null) return;
  const nextParent = parentRow(alloc, foldIn.curIdx, 0);
  if (nextParent < 0) return;
  walkFirstParentChain(alloc, foldIn.curBranch, foldIn.curIdx, nextParent);
}

/**
 * Assign every commit to a graph lane per ADR-039 §3.5b (hotfix #1002
 * algorithm). Pure function: does NOT mutate its input.
 */
export function assignLanes(commits: GitCommit[]): LaneAssignment[] {
  if (commits.length === 0) return [];

  const alloc = buildAllocator(commits);
  const n = commits.length;

  // Outer loop. Re-enters merge vertices until all parents are consumed.
  let i = 0;
  while (i < n) {
    const hasMoreParents = alloc.state[i].nextParentIdx < commits[i].parents.length;
    if (alloc.state[i].branch === null || hasMoreParents) {
      determinePath(alloc, i);
      if (alloc.state[i].nextParentIdx >= commits[i].parents.length) {
        i++;
      }
    } else {
      i++;
    }
  }

  // Build the LaneAssignment output array.
  const out: LaneAssignment[] = new Array(n);
  for (let r = 0; r < n; r++) {
    const branch = alloc.state[r].branch;
    const lane = branch !== null ? branch.colour : 0;
    // Hotfix #1010: color_index follows the branch (allocation order)
    // rather than the lane number.
    const colorIndex = branch !== null ? branch.colorIndex : 0 % PALETTE.length;
    out[r] = {
      sha: commits[r].sha,
      lane,
      merge_lanes: alloc.mergeLanes[r],
      color_index: colorIndex,
      filtered_out: false,
    };
  }

  pinTrunkToLaneZero(out, commits);

  return out;
}

/**
 * Helper exposed for unit tests and the renderer: given a
 * `LaneAssignment[]` result, return the maximum lane index used.
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
