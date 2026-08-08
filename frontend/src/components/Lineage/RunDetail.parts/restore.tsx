/**
 * "Restore" — return the project to how it was at a recorded run.
 *
 * ADR-039 §6 Phase 4, rewritten by ADR-038 Addendum 1 §11.1 (#2033).
 *
 * What changed and why: this button used to be labelled "Restore workflow" and
 * scoped its restore to `workflows/<workflow_id>.yaml`. A user whose block had
 * broken would open the run that worked, press it, and watch the same failure
 * — the workflow graph came back, the block source that actually broke did
 * not. Meanwhile the Git tab's `Restore`, one tab over and identically named,
 * did the full-tree restore that would have fixed it.
 *
 * It now opens the shared `RestoreDialog`, which states the scope, runs the
 * ADR-038 §3.6 preflight, and performs a full-tree restore at the run's
 * `workflow_git_commit`.
 *
 * The degraded-run guard is unchanged: a run whose pre-run auto-commit failed
 * has `workflow_git_commit === null` and no resolvable git anchor, so there is
 * nothing to restore to and the button stays disabled.
 */

import { useState } from "react";

import { RestoreDialog } from "../RestoreDialog";

/**
 * Minimal ``runs`` row shape — enough for the Restore button.
 *
 * A STRUCTURAL SUBSET of `LineageRunSummary`, so callers can pass either.
 * Keeping the narrow interface lets the helpers be tested without pulling in
 * the full lineage type graph.
 */
export interface RunRecordForRestore {
  run_id: string;
  workflow_id: string;
  workflow_git_commit: string | null;
  /** ISO-8601 start time, used to label the target in the dialog heading. */
  started_at?: string;
}

/**
 * Label the restore target in the dialog heading.
 *
 * Prefers the run's start time — "the state as of when this ran" is how a user
 * thinks about a run — and falls back to the short run id when the row has no
 * timestamp (only possible for a malformed record).
 */
export function restoreTargetLabel(run: RunRecordForRestore): string {
  if (run.started_at) {
    const parsed = new Date(run.started_at);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleString();
    }
  }
  return `run ${run.run_id.slice(0, 8)}`;
}

/**
 * The recovery hint shown after a restore that had to commit dirty work first.
 *
 * ADR-039 Addendum 1 (#1354): the backend auto-commits uncommitted changes
 * before overlaying the historical content, so "restore" never means "lose
 * what I was doing". Naming the commit is what makes that legible.
 *
 * Exported and rendered by the caller rather than by `RestoreRunButton`: the
 * button sits in a `flex items-center` row, and a full sentence inside that
 * row stretches the flex item and shoves the next button far to the right. A
 * notice belongs on its own line.
 */
export function restoreAutoCommitHint(autoCommitSha: string): string {
  return `Your unsaved changes were committed as ${autoCommitSha.slice(0, 7)} before the restore — see History to get back to them.`;
}

interface RestoreRunButtonProps {
  run: RunRecordForRestore;
  /**
   * Fired after a successful restore so the parent (LineageTab / RunDetail
   * consumer) can refresh the canvas + the GitStatusBadge, and surface the
   * recovery hint. ``autoCommitSha`` is null when the tree was already clean
   * and nothing needed committing.
   */
  onRestored?: (autoCommitSha: string | null) => void;
}

/**
 * "Restore" button per ADR-038 Addendum 1 §11.1. Disabled when
 * ``workflow_git_commit`` is null (auto-commit was off, failed, or the run
 * pre-dates the feature).
 */
export function RestoreRunButton({ run, onRestored }: RestoreRunButtonProps) {
  const [dialogOpen, setDialogOpen] = useState(false);

  const commitSha = run.workflow_git_commit;

  return (
    <div className="run-detail__restore" data-testid="run-detail-restore">
      <button
        type="button"
        className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:bg-stone-400"
        data-testid="run-detail-restore-button"
        disabled={!commitSha}
        onClick={() => setDialogOpen(true)}
        title={
          commitSha
            ? `Restore the project to how it was at commit ${commitSha.slice(0, 7)}`
            : "No recorded git commit for this run — restore unavailable"
        }
      >
        Restore
      </button>
      {dialogOpen && commitSha && (
        <RestoreDialog
          commitSha={commitSha}
          targetLabel={restoreTargetLabel(run)}
          runId={run.run_id}
          onClose={() => setDialogOpen(false)}
          onRestored={(autoCommitSha) => onRestored?.(autoCommitSha)}
        />
      )}
    </div>
  );
}
