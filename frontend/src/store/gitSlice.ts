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

import { api, ApiError } from "../lib/api";
import type {
  GitBranch,
  GitCommit,
  GitCommitPrefix,
  GitHistoryFilter,
  GitStatus,
} from "../types/api";
import type { AppStore } from "./types";

const LOG_ALL_KEY = "<all>";

function logKey(branch?: string): string {
  return branch && branch.length > 0 ? branch : LOG_ALL_KEY;
}

function describeApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 503) {
      return "Git binary not available. Reinitialize from Settings → Git.";
    }
    return err.message || fallback;
  }
  if (err instanceof Error) {
    return err.message || fallback;
  }
  return fallback;
}

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
  mergeInProgress: GitMergeInProgress | null;
  lastError: string | null;
  /**
   * ADR-039 Addendum 1 (#1354) — transient "safety auto-commit landed"
   * notice. Set by `switchBranch` / `restore` when the backend
   * response carries a non-null `auto_commit_sha`, consumed by
   * `BranchPicker` (toast on switch) and `RestoreWorkflowButton`
   * (inline hint on restore). Components clear it via
   * `setLastNotice(null)` after rendering, mirroring the
   * `lastError` lifecycle. Kept distinct from `lastError` so
   * downstream UI does not confuse "your change was committed
   * safely" with "something failed".
   */
  lastNotice: string | null;
  /**
   * ADR-039 §3.5 (#972 — Codex P1 on PR #974) — branch the user clicked
   * "Merge into current" on. Driving this from the slice (rather than
   * local Git-tab state) keeps the MergeFlow modal mounted at the
   * BottomPanel level so switching bottom tabs during an in-flight
   * conflict resolution does NOT tear it down and orphan the merge
   * (MergeFlow's close guard would otherwise be bypassed). `null` =
   * modal hidden.
   */
  mergeFlowSource: string | null;

  /**
   * Project ID active when `mergeFlowSource` was set (#975 Codex P1 on
   * PR #980). Used by the App-level `<AppLevelMergeFlow>` mount to
   * gate visibility: the modal renders only when the current open
   * project matches this id. Switching to a different project hides
   * the modal (state preserved); switching back re-shows it. Without
   * this gate, modal actions like `complete merge` / `abort merge`
   * would run against the wrong backend project context. `null` when
   * no merge is in flight.
   */
  mergeFlowProjectId: string | null;

  // Actions — D39-2.3b fills bodies.
  setHistoryFilter: (filter: GitHistoryFilter) => void;
  invalidateHistory: () => void;
  loadBranches: () => Promise<void>;
  loadLog: (branch?: string) => Promise<void>;
  loadStatus: () => Promise<void>;
  commit: (message: string, files?: string[]) => Promise<string>;
  switchBranch: (name: string) => Promise<{ auto_commit_sha: string | null }>;
  createBranch: (name: string, baseSha?: string) => Promise<void>;
  deleteBranch: (name: string, force?: boolean) => Promise<void>;
  restore: (
    commitSha: string,
    files?: string[],
  ) => Promise<{ status: "ok"; auto_commit_sha: string | null }>;
  setMergeInProgress: (state: GitMergeInProgress | null) => void;
  /**
   * Open or close MergeFlow. `source` is the branch being merged into
   * the current branch (or `null` to close). `projectId` is the
   * current open project's id — stamped here so the App-level mount
   * can gate visibility against project switches (#975 Codex P1 on
   * PR #980). Pass `null` for `projectId` when closing (`source=null`)
   * or when opening outside any project context (test fixtures).
   */
  setMergeFlowSource: (source: string | null, projectId?: string | null) => void;
  setLastError: (message: string | null) => void;
  setLastNotice: (message: string | null) => void;
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

export const createGitSlice: StateCreator<AppStore, [], [], GitSlice> = (set, get) => ({
  branches: null,
  currentBranch: null,
  logCache: {},
  logLoading: {},
  historyFilter: "manual",
  status: null,
  mergeInProgress: null,
  mergeFlowSource: null,
  mergeFlowProjectId: null,
  lastError: null,
  lastNotice: null,

  setHistoryFilter: (filter) => set({ historyFilter: filter }),

  invalidateHistory: () => {
    // Clear cached log / status / branch list. Called from useWebSocket on
    // `git.head_changed` and from any other action that needs to discard
    // stale git state (commit, switch, restore, merge resolve).
    set({ logCache: {}, status: null, branches: null });
    // #984 fix: actively re-fetch instead of waiting for "the next consumer
    // render" — no consumer (BranchPicker, GitHistoryList, GitStatusBadge)
    // is wired to re-fetch on state=null. They only call their respective
    // loadXxx() inside a useEffect that depends on currentProjectId, which
    // only fires once on mount and on project switch. Without this
    // re-fetch, every git.head_changed event left the UI permanently
    // stuck on "Loading branches…" / "git: loading…" until project close.
    void get().loadBranches();
    void get().loadStatus();
    void get().loadLog();
  },

  setMergeInProgress: (state) => set({ mergeInProgress: state }),
  // #972 (Codex P1 on PR #974) — UI-only field; setting null hides the
  // MergeFlow modal. Mounted at App level (#975) so it survives bottom-
  // tab switches AND project switch/close. `projectId` is stamped so
  // App-level mount can hide the modal when user navigates to a
  // different project mid-conflict (state preserved; comes back on
  // returning to the original project) — prevents Complete/Abort
  // operations from being routed to the wrong backend project context.
  setMergeFlowSource: (source, projectId) =>
    set({
      mergeFlowSource: source,
      mergeFlowProjectId: source === null ? null : (projectId ?? null),
    }),
  setLastError: (message) => set({ lastError: message }),
  setLastNotice: (message) => set({ lastNotice: message }),

  loadBranches: async () => {
    try {
      const branches = await api.gitBranches();
      const current = branches.find((b) => b.is_current)?.name ?? null;
      set({ branches, currentBranch: current, lastError: null });
    } catch (err) {
      set({ lastError: describeApiError(err, "Failed to load branches") });
    }
  },

  loadLog: async (branch?: string) => {
    const key = logKey(branch);
    set((state) => ({ logLoading: { ...state.logLoading, [key]: true } }));
    try {
      const commits = await api.gitLog(branch ? { branch } : undefined);
      set((state) => ({
        logCache: { ...state.logCache, [key]: commits },
        logLoading: { ...state.logLoading, [key]: false },
        lastError: null,
      }));
    } catch (err) {
      set((state) => ({
        logLoading: { ...state.logLoading, [key]: false },
        lastError: describeApiError(err, "Failed to load commit history"),
      }));
    }
  },

  loadStatus: async () => {
    try {
      const status = await api.gitStatus();
      set({ status, lastError: null });
    } catch (err) {
      set({ lastError: describeApiError(err, "Failed to load git status") });
    }
  },

  commit: async (message: string, files?: string[]) => {
    try {
      const resp = await api.gitCommit({ message, files });
      // Invalidate caches so the next render picks up the new commit + clean tree.
      set({ logCache: {}, status: null, lastError: null });
      // Best-effort refresh: status + log for the current branch.
      const branch = get().currentBranch ?? undefined;
      void get().loadStatus();
      void get().loadLog(branch);
      return resp.commit_sha;
    } catch (err) {
      const message = describeApiError(err, "Commit failed");
      set({ lastError: message });
      throw err instanceof Error ? err : new Error(message);
    }
  },

  switchBranch: async (name: string) => {
    try {
      const oldBranch = get().currentBranch;
      const result = await api.gitBranchSwitch(name);
      const autoSha = result.auto_commit_sha ?? null;
      // Clear all caches; HEAD moved.
      set({
        logCache: {},
        status: null,
        branches: null,
        lastError: null,
        // ADR-039 Addendum 1 (#1354) — surface the safety auto-commit
        // to the user via a transient toast. `BranchPicker` consumes
        // `lastNotice` and clears it on its next mount cycle.
        lastNotice: autoSha
          ? `Auto-committed unsaved changes on ${oldBranch ?? "previous branch"} as ${autoSha.slice(0, 7)} before switching to ${name}.`
          : null,
      });
      await get().loadBranches();
      void get().loadStatus();
      void get().loadLog(name);
      return { auto_commit_sha: autoSha };
    } catch (err) {
      set({ lastError: describeApiError(err, `Failed to switch to '${name}'`) });
      throw err;
    }
  },

  createBranch: async (name: string, baseSha?: string) => {
    try {
      await api.gitBranchCreate({ name, base_sha: baseSha });
      set({ branches: null, lastError: null });
      await get().loadBranches();
    } catch (err) {
      set({ lastError: describeApiError(err, `Failed to create branch '${name}'`) });
      throw err;
    }
  },

  deleteBranch: async (name: string, force = false) => {
    try {
      await api.gitBranchDelete(name, force);
      set({ branches: null, lastError: null });
      await get().loadBranches();
    } catch (err) {
      set({ lastError: describeApiError(err, `Failed to delete branch '${name}'`) });
      throw err;
    }
  },

  restore: async (commitSha: string, files?: string[]) => {
    try {
      const result = await api.gitRestore({ commit_sha: commitSha, files });
      const autoSha = result.auto_commit_sha ?? null;
      set({
        status: null,
        lastError: null,
        // ADR-039 Addendum 1 (#1354) — surface the auto-commit hint to
        // the user. `RestoreWorkflowButton` consumes `lastNotice` (or
        // reads `auto_commit_sha` directly from the awaited result;
        // either path is supported).
        lastNotice: autoSha
          ? `Your unsaved changes were committed as ${autoSha.slice(0, 7)} before the restore — see History tab to revert if unintended.`
          : null,
      });
      void get().loadStatus();
      // History changed — reload the active log so the new auto:
      // pre-restore commit shows up immediately.
      if (autoSha) void get().loadLog();
      return result;
    } catch (err) {
      set({ lastError: describeApiError(err, "Restore failed") });
      throw err;
    }
  },
});
