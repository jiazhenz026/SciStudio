/*
 * frontend/src/components/Lineage/RunDetail.tsx — ADR-038 §3.8 right pane.
 *
 * STRUCTURE (post-#1422 split)
 * ----------------------------
 *
 * The orchestrator that composes the header + blocks list + footer
 * affordances. Heavy presentational subtrees and helpers were moved to
 * `RunDetail.parts/` so each file stays under the 500-LOC ceiling:
 *
 *   - `parts/format.ts`              — `formatLocalDateTime`, `formatDuration`
 *   - `parts/RunDetailHeader.tsx`    — metadata header + parent-run link
 *   - `parts/PartialRerunBanner.tsx` — ADR-038 §3.6a banner
 *   - `parts/restore.tsx`            — `RestoreWorkflowButton`, `runRestoreWorkflow`,
 *                                      `workflowYamlPathForRun`, `RunRecordForRestore`
 *
 * The named exports below are re-exports from `parts/restore.tsx` so the
 * Phase 3.5 integration test (`RunDetail.restore.test.tsx`) continues to
 * import them directly from `./RunDetail`.
 */

import type { ReactElement } from "react";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import { BlockExecutionCard } from "./BlockExecutionCard";
import { PartialRerunBanner } from "./RunDetail.parts/PartialRerunBanner";
import { RestoreWorkflowButton } from "./RunDetail.parts/restore";
import { RunDetailHeader } from "./RunDetail.parts/RunDetailHeader";

// Re-exports for the ADR-039 Restore helpers. `RunDetail.restore.test.tsx`
// imports these names directly from `./RunDetail`; keeping the re-export
// avoids touching the test file's import paths post-split.
export type { RunRecordForRestore } from "./RunDetail.parts/restore";
export {
  RestoreWorkflowButton,
  runRestoreWorkflow,
  workflowYamlPathForRun,
} from "./RunDetail.parts/restore";

export function RunDetail(): ReactElement {
  const selectedRunId = useAppStore((s) => s.selectedRunId);
  const detail = useAppStore((s) => (selectedRunId ? s.runDetails[selectedRunId] : undefined));
  const loading = useAppStore((s) => (selectedRunId ? s.runDetailLoading[selectedRunId] : false));
  const error = useAppStore((s) => (selectedRunId ? s.runDetailError[selectedRunId] : null));
  const openMethodsDialog = useAppStore((s) => s.openMethodsDialog);
  const openRerunDialog = useAppStore((s) => s.openRerunDialog);
  const selectRun = useAppStore((s) => s.selectRun);

  if (selectedRunId === null) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="run-detail-empty">
        <p className="text-sm text-stone-500">Select a run on the left to see its detail.</p>
      </div>
    );
  }

  if (loading && detail === undefined) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="run-detail-loading">
        <p className="text-sm text-stone-500">Loading run detail…</p>
      </div>
    );
  }

  if (error && detail === undefined) {
    return (
      <div
        className="m-4 rounded-2xl border border-rose-200 bg-rose-50 p-4"
        data-testid="run-detail-error"
      >
        <p className="text-sm text-rose-700">{error}</p>
      </div>
    );
  }

  if (detail === undefined) {
    // Fallback: should not normally hit this state.
    return (
      <div className="flex h-full items-center justify-center" data-testid="run-detail-empty">
        <p className="text-sm text-stone-500">Select a run on the left to see its detail.</p>
      </div>
    );
  }

  const run = detail.run;
  const isRunning = run.status === "running";
  const inlineError = error ?? null;

  return (
    <section
      className="flex h-full flex-col"
      data-testid="run-detail"
      role="region"
      aria-label={`Detail for run ${run.run_id}`}
    >
      <RunDetailHeader run={run} inlineError={inlineError} selectRun={selectRun} />

      <PartialRerunBanner run={run} selectRun={selectRun} />

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" data-testid="run-detail-blocks">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
          Blocks ({detail.blocks.length})
        </h4>
        {detail.blocks.length === 0 ? (
          <p className="mt-2 text-xs text-stone-500">(No blocks executed)</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {detail.blocks.map((blk) => (
              <li key={blk.block_execution_id}>
                <BlockExecutionCard execution={blk} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <footer
        className="flex items-center gap-2 border-t border-stone-200 px-4 py-3"
        data-testid="run-detail-actions"
      >
        <button
          type="button"
          className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:bg-stone-400"
          data-testid="run-detail-rerun-button"
          aria-disabled={isRunning}
          disabled={isRunning}
          title={isRunning ? "Wait for run to finish" : undefined}
          onClick={() => openRerunDialog(run.run_id)}
        >
          Re-run
        </button>
        <button
          type="button"
          className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
          data-testid="run-detail-methods-button"
          onClick={() => openMethodsDialog(run.run_id)}
        >
          Export methods
        </button>
        {/*
         * ADR-039 §6 Phase 4 — Restore this run's workflow.
         *
         * Phase 3.5 integration: the Restore affordance is rendered in
         * the RunDetail footer alongside Re-run and Export methods. The
         * button issues a ``gitRestore`` call scoped to the run's
         * workflow YAML at the captured ``workflow_git_commit`` SHA,
         * implementing the soft-restore semantics from
         * ADR-038 §3.8 / ADR-039 §6 Phase 4. Disabled when
         * ``workflow_git_commit`` is null (degraded-mode run).
         *
         * #1400 hotfix: the parent now wires ``onRestored`` so the
         * canvas refreshes after the YAML is rewritten on disk. Without
         * this callback the gitRestore succeeded but the canvas kept
         * showing the in-memory snapshot from before — the WS
         * ``workflow.changed`` watcher is unreliable for git-checkout
         * file replacements on Windows (#1322). If the same workflow is
         * currently open we refetch and replace its slice in place;
         * otherwise we openTab so the user sees the just-restored state.
         */}
        <RestoreWorkflowButton
          run={run}
          onRestored={() => {
            void (async () => {
              try {
                const fresh = await api.getWorkflow(run.workflow_id);
                const store = useAppStore.getState();
                if (store.workflowId === run.workflow_id) {
                  store.setWorkflow(fresh);
                } else {
                  store.openTab(fresh, run.workflow_id);
                }
              } catch (err) {
                // best-effort — the gitRestore itself already succeeded;
                // worst case the user can refresh manually via the file
                // tree. Surface to console for diagnosis.
                // eslint-disable-next-line no-console
                console.warn("[RunDetail] canvas refresh after restore failed:", err);
              }
            })();
          }}
        />
      </footer>
    </section>
  );
}
