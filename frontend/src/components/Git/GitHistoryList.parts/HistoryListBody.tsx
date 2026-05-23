/**
 * The list-view body of GitHistoryList — loading, empty, and rows.
 * Extracted in #1413 so the main component fits under the 150-line limit.
 */
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import type { GitCommit } from "../../../types/api";
import { HistoryRow } from "./HistoryRow";

export interface HistoryListBodyProps {
  loading: boolean;
  commits: GitCommit[] | null;
  visibleCommits: GitCommit[];
  selectedCommit: GitCommit | null;
  onSelect: (commit: GitCommit) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLLIElement>, commit: GitCommit) => void;
  onDiff: (commit: GitCommit) => void;
  onRestore: (commit: GitCommit) => void;
}

export function HistoryListBody({
  loading,
  commits,
  visibleCommits,
  selectedCommit,
  onSelect,
  onKeyDown,
  onDiff,
  onRestore,
}: HistoryListBodyProps) {
  if (loading || commits === null) {
    return (
      <div data-testid="git-history-loading" className="px-3 py-4 text-xs text-stone-500">
        Loading commit history…
      </div>
    );
  }
  if (visibleCommits.length === 0) {
    if (commits.length === 0) {
      return (
        <div data-testid="git-history-empty" className="px-3 py-4 text-xs text-stone-500">
          No commits yet on this branch.
        </div>
      );
    }
    return (
      <div
        data-testid="git-history-empty-after-filter"
        className="px-3 py-4 text-xs text-stone-500"
      >
        Only auto/agent commits exist on this branch. Switch the filter to All to see them.
      </div>
    );
  }
  return (
    <ul data-testid="git-history-rows" role="list" className="min-h-0 flex-1 overflow-y-auto">
      {visibleCommits.map((commit) => (
        <HistoryRow
          key={commit.sha}
          commit={commit}
          isSelected={selectedCommit?.sha === commit.sha}
          onSelect={onSelect}
          onKeyDown={onKeyDown}
          onDiff={onDiff}
          onRestore={onRestore}
        />
      ))}
    </ul>
  );
}
