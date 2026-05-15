/**
 * ADR-039 §3.5 + §3.4 + §3.4a + §3.5c — GitHistoryList (SKELETON).
 *
 * Purpose
 * -------
 * Reverse-chronological commit list with a header-level filter dropdown
 * (Manual / All / Auto / Agent). Click a row → opens GitDiffModal showing
 * `commit_sha^..commit_sha`. Each row also has a "Restore this version"
 * button that calls `gitSlice.restore({commit_sha})`.
 *
 * Lives in the "Git" tab inside the Bottom Panel (the cascade does NOT
 * register a new BottomTab in this phase — D39-2.3b decides whether to
 * add the tab to `BottomPanel.tsx` or whether the History list lives on
 * a side panel — that decision is documented in the BranchPicker
 * skeleton). For the SKELETON: this component renders standalone.
 *
 * Props
 * -----
 *   branch?:                   string         — null → log --all
 *   onCommitClick?:            (commit: GitCommit) => void
 *                                              Used when caller wants to
 *                                              intercept the diff modal (e.g.
 *                                              Lineage tab's "restore this
 *                                              run's workflow" flow).
 *   onRestoreClick?:           (commit: GitCommit) => void
 *                                              Defaults to gitSlice.restore.
 *   showFilterDropdown?:       boolean        — defaults true. The Graph view
 *                                              (D39-2.4a) shares the same
 *                                              filter so will pass false to
 *                                              avoid two dropdowns.
 *   className?:                string
 *
 * Slice state read (`useAppStore`)
 * --------------------------------
 *   logCache:        Record<string, GitCommit[]>
 *   logLoading:      Record<string, boolean>
 *   historyFilter:   GitHistoryFilter
 *   setHistoryFilter: (filter) => void
 *   loadLog:         (branch?) => Promise<void>
 *
 * Event flow (user → dispatches)
 * ------------------------------
 *   - mount / branch prop change → loadLog(branch)
 *   - click commit row → onCommitClick(commit) (or open GitDiffModal inline)
 *   - click row's restore button → onRestoreClick(commit) or gitSlice.restore
 *   - filter dropdown change → setHistoryFilter(filter)
 *
 * Layout markup with data-testids
 * -------------------------------
 *   <div data-testid="git-history-list" className="flex flex-col">
 *     <div className="flex items-center gap-2 px-3 py-2 border-b">
 *       <Select
 *         data-testid="git-history-filter"
 *         value={historyFilter}
 *         onChange={setHistoryFilter}
 *       >
 *         <option value="manual">Manual milestones</option>
 *         <option value="all">All (incl. auto)</option>
 *         <option value="auto">Auto only (debug)</option>
 *         <option value="agent">Agent only (debug)</option>
 *       </Select>
 *       <button data-testid="git-history-refresh" onClick={() => loadLog(branch)}>
 *         Refresh
 *       </button>
 *     </div>
 *     {logLoading[key] ? <Spinner data-testid="git-history-loading" /> :
 *       visibleCommits.length === 0 ? (
 *         <div data-testid="git-history-empty">No commits yet on this branch.</div>
 *       ) : (
 *         <ul data-testid="git-history-rows" role="list">
 *           {visibleCommits.map((commit) => (
 *             <li
 *               key={commit.sha}
 *               data-testid={`git-history-row-${commit.short_sha}`}
 *               data-commit-prefix={classifyPrefix(commit.subject)}  // "auto"|"agent"|"user"
 *               role="button"
 *               tabIndex={0}
 *               onClick={() => onCommitClick?.(commit)}
 *             >
 *               <span data-testid="git-history-row-icon">
 *                 {prefix === "agent" ? "🤖" : prefix === "auto" ? "·" : "👤"}
 *               </span>
 *               <span data-testid="git-history-row-short-sha">{commit.short_sha}</span>
 *               <span data-testid="git-history-row-subject">{commit.subject}</span>
 *               <span data-testid="git-history-row-author">{commit.author_name}</span>
 *               <time data-testid="git-history-row-date">{commit.author_date}</time>
 *               <button
 *                 data-testid={`git-history-row-restore-${commit.short_sha}`}
 *                 onClick={(e) => { e.stopPropagation(); onRestoreClick(commit); }}
 *               >
 *                 Restore this version
 *               </button>
 *             </li>
 *           ))}
 *         </ul>
 *       )}
 *   </div>
 *
 * Copy strings
 * ------------
 *   Filter options: "Manual milestones" / "All (incl. auto)" /
 *                   "Auto only (debug)" / "Agent only (debug)"
 *                   (must match ADR §3.4 line 181-184)
 *   Empty:          "No commits yet on this branch."
 *   Loading:        "Loading commit history…"
 *   Refresh:        "Refresh"
 *   Restore row:    "Restore this version"
 *   Restore tooltip: "Soft-restore: copy this commit's files into the working
 *                     tree without moving HEAD. (Hard restore lives in the
 *                     advanced menu.)"
 *
 * Keyboard shortcuts
 * ------------------
 *   - Up/Down arrow keys move focus between rows (custom keyhandler).
 *   - Enter on a focused row → onCommitClick(commit).
 *   - R on a focused row → onRestoreClick(commit) (confirm-once dialog
 *     deferred to D39-2.3b).
 *
 * Accessibility
 * -------------
 *   - <ul role="list"> with <li role="button" tabIndex={0}> — common
 *     focus-managed list pattern used by other SciEasy lists.
 *   - Filter dropdown uses native <select> for keyboard parity with the
 *     rest of the toolbar.
 *   - Time elements use ISO timestamps via <time dateTime={iso}>.
 *
 * Edge cases
 * ----------
 *   - logCache[key] missing → on mount, dispatch loadLog. Render
 *     "Loading commit history…" until logLoading[key] flips false.
 *   - All commits filtered out (e.g. "manual" filter but every commit is
 *     `auto:`) → show <div data-testid="git-history-empty-after-filter">
 *       "Only auto/agent commits exist on this branch.
 *        Switch the filter to All to see them."
 *   - Restore on dirty tree → backend auto-stashes (per ADR §3.6); the
 *     server responds with {status: "stashed", stash_id}. D39-2.3b is
 *     responsible for showing the StashApplyDialog when that response
 *     arrives.
 *
 * Virtualization plan (D39-2.3b)
 * ------------------------------
 *   - For <500 commits: no virtualization (modern browsers render 500
 *     DOM rows fine).
 *   - For 500-10000 commits: drop in `@tanstack/react-virtual` here.
 *   - Beyond 10000: server-side pagination via the `limit` query param;
 *     out of scope for v1.
 *
 * Tests (see GitHistoryList.test.tsx)
 * -----------------------------------
 *   - renders loading state when logLoading[branch] === true
 *   - renders empty state when logCache[branch] === []
 *   - renders one row per commit with short_sha + subject + author
 *   - filter dropdown defaulted to "manual" hides "auto:" rows
 *   - filter "all" reveals previously-hidden auto rows
 *   - clicking row dispatches onCommitClick
 *   - clicking restore button dispatches onRestoreClick
 */
import type { JSX } from "react";

import type { GitCommit } from "../../types/api";

export interface GitHistoryListProps {
  branch?: string;
  onCommitClick?: (commit: GitCommit) => void;
  onRestoreClick?: (commit: GitCommit) => void;
  showFilterDropdown?: boolean;
  className?: string;
}

export function GitHistoryList(_props: GitHistoryListProps): JSX.Element {
  // TODO: D39-2.3b — implement the markup per the data-testid contract
  // above, wire loadLog on mount + branch change, render rows via
  // selectVisibleCommits(commits, historyFilter).
  throw new Error("TODO: D39-2.3b — implement GitHistoryList body");
}
