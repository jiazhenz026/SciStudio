/**
 * ADR-039 §6 Phase 4 — "Restore this run's workflow" helpers + button.
 *
 * Extracted from `RunDetail.tsx` (#1422). These helpers were authored
 * on `track/adr-039/git-versioning` and overlaid into the ADR-038
 * full-body `RunDetail.tsx`; the structural overlay is retained, but
 * the implementation lives here so each file stays ≤ 500 LOC.
 *
 * `RunRecordForRestore` is a STRUCTURAL SUBSET of `LineageRunSummary`
 * (run_id, workflow_id, workflow_git_commit are all present in the
 * ADR-038 wire type), so callers can pass either. We keep the narrow
 * interface so the helpers stay testable without pulling the full
 * lineage type graph.
 *
 * The names below are re-exported from `RunDetail.tsx` so existing
 * `import { RestoreWorkflowButton, runRestoreWorkflow,
 * workflowYamlPathForRun } from "./RunDetail"` keeps compiling
 * (e.g. `RunDetail.restore.test.tsx`).
 */

import { useState } from "react";

import { api } from "../../../lib/api";

/**
 * Minimal ``runs`` row shape — enough for the Restore button.
 *
 * ADR-038 §3.1 ``runs`` columns referenced:
 * - ``run_id`` — opaque ID used by the Lineage list.
 * - ``workflow_git_commit`` — ADR-039 join key (may be ``null`` for
 *   degraded-mode runs that pre-date the auto-commit hook).
 * - ``workflow_id`` — used to resolve the YAML file scope for restore.
 */
export interface RunRecordForRestore {
  run_id: string;
  workflow_id: string;
  workflow_git_commit: string | null;
}

/**
 * Resolve the on-disk workflow YAML path for a run.
 *
 * The path layout is fixed by ``ApiRuntime.workflow_path``:
 * ``<project>/workflows/<workflow_id>.yaml``. The git engine works in
 * project-relative paths, so the leading ``<project>/`` is dropped.
 */
export function workflowYamlPathForRun(run: { workflow_id: string }): string {
  return `workflows/${run.workflow_id}.yaml`;
}

/**
 * Issue the ``gitRestore`` call for a given run's workflow YAML.
 *
 * Exported separately so the integration test can verify the exact
 * request body without rendering the React component. Failures bubble
 * up to the caller — the button below catches them and renders a
 * short error string.
 */
export async function runRestoreWorkflow(
  run: RunRecordForRestore,
): Promise<{ status: "ok"; auto_commit_sha: string | null }> {
  if (!run.workflow_git_commit) {
    throw new Error("This run has no recorded git commit (degraded mode). Restore unavailable.");
  }
  // ADR-039 Addendum 1 (#1354): the backend auto-commits any dirty
  // working-tree state BEFORE the soft restore and returns
  // `auto_commit_sha`. We forward the full result so the caller can
  // surface "Your unsaved changes were committed as <sha>" — the
  // user-reported Lineage-Restore confusion was specifically the
  // pre-addendum amber "stashed as <id>" message; this replacement
  // copy uses language the four-op user model already understands.
  const result = await api.gitRestore({
    commit_sha: run.workflow_git_commit,
    files: [workflowYamlPathForRun(run)],
  });
  return result;
}

interface RestoreWorkflowButtonProps {
  run: RunRecordForRestore;
  /**
   * Optional callback fired on successful restore so the parent
   * (LineageTab / RunDetail consumer) can refresh the canvas + the
   * GitStatusBadge. No-op by default.
   */
  onRestored?: () => void;
}

/**
 * "Restore this run's workflow" button per ADR-038 §3.8 + ADR-039 §6
 * Phase 4. Disabled when ``workflow_git_commit`` is null (auto-commit
 * was off or pre-feature run).
 */
export function RestoreWorkflowButton({ run, onRestored }: RestoreWorkflowButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // ADR-039 Addendum 1 (#1354): replaces the pre-addendum amber
  // "stashed as <id>" hint. The user-reported Lineage Restore
  // confusion was caused by stash drawer language the four-op user
  // model does not include. Copy now uses History tab terminology
  // every user already understands.
  const [autoCommitHint, setAutoCommitHint] = useState<string | null>(null);

  const disabled = busy || !run.workflow_git_commit;

  const handleClick = async () => {
    setError(null);
    setAutoCommitHint(null);
    setBusy(true);
    try {
      const result = await runRestoreWorkflow(run);
      if (result.auto_commit_sha) {
        setAutoCommitHint(
          `Your unsaved changes were committed as ${result.auto_commit_sha.slice(0, 7)} before the restore — see History tab to revert if unintended.`,
        );
      }
      onRestored?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="run-detail__restore" data-testid="run-detail-restore">
      <button
        type="button"
        className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink disabled:opacity-50"
        data-testid="run-detail-restore-button"
        disabled={disabled}
        onClick={handleClick}
        title={
          run.workflow_git_commit
            ? `Restore workflow YAML to commit ${run.workflow_git_commit.slice(0, 7)}`
            : "No recorded git commit for this run — restore unavailable"
        }
      >
        {busy ? "Restoring..." : "Restore this run's workflow"}
      </button>
      {error && (
        <div
          className="run-detail__restore-error mt-1 text-xs text-rose-700"
          role="alert"
          data-testid="run-detail-restore-error"
        >
          {error}
        </div>
      )}
      {autoCommitHint && !error && (
        <div
          className="run-detail__restore-auto-commit-hint mt-1 text-xs text-stone-600"
          role="status"
          data-testid="run-detail-restore-auto-commit-hint"
        >
          {autoCommitHint}
        </div>
      )}
    </div>
  );
}
