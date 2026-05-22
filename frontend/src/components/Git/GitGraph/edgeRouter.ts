/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph edge routing (SKELETON).
 *
 * Status: SKELETON. All non-pure-helper code paths throw
 * `Error("TODO: D39-2.4b — ...")`. D39-2.4b (the IMPL phase) will fill
 * in the bezier-curve math sketched below.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * For each commit, draw a connector line from the commit's dot to EACH
 * of its parent commits' dots. Three visual cases per edge:
 *
 *   1. SAME LANE          → vertical straight segment.
 *
 *        ●  commit
 *        │
 *        ●  parent
 *
 *   2. LANE JUMP DOWN     → child in lane L_c, parent in lane L_p (L_p != L_c)
 *      → bezier S-curve that originates straight down from the child
 *        and lands straight up at the parent.
 *
 *        ●          commit (lane 0)
 *        │╲
 *        │ ╲
 *        │  ╲
 *           ●       parent (lane 1)
 *
 *   3. MERGE FOLD-IN     → child is a merge commit; the merge_lanes parent
 *      → emerges from the parent's lane and bezier-curves INTO the child's
 *        lane at the dot.
 *
 *        ●          merge child (lane 0)
 *       ╱│
 *      ╱ │
 *     ●  │          incoming parent (lane 1)
 *        ●          first parent  (lane 0)
 *
 * Visual style references VS Code / GitLens / JetBrains as design
 * inspiration (functional UI conventions are not copyright-protected
 * per ADR-039 §3.5b).
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   assignments: LaneAssignment[]   — from `laneAssign.assignLanes`.
 *   commits:     GitCommit[]        — parallel array; assignments[i]
 *                                     describes commits[i]. We need the
 *                                     parents array to know which other
 *                                     row to draw an edge to.
 *
 * Invariants:
 *   - `assignments.length === commits.length`.
 *   - `assignments[i].sha === commits[i].sha`.
 *   - For each parent SHA in `commits[i].parents`, the parent appears
 *     LATER in the array (topological order, children-first). If the
 *     parent SHA is NOT in the array (truncated log), we omit the edge
 *     and emit a `dangling: true` marker so the renderer can draw a
 *     stub arrow at the bottom row.
 *
 * ============================================================================
 * OUTPUT
 * ============================================================================
 *
 *   GraphEdge[]
 *     [
 *       {
 *         child_sha:    string;
 *         parent_sha:   string;
 *         child_idx:    number;      // index in assignments array
 *         parent_idx:   number;      // index in assignments array (-1 if dangling)
 *         child_lane:   number;
 *         parent_lane:  number;
 *         path:         string;      // SVG path-d string ready to use
 *         color_index:  number;      // inherits from child_lane for merges,
 *                                    // from parent_lane for fast-forwards
 *         dangling:     boolean;     // true if parent_sha not in input
 *       },
 *       ...
 *     ]
 *
 * The renderer feeds `path` directly into `<path d={edge.path} ... />`.
 *
 * ============================================================================
 * SVG COORDINATE SYSTEM
 * ============================================================================
 *
 * Right-handed, origin top-left. Y grows DOWNWARD (commits at the top of
 * the log are at low y).
 *
 *   COMMIT_RADIUS         = 4  (visible commits; filtered commits = 2)
 *   ROW_HEIGHT            = 22 (vertical distance between two commits)
 *   LANE_PITCH            = 16 (horizontal distance between two lanes)
 *   LANE_X_OFFSET         = 12 (left padding before lane 0)
 *
 *   centerOf(idx, lane) = {
 *     x: LANE_X_OFFSET + lane * LANE_PITCH,
 *     y: idx * ROW_HEIGHT + ROW_HEIGHT / 2
 *   }
 *
 * D39-2.4b: these constants live in `colorPalette.ts` alongside the
 * palette, or in a sibling `layoutConstants.ts`. Final placement is the
 * IMPL agent's call.
 *
 * ============================================================================
 * ALGORITHM — bezier curve math
 * ============================================================================
 *
 * For each (child_idx, parent_idx) edge:
 *
 *   const C = centerOf(child_idx, child_lane);
 *   const P = centerOf(parent_idx, parent_lane);
 *
 *   if (child_lane === parent_lane) {
 *     // Case 1: straight vertical
 *     path = `M ${C.x} ${C.y} L ${P.x} ${P.y}`;
 *   } else {
 *     // Case 2 / 3: S-curve. The control points are placed so the
 *     // curve leaves the child vertically and arrives at the parent
 *     // vertically. This is the standard "GitGraph S-curve" — see
 *     // mhutchie/vscode-git-graph rendering notes (algorithm only;
 *     // no code copied).
 *     const midY = (C.y + P.y) / 2;
 *     // First control point: directly below child by half a row
 *     // Second control point: directly above parent by half a row
 *     path =
 *       `M ${C.x} ${C.y} ` +
 *       `C ${C.x} ${midY}, ${P.x} ${midY}, ${P.x} ${P.y}`;
 *   }
 *
 * Edge color resolution (hotfix #994 supersedes #990):
 *   Every edge inherits the color of `max(child_lane, parent_lane)` —
 *   the side-branch lane, with lane 0 as the trunk.
 *
 *   The previous rule split: primary edges took the parent lane, merge
 *   edges took the child lane. That sounded principled but produced a
 *   visible inconsistency at fork points: a side-branch dot would render
 *   in its lane's color (e.g. green) but the fork edge curving back to
 *   the common-ancestor parent suddenly switched to the main lane's color
 *   (blue) — breaking the "one branch is one color end-to-end" mental
 *   model.
 *
 *   Surveyed industry implementations (2026-05-15 evidence collection):
 *
 *   - **VS Code Git Graph** (`mhutchie/vscode-git-graph`, `web/graph.ts`
 *     `Branch.draw`) attaches every line segment to the `Branch` object
 *     and strokes with `this.colour`, so a side branch's fork slant is
 *     stroked with the **child** branch's color.
 *   - **IntelliJ Platform / PyCharm** (`PrintElementPresentationManagerImpl.kt`
 *     `getColorId`) picks the edge endpoint with the larger `layoutIndex`
 *     for the color source. Side branches have larger indices than the
 *     trunk they fork off, so the side branch's color wins.
 *   - **GitLens / GitKraken** (`@gitkraken/gitkraken-components`, closed
 *     source — observational only) paints each branch end-to-end with
 *     one color including fork slants.
 *   - **gitk** (`git.git/gitk-git/gitk` `proc drawparentlinks`) is the
 *     only legacy outlier using parent color. SciStudio's old rule matched
 *     gitk.
 *
 *   The new rule (child-lane for every edge) aligns SciStudio with every
 *   modern git GUI and matches the user-stated mental model that "the
 *   green branch should stay green". The geometry still reads "the merged-
 *   in branch ENDS at the merge commit" because the dot renders on top of
 *   the edge — only the edge stroke color flipped.
 *
 *   **Refinement (hotfix #994, Phase 4a Test 6 follow-up)**: "child lane"
 *   is the wrong invariant for octopus / stash / merge topologies where
 *   the CHILD is on the trunk (lane 0) and parents fan out to side lanes.
 *   In those cases #990's rule made the fork-out curve take the trunk's
 *   color while the destination dot was a side-branch color, reintroducing
 *   the same mismatch under a different topology.
 *
 *   #994 replaces "child lane" with `max(child_lane, parent_lane)`. This:
 *
 *   1. Preserves #990's fix for the fork case: child on lane 1, parent on
 *      lane 0 → `max(1, 0) = 1` (side color).
 *   2. Fixes the stash/octopus case: child on lane 0, parent on lane 2 →
 *      `max(0, 2) = 2` (side color, matching the side-branch dot).
 *   3. Linear case (`child_lane === parent_lane`) is a no-op.
 *
 *   This matches IntelliJ's `PrintElementPresentationManagerImpl.getColorId`
 *   ("larger layoutIndex wins"; layoutIndex grows toward side branches).
 *
 * ============================================================================
 * COMPLEXITY
 * ============================================================================
 *
 *   Time:  O(C + E) where C = #commits, E = total parent links.
 *          For a linear history E = C-1. For a merge-heavy history
 *          E ~ 1.2 * C in practice.
 *   Space: O(E) for the output, plus a `Map<sha, idx>` of size C for
 *          O(1) parent-row lookup. Pre-built once at function entry.
 *
 * ============================================================================
 * EDGE CASES (cover in D39-2.4b tests)
 * ============================================================================
 *
 *   1. EMPTY INPUT
 *      → return [].
 *
 *   2. SINGLE COMMIT, NO PARENTS
 *      → return []. No edges to draw.
 *
 *   3. DANGLING PARENT (truncated `git log --max-count=N`)
 *      → parent SHA not in commits. Emit a GraphEdge with parent_idx=-1
 *        and `dangling: true`. The renderer draws a short downward stub
 *        from the child dot, fading out. `path` for dangling edges goes
 *        from C to (C.x, C.y + ROW_HEIGHT) — half a row beyond the last
 *        visible commit.
 *
 *   4. SELF-CYCLE (parent === child)
 *      → Impossible in real git; if input is malformed, skip the edge
 *        with a console.warn (defensive). Test: malformed fixture.
 *
 *   5. OCTOPUS MERGE
 *      → For parents[2..N-1], use the corresponding `merge_lanes[i]`
 *        as parent_lane. The IMPL must lookup parent_idx for each
 *        parent SHA separately, since each parent may live in a
 *        different row.
 *
 *   6. MERGE WITH PARENT IN SAME LANE
 *      → Rare but possible if a side-branch was rebased onto the
 *        primary lane. Treat as Case 1 (straight vertical). Don't
 *        special-case.
 *
 *   7. VERY LARGE LANE JUMP (lane delta > 5)
 *      → The S-curve mathematically still works, but visually a
 *        7-lane jump looks pinched. Renderer concern; the path
 *        string is correct. v1.1 may add a "shoulder" control point
 *        to flatten the curve. Out of scope for v1.
 *
 *   8. FILTERED COMMITS IN THE MIDDLE OF AN EDGE
 *      → The edge still flows THROUGH the filtered commit's row;
 *        nothing about the algorithm changes. The renderer dims the
 *        filtered commit's dot but keeps the edges flowing
 *        unchanged. (Per ADR §3.5c.)
 *
 * ============================================================================
 * TEST FIXTURE SKETCH (D39-2.4b will codify these)
 * ============================================================================
 *
 *   Fixture A — linear:
 *     [C3(lane 0)→C2, C2(lane 0)→C1, C1(lane 0)→]
 *     expected 2 edges, all straight vertical, all sharing color 0
 *
 *   Fixture B — fan-out and merge:
 *     C3(lane 0, parents [C2a, C2b], merge_lanes [1])
 *     C2a(lane 0, parents [C1])
 *     C2b(lane 1, parents [C1])
 *     C1(lane 0, parents [])
 *     expected 4 edges:
 *       C3→C2a  straight vertical, color 0    (primary)
 *       C3→C2b  bezier 0→1,      color 0    (merge — inherits child lane)
 *       C2a→C1  straight vertical, color 0    (primary)
 *       C2b→C1  bezier 1→0,      color 0    (primary — inherits parent lane)
 *
 *   Fixture C — dangling parent (truncated log):
 *     C2(lane 0, parents [<UNKNOWN_SHA>])
 *     C1 not present
 *     expected 1 edge: dangling=true, parent_idx=-1, path ends half a row
 *     past C2's center.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - Called once per `assignLanes` result (memoised on the assignments
 *     reference).
 *   - Output passed to `GraphSVG.tsx` which renders each `path` inside
 *     an `<svg>` group.
 *   - Color resolution uses `colorPalette.ts`.
 *
 * ============================================================================
 */

import type { GitCommit } from "../../../types/api";

import { LANE_PITCH, LANE_X_OFFSET, PALETTE, ROW_HEIGHT } from "./colorPalette";
import type { LaneAssignment } from "./laneAssign";

/**
 * A single edge in the rendered graph. The renderer drops `path` into
 * an `<svg><path d={...}/></svg>` element verbatim.
 */
export interface GraphEdge {
  child_sha: string;
  parent_sha: string;
  /** Row index of the child in the `assignments` array. */
  child_idx: number;
  /** Row index of the parent in the `assignments` array, or -1 if dangling. */
  parent_idx: number;
  child_lane: number;
  parent_lane: number;
  /** SVG path-d string; ready to use in `<path d={...}/>`. */
  path: string;
  /**
   * Palette index. Primary edges inherit from the parent's lane; merge
   * (fold-in) edges inherit from the child's lane. See the algorithm
   * docstring above for rationale.
   */
  color_index: number;
  /**
   * True when the parent SHA is not in the input commit list (a
   * truncated `git log` result). Renderer draws a short fading stub.
   */
  dangling: boolean;
}

/**
 * Compute the SVG edge geometry for a graph laid out by
 * {@link assignLanes}.
 *
 * Pure function: does not mutate inputs.
 *
 * D39-2.4a SKELETON: throws — body is filled in D39-2.4b.
 * D39-2.4b IMPL contract: implement bezier-curve math per the docstring
 * above. The constants (ROW_HEIGHT, LANE_PITCH, …) should live in a
 * single shared module to keep `GraphSVG.tsx` and this file aligned.
 *
 * @param assignments - From `assignLanes(commits)`.
 * @param commits     - The same commit array passed to `assignLanes`,
 *                      needed for parent-SHA → row-index resolution.
 * @returns Array of edges (one per parent link), suitable for SVG rendering.
 */
export function routeEdges(assignments: LaneAssignment[], commits: GitCommit[]): GraphEdge[] {
  if (assignments.length === 0) return [];

  const index = buildShaIndex(commits);
  const out: GraphEdge[] = [];

  for (let i = 0; i < commits.length; i++) {
    const child = commits[i];
    const childAssign = assignments[i];
    if (!childAssign || childAssign.sha !== child.sha) {
      // Defensive: the contract says assignments[i].sha === commits[i].sha.
      // Skip silently rather than crash.
      continue;
    }
    const childLane = childAssign.lane;

    for (let p = 0; p < child.parents.length; p++) {
      const parentSha = child.parents[p];
      if (parentSha === child.sha) {
        // Defensive: self-cycle never appears in real git output.
        console.warn(`edgeRouter: self-cycle on commit ${child.sha}; dropping edge.`);
        continue;
      }
      const parentIdx = index.has(parentSha) ? index.get(parentSha)! : -1;

      // Parent lane resolution:
      //   - For parents[0]: the lane the parent eventually lands in. We
      //     find it from `assignments[parentIdx].lane` when known. If the
      //     parent is truncated (dangling), use the child lane as a stub.
      //   - For parents[1..]: from `childAssign.merge_lanes[p-1]`. This is
      //     the lane the merge fold-in "comes in" on; the parent SHA gets
      //     written into `active_lanes[new_lane]` during assignLanes, so
      //     when the parent is later drawn it WILL land in `merge_lanes[p-1]`.
      let parentLane: number;
      if (p === 0) {
        if (parentIdx >= 0 && assignments[parentIdx]) {
          parentLane = assignments[parentIdx].lane;
        } else {
          parentLane = childLane;
        }
      } else {
        // merge_lanes is parallel to parents.slice(1)
        const ml = childAssign.merge_lanes[p - 1];
        parentLane = ml !== undefined ? ml : childLane;
      }

      const childCenter = centerOf(i, childLane);
      const parentCenter =
        parentIdx >= 0
          ? centerOf(parentIdx, parentLane)
          : // Dangling: stub goes half a row below the child.
            { x: childCenter.x, y: childCenter.y + ROW_HEIGHT / 2 };

      let path: string;
      if (childLane === parentLane || parentIdx < 0) {
        // Case 1 (or dangling stub): straight vertical.
        path = `M ${childCenter.x} ${childCenter.y} ` + `L ${parentCenter.x} ${parentCenter.y}`;
      } else if (parentLane > childLane) {
        // FORK-OUT (hotfix #1012 — supersedes #1005's mid-row corner):
        // The parent lives on a side lane to the right of the child.
        // This is a merge fold-in or new branch sprouting off the
        // child's lane. Place the corner at the CHILD's row so the
        // child dot draws on top of the corner — the horizontal
        // segment extends RIGHT from the child dot, then drops
        // vertically onto the parent's lane. Pre-#1012 the corner sat
        // at midY (the empty space between two dot rows), which made
        // the horizontal cross-cut OTHER lanes' vertical edges at
        // mid-row coordinates — visually it looked like dangling
        // lines because the horizontal segment overlapped main's
        // vertical line without a dot to anchor it.
        //   ●── (child, lane C)
        //         │
        //         │
        //         ●  (parent, lane P > C)
        path =
          `M ${childCenter.x} ${childCenter.y} ` +
          `L ${parentCenter.x} ${childCenter.y} ` +
          `L ${parentCenter.x} ${parentCenter.y}`;
      } else {
        // FORK-BACK (hotfix #1012): the child lives on a side lane,
        // the parent is on a lane to the left (typically main). This
        // is a side branch terminating into the trunk. Place the
        // corner at the PARENT's row so the parent dot draws on top —
        // the line first drops vertically on the child's lane, then
        // turns LEFT at the parent's row and ends inside the parent
        // dot.
        //         ●   (child, lane C)
        //         │
        //         │
        //   ●─────┘   (parent, lane P < C)
        path =
          `M ${childCenter.x} ${childCenter.y} ` +
          `L ${childCenter.x} ${parentCenter.y} ` +
          `L ${parentCenter.x} ${parentCenter.y}`;
      }

      // Hotfix #994: edge color follows the side-branch lane —
      // `max(childLane, parentLane)`. This matches IntelliJ /
      // vscode-git-graph: the OUTER branch's colour wins.
      //
      // Hotfix #1010: `color_index` is now per-branch (allocation order),
      // not `lane % PALETTE.length`. So we look up the actual palette
      // index from whichever endpoint sits on the larger lane, instead of
      // recomputing from the lane number. For dangling parents fall back
      // to the child's colour.
      let colorIndex: number;
      if (childLane >= parentLane || parentIdx < 0) {
        colorIndex = childAssign.color_index;
      } else {
        colorIndex = assignments[parentIdx].color_index;
      }
      colorIndex = ((colorIndex % PALETTE.length) + PALETTE.length) % PALETTE.length;

      out.push({
        child_sha: child.sha,
        parent_sha: parentSha,
        child_idx: i,
        parent_idx: parentIdx,
        child_lane: childLane,
        parent_lane: parentLane,
        path,
        color_index: colorIndex,
        dangling: parentIdx < 0,
      });
    }
  }

  return out;
}

/**
 * Coordinate helper exposed for the renderer (`GraphSVG.tsx`) so it can
 * place commit dots at the same anchor points the edges originate from.
 */
export function centerOf(idx: number, lane: number): { x: number; y: number } {
  return {
    x: LANE_X_OFFSET + lane * LANE_PITCH,
    y: idx * ROW_HEIGHT + ROW_HEIGHT / 2,
  };
}

/**
 * Pure helper exposed for tests: build a Map<sha, idx> for O(1)
 * parent-row lookup. Kept implemented (not a TODO) because it has no
 * dependency on the unimplemented bezier math and is independently
 * useful in tests.
 */
export function buildShaIndex(commits: GitCommit[]): Map<string, number> {
  const m = new Map<string, number>();
  for (let i = 0; i < commits.length; i++) {
    m.set(commits[i].sha, i);
  }
  return m;
}
