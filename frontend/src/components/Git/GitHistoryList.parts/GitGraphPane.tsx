/**
 * ADR-039 §3.5b — branch graph panel. Extracted from GitHistoryList in
 * #1413 so the parent file stays small.
 */
import { useEffect } from "react";
import type { JSX } from "react";

import { GraphSVG } from "../GitGraph/GraphSVG";
import { ROW_HEIGHT } from "../GitGraph/colorPalette";
import { useGraphData } from "../GitGraph/integration";
import { useGraphInteractions } from "../GitGraph/interactions";

export interface GitGraphPaneProps {
  onCommitClick?: (sha: string) => void;
}

export function GitGraphPane({ onCommitClick }: GitGraphPaneProps = {}): JSX.Element {
  const data = useGraphData();
  const interactions = useGraphInteractions(data.commits.length, onCommitClick, data.commits);
  const { focusedRow, scrollContainerRef } = interactions;

  // ADR-039 Addendum 1 §11.3 audit P3-2 (#1394): clicking a graph dot (or
  // keyboard-navigating) sets `focusedRow`, but if the matching row is
  // scrolled out of the virtualization window the user sees no effect.
  // Scroll the focused row into view (centered) whenever it changes.
  //
  // Rows are absolutely positioned at `idx * ROW_HEIGHT` (see GraphSVG /
  // GraphLabels), so we scroll the container programmatically rather than
  // relying on a per-row DOM node, which may not be mounted while
  // virtualized out.
  useEffect(() => {
    if (focusedRow === null) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    const rowTop = focusedRow * ROW_HEIGHT;
    const rowCenter = rowTop + ROW_HEIGHT / 2;
    const target = rowCenter - el.clientHeight / 2;
    const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
    const next = Math.max(0, Math.min(target, maxScroll));
    el.scrollTo({ top: next, behavior: "smooth" });
  }, [focusedRow, scrollContainerRef]);

  if (data.loading) {
    return (
      <div
        data-testid="git-graph-loading"
        className="flex flex-1 items-center justify-center px-3 py-4 text-xs text-stone-500"
      >
        Loading commit graph…
      </div>
    );
  }
  if (data.commits.length === 0) {
    return (
      <div
        data-testid="git-graph-empty"
        className="flex flex-1 items-center justify-center px-3 py-4 text-xs text-stone-500"
      >
        No commits to display.
      </div>
    );
  }
  return (
    <div
      ref={interactions.scrollContainerRef}
      data-testid="git-graph-scroll"
      className="min-h-0 flex-1 overflow-y-auto outline-none"
      tabIndex={0}
      onKeyDown={interactions.onCommitDotKeyDown}
    >
      <GraphSVG
        assignments={data.assignments}
        edges={data.edges}
        commits={data.commits}
        onCommitClick={interactions.onCommitClick}
        visibleRange={interactions.visibleRange}
        hoveredIdx={null}
        focusedIdx={interactions.focusedRow}
      />
    </div>
  );
}
