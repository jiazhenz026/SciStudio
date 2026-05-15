/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph lane assignment (SKELETON).
 *
 * Status: SKELETON. All non-pure-helper code paths throw
 * `Error("TODO: D39-2.4b — ...")`. D39-2.4b (the IMPL phase) will replace
 * the throw with the algorithm body sketched below.
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
 * Lanes are recycled as branches end (their tip has no later commit that
 * needs the lane). Merge commits "fold" extra parents into new lanes. The
 * algorithm is the standard public-knowledge DAG lane-assignment problem;
 * see ADR-039 §3.5b for the line of provenance (textbook material; no
 * library code copied).
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   commits: GitCommit[]   — already in topological order (`git log` newest
 *                            first is the typical ordering). Each commit
 *                            knows its own `sha` and `parents: string[]`.
 *
 * Topological-order assumption: every commit MUST appear AFTER its children
 * in the array (i.e. children first, parents later). `git log --topo-order`
 * gives us this for free.
 *
 * ============================================================================
 * OUTPUT
 * ============================================================================
 *
 *   LaneAssignment[]
 *     [
 *       {
 *         sha:           string;
 *         lane:          number;            // primary lane the dot lives on
 *         merge_lanes:   number[];          // extra lanes for parents 2..N
 *                                           // (octopus merges may push N>2)
 *         color_index:   number;            // input to colorPalette.ts
 *         filtered_out:  boolean;           // does this commit pass the
 *                                           // current historyFilter? Dimmed
 *                                           // rendering iff false (§3.5c).
 *       },
 *       ...
 *     ]
 *
 * `lane` is a zero-based column index; the SVG layer multiplies by the
 * lane-pitch (likely 16px). `merge_lanes[i]` is the lane that parents[i+1]
 * comes IN on (parent[0] always continues `lane`). `color_index` is
 * deterministic on the lane number per ADR §3.5b "branch color rotation".
 *
 * ============================================================================
 * ALGORITHM (per ADR-039 §3.5b sketch)
 * ============================================================================
 *
 * Maintain a sparse array `active_lanes: (string | null)[]` where the value
 * at slot `i` is the SHA the lane is "waiting for" — i.e. the next commit
 * that should land in lane `i` because some already-drawn child of it has
 * declared this lane as the home of its first parent. A `null` value means
 * the lane is currently free for reuse.
 *
 *   for each commit in topo-order:
 *     1. PICK LANE
 *        Try to reuse a lane: scan active_lanes for an entry === commit.sha.
 *          If found:  reuse that index → lane.
 *          If none:   first null slot, or push a new lane on the right.
 *
 *     2. RECORD LANE
 *        commit.lane = lane
 *
 *     3. FORWARD FIRST PARENT
 *        active_lanes[lane] = commit.parents[0] ?? null
 *          (null = orphan / root commit; lane becomes free immediately)
 *
 *     4. FOLD EXTRA PARENTS (merge commits)
 *        for extra in commit.parents.slice(1):
 *          new_lane := first null slot in active_lanes, or push new
 *          active_lanes[new_lane] = extra
 *          commit.merge_lanes.push(new_lane)
 *
 *     5. ASSIGN COLOR
 *        color_index = lane mod COLORS.length     (palette in colorPalette.ts)
 *
 * Reference pseudocode from ADR-039 §3.5b (verbatim):
 *
 *   function assignLanes(commits: GitCommit[]): GitCommit[] {
 *     const active_lanes: (string | null)[] = []
 *     for (const commit of commits) {
 *       let lane = active_lanes.findIndex(sha => sha === commit.sha)
 *       if (lane === -1) {
 *         lane = active_lanes.findIndex(s => s === null)
 *         if (lane === -1) lane = active_lanes.length, active_lanes.push(null)
 *       }
 *       commit.lane = lane
 *       active_lanes[lane] = commit.parents[0] ?? null
 *       for (const extra of commit.parents.slice(1)) {
 *         let new_lane = active_lanes.findIndex(s => s === null)
 *         if (new_lane === -1) new_lane = active_lanes.length, active_lanes.push(null)
 *         active_lanes[new_lane] = extra
 *         commit.merge_lanes ??= []
 *         commit.merge_lanes.push(new_lane)
 *       }
 *     }
 *     return commits
 *   }
 *
 * The D39-2.4b IMPL will translate the above into the LaneAssignment[]
 * output shape (the sketch mutates `commit` in place; our impl returns
 * a new array of `LaneAssignment` records to keep the input immutable
 * and make the function pure).
 *
 * ============================================================================
 * COMPLEXITY
 * ============================================================================
 *
 *   Time:  O(C * L)  where C = #commits, L = max concurrent lanes.
 *          In practice L is small (~10 for typical scientific projects),
 *          so this is effectively O(C). The `findIndex` scans are the
 *          inner loop. For pathological repos with hundreds of concurrent
 *          branches, an auxiliary `Map<sha, lane>` reduces the SHA lookup
 *          to O(1) but trades memory; defer until profiling demands it.
 *   Space: O(L) for `active_lanes` + O(C) for output. The input is not
 *          mutated.
 *
 * Performance target (ADR §3.5b): 1000 commits without virtualization,
 * 10000+ commits with virtualization.
 *
 * ============================================================================
 * EDGE CASES (cover in D39-2.4b tests)
 * ============================================================================
 *
 *   1. EMPTY INPUT
 *      → return [].
 *
 *   2. SINGLE COMMIT (initial commit)
 *      → parents = []; lane = 0; merge_lanes = [].
 *      → active_lanes ends as [null] (lane immediately freed).
 *
 *   3. ROOT COMMIT IN THE MIDDLE OF THE LOG
 *      → A commit with empty parents array that isn't the first. Happens
 *        when a repo has multiple disconnected root commits (e.g. a
 *        cherry-picked-from-nothing or grafted history). The lane the
 *        root commit occupies should free immediately
 *        (active_lanes[lane] = null) so a later concurrent branch can
 *        reuse it.
 *
 *   4. LINEAR HISTORY
 *      → All commits have exactly 1 parent. All lane = 0. merge_lanes = [].
 *
 *   5. SIMPLE TWO-WAY MERGE
 *      → A merge commit M has parents [P0, P1].
 *      → M.lane = lane(P0)  (reuses the lane left by P0)
 *      → M.merge_lanes = [lane(P1) or a new lane reserved for P1].
 *      → Edge router will draw a bezier from M down to P1.
 *
 *   6. OCTOPUS MERGE (parents.length > 2)
 *      → parents[2..N-1] each allocate their own lanes. merge_lanes will
 *        have length N-1.
 *      → ADR-039 does not call this out, but git allows octopus merges;
 *        the algorithm handles it naturally.
 *
 *   7. ORPHAN BRANCH (a tip whose first commit has no parents)
 *      → When the topo-order reaches it, no lane will be "waiting for"
 *        its SHA. Step 1 finds a free lane (or pushes new). Step 3 sets
 *        active_lanes[lane] = null. Effectively a new column for one
 *        commit, then the lane goes free.
 *
 *   8. ABANDONED BRANCH (lane never reused later)
 *      → Lane stays in active_lanes with value = parent_sha, but if no
 *        later commit references it, it'll stay until the end. That is
 *        fine for the layout — empty lanes between active ones are
 *        drawn as gaps. Optional: post-pass to collapse trailing null
 *        lanes, but not required for correctness.
 *
 *   9. AMENDED COMMIT (`git commit --amend`)
 *      → From the algorithm's view, an amended commit is just a commit
 *        with a different SHA. No special handling.
 *
 *  10. STALE / UNREACHABLE COMMITS (`git reflog`)
 *      → Not in `git log` output; therefore not in the input. Out of
 *        scope for v1.
 *
 *  11. FILTERED COMMITS (auto: / agent: per §3.5c)
 *      → Filter is applied OUTSIDE this function. We still draw EVERY
 *        commit in the graph (topology must be preserved). The renderer
 *        dims filtered commits to small grey dots. `filtered_out` in
 *        the output is a hint to the renderer; the layout itself is
 *        filter-independent. D39-2.4b: read `historyFilter` from
 *        `gitSlice` inside `integration.ts`, apply
 *        `selectVisibleCommits` to derive the bool per row, but do NOT
 *        omit commits from the lane-assignment input.
 *
 * ============================================================================
 * TEST FIXTURE SKETCH (D39-2.4b will codify these)
 * ============================================================================
 *
 *   Fixture A — linear:
 *     commits: [C3→C2, C2→C1, C1→ ]
 *     expected: all lane=0; merge_lanes=[] each
 *
 *   Fixture B — single merge:
 *     C3 (parents [C2a, C2b]) → C2a (parents [C1]) → C2b (parents [C1]) → C1
 *       (topo order: C3, C2a, C2b, C1)
 *     expected:
 *       C3.lane=0  C3.merge_lanes=[1]
 *       C2a.lane=0
 *       C2b.lane=1
 *       C1.lane=0  (C2b's lane recycled because C1 is C2b's only parent
 *                   AND it's also C2a's parent → first-parent wins; the
 *                   second occurrence of C1 in active_lanes after
 *                   processing C2b will recycle into C2a's slot when C1
 *                   is reached — exact reuse priority depends on the
 *                   findIndex order in the sketch).
 *
 *   Fixture C — octopus merge:
 *     C2 (parents [P0, P1, P2]) → P0 → P1 → P2
 *     expected:
 *       C2.lane=0  C2.merge_lanes=[1,2]
 *
 *   Fixture D — orphan root in the middle:
 *     C3 → C2 → C1 (parents []) ; plus a parallel C2'→C1' (parents [])
 *     expected: two simultaneously active lanes that both free at root.
 *
 *   Fixture E — abandoned tip:
 *     C5 → C4 → C3 → C2 → C1, plus a branch C3' → C2' off C2
 *     C3' lane stays open until end. Renderer treats it as a normal
 *     branch tip with no later commits.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - Called by `integration.ts` once per `gitSlice.logCache[<all>]`
 *     refresh.
 *   - Result is memoised on the commit-list reference (referential
 *     equality) so re-renders of GraphSVG do not recompute. The
 *     integration layer is responsible for invalidating on
 *     `git.head_changed` (it already invalidates `logCache`).
 *   - Output passed to `edgeRouter.ts` to compute per-edge bezier
 *     paths.
 *
 * ============================================================================
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
 * Assign every commit to a graph lane per ADR-039 §3.5b.
 *
 * Pure function: does NOT mutate its input. Returns a parallel array of
 * {@link LaneAssignment} records in the same order as `commits`.
 *
 * D39-2.4a SKELETON: throws — body is filled in D39-2.4b.
 * D39-2.4b IMPL contract: implement the algorithm in the comment block
 * above. The reference pseudocode is verbatim from ADR-039 §3.5b.
 *
 * @param commits - Commits in topological order (children first).
 * @returns A parallel array of lane assignments; `result[i]` describes
 *          `commits[i]`.
 */
export function assignLanes(commits: GitCommit[]): LaneAssignment[] {
  if (commits.length === 0) return [];

  // `active_lanes[i]` is the SHA the lane is "waiting for" — set to the
  // first parent of the last commit drawn in that lane. A `null` slot
  // means the lane is free for reuse.
  const active_lanes: (string | null)[] = [];
  const out: LaneAssignment[] = new Array(commits.length);

  for (let i = 0; i < commits.length; i++) {
    const commit = commits[i];

    // 1. PICK LANE — reuse a lane waiting for this SHA, else first free
    //    slot, else extend.
    let lane = active_lanes.findIndex((sha) => sha === commit.sha);
    if (lane === -1) {
      lane = active_lanes.findIndex((s) => s === null);
      if (lane === -1) {
        lane = active_lanes.length;
        active_lanes.push(null);
      }
    }

    // 3. FORWARD FIRST PARENT — null for root commits frees the lane.
    const firstParent = commit.parents[0];
    active_lanes[lane] = firstParent !== undefined ? firstParent : null;

    // 4. FOLD EXTRA PARENTS (merge commits) — each extra parent gets a
    //    new lane (first null slot, else extend).
    const merge_lanes: number[] = [];
    for (let p = 1; p < commit.parents.length; p++) {
      const extra = commit.parents[p];
      let new_lane = active_lanes.findIndex((s) => s === null);
      if (new_lane === -1) {
        new_lane = active_lanes.length;
        active_lanes.push(null);
      }
      active_lanes[new_lane] = extra;
      merge_lanes.push(new_lane);
    }

    // 5. ASSIGN COLOR — deterministic on lane mod palette length.
    out[i] = {
      sha: commit.sha,
      lane,
      merge_lanes,
      color_index: lane % PALETTE.length,
      filtered_out: false,
    };
  }

  return out;
}

/**
 * Helper exposed for unit tests in D39-2.4b: given a `LaneAssignment[]`
 * result, return the maximum lane index used (i.e. the graph width in
 * lanes). Pure; safe to keep as-is.
 *
 * D39-2.4a: a thin pure helper that operates on the OUTPUT of
 * {@link assignLanes}. We keep it filled out (not a TODO) because
 * (a) it has no dependencies on the unimplemented algorithm, and
 * (b) GraphSVG.tsx wants this in skeleton form to size the SVG viewBox.
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
