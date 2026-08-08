/**
 * Restore confirmation dialog — ADR-038 Addendum 1 §11.4 (#2033).
 *
 * The single confirmation surface for Restore, shared by the Git tab's history
 * rows and the Run history tab's run detail. It replaces `RerunDialog` (whose
 * shell it reuses) and the Git tab's `window.confirm`.
 *
 * Two things it must get right, both of which the surfaces it replaces got
 * wrong:
 *
 * 1. **Scope.** Restore rewrites the whole project tree at the target commit —
 *    workflows, custom blocks, scripts, notes. The Run history button used to
 *    restore one workflow YAML and say nothing about it, which is why a user
 *    who had broken a block could restore "the run that worked" and watch it
 *    fail again. The copy states the real scope before the user commits to it.
 *
 * 2. **What is not covered.** Nothing outside the project folder is restored:
 *    SciStudio's own version, installed packages, the Python environment, and
 *    the input data files. The preflight names the drift it can see; the copy
 *    names the boundary.
 */

import { useState, type ReactElement } from "react";

import { api } from "../../lib/api";
import { PreflightReport } from "./RestoreDialog.parts/PreflightReport";
import { useRestorePreflight } from "./RestoreDialog.parts/useRestorePreflight";

export interface RestoreDialogProps {
  /** Full SHA to restore the working tree to. */
  commitSha: string;
  /**
   * Human-readable identification of the target, rendered in the heading —
   * a commit subject from the Git tab, or a run's start time from Run history.
   */
  targetLabel: string;
  /**
   * The run this restore was launched from, when there is one. Run history
   * passes it; the Git tab restores an arbitrary commit and has none.
   *
   * Several runs can share a commit — the pre-run auto-commit is skipped on an
   * already-clean tree — so without this the preflight compares against the
   * newest run at that SHA, which may be a subsequent failure rather than the
   * run the user chose.
   */
  runId?: string;
  onClose: () => void;
  /**
   * Fired after a successful restore with the auto-commit SHA the backend
   * created for uncommitted work (null when the tree was already clean), so
   * the caller can refresh its view and surface the recovery hint.
   */
  onRestored?: (autoCommitSha: string | null) => void;
}

export function RestoreDialog({
  commitSha,
  targetLabel,
  runId,
  onClose,
  onRestored,
}: RestoreDialogProps): ReactElement {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { preflight, loading, error } = useRestorePreflight(commitSha, onClose, runId);

  async function handleConfirm(): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    let autoCommitSha: string | null = null;
    try {
      // No `files` argument: this is a full-tree restore. ADR-038 Addendum 1
      // §11.1 — the narrow single-YAML variant is what made Restore unable to
      // recover a broken block, which is the defect this issue exists to fix.
      const result = await api.gitRestore({ commit_sha: commitSha });
      autoCommitSha = result.auto_commit_sha ?? null;
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
      return;
    }
    // The restore landed. A downstream refresh failure must not leave the
    // dialog open inviting a second restore of the same commit.
    onRestored?.(autoCommitSha);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="restore-dialog-title"
        data-testid="restore-dialog"
        className="w-[640px] max-w-[90vw] rounded-3xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3">
          <h2 id="restore-dialog-title" className="text-lg font-semibold text-ink">
            Restore · {targetLabel}
          </h2>
          <button
            type="button"
            aria-label="Close"
            className="ml-auto rounded-full p-2 hover:bg-stone-100"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <p className="mt-2 text-sm text-stone-600">
          This puts your whole project back to how it was at this version — workflows, custom
          blocks, scripts, and notes. Your current work is committed first, so you can get back to
          it from History.
        </p>
        <p className="mt-2 text-sm text-stone-600">
          Your data files are left alone, and so is your software environment.
        </p>

        {loading && (
          <p className="mt-3 text-sm text-stone-500" data-testid="restore-dialog-loading">
            Checking inputs and environment…
          </p>
        )}

        {!loading && <PreflightReport preflight={preflight} error={error} />}

        {submitError && (
          <p
            className="mt-3 rounded bg-rose-50 p-3 text-sm text-rose-700"
            aria-live="polite"
            data-testid="restore-dialog-submit-error"
          >
            {submitError}
          </p>
        )}

        <footer className="mt-5 flex items-center gap-2">
          <button
            type="button"
            className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:bg-stone-400"
            data-testid="restore-dialog-confirm"
            disabled={submitting || loading}
            onClick={() => {
              void handleConfirm();
            }}
          >
            {submitting ? "Restoring…" : "Restore"}
          </button>
          <button
            type="button"
            className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
            data-testid="restore-dialog-cancel"
            onClick={onClose}
          >
            Cancel
          </button>
        </footer>
      </div>
    </div>
  );
}
