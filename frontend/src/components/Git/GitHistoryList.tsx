/**
 * ADR-039 §3.5 + §3.4 + §3.4a + §3.5c — GitHistoryList.
 *
 * Reverse-chronological commit list with a header-level filter dropdown
 * (Manual / All / Auto / Agent). Click a row → onCommitClick (defaults to
 * opening GitDiffModal). "Restore this version" button per row →
 * gitSlice.restore.
 */
import { useCallback, useEffect, useState } from "react";
import type { JSX, KeyboardEvent as ReactKeyboardEvent } from "react";

import { useAppStore } from "../../store";
import type { GitCommit, GitHistoryFilter } from "../../types/api";
import { classifyPrefix, selectVisibleCommits } from "../../store/gitSlice";
import { GitDiffModal } from "./GitDiffModal";
import { StashApplyDialog } from "./StashApplyDialog";

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
  // Codex P2-A on PR #940: when restore auto-stashes, surface the
  // StashApplyDialog so the user can choose Apply / Keep / Discard.
  const [stashPrompt, setStashPrompt] = useState<string | null>(null);

  useEffect(() => {
    if (commits === null && !loading) {
      void loadLog(branch);
    }
  }, [branch, commits, loading, loadLog]);

  const handleRowClick = useCallback(
    (commit: GitCommit) => {
      if (onCommitClick) {
        onCommitClick(commit);
      } else {
        // Codex P2-B on PR #940: for a root commit (no parents), comparing
        // `from=commit.sha` to working tree (the backend default for `to`)
        // shows the inverse of the initial state rather than the commit's
        // own patch. Use the empty-tree hash (well-known git constant) as the
        // parent so the initial commit displays as additions of every file.
        const parent = commit.parents[0];
        if (parent) {
          setDiffOpen({ from: parent, to: commit.sha });
        } else {
          const EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
          setDiffOpen({ from: EMPTY_TREE_SHA, to: commit.sha });
        }
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
        `Restore files from commit ${commit.short_sha}?\n\n${commit.subject}\n\nThis will overwrite the working tree (uncommitted changes will be auto-stashed).`,
      );
      if (!ok) return;
      // Codex P2-A on PR #940: open StashApplyDialog when the backend
      // auto-stashed the dirty tree (ADR-039 §3.6) so the user sees where
      // their unsaved edits went.
      void restore(commit.sha)
        .then((result) => {
          if (result && result.status === "stashed") {
            setStashPrompt(result.stash_id);
          }
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.warn("[GitHistoryList] restore failed:", err);
        });
    },
    [onRestoreClick, restore],
  );

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLLIElement>, commit: GitCommit) => {
      if (event.key === "Enter") {
        event.preventDefault();
        handleRowClick(commit);
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        handleRestore(commit);
      }
    },
    [handleRowClick, handleRestore],
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
        </div>
      )}

      {loading ? (
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
            return (
              <li
                key={commit.sha}
                data-testid={`git-history-row-${commit.short_sha}`}
                data-commit-prefix={prefix}
                role="button"
                tabIndex={0}
                onClick={() => handleRowClick(commit)}
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
                  data-testid={`git-history-row-restore-${commit.short_sha}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRestore(commit);
                  }}
                  title="Soft-restore: copy this commit's files into the working tree without moving HEAD."
                  className="ml-2 rounded border border-stone-300 px-2 py-0.5 text-[10px] hover:bg-stone-100"
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

      {stashPrompt !== null && (
        <StashApplyDialog
          open={true}
          stashId={stashPrompt}
          onClose={() => setStashPrompt(null)}
        />
      )}
    </div>
  );
}
