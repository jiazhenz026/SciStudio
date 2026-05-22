/**
 * ADR-039 §3.5b / §6 Phase 3 — Branch-graph interactions.
 *
 * D39-2.4b IMPL: lightweight hook encapsulating hover state, focus state,
 * keyboard navigation, and a manual scroll-driven virtualization window.
 *
 * Virtualization decision: the skeleton docstring referenced
 * `@tanstack/react-virtual`, but that package is NOT in
 * `frontend/package.json` and cascade hygiene rules forbid adding new
 * dependencies in a worktree (see `00-common-boilerplate.md` §2). We
 * implement a manual window — given the container's scroll position and
 * height, compute the inclusive-exclusive row range that is currently
 * visible (plus an overscan of 10 rows on each side). This is sufficient
 * for the ADR §3.5b performance target (1000 commits without
 * virtualization, 10k with overscan trimming).
 *
 * ADR-039 Addendum 1 §11.3 (issue #1355): the graph commit-dot click no
 * longer opens `GitDiffModal` directly. Instead it sets the focused-row
 * index and the user activates `[Diff]` / `[Restore]` from the list
 * view's inline per-row buttons (Tab back to list view if needed). Enter
 * / Space on the focused dot is similarly a no-op for opening the
 * modal; previously it would activate the diff.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";

import { useAppStore } from "../../../store";
import type { GitCommit } from "../../../types/api";

import { ROW_HEIGHT } from "./colorPalette";

export interface GraphInteractionsApi {
  /** Inclusive-exclusive row window driven by scroll position. */
  visibleRange: [number, number];
  /** Currently focused row index (keyboard navigation), null if none. */
  focusedRow: number | null;
  setFocusedRow: (idx: number | null) => void;
  /** Currently hovered commit SHA (for the floating tooltip), null if none. */
  hoveredSha: string | null;
  setHoveredSha: (sha: string | null) => void;
  /**
   * Graph commit-dot click handler. ADR-039 Addendum 1 §11.3 (issue
   * #1355): this no longer opens GitDiffModal. It clears any stale
   * `lastError`, sets the focused-row index to the clicked commit, and
   * invokes `onOpenDiff` only if a consumer explicitly supplied one
   * (call sites in scope of #1355 pass `undefined`).
   */
  onCommitClick: (sha: string) => void;
  /**
   * Arrow-up / arrow-down moves focusedRow. Enter triggers click-equiv
   * on the currently focused row.
   */
  onCommitDotKeyDown: (event: React.KeyboardEvent<Element>) => void;
  /** Ref the consumer attaches to the scrollable container. */
  scrollContainerRef: React.RefObject<HTMLDivElement>;
}

/**
 * Click handler factory — exposed for tests and for callers that want to
 * dispatch a diff modal open WITHOUT mounting the full hook.
 *
 * Returns a (sha) → void that sets gitSlice.lastError to null and
 * delegates to the caller's `onOpen` callback so the panel can mount its
 * `GitDiffModal`.
 */
export function makeCommitClickHandler(onOpen: (sha: string) => void): (sha: string) => void {
  return (sha: string) => {
    if (!sha) return;
    onOpen(sha);
  };
}

/**
 * Hook factory. Driven by container scroll position + an overscan window.
 *
 * @param totalRows - The number of rows the graph would render if nothing
 *                    were virtualized.
 * @param onOpenDiff - Callback fired by `onCommitClick` so the consumer
 *                     panel can open its `GitDiffModal`.
 */
export function useGraphInteractions(
  totalRows: number,
  onOpenDiff?: (sha: string) => void,
  commits?: GitCommit[],
): GraphInteractionsApi {
  const setLastError = useAppStore((s) => s.setLastError);

  const [focusedRow, setFocusedRow] = useState<number | null>(null);
  const [hoveredSha, setHoveredSha] = useState<string | null>(null);

  // Keep `commits` in a ref so the keyboard handler always sees the
  // latest array without forcing the callback to recreate on every
  // render.
  const commitsRef = useRef<GitCommit[] | undefined>(commits);
  commitsRef.current = commits;

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  // Initial range covers ~80 rows (a typical desktop viewport at ROW_HEIGHT=22).
  const [visibleRange, setVisibleRange] = useState<[number, number]>(() => [
    0,
    Math.min(totalRows, 80),
  ]);

  const OVERSCAN = 10;

  // Recompute the visible range whenever the container scrolls or the
  // total row count changes.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) {
      // No container → render everything (test environment, etc.).
      setVisibleRange([0, totalRows]);
      return;
    }
    const compute = () => {
      const top = el.scrollTop;
      const h = el.clientHeight;
      const firstVisible = Math.max(0, Math.floor(top / ROW_HEIGHT) - OVERSCAN);
      const lastVisible = Math.min(totalRows, Math.ceil((top + h) / ROW_HEIGHT) + OVERSCAN);
      setVisibleRange([firstVisible, lastVisible]);
    };
    compute();
    el.addEventListener("scroll", compute, { passive: true });
    return () => {
      el.removeEventListener("scroll", compute);
    };
  }, [totalRows]);

  const onCommitClick = useCallback(
    (sha: string) => {
      if (!sha) return;
      setLastError(null);
      // ADR-039 Addendum 1 §11.3 (issue #1355): graph dot click sets
      // focus on the matching commit's row but no longer opens
      // GitDiffModal. The diff is reachable via the per-row `[Diff]`
      // button after switching to list view, or via the `d` hotkey on
      // the focused list row.
      const commits = commitsRef.current;
      if (commits) {
        const idx = commits.findIndex((c) => c.sha === sha);
        if (idx >= 0) setFocusedRow(idx);
      }
      onOpenDiff?.(sha);
    },
    [onOpenDiff, setLastError],
  );

  const onCommitDotKeyDown = useCallback(
    (event: React.KeyboardEvent<Element>) => {
      if (totalRows === 0) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setFocusedRow((cur) => {
          const next = cur === null ? 0 : Math.min(totalRows - 1, cur + 1);
          return next;
        });
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setFocusedRow((cur) => {
          const next = cur === null ? 0 : Math.max(0, cur - 1);
          return next;
        });
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        // ADR-039 Addendum 1 §11.3 (issue #1355): Enter / Space on the
        // focused graph dot no longer opens GitDiffModal. The previous
        // PR #952 behavior is superseded — the diff is now an opt-in
        // action available from the list view's `[Diff]` button or the
        // `d` hotkey on a focused list row. We preserve `setLastError`
        // for consistency with prior behavior and still forward to a
        // caller-supplied `onOpenDiff` (in #1355 scope the consumer
        // passes `undefined`, which means this becomes a no-op).
        setFocusedRow((cur) => {
          if (cur === null) return cur;
          const commits = commitsRef.current;
          const commit = commits && commits[cur];
          if (commit) {
            setLastError(null);
            onOpenDiff?.(commit.sha);
          }
          return cur;
        });
      }
    },
    [totalRows, onOpenDiff, setLastError],
  );

  return {
    visibleRange,
    focusedRow,
    setFocusedRow,
    hoveredSha,
    setHoveredSha,
    onCommitClick,
    onCommitDotKeyDown,
    scrollContainerRef: scrollContainerRef as React.RefObject<HTMLDivElement>,
  };
}
