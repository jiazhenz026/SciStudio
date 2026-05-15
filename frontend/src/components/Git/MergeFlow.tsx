/**
 * ADR-039 §3.5a / §3.7 / §6 Phase 3 — Merge flow orchestrator (SKELETON).
 *
 * Status: SKELETON. Returns a stub div that says "Merge flow (TODO:
 * D39-2.4b)" so the parent panel can mount it without crashing. The
 * orchestration logic lives in D39-2.4b.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Drive a merge from start to finish. The merge has three possible
 * outcomes per `POST /api/git/merge` (see `api.ts:gitMerge` and ADR
 * §3.5a):
 *
 *   1. result === "fast-forward"  → no merge commit; HEAD just moved.
 *      Show a brief "Fast-forwarded to <sha>" toast and close.
 *
 *   2. result === "clean"          → three-way merge succeeded with no
 *      conflicts; git already wrote a merge commit. Show a "Merged
 *      <branch> into <current>" toast and close.
 *
 *   3. result === "conflict"       → git left the working tree in a
 *      conflicted state. Open `ConflictResolveView` with the list of
 *      conflicted files. The user resolves each (via Monaco editor +
 *      ConflictMarkerDecoration glyph buttons), marks each Resolved
 *      (POST /api/git/merge/stage), then clicks "Complete Merge"
 *      (POST /api/git/merge/complete) or "Abort Merge"
 *      (POST /api/git/merge/abort).
 *
 * The orchestrator's job is to translate the result code into the right
 * UI state and to gate the user's "complete" action until all conflicts
 * are marked resolved.
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   props:
 *     sourceBranch: string;      // branch to merge into current
 *     isOpen:       boolean;     // controls modal visibility
 *     onClose:      () => void;  // closes the modal
 *
 * The current branch is read from `gitSlice.currentBranch`.
 *
 * ============================================================================
 * STATE MACHINE
 * ============================================================================
 *
 *   IDLE  ─ user clicks "Merge" in BranchPicker ─►  IN_FLIGHT (call /api/git/merge)
 *   IN_FLIGHT
 *     ├─ response: fast-forward / clean ─► SUCCESS ─ toast ─► CLOSE
 *     ├─ response: conflict             ─► CONFLICT ─ render ConflictResolveView
 *     │                                       ├─ user resolves all + Complete ─► IN_FLIGHT_COMPLETE
 *     │                                       │       └─ /api/git/merge/complete
 *     │                                       │             └─ SUCCESS ─► CLOSE
 *     │                                       └─ user clicks Abort ─► IN_FLIGHT_ABORT
 *     │                                               └─ /api/git/merge/abort
 *     │                                                     └─ CLOSE (no commit)
 *     └─ response: HTTP error          ─► ERROR ─ show message ─► CLOSE
 *
 * Implementation: a single `phase: "idle" | "in_flight" | "conflict" |
 * "completing" | "aborting" | "error"` useState, plus a derived
 * `conflictedFiles: string[]` from the API response.
 *
 * ============================================================================
 * GIT SLICE INTERACTION
 * ============================================================================
 *
 *   - On entering CONFLICT phase, call
 *     `gitSlice.setMergeInProgress({source_branch, conflicted_files})`.
 *     This is what `CodeEditor.tsx` reads to decide whether to register
 *     the ConflictMarkerDecoration.
 *
 *   - On entering SUCCESS or ABORT exit, call
 *     `gitSlice.setMergeInProgress(null)` so CodeEditor removes the
 *     decorations.
 *
 *   - After a successful complete, `gitSlice.invalidateHistory()` so the
 *     GitHistoryList picks up the new merge commit. (The backend also
 *     emits `git.head_changed`; `useWebSocket.ts` triggers the same
 *     invalidation. Double-call is idempotent.)
 *
 * ============================================================================
 * ACCESSIBILITY
 * ============================================================================
 *
 *   - Modal uses Radix Dialog (or our existing `Modal` component if one
 *     exists in the cascade — D39-2.4b discretion). aria-label =
 *     "Merge {sourceBranch} into {currentBranch}".
 *   - On entering CONFLICT phase, focus auto-jumps to the first
 *     conflicted file row.
 *   - Errors surface via the slice's `aria-live="polite"` region (as
 *     documented in `gitSlice.ts`).
 *
 * ============================================================================
 * COPY STRINGS (D39-2.4b consumes literally)
 * ============================================================================
 *
 *   - Title:   "Merge {sourceBranch} into {currentBranch}"
 *   - Confirm: "Merge"           (initial state)
 *   - FF toast:     "Fast-forwarded {currentBranch} to {sourceBranch}."
 *   - Clean toast:  "Merged {sourceBranch} into {currentBranch}."
 *   - Conflict header: "{n} files have conflicts. Resolve each, then click Complete Merge."
 *   - Complete button: "Complete Merge"
 *   - Abort button:    "Abort Merge"
 *   - Abort confirm:   "Discard the in-progress merge? All resolution work will be lost."
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. NETWORK FAILURE mid-merge — phase=ERROR with the error string from
 *      `ApiError.message`. Working tree may or may not be in a conflict
 *      state depending on where git failed. User must `gitMergeAbort()`
 *      manually from CLI or restart SciEasy (rare path).
 *
 *   2. USER CLOSES MODAL DURING CONFLICT — modal close is BLOCKED unless
 *      phase is idle / success / error. Closing the modal mid-conflict
 *      would orphan the conflicted working tree.
 *
 *   3. CURRENT BRANCH CHANGES MID-FLOW — should not happen because the
 *      modal blocks the rest of the UI. If it does (programmatic
 *      switchBranch from elsewhere), the SUCCESS toast still uses the
 *      branch name captured at modal open.
 *
 *   4. EMPTY CONFLICTED_FILES IN RESPONSE — never happens per backend
 *      contract (conflict result always has >=1 file). Defensive: treat
 *      as clean and warn.
 *
 *   5. CHERRY-PICK reuses this same flow — D39-2.4b: add an optional
 *      `mode: "merge" | "cherry-pick"` prop and a `cherryPickSha` prop.
 *      Skeleton scope is merge only; cherry-pick wiring is a
 *      follow-up consideration documented in the issue.
 *
 * ============================================================================
 */

export interface MergeFlowProps {
  /** Branch the user wants to merge INTO the current branch. */
  sourceBranch: string;
  /** Controls modal visibility. */
  isOpen: boolean;
  /** Caller-supplied close handler. The modal also closes itself on success. */
  onClose: () => void;
}

/**
 * Merge-flow modal (SKELETON).
 *
 * D39-2.4a: returns a placeholder. D39-2.4b: implement the full state
 * machine, wire `gitMerge` / `gitMergeComplete` / `gitMergeAbort`,
 * render `ConflictResolveView` in conflict phase, set/clear
 * `gitSlice.mergeInProgress`.
 */
export function MergeFlow(props: MergeFlowProps): JSX.Element | null {
  void props.sourceBranch;
  void props.onClose;
  if (!props.isOpen) return null;
  return (
    <div
      data-testid="merge-flow-skeleton"
      role="dialog"
      aria-label="Merge flow (not yet implemented — D39-2.4b)"
      className="fixed inset-0 flex items-center justify-center bg-black/30 text-sm text-stone-500"
    >
      <div className="rounded bg-white p-6 shadow-lg">
        Merge flow (TODO: D39-2.4b)
      </div>
    </div>
  );
}

export default MergeFlow;
