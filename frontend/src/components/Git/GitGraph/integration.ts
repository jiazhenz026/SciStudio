/**
 * ADR-039 §3.5b / §3.5c / §6 Phase 3 — Branch-graph slice integration.
 *
 * D39-2.4b IMPL: implements `useGraphData()` against `gitSlice` with
 * referential-equality memoisation on `(commits, historyFilter)`. Pulls
 * commits from `logCache["<all>"]`, applies the §3.5c filter to derive
 * `filtered_out` per row WITHOUT removing commits from the topology,
 * memoises `assignLanes` + `routeEdges` so re-renders skip recompute.
 */
import { useEffect, useMemo } from "react";

import { useAppStore } from "../../../store";
import { classifyPrefix } from "../../../store/gitSlice";
import type { GitCommit, GitHistoryFilter } from "../../../types/api";

import { type GraphEdge, routeEdges } from "./edgeRouter";
import { assignLanes, type LaneAssignment } from "./laneAssign";

const LOG_ALL_KEY = "<all>";

/** Return shape of {@link useGraphData}. */
export interface GraphData {
  commits: GitCommit[];
  assignments: LaneAssignment[];
  edges: GraphEdge[];
  loading: boolean;
  error: string | null;
}

/**
 * Apply the history filter to derive the `filtered_out` boolean per row.
 * The topology is preserved (the assignment input is the FULL commit
 * list); only the rendering hint flips.
 */
function applyFilter(
  assignments: LaneAssignment[],
  commits: GitCommit[],
  filter: GitHistoryFilter,
): LaneAssignment[] {
  if (filter === "all") {
    // All visible → no filtered_out flips needed; keep refs if possible.
    return assignments.every((a) => a.filtered_out === false)
      ? assignments
      : assignments.map((a) => ({ ...a, filtered_out: false }));
  }
  return assignments.map((a, i) => {
    const commit = commits[i];
    if (!commit) return a;
    const prefix = classifyPrefix(commit.subject);
    let visible: boolean;
    if (filter === "manual") visible = prefix === "user";
    else if (filter === "auto") visible = prefix === "auto";
    else if (filter === "agent") visible = prefix === "agent";
    else visible = true;
    const filtered = !visible;
    if (a.filtered_out === filtered) return a;
    return { ...a, filtered_out: filtered };
  });
}

/**
 * React hook: pull commits from gitSlice, run them through
 * `assignLanes` + `routeEdges`, return memoised result.
 *
 * Triggers `loadLog()` on first call when the `<all>` cache is missing.
 */
export function useGraphData(): GraphData {
  const commitsRaw = useAppStore((s) => s.logCache[LOG_ALL_KEY] ?? null);
  const loadingFlag = useAppStore((s) => s.logLoading[LOG_ALL_KEY] ?? false);
  const historyFilter = useAppStore((s) => s.historyFilter);
  const lastError = useAppStore((s) => s.lastError);
  const loadLog = useAppStore((s) => s.loadLog);

  useEffect(() => {
    if (commitsRaw === null && !loadingFlag) {
      // Fire-and-forget; the slice will populate the cache and trigger
      // a re-render.
      void loadLog();
    }
  }, [commitsRaw, loadingFlag, loadLog]);

  // Memo: only recompute when the commits-array REFERENCE changes.
  const baseAssignments = useMemo(() => {
    if (commitsRaw === null) return [];
    return assignLanes(commitsRaw);
  }, [commitsRaw]);

  const baseEdges = useMemo(() => {
    if (commitsRaw === null || baseAssignments.length === 0) return [];
    return routeEdges(baseAssignments, commitsRaw);
  }, [commitsRaw, baseAssignments]);

  // Filter pass: cheap (O(C)); doesn't recompute lanes/edges.
  const filteredAssignments = useMemo(() => {
    if (commitsRaw === null) return [];
    return applyFilter(baseAssignments, commitsRaw, historyFilter);
  }, [baseAssignments, commitsRaw, historyFilter]);

  return {
    commits: commitsRaw ?? [],
    assignments: filteredAssignments,
    edges: baseEdges,
    loading: commitsRaw === null && loadingFlag,
    error: lastError,
  };
}
