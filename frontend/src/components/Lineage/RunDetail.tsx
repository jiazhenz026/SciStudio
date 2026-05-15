/*
 * frontend/src/components/Lineage/RunDetail.tsx — ADR-038 §3.8 right pane
 * =======================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 *
 * Purpose
 * -------
 * Right-pane detail surface. Renders metadata for the selected run +
 * an ordered list of BlockExecutionCard (one per block_executions row) +
 * the two primary affordances: Re-run and Export methods (ADR-038 §3.8).
 *
 * Props
 * -----
 * Accepts NO props. Reads from useAppStore().lineageSlice.
 *
 * State consumed
 * --------------
 *   - selectedRunId
 *   - runDetails[selectedRunId] (LineageRunDetail | undefined)
 *   - runDetailLoading[selectedRunId]
 *   - runDetailError[selectedRunId]
 *   - openMethodsDialog(runId)
 *   - openRerunDialog(runId)
 *
 * Layout markup pseudocode (vitest selectors)
 * -------------------------------------------
 *
 * Case 1 — selectedRunId === null:
 *
 *   <div
 *     className="flex h-full items-center justify-center"
 *     data-testid="run-detail-empty"
 *   >
 *     <p className="text-sm text-stone-500">
 *       Select a run on the left to see its detail.
 *     </p>
 *   </div>
 *
 * Case 2 — runDetailLoading[selectedRunId]:
 *
 *   <div data-testid="run-detail-loading">Loading run detail…</div>
 *
 * Case 3 — runDetailError[selectedRunId] !== null:
 *
 *   <div className="m-4 rounded-2xl border border-rose-200 bg-rose-50 p-4"
 *        data-testid="run-detail-error">
 *     <p className="text-sm text-rose-700">
 *       {runDetailError[selectedRunId]}
 *     </p>
 *   </div>
 *
 * Case 4 — happy path (detail !== undefined):
 *
 *   <section
 *     className="flex h-full flex-col"
 *     data-testid="run-detail"
 *     role="region"
 *     aria-label={`Detail for run ${detail.run.run_id}`}
 *   >
 *     <header className="border-b border-stone-200 px-4 py-3">
 *       <h3 className="text-sm font-semibold text-ink">
 *         Run {detail.run.run_id.slice(0, 8)}
 *       </h3>
 *       <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
 *         <dt className="text-stone-500">Workflow</dt>
 *         <dd>{detail.run.workflow_id}</dd>
 *
 *         <dt className="text-stone-500">Started</dt>
 *         <dd>{formatLocalDateTime(detail.run.started_at)}</dd>
 *
 *         <dt className="text-stone-500">Duration</dt>
 *         <dd>{formatDuration(detail.run)}</dd>
 *
 *         <dt className="text-stone-500">Status</dt>
 *         <dd>{detail.run.status}</dd>
 *
 *         <dt className="text-stone-500">Triggered by</dt>
 *         <dd>{detail.run.triggered_by}</dd>
 *
 *         {detail.run.workflow_git_commit && (
 *           <>
 *             <dt className="text-stone-500">Git commit</dt>
 *             <dd>
 *               {detail.run.workflow_git_commit.slice(0, 12)}
 *               {detail.run.workflow_dirty && " (dirty)"}
 *             </dd>
 *           </>
 *         )}
 *
 *         {detail.run.parent_run_id && (
 *           <>
 *             <dt className="text-stone-500">Parent run</dt>
 *             <dd>{detail.run.parent_run_id.slice(0, 8)}</dd>
 *           </>
 *         )}
 *
 *         {detail.run.execute_from_block_id && (
 *           <>
 *             <dt className="text-stone-500">Run-from block</dt>
 *             <dd>{detail.run.execute_from_block_id}</dd>
 *           </>
 *         )}
 *       </dl>
 *     </header>
 *
 *     <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
 *          data-testid="run-detail-blocks">
 *       <h4 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
 *         Blocks ({detail.blocks.length})
 *       </h4>
 *       <ul className="mt-2 space-y-2">
 *         {detail.blocks.map((blk) => (
 *           <li key={blk.block_execution_id}>
 *             <BlockExecutionCard execution={blk} />
 *           </li>
 *         ))}
 *       </ul>
 *     </div>
 *
 *     <footer className="flex items-center gap-2 border-t border-stone-200 px-4 py-3"
 *             data-testid="run-detail-actions">
 *       <button
 *         type="button"
 *         className="rounded-full bg-ink px-4 py-2 text-sm text-white"
 *         data-testid="run-detail-rerun-button"
 *         onClick={() => openRerunDialog(detail.run.run_id)}
 *       >
 *         Re-run
 *       </button>
 *       <button
 *         type="button"
 *         className="rounded-full border border-stone-300 bg-white px-4 py-2 text-sm text-ink"
 *         data-testid="run-detail-methods-button"
 *         onClick={() => openMethodsDialog(detail.run.run_id)}
 *       >
 *         Export methods
 *       </button>
 *     </footer>
 *   </section>
 *
 * Copy strings (English, freeze)
 * ------------------------------
 *   Empty (no selection): "Select a run on the left to see its detail."
 *   Loading:              "Loading run detail…"
 *   Re-run button label:  "Re-run"
 *   Export methods label: "Export methods"
 *   "Blocks (N)"          (where N = detail.blocks.length)
 *   "Parent run"          (label for parent_run_id row)
 *   "Run-from block"      (label for execute_from_block_id row)
 *
 * Edge cases
 * ----------
 *   1. detail.blocks.length === 0: render "(No blocks executed)" below the
 *      "Blocks" heading instead of an empty <ul>.
 *   2. detail.run.status === "running": footer buttons still render but
 *      Re-run is disabled with title="Wait for run to finish" — opening a
 *      re-run dialog on a live run is nonsensical.
 *   3. detail.run.status === "failed" / "cancelled": both buttons enabled
 *      (you may want to export the failed methods OR re-run with same
 *      params to retry).
 *   4. workflow_git_commit === null: omit the row entirely (do not render
 *      "git: (no commit)").
 *   5. environment_snapshot empty object: still safe; the Methods dialog
 *      handles env rendering — RunDetail does not show env inline.
 *
 * Accessibility
 * -------------
 *   - <section role="region" aria-label="Detail for run {id}"> at top
 *   - <dl> for the metadata grid (semantic correctness for screen readers)
 *   - Buttons have explicit type="button" (default in <form> would submit)
 *   - Re-run button disabled state surfaces via aria-disabled when running
 *
 * Keyboard
 * --------
 *   No new shortcuts beyond what LineageTab owns. Tab order: rerun button
 *   first, then methods button (matches visual order).
 *
 * Test plan (RunDetail.test.tsx)
 * ------------------------------
 *   1. selectedRunId===null renders [data-testid=run-detail-empty]
 *   2. loading state renders [data-testid=run-detail-loading]
 *   3. error state renders [data-testid=run-detail-error] with the message
 *   4. happy path renders [data-testid=run-detail] with header dl + blocks
 *   5. clicking [data-testid=run-detail-rerun-button] dispatches
 *      openRerunDialog(run_id)
 *   6. clicking [data-testid=run-detail-methods-button] dispatches
 *      openMethodsDialog(run_id)
 *   7. running status disables Re-run button (aria-disabled="true")
 *   8. parent_run_id renders a "Parent run" dt/dd pair
 */

import type { ReactElement } from "react";

import { useAppStore } from "../../store";
import type { LineageRunSummary } from "../../types/lineage";
import { BlockExecutionCard } from "./BlockExecutionCard";

function formatLocalDateTime(iso: string): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatDuration(run: LineageRunSummary): string {
  const ms = run.duration_ms;
  if (ms === null) {
    return run.status === "running" ? "in progress" : "—";
  }
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${s}s`;
}

export function RunDetail(): ReactElement {
  const selectedRunId = useAppStore((s) => s.selectedRunId);
  const detail = useAppStore((s) =>
    selectedRunId ? s.runDetails[selectedRunId] : undefined,
  );
  const loading = useAppStore((s) =>
    selectedRunId ? s.runDetailLoading[selectedRunId] : false,
  );
  const error = useAppStore((s) =>
    selectedRunId ? s.runDetailError[selectedRunId] : null,
  );
  const openMethodsDialog = useAppStore((s) => s.openMethodsDialog);
  const openRerunDialog = useAppStore((s) => s.openRerunDialog);

  if (selectedRunId === null) {
    return (
      <div
        className="flex h-full items-center justify-center"
        data-testid="run-detail-empty"
      >
        <p className="text-sm text-stone-500">
          Select a run on the left to see its detail.
        </p>
      </div>
    );
  }

  if (loading && detail === undefined) {
    return (
      <div
        className="flex h-full items-center justify-center"
        data-testid="run-detail-loading"
      >
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
      <div
        className="flex h-full items-center justify-center"
        data-testid="run-detail-empty"
      >
        <p className="text-sm text-stone-500">
          Select a run on the left to see its detail.
        </p>
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
      <header className="border-b border-stone-200 px-4 py-3">
        <h3 className="text-sm font-semibold text-ink">
          Run {run.run_id.slice(0, 8)}
        </h3>
        {inlineError && (
          <p
            className="mt-1 text-xs text-rose-700"
            data-testid="run-detail-stale-error"
          >
            {inlineError}
          </p>
        )}
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <dt className="text-stone-500">Workflow</dt>
          <dd>{run.workflow_id}</dd>

          <dt className="text-stone-500">Started</dt>
          <dd>{formatLocalDateTime(run.started_at)}</dd>

          <dt className="text-stone-500">Duration</dt>
          <dd>{formatDuration(run)}</dd>

          <dt className="text-stone-500">Status</dt>
          <dd>{run.status}</dd>

          <dt className="text-stone-500">Triggered by</dt>
          <dd>{run.triggered_by}</dd>

          {run.workflow_git_commit && (
            <>
              <dt className="text-stone-500">Git commit</dt>
              <dd>
                {run.workflow_git_commit.slice(0, 12)}
                {run.workflow_dirty && " (dirty)"}
              </dd>
            </>
          )}

          {run.parent_run_id && (
            <>
              <dt className="text-stone-500">Parent run</dt>
              <dd>{run.parent_run_id.slice(0, 8)}</dd>
            </>
          )}

          {run.execute_from_block_id && (
            <>
              <dt className="text-stone-500">Run-from block</dt>
              <dd>{run.execute_from_block_id}</dd>
            </>
          )}
        </dl>
      </header>

      <div
        className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
        data-testid="run-detail-blocks"
      >
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
      </footer>
    </section>
  );
}
