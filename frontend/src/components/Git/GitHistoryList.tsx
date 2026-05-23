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

import { selectVisibleCommits } from "../../store/gitSlice";
import { useAppStore } from "../../store";
import type { GitCommit } from "../../types/api";
import { GitDiffModal } from "./GitDiffModal";
import { GitGraphPane } from "./GitHistoryList.parts/GitGraphPane";
import { HistoryListBody } from "./GitHistoryList.parts/HistoryListBody";
import { HistoryToolbar } from "./GitHistoryList.parts/HistoryToolbar";

export interface GitHistoryListProps {
  branch?: string;
  onCommitClick?: (commit: GitCommit) => void;
  onRestoreClick?: (commit: GitCommit) => void;
  showFilterDropdown?: boolean;
  className?: string;
}

interface UseDiffActionOpts {
  onCommitClick?: (commit: GitCommit) => void;
}

interface DiffOpenState {
  from: string;
  to?: string;
}

function useDiffAction(opts: UseDiffActionOpts): {
  diffOpen: DiffOpenState | null;
  setDiffOpen: (s: DiffOpenState | null) => void;
  handleDiff: (commit: GitCommit) => void;
} {
  const [diffOpen, setDiffOpen] = useState<DiffOpenState | null>(null);
  // ADR-039 Addendum 1 §11.3 (issue #1355): opening the diff modal is no
  // longer driven by row clicks. The per-row [Diff] button + `d` hotkey
  // both come through here.
  const handleDiff = useCallback(
    (commit: GitCommit) => {
      if (opts.onCommitClick) {
        opts.onCommitClick(commit);
        return;
      }
      // Codex P2-B on PR #940: for a root commit (no parents), comparing
      // `from=commit.sha` to working tree shows the inverse of the initial
      // state. Use the empty-tree hash as the parent so the initial commit
      // displays as additions of every file.
      const parent = commit.parents[0];
      if (parent) {
        setDiffOpen({ from: parent, to: commit.sha });
      } else {
        const EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
        setDiffOpen({ from: EMPTY_TREE_SHA, to: commit.sha });
      }
    },
    [opts],
  );
  return { diffOpen, setDiffOpen, handleDiff };
}

function useRestoreAction(onRestoreClick?: (commit: GitCommit) => void) {
  const restore = useAppStore((s) => s.restore);
  return useCallback(
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
        console.warn("[GitHistoryList] restore failed:", err);
      });
    },
    [onRestoreClick, restore],
  );
}

export function GitHistoryList(props: GitHistoryListProps): JSX.Element {
  const { branch, onCommitClick, onRestoreClick, showFilterDropdown = true, className } = props;

  const logCache = useAppStore((s) => s.logCache);
  const logLoading = useAppStore((s) => s.logLoading);
  const historyFilter = useAppStore((s) => s.historyFilter);
  const setHistoryFilter = useAppStore((s) => s.setHistoryFilter);
  const loadLog = useAppStore((s) => s.loadLog);

  const key = branch && branch.length > 0 ? branch : "<all>";
  const commits = logCache[key] ?? null;
  const loading = logLoading[key] === true;

  // Hotfix #1000: default Git tab view is Graph (per Phase 4a feedback —
  // graph is the primary affordance; List is a fallback for plain text).
  const [viewMode, setViewMode] = useState<"list" | "graph">("graph");
  // #1400: lifted selection state, shared between Graph and List views.
  const [selectedCommit, setSelectedCommit] = useState<GitCommit | null>(null);

  useEffect(() => {
    if (commits === null && !loading) {
      void loadLog(branch);
    }
  }, [branch, commits, loading, loadLog]);

  const { diffOpen, setDiffOpen, handleDiff } = useDiffAction({ onCommitClick });
  const handleRestore = useRestoreAction(onRestoreClick);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLLIElement>, commit: GitCommit) => {
      // ADR-039 Addendum 1 §11.3 (issue #1355): `d` opens diff, `r` restore.
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
    <div data-testid="git-history-list" className={`flex h-full flex-col ${className ?? ""}`}>
      {showFilterDropdown && (
        <HistoryToolbar
          historyFilter={historyFilter}
          onFilterChange={setHistoryFilter}
          onRefresh={() => void loadLog(branch)}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          selectedCommit={selectedCommit}
          onDiffSelected={() => {
            if (selectedCommit) handleDiff(selectedCommit);
          }}
          onRestoreSelected={() => {
            if (selectedCommit) handleRestore(selectedCommit);
          }}
        />
      )}

      {viewMode === "graph" ? (
        <GitGraphPane
          onCommitClick={(sha) => {
            const c = (commits ?? []).find((x) => x.sha === sha);
            if (c) setSelectedCommit(c);
          }}
        />
      ) : (
        <HistoryListBody
          loading={loading}
          commits={commits}
          visibleCommits={visibleCommits}
          selectedCommit={selectedCommit}
          onSelect={setSelectedCommit}
          onKeyDown={onKeyDown}
          onDiff={handleDiff}
          onRestore={handleRestore}
        />
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
