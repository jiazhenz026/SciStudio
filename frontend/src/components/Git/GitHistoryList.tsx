/**
 * ADR-039 §3.5 + §3.4 + §3.4a + §3.5c — GitHistoryList.
 *
 * Reverse-chronological commit list with a header-level filter dropdown
 * (Manual / All / Auto / Agent). Each row exposes inline `[Diff]` and
 * `[Restore]` buttons.
 *
 * ADR-039 Addendum 1 §11.3 (issue #1355): the previous row-click →
 * `GitDiffModal` shortcut surprised users who clicked a row to "select"
 * it. The whole-row click is now a focus-only affordance; the destructive
 * (or modal-heavy) action is opt-in via the per-row `[Diff]` and
 * `[Restore]` buttons. The `d` / `r` hotkeys on a focused row mirror the
 * buttons.
 */
import { useCallback, useEffect, useState } from "react";
import type { JSX, KeyboardEvent as ReactKeyboardEvent } from "react";

import { useAppStore } from "../../store";
import type { GitCommit, GitHistoryFilter } from "../../types/api";
import { classifyPrefix, selectVisibleCommits } from "../../store/gitSlice";
import { GitDiffModal } from "./GitDiffModal";
import { GraphSVG } from "./GitGraph/GraphSVG";
import { useGraphData } from "./GitGraph/integration";
import { useGraphInteractions } from "./GitGraph/interactions";

const PREFIX_ICON: Record<string, string> = {
  auto: "·",
  agent: "🤖",
  user: "👤",
};

const FILTER_OPTIONS: { value: GitHistoryFilter; label: string }[] = [
  { value: "manual", label: "Manual milestones" },
  { value: "all", label: "All (incl. auto)" },
  { value: "auto", label: "Auto only (debug)" },
  { value: "agent", label: "Agent only (debug)" },
];

export interface GitHistoryListProps {
  branch?: string;
  onCommitClick?: (commit: GitCommit) => void;
  onRestoreClick?: (commit: GitCommit) => void;
  showFilterDropdown?: boolean;
  className?: string;
}

export function GitHistoryList(props: GitHistoryListProps): JSX.Element {
  const { branch, onCommitClick, onRestoreClick, showFilterDropdown = true, className } = props;

  const logCache = useAppStore((s) => s.logCache);
  const logLoading = useAppStore((s) => s.logLoading);
  const historyFilter = useAppStore((s) => s.historyFilter);
  const setHistoryFilter = useAppStore((s) => s.setHistoryFilter);
  const loadLog = useAppStore((s) => s.loadLog);
  const restore = useAppStore((s) => s.restore);

  const key = branch && branch.length > 0 ? branch : "<all>";
  const commits = logCache[key] ?? null;
  const loading = logLoading[key] === true;

  // Internal diff modal state — opened by default if onCommitClick not given.
  const [diffOpen, setDiffOpen] = useState<{ from: string; to?: string } | null>(null);
  // ADR-039 §3.5b / D39-2.4b — view toggle: list vs branch graph.
  // Hotfix #1000: default Git tab view is Graph (per Phase 4a feedback —
  // graph is the primary affordance; List is a fallback for plain text).
  const [viewMode, setViewMode] = useState<"list" | "graph">("graph");

  useEffect(() => {
    if (commits === null && !loading) {
      void loadLog(branch);
    }
  }, [branch, commits, loading, loadLog]);

  // ADR-039 Addendum 1 §11.3 (issue #1355): opening the diff modal is no
  // longer driven by row clicks. Both the per-row `[Diff]` button and the
  // `d` hotkey go through `handleDiff`. The optional `onCommitClick` prop
  // is preserved so embedders that still want a row-level selection
  // callback (notification, telemetry) can opt in without re-introducing
  // the modal.
  const handleDiff = useCallback(
    (commit: GitCommit) => {
      if (onCommitClick) {
        onCommitClick(commit);
        return;
      }
      // Codex P2-B on PR #940: for a root commit (no parents), comparing
      // `from=commit.sha` to working tree (the backend default for `to`)
      // shows the inverse of the initial state rather than the commit's
      // own patch. Use the empty-tree hash (well-known git constant) as
      // the parent so the initial commit displays as additions of every
      // file.
      const parent = commit.parents[0];
      if (parent) {
        setDiffOpen({ from: parent, to: commit.sha });
      } else {
        const EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
        setDiffOpen({ from: EMPTY_TREE_SHA, to: commit.sha });
      }
    },
    [onCommitClick],
  );

  const handleRestore = useCallback(
    (commit: GitCommit) => {
      if (onRestoreClick) {
        onRestoreClick(commit);
        return;
      }
      const ok = window.confirm(
        `Restore files from commit ${commit.short_sha}?\n\n${commit.subject}\n\nThis will overwrite the working tree.`,
      );
      if (!ok) return;
      void restore(commit.sha).catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[GitHistoryList] restore failed:", err);
      });
    },
    [onRestoreClick, restore],
  );

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLLIElement>, commit: GitCommit) => {
      // ADR-039 Addendum 1 §11.3 (issue #1355): Enter no longer opens the
      // diff modal. The row remains keyboard-focusable so its inline
      // buttons are Tab-reachable, but activation of the row itself is a
      // no-op. `d` opens the diff, `r` triggers the restore confirm —
      // mirroring the per-row buttons.
      if (event.key.toLowerCase() === "d") {
        event.preventDefault();
        handleDiff(commit);
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        handleRestore(commit);
      }
    },
    [handleDiff, handleRestore],
  );

  const visibleCommits = commits ? selectVisibleCommits(commits, historyFilter) : [];

  return (
    <div
      data-testid="git-history-list"
      className={`flex h-full flex-col ${className ?? ""}`}
    >
      {showFilterDropdown && (
        <div className="flex items-center gap-2 border-b border-stone-200 px-3 py-2">
          <label htmlFor="git-history-filter-select" className="sr-only">
            Filter commits
          </label>
          <select
            id="git-history-filter-select"
            data-testid="git-history-filter"
            value={historyFilter}
            onChange={(e) => setHistoryFilter(e.target.value as GitHistoryFilter)}
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
            onClick={() => void loadLog(branch)}
            className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
          >
            Refresh
          </button>
          {/*
            Hotfix #1000: Graph is the default and renders FIRST in the
            toggle (left side) — matches "graph is the primary affordance"
            feedback. List moves to the right as the fallback.
          */}
          <div
            data-testid="git-history-view-toggle"
            className="ml-auto flex gap-1 rounded border border-stone-300 p-0.5 text-xs"
          >
            <button
              type="button"
              data-testid="git-history-view-graph"
              aria-pressed={viewMode === "graph"}
              onClick={() => setViewMode("graph")}
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
              onClick={() => setViewMode("list")}
              className={`rounded px-2 py-0.5 ${
                viewMode === "list" ? "bg-stone-200" : "hover:bg-stone-100"
              }`}
            >
              List
            </button>
          </div>
        </div>
      )}

      {viewMode === "graph" ? (
        // ADR-039 Addendum 1 §11.3 (issue #1355): the graph commit-dot
        // click no longer opens GitDiffModal — the diff is now an
        // opt-in action exposed by the per-row `[Diff]` button in the
        // List view. Passing `undefined` here means the `interactions`
        // hook still updates focus/lastError but does not open the
        // modal.
        <GitGraphPane />
      ) : loading ? (
        <div
          data-testid="git-history-loading"
          className="px-3 py-4 text-xs text-stone-500"
        >
          Loading commit history…
        </div>
      ) : commits === null ? (
        <div
          data-testid="git-history-loading"
          className="px-3 py-4 text-xs text-stone-500"
        >
          Loading commit history…
        </div>
      ) : visibleCommits.length === 0 ? (
        commits.length === 0 ? (
          <div
            data-testid="git-history-empty"
            className="px-3 py-4 text-xs text-stone-500"
          >
            No commits yet on this branch.
          </div>
        ) : (
          <div
            data-testid="git-history-empty-after-filter"
            className="px-3 py-4 text-xs text-stone-500"
          >
            Only auto/agent commits exist on this branch. Switch the filter to All to see them.
          </div>
        )
      ) : (
        <ul
          data-testid="git-history-rows"
          role="list"
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {visibleCommits.map((commit) => {
            const prefix = classifyPrefix(commit.subject);
            // ADR-039 Addendum 1 §11.3 (issue #1355): the row is no
            // longer a click-to-open-diff button. It stays focusable
            // (Tab + arrow keys) so the per-row `[Diff]` / `[Restore]`
            // buttons and the `d` / `r` hotkeys are reachable, but
            // activating the row itself does nothing.
            return (
              <li
                key={commit.sha}
                data-testid={`git-history-row-${commit.short_sha}`}
                data-commit-prefix={prefix}
                tabIndex={0}
                onKeyDown={(e) => onKeyDown(e, commit)}
                className="flex items-center gap-2 border-b border-stone-100 px-3 py-2 text-xs hover:bg-stone-50 focus:bg-stone-100 focus:outline-none"
              >
                <span data-testid="git-history-row-icon" aria-hidden>
                  {PREFIX_ICON[prefix] ?? "·"}
                </span>
                <code
                  data-testid="git-history-row-short-sha"
                  className="font-mono text-stone-500"
                >
                  {commit.short_sha}
                </code>
                <span
                  data-testid="git-history-row-subject"
                  className="flex-1 truncate text-ink"
                  title={commit.subject}
                >
                  {commit.subject}
                </span>
                <span
                  data-testid="git-history-row-author"
                  className="hidden text-stone-500 sm:inline"
                >
                  {commit.author_name}
                </span>
                <time
                  data-testid="git-history-row-date"
                  dateTime={commit.author_date}
                  className="text-stone-400"
                >
                  {new Date(commit.author_date).toLocaleString()}
                </time>
                <button
                  type="button"
                  data-testid={`git-history-row-diff-${commit.short_sha}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDiff(commit);
                  }}
                  title="Show diff against parent commit."
                  className="ml-2 rounded border border-stone-300 px-2 py-0.5 text-[10px] hover:bg-stone-100"
                >
                  Diff
                </button>
                <button
                  type="button"
                  data-testid={`git-history-row-restore-${commit.short_sha}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRestore(commit);
                  }}
                  title="Soft-restore: copy this commit's files into the working tree without moving HEAD."
                  className="ml-1 rounded border border-stone-300 px-2 py-0.5 text-[10px] hover:bg-stone-100"
                >
                  Restore this version
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {diffOpen && (
        <GitDiffModal
          open={true}
          from={diffOpen.from}
          to={diffOpen.to}
          onClose={() => setDiffOpen(null)}
        />
      )}
    </div>
  );
}

/**
 * ADR-039 §3.5b — branch graph panel.
 *
 * Mounted by `GitHistoryList` when the user toggles to "Graph" mode.
 * Pulls assignments / edges via `useGraphData()` and wires
 * `useGraphInteractions` for scroll-driven virtualization + keyboard
 * navigation.
 *
 * ADR-039 Addendum 1 §11.3 (issue #1355): `onCommitClick` is now
 * optional. Callers in this file omit it because the dot click is a
 * focus-only affordance now; the diff modal is reached via the List
 * view's per-row `[Diff]` button. Embedders that still want a custom
 * click target (selection, telemetry) can pass one.
 */
function GitGraphPane({
  onCommitClick,
}: {
  onCommitClick?: (sha: string) => void;
} = {}): JSX.Element {
  const data = useGraphData();
  const interactions = useGraphInteractions(
    data.commits.length,
    onCommitClick,
    data.commits,
  );

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
