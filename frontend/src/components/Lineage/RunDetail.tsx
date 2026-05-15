/**
 * ADR-038 §3.8 / ADR-039 §3.5 — RunDetail right pane.
 *
 * D39-2.5 cross-track integration point: this component renders the
 * "Restore this run's workflow" affordance described in ADR-038 §3.8 +
 * ADR-039 §6 Phase 4. The button takes the captured
 * ``run.workflow_git_commit`` SHA (ADR-038 ``runs`` row, populated by
 * the ADR-039 ``start_workflow`` hook in ``api/runtime.py``) and calls
 * the ADR-039 ``gitRestore`` REST endpoint, passing the workflow YAML
 * path as the file scope. The result is a soft-restore of only the
 * workflow YAML to the exact state that produced this run — no
 * branch movement, no detached HEAD, no other files touched.
 *
 * Why this file lives on the ADR-039 tracking branch
 * ---------------------------------------------------
 * The full Lineage tab (skeleton + impl) lives on
 * ``track/adr-038/lineage-db`` (PRs #936, #937, #944, #951). On the
 * ADR-039 tracking branch where this PR lands, the Lineage tab is not
 * yet present. The dispatch for D39-2.5 explicitly authorizes this
 * single cross-track edit so the Restore affordance is wired into the
 * versioning REST surface before the Phase 4 final-merge PRs reconcile
 * both tracks into ``main``.
 *
 * Once the ADR-038 ``RunDetail.tsx`` lands on ``main``, the Phase 4
 * integration PR for ADR-039 merges that file's full body with the
 * ``RestoreWorkflowButton`` and ``runRestoreWorkflow`` defined here.
 * The exported names below are stable so the merge is a clean
 * additive overlay rather than a rewrite.
 */
import { useState } from "react";

import { api } from "../../lib/api";

/**
 * Minimal ``runs`` row shape — enough for the Restore button.
 *
 * The authoritative shape lives on ``track/adr-038/lineage-db`` in
 * ``frontend/src/types/api.ts`` (post-D38 integration). On this branch
 * we define only the fields the Restore affordance reads so the
 * component compiles standalone. When the tracks reconcile in Phase 4,
 * the broader ``RunRecord`` import replaces this local alias.
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
export async function runRestoreWorkflow(run: RunRecordForRestore): Promise<void> {
  if (!run.workflow_git_commit) {
    throw new Error(
      "This run has no recorded git commit (degraded mode). Restore unavailable.",
    );
  }
  await api.gitRestore({
    commit_sha: run.workflow_git_commit,
    files: [workflowYamlPathForRun(run)],
  });
}

interface RestoreWorkflowButtonProps {
  run: RunRecordForRestore;
  /**
   * Optional callback fired on successful restore so a parent (the
   * full Lineage tab on the integrated branch) can refresh the canvas
   * + GitStatusBadge. No-op by default.
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

  const disabled = busy || !run.workflow_git_commit;

  const handleClick = async () => {
    setError(null);
    setBusy(true);
    try {
      await runRestoreWorkflow(run);
      onRestored?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="run-detail__restore">
      <button
        type="button"
        className="btn btn-secondary"
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
        <div className="run-detail__restore-error" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

interface RunDetailProps {
  run: RunRecordForRestore;
  onRestored?: () => void;
}

/**
 * Minimal RunDetail right-pane stub for the ADR-039 tracking branch.
 *
 * On ``track/adr-038/lineage-db`` this file holds the full right-pane
 * implementation (header, parameter table, block execution list,
 * methods export button — see ADR-038 §3.8). Here we render only the
 * Restore button so the cross-track wiring is testable. The Phase 4
 * final-merge PR overlays the rest of the right pane on top of this
 * Restore affordance.
 */
export default function RunDetail({ run, onRestored }: RunDetailProps) {
  return (
    <div className="run-detail" data-testid="run-detail">
      <h2 className="run-detail__title">Run {run.run_id}</h2>
      <RestoreWorkflowButton run={run} onRestored={onRestored} />
    </div>
  );
}
