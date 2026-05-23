/**
 * ADR-039 §3.5b — branch graph panel. Extracted from GitHistoryList in
 * #1413 so the parent file stays small.
 */
import type { JSX } from "react";

import { GraphSVG } from "../GitGraph/GraphSVG";
import { useGraphData } from "../GitGraph/integration";
import { useGraphInteractions } from "../GitGraph/interactions";

export interface GitGraphPaneProps {
  onCommitClick?: (sha: string) => void;
}

export function GitGraphPane({ onCommitClick }: GitGraphPaneProps = {}): JSX.Element {
  const data = useGraphData();
  const interactions = useGraphInteractions(data.commits.length, onCommitClick, data.commits);

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
