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
 *   - `parts/restore.tsx`            — `RestoreRunButton`, `restoreTargetLabel`,
 *                                      `RunRecordForRestore`
 *
 * The named exports below are re-exports from `parts/restore.tsx` so the
 * Phase 3.5 integration test (`RunDetail.restore.test.tsx`) continues to
 * import them directly from `./RunDetail`.
 */

import { useEffect, useState, type ReactElement } from "react";

import { api } from "../../lib/api";
import { useAppStore } from "../../store";
import { BlockExecutionCard } from "./BlockExecutionCard";
import { PartialRerunBanner } from "./RunDetail.parts/PartialRerunBanner";
import { RestoreRunButton, restoreAutoCommitHint } from "./RunDetail.parts/restore";
import { RunDetailHeader } from "./RunDetail.parts/RunDetailHeader";

// Re-exports for the Restore helpers. `RunDetail.restore.test.tsx` imports
// these names directly from `./RunDetail`; keeping the re-export avoids
// touching the test file's import paths post-split.
export type { RunRecordForRestore } from "./RunDetail.parts/restore";
export {
  RestoreRunButton,
  restoreTargetLabel,
  restoreAutoCommitHint,
} from "./RunDetail.parts/restore";

export function RunDetail(): ReactElement {
  // Post-restore recovery hint, owned here rather than by `RestoreRunButton`
  // so it can render on its own line below the action row (see the footer).
  const [autoCommitHint, setAutoCommitHint] = useState<string | null>(null);
  const selectedRunId = useAppStore((s) => s.selectedRunId);
  const detail = useAppStore((s) => (selectedRunId ? s.runDetails[selectedRunId] : undefined));
  const loading = useAppStore((s) => (selectedRunId ? s.runDetailLoading[selectedRunId] : false));
  const error = useAppStore((s) => (selectedRunId ? s.runDetailError[selectedRunId] : null));
  const openMethodsDialog = useAppStore((s) => s.openMethodsDialog);
  const selectRun = useAppStore((s) => s.selectRun);

  // The hint describes one restore of one run. Selecting a different run makes
  // it stale, so drop it rather than leaving it attached to the wrong record.
  useEffect(() => {
    setAutoCommitHint(null);
  }, [selectedRunId]);

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

      {/*
       * The footer stacks: an action row, and below it the post-restore
       * recovery hint. The hint used to render inside `RestoreRunButton`,
       * which made it a child of the action row's flex item — a full sentence
       * there stretched that item and pushed "Export methods" far right.
       */}
      <footer className="border-t border-stone-200 px-4 py-3" data-testid="run-detail-actions">
        <div className="flex items-center gap-2">
          {/*
           * ADR-039 §6 Phase 4, rewritten by ADR-038 Addendum 1 §11.1
           * (#2033). Restore is the only action in this footer — the Re-run
           * button went in #1721 and the rest of that feature in #2033. The
           * button opens `RestoreDialog`, which runs the §3.6 preflight and
           * then restores the FULL TREE at the run's `workflow_git_commit`.
           * It used to restore only `workflows/<id>.yaml`, which could not
           * recover a broken custom block — the defect #2033 fixes.
           * Disabled when `workflow_git_commit` is null (degraded-mode run).
           *
           * #1400 hotfix: the parent wires ``onRestored`` so the canvas
           * refreshes after the YAML is rewritten on disk — the WS
           * ``workflow.changed`` watcher is unreliable for git-checkout
           * file replacements on Windows (#1322). If the same workflow is
           * currently open we refetch and replace its slice in place;
           * otherwise we openTab so the user sees the just-restored state.
           */}
          <RestoreRunButton
            run={run}
            onRestored={(autoCommitSha) => {
              setAutoCommitHint(autoCommitSha ? restoreAutoCommitHint(autoCommitSha) : null);
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
          <button
            type="button"
            className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
            data-testid="run-detail-methods-button"
            onClick={() => openMethodsDialog(run.run_id)}
          >
            Export methods
          </button>
        </div>
        {autoCommitHint && (
          <p
            className="run-detail__restore-auto-commit-hint mt-2 text-xs text-stone-600"
            role="status"
            data-testid="run-detail-restore-auto-commit-hint"
          >
            {autoCommitHint}
          </p>
        )}
      </footer>
    </section>
  );
}
