/**
 * ADR-039 §6 Phase 2 — Git versioning Zustand slice (SKELETON).
 *
 * Status: SKELETON. All non-trivial state-mutation handlers throw
 * `Error("TODO: D39-2.3b — ...")`. D39-2.3b (the IMPL phase) will fill
 * the bodies and make this slice self-consistent. Skeleton-only state
 * defaults are wired so other slices and components can import without
 * runtime crashes during the skeleton phase — only mutation methods
 * trip the TODO.
 *
 * STATE SHAPE
 * -----------
 *   branches:         GitBranch[] | null
 *       Local branch list cached from `GET /api/git/branches`. `null` until
 *       first fetch; empty array = "no branches" (impossible on a real repo,
 *       but a valid sentinel during init / errors).
 *   currentBranch:    string | null
 *       Name of the currently-checked-out branch. Resolved from
 *       `branches.find(b => b.is_current)`. Cached separately so the
 *       BranchPicker can render a label without resolving the array every
 *       render.
 *   logCache:         Record<string, GitCommit[]>
 *       Keyed by branch name (or "<all>" for `--all` log). The History panel
 *       consults this first; on a cache miss it dispatches `loadLog(branch)`.
 *   logLoading:       Record<string, boolean>
 *       Per-branch loading flag so the History panel can render a spinner
 *       without blocking the rest of the UI.
 *   historyFilter:    GitHistoryFilter   (DEFAULT: "manual")
 *       Drives BOTH GitHistoryList AND the future GitGraph view per
 *       ADR-039 §3.5c. Persisted across panel re-renders inside this slice.
 *   status:           GitStatus | null
 *       Working-tree status from `GET /api/git/status`. Refreshed on
 *       `git.head_changed` events (via useWebSocket.ts → invalidateAll).
 *       The toolbar GitStatusBadge renders the `dirty` boolean.
 *   stashes:          GitStashEntry[] | null
 *       Cached from `GET /api/git/stash`. The StashListPanel consults this
 *       and `loadStashes()` refreshes.
 *   mergeInProgress:  { source_branch: string; conflicted_files: string[] } | null
 *       Set by `MergeFlow.tsx` (D39-2.4a, NOT THIS SKELETON) when a merge
 *       returns "conflict". `null` outside of a conflict resolution flow.
 *       Defined here in the skeleton so D39-2.4a can plug in without
 *       widening the state surface later.
 *   lastError:        string | null
 *       Last user-visible error (e.g. "Cannot commit: nothing to commit").
 *       Surfaced by CommitDialog / BranchPicker / etc. Cleared on next op.
 *
 * EVENTS / INVALIDATION
 * ---------------------
 * `useWebSocket.ts` receives `git.head_changed` over the WS and must call
 * `gitSlice.invalidateHistory()` — this clears `logCache`, `status`, and
 * `branches` so the next render fetches fresh. The current useWebSocket
 * handler has a TODO marker pointing at exactly this slice method.
 *
 * SELECTORS (helpers, NOT actions)
 * --------------------------------
 *   - selectVisibleCommits(commits, filter) → GitCommit[]
 *       Apply `historyFilter` to a commit list. The History list and
 *       GitGraph both pass through this (graph dims hidden commits).
 *   - classifyPrefix(message) → GitCommitPrefix
 *       Pure function; returns "auto" | "agent" | "user" per ADR §3.4a.
 *
 * COPY STRINGS (the IMPL phase consumes these literally)
 * ------------------------------------------------------
 *   - "Loading commit history…"            (HistoryList empty/loading state)
 *   - "No commits yet on this branch."     (HistoryList empty/loaded state)
 *   - "Working tree clean"                  (StatusBadge tooltip when !dirty)
 *   - "Working tree has uncommitted changes" (StatusBadge tooltip when dirty)
 *   - "Cannot commit: nothing to commit."   (CommitDialog error from /commit 409)
 *   - "Commit message cannot be empty."     (CommitDialog client-side validation)
 *
 * KEYBOARD SHORTCUTS (per ADR §3 — see CommitDialog / BranchPicker)
 * -----------------------------------------------------------------
 *   - Ctrl+K, C → open Commit dialog            (CommitDialog mounts via Toolbar)
 *   - Ctrl+K, B → open Branch picker            (BranchPicker focus)
 *   - Ctrl+K, S → quick-show status badge tooltip (optional, v1.1)
 *
 * EDGE CASES
 * ----------
 *   - No active project: ALL fetch actions are no-ops (gitSlice returns
 *     defaults). Components hide / disable themselves when project is null.
 *   - Bundled git missing (503 from API): `lastError = "Git binary not
 *     available. Reinitialize from Settings → Git."` + UI degrades to
 *     hide commit / branch buttons. The version-control surface is
 *     unavailable, not crashed.
 *   - Concurrent calls: each fetch action sets `logLoading[branch] = true`
 *     before dispatching and clears it inside .finally. Out-of-order
 *     responses for the same branch keep the most recent payload.
 *   - "all" branches key: when the GitGraph view loads `git log --all`,
 *     the slice keys that response under "<all>" in `logCache`. The
 *     History panel and the Graph view share this cache when both are
 *     visible.
 *
 * ACCESSIBILITY
 * -------------
 *   This slice is not directly rendered, but consumer components MUST
 *   surface `lastError` through an aria-live="polite" region so screen
 *   readers announce git failures. Documented here so D39-2.3b is
 *   reminded.
 */
import type { StateCreator } from "zustand";

import type {
  GitBranch,
  GitCommit,
  GitCommitPrefix,
  GitHistoryFilter,
  GitStashEntry,
  GitStatus,
} from "../types/api";
import type { AppStore } from "./types";

// ---------------------------------------------------------------------------
// State shape (exported separately so AppStore can union it in)
// ---------------------------------------------------------------------------

export interface GitMergeInProgress {
  source_branch: string;
  conflicted_files: string[];
}

export interface GitSlice {
  branches: GitBranch[] | null;
  currentBranch: string | null;
  logCache: Record<string, GitCommit[]>;
  logLoading: Record<string, boolean>;
  historyFilter: GitHistoryFilter;
  status: GitStatus | null;
  stashes: GitStashEntry[] | null;
  mergeInProgress: GitMergeInProgress | null;
  lastError: string | null;

  // Actions — D39-2.3b fills bodies.
  setHistoryFilter: (filter: GitHistoryFilter) => void;
  invalidateHistory: () => void;
  loadBranches: () => Promise<void>;
  loadLog: (branch?: string) => Promise<void>;
  loadStatus: () => Promise<void>;
  loadStashes: () => Promise<void>;
  commit: (message: string, files?: string[]) => Promise<string>;
  switchBranch: (name: string) => Promise<void>;
  createBranch: (name: string, baseSha?: string) => Promise<void>;
  deleteBranch: (name: string, force?: boolean) => Promise<void>;
  restore: (commitSha: string, files?: string[]) => Promise<void>;
  setMergeInProgress: (state: GitMergeInProgress | null) => void;
  setLastError: (message: string | null) => void;
}

// ---------------------------------------------------------------------------
// Pure helpers (always safe to call — no IO, no TODO)
// ---------------------------------------------------------------------------

/**
 * Classify a commit message by its prefix per ADR-039 §3.4 / §3.4a.
 *
 * Implementation contract:
 *   - Strict prefix match on the FIRST line (subject) only.
 *   - "auto:" → "auto"
 *   - "agent:" → "agent"
 *   - anything else → "user"
 *   - Whitespace before the prefix MUST cause classification to fall back to
 *     "user" (we don't accept "  auto: foo" — that is a user commit whose
 *     message coincidentally starts with whitespace).
 *
 * D39-2.3b: this implementation is safe to keep as-is; it is pure logic.
 */
export function classifyPrefix(message: string): GitCommitPrefix {
  const firstLine = (message ?? "").split("\n", 1)[0] ?? "";
  if (firstLine.startsWith("auto:")) return "auto";
  if (firstLine.startsWith("agent:")) return "agent";
  return "user";
}

/**
 * Apply the history filter to a commit list. Pure function — safe to call
 * during render. Returns a new array (does not mutate).
 *
 * Filter rules (ADR §3.4 / §3.5c):
 *   - "manual": exclude prefix === "auto" AND prefix === "agent"
 *   - "all":    no filtering
 *   - "auto":   include only prefix === "auto"
 *   - "agent":  include only prefix === "agent"
 *
 * D39-2.3b: this implementation is safe to keep as-is; it is pure logic.
 */
export function selectVisibleCommits(
  commits: GitCommit[],
  filter: GitHistoryFilter,
): GitCommit[] {
  if (filter === "all") return [...commits];
  return commits.filter((c) => {
    const p = classifyPrefix(c.subject);
    if (filter === "manual") return p === "user";
    if (filter === "auto") return p === "auto";
    if (filter === "agent") return p === "agent";
    return true;
  });
}

// ---------------------------------------------------------------------------
// Slice factory
// ---------------------------------------------------------------------------

export const createGitSlice: StateCreator<AppStore, [], [], GitSlice> = (set) => ({
  branches: null,
  currentBranch: null,
  logCache: {},
  logLoading: {},
  historyFilter: "manual",
  status: null,
  stashes: null,
  mergeInProgress: null,
  lastError: null,

  setHistoryFilter: (filter) => set({ historyFilter: filter }),

  invalidateHistory: () =>
    // TODO: D39-2.3b — invalidate logCache, status, branches; trigger next
    // fetch lazily on next consumer read.
    set({ logCache: {}, status: null, branches: null }),

  setMergeInProgress: (state) => set({ mergeInProgress: state }),
  setLastError: (message) => set({ lastError: message }),

  loadBranches: async () => {
    throw new Error("TODO: D39-2.3b — fetch /api/git/branches and populate state");
  },
  loadLog: async (_branch?: string) => {
    throw new Error("TODO: D39-2.3b — fetch /api/git/log and populate logCache");
  },
  loadStatus: async () => {
    throw new Error("TODO: D39-2.3b — fetch /api/git/status and populate state.status");
  },
  loadStashes: async () => {
    throw new Error("TODO: D39-2.3b — fetch /api/git/stash and populate state.stashes");
  },
  commit: async (_message: string, _files?: string[]) => {
    throw new Error("TODO: D39-2.3b — POST /api/git/commit and refresh log");
  },
  switchBranch: async (_name: string) => {
    throw new Error("TODO: D39-2.3b — POST /api/git/branch/switch and refresh");
  },
  createBranch: async (_name: string, _baseSha?: string) => {
    throw new Error("TODO: D39-2.3b — POST /api/git/branch/create and refresh");
  },
  deleteBranch: async (_name: string, _force?: boolean) => {
    throw new Error("TODO: D39-2.3b — DELETE /api/git/branches/<name>");
  },
  restore: async (_commitSha: string, _files?: string[]) => {
    throw new Error("TODO: D39-2.3b — POST /api/git/restore and refresh");
  },
});
