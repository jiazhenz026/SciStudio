/**
 * Header toolbar for GitHistoryList (#1413).
 *
 * Carries the filter dropdown, Refresh button, top-level Diff/Restore
 * buttons (#1400), and Graph/List view toggle (#1000).
 */
import type { GitCommit, GitHistoryFilter } from "../../../types/api";

const FILTER_OPTIONS: { value: GitHistoryFilter; label: string }[] = [
  { value: "manual", label: "Manual milestones" },
  { value: "all", label: "All (incl. auto)" },
  { value: "auto", label: "Auto only (debug)" },
  { value: "agent", label: "Agent only (debug)" },
];

export interface HistoryToolbarProps {
  historyFilter: GitHistoryFilter;
  onFilterChange: (next: GitHistoryFilter) => void;
  onRefresh: () => void;
  viewMode: "list" | "graph";
  onViewModeChange: (next: "list" | "graph") => void;
  selectedCommit: GitCommit | null;
  onDiffSelected: () => void;
  onRestoreSelected: () => void;
}

export function HistoryToolbar({
  historyFilter,
  onFilterChange,
  onRefresh,
  viewMode,
  onViewModeChange,
  selectedCommit,
  onDiffSelected,
  onRestoreSelected,
}: HistoryToolbarProps) {
  return (
    <div className="flex items-center gap-2 border-b border-stone-200 px-3 py-2">
      <label htmlFor="git-history-filter-select" className="sr-only">
        Filter commits
      </label>
      <select
        id="git-history-filter-select"
        data-testid="git-history-filter"
        value={historyFilter}
        onChange={(e) => onFilterChange(e.target.value as GitHistoryFilter)}
        className="rounded border border-stone-300 px-2 py-1 text-xs"
      >
        {FILTER_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        data-testid="git-history-refresh"
        onClick={onRefresh}
        className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
      >
        Refresh
      </button>
      <button
        type="button"
        data-testid="git-history-toolbar-diff"
        onClick={onDiffSelected}
        disabled={selectedCommit === null}
        title={
          selectedCommit
            ? `Diff ${selectedCommit.short_sha} against its parent.`
            : "Select a commit (click a graph dot or a list row) to enable."
        }
        className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Diff
      </button>
      <button
        type="button"
        data-testid="git-history-toolbar-restore"
        onClick={onRestoreSelected}
        disabled={selectedCommit === null}
        title={
          selectedCommit
            ? `Soft-restore files from ${selectedCommit.short_sha} into the working tree.`
            : "Select a commit (click a graph dot or a list row) to enable."
        }
        className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Restore
      </button>
      {selectedCommit && (
        <span
          data-testid="git-history-toolbar-selection"
          className="text-[10px] text-stone-500"
          title={`Selected commit: ${selectedCommit.sha}`}
        >
          ({selectedCommit.short_sha})
        </span>
      )}
      <div
        data-testid="git-history-view-toggle"
        className="ml-auto flex gap-1 rounded border border-stone-300 p-0.5 text-xs"
      >
        <button
          type="button"
          data-testid="git-history-view-graph"
          aria-pressed={viewMode === "graph"}
          onClick={() => onViewModeChange("graph")}
          className={`rounded px-2 py-0.5 ${
            viewMode === "graph" ? "bg-stone-200" : "hover:bg-stone-100"
          }`}
        >
          Graph
        </button>
        <button
          type="button"
          data-testid="git-history-view-list"
          aria-pressed={viewMode === "list"}
          onClick={() => onViewModeChange("list")}
          className={`rounded px-2 py-0.5 ${
            viewMode === "list" ? "bg-stone-200" : "hover:bg-stone-100"
          }`}
        >
          List
        </button>
      </div>
    </div>
  );
}
