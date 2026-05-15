/**
 * ADR-039 §3.5a / §6 Phase 3 — Conflict resolution view (SKELETON).
 *
 * Status: SKELETON. Returns a stub div listing the conflicted files
 * from props. Full per-file resolution status + action buttons land in
 * D39-2.4b.
 *
 * ============================================================================
 * PURPOSE
 * ============================================================================
 *
 * Lives INSIDE `MergeFlow.tsx` when the merge result is "conflict". A
 * sidebar list of conflicted files; each row shows:
 *
 *   - The file's relative path.
 *   - A status badge: "Unresolved" / "Resolved" (per-file local state).
 *   - A "Open" button that focuses the file in the main `CodeEditor`
 *     tab area — Monaco decorations from `ConflictMarkerDecoration.ts`
 *     then surface the in-editor action buttons.
 *   - A "Mark Resolved" button that calls `gitMergeStageFile(filePath)`
 *     against the backend. This is what tells git "this file is done";
 *     git stages it into the merge commit's tree.
 *
 * Two top-level buttons (footer):
 *
 *   - "Complete Merge": enabled only when ALL files are Resolved.
 *     Calls `gitMergeComplete()`. On success, `MergeFlow` closes.
 *
 *   - "Abort Merge": always enabled. Asks the user to confirm; on
 *     confirm calls `gitMergeAbort()`. The working tree reverts to
 *     pre-merge state.
 *
 * ============================================================================
 * INPUT
 * ============================================================================
 *
 *   props:
 *     conflictedFiles: string[];       // relative paths
 *     onOpenFile:      (path: string) => void;  // focus the file tab
 *     onResolveAll:    () => Promise<void>;     // wraps gitMergeComplete
 *     onAbort:         () => Promise<void>;     // wraps gitMergeAbort
 *
 * Status state per file lives in this component (`useState<Map<file,
 * "unresolved"|"resolved">>`). D39-2.4b: consider whether to lift this
 * to `gitSlice.mergeInProgress.resolved_files` — likely yes, so a
 * background `git.head_changed` doesn't lose status. Skeleton documents
 * both options.
 *
 * ============================================================================
 * STATE-SYNC SUBTLETY
 * ============================================================================
 *
 * `gitMergeStageFile(path)` mutates git's index. After staging, calling
 * `gitStatus()` would show the file under `staged` and not under
 * `conflicted`. But polling status on every action is wasteful — D39-2.4b
 * should rely on the local map AND a final `gitStatus()` consistency
 * check before enabling "Complete Merge".
 *
 * If a user resolves a file via the editor manually (deletes all
 * markers + saves) but DOES NOT click "Mark Resolved", the merge is
 * not stageable. D39-2.4b should detect "no markers in file" and
 * auto-prompt "Looks like you've removed all conflict markers. Mark
 * this file resolved?".
 *
 * ============================================================================
 * COPY STRINGS
 * ============================================================================
 *
 *   - Header:        "Conflicts in this merge"
 *   - Empty state:   "No conflicted files." (defensive; should never render)
 *   - Status badge:  "Unresolved" / "Resolved"
 *   - Open button:   "Open in editor"
 *   - Mark button:   "Mark Resolved"
 *   - Confirm dialog: "Discard the in-progress merge? All resolution work will be lost."
 *
 * ============================================================================
 * ACCESSIBILITY
 * ============================================================================
 *
 *   - The list is a `<ul role="listbox">` with each file a
 *     `<li role="option">`.
 *   - "Mark Resolved" button has `aria-describedby` pointing at the
 *     file's status badge so screen readers narrate "Mark file X as
 *     resolved; currently Unresolved".
 *   - "Complete Merge" button has aria-disabled=true (NOT
 *     disabled=true) when not all files are resolved, so the screen
 *     reader still announces it.
 *
 * ============================================================================
 * EDGE CASES
 * ============================================================================
 *
 *   1. ZERO conflicted files (defensive) → render empty-state message.
 *   2. USER DELETES THE FILE on disk mid-flow → `gitMergeStageFile`
 *      returns an error; surface via `gitSlice.lastError`.
 *   3. EXTERNAL git commit while conflict open (user runs `git commit`
 *      from CLI) → `git.head_changed` event fires; MergeFlow detects
 *      mergeInProgress is no longer relevant; closes itself with a
 *      toast "Merge completed externally."
 *   4. MERGE ABORT FAILS (rare; usually means a deeper git
 *      malfunction) → surface the error; do not close the modal.
 *
 * ============================================================================
 */

export interface ConflictResolveViewProps {
  /** Files git left in conflicted state. */
  conflictedFiles: string[];
  /** Focus the file in the main editor tab area. */
  onOpenFile: (path: string) => void;
  /** Wraps `api.gitMergeComplete()` plus optimistic UI update. */
  onResolveAll: () => Promise<void>;
  /** Wraps `api.gitMergeAbort()` plus optimistic UI update. */
  onAbort: () => Promise<void>;
}

/**
 * Conflict resolution sidebar (SKELETON).
 *
 * D39-2.4a: renders a static stub list. D39-2.4b: implement full per-file
 * status tracking + action wiring.
 */
export function ConflictResolveView(props: ConflictResolveViewProps): JSX.Element {
  void props.onOpenFile;
  void props.onResolveAll;
  void props.onAbort;
  return (
    <div
      data-testid="conflict-resolve-view-skeleton"
      className="flex h-full w-full flex-col gap-2 p-4 text-sm"
    >
      <h2 className="text-base font-semibold">Conflicts in this merge</h2>
      {props.conflictedFiles.length === 0 ? (
        <p className="text-stone-500">No conflicted files.</p>
      ) : (
        <ul role="listbox" className="flex flex-col gap-1">
          {props.conflictedFiles.map((f) => (
            <li
              key={f}
              role="option"
              aria-selected={false}
              className="rounded bg-stone-100 px-2 py-1 font-mono text-xs"
            >
              {f}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-stone-400">(TODO: D39-2.4b — wire action buttons)</p>
    </div>
  );
}

export default ConflictResolveView;
