/**
 * ADR-039 §3.5b / §3.5c / §6 Phase 3 — Branch-graph slice integration
 * (SKELETON).
 *
 * Status: SKELETON. Throws on the main entry point. D39-2.4b fills it in.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Glue between `gitSlice` and the renderless graph primitives
 * (`laneAssign`, `edgeRouter`). Owns:
 *
 *   1. SELECT the right commit list from `gitSlice.logCache`. The graph
 *      view shows ALL branches; the key is the "<all>" key in
 *      `logCache` (see `gitSlice.ts:LOG_ALL_KEY`).
 *
 *   2. APPLY the historyFilter (§3.5c) to derive `filtered_out` per row
 *      WITHOUT removing commits from the topology. The graph dims
 *      filtered commits to small grey dots but their edges still flow.
 *
 *   3. MEMOISE the `assignLanes` → `routeEdges` chain on commit-list
 *      reference equality. Re-renders that don't change the cache
 *      should return the same `{ assignments, edges }` references.
 *
 *   4. INVALIDATE on `git.head_changed` — handled inside `gitSlice`
 *      already (it clears `logCache`), so this module just needs to
 *      react to that clearing.
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   Consumes (read-only) from `useAppStore()`:
 *     - logCache["<all>"]: GitCommit[] | undefined
 *     - historyFilter: GitHistoryFilter
 *
 * ============================================================================
 * OUTPUT
 * ============================================================================
 *
 *   useGraphData(): {
 *     commits:      GitCommit[];
 *     assignments:  LaneAssignment[];
 *     edges:        GraphEdge[];
 *     loading:      boolean;
 *     error:        string | null;
 *   }
 *
 *   `loading` is true when logCache["<all>"] is undefined and a refresh
 *   is in flight. `error` mirrors `gitSlice.lastError` for graph-relevant
 *   errors only.
 *
 * ============================================================================
 * MEMOISATION CONTRACT
 * ============================================================================
 *
 * The memo key is `(logCacheAllRef, historyFilter)`. As long as the
 * commit array reference is unchanged AND the filter is unchanged,
 * the same `{ assignments, edges }` object is returned. This is the
 * referential-equality optimisation that lets `GraphSVG.tsx` skip
 * re-renders during scroll / hover.
 *
 * D39-2.4b: implement with `useMemo`. If profiling shows the
 * assign+route compute is the bottleneck, move to a Zustand-selector
 * with `shallow` equality.
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. logCache["<all>"] is missing → dispatch `loadLog()` (no branch
 *      arg → "<all>") and return loading:true. After the fetch resolves,
 *      the slice updates and the consumer re-renders.
 *   2. Empty repo (no commits) → return `{commits:[], assignments:[],
 *      edges:[], loading:false, error:null}`. GraphSVG renders an empty
 *      message.
 *   3. Filter changes mid-render → memo cache miss; recompute. The
 *      assignment ALGORITHM does NOT depend on filter (lanes are
 *      topology-only), only the `filtered_out` boolean flips. An IMPL
 *      optimization (D39-2.4b discretion): cache assignments separately
 *      and only re-derive `filtered_out` on filter change.
 *   4. `lastError` set by a `loadLog` failure → surface it in `error`
 *      so the panel can render an error state. Clear on next successful
 *      load.
 *
 * ============================================================================
 * INTEGRATION
 * ============================================================================
 *
 *   - Called by the future GitGraphView panel (D39-2.4b creates this; not
 *     in the skeleton owned-files list).
 *   - Reads from `gitSlice` only — no other slices.
 *
 * ============================================================================
 */

import type { GitCommit } from "../../../types/api";

import type { GraphEdge } from "./edgeRouter";
import type { LaneAssignment } from "./laneAssign";

/**
 * Return shape of {@link useGraphData}.
 */
export interface GraphData {
  commits: GitCommit[];
  assignments: LaneAssignment[];
  edges: GraphEdge[];
  loading: boolean;
  error: string | null;
}

/**
 * React hook: pull commits from gitSlice, run them through
 * `assignLanes` + `routeEdges`, return memoised result.
 *
 * D39-2.4a SKELETON: throws.
 * D39-2.4b IMPL: implement per the docstring above. Trigger
 * `loadLog()` when cache misses.
 */
export function useGraphData(): GraphData {
  throw new Error(
    "TODO: D39-2.4b — implement useGraphData per the docstring above. " +
      "Pull logCache['<all>'] + historyFilter from gitSlice, apply " +
      "selectVisibleCommits to derive `filtered_out`, memoise " +
      "assignLanes+routeEdges on (commitsRef, historyFilter).",
  );
}
