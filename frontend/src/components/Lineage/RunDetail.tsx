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

import { useState } from "react";
import type { ReactElement } from "react";

import { api } from "../../lib/api";
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
  const selectRun = useAppStore((s) => s.selectRun);

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
      {/*
       * Hotfix #999: compact header so the blocks list — the primary
       * content per ADR-038 §3.8 — keeps most of the vertical space.
       * The 4-column auto/1fr/auto/1fr grid interleaves dt/dd pairs
       * horizontally: 5-8 metadata fields collapse from 7 rows (current
       * grid-cols-2) to ~3-4 rows. py-2 instead of py-3 + smaller heading
       * line-height save another ~10px. The Blocks section uses
       * `flex-1 overflow-y-auto` (line 421) so it absorbs the saved
       * vertical pixels.
       */}
      <header className="border-b border-stone-200 px-4 py-2">
        <h3 className="text-sm font-semibold leading-tight text-ink">
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
        <dl className="mt-1.5 grid grid-cols-[auto_1fr_auto_1fr] gap-x-3 gap-y-0.5 text-xs">
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
              <dd>
                <button
                  type="button"
                  className="rounded text-ink underline decoration-dotted underline-offset-2 hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                  data-testid="run-detail-parent-link"
                  title={`Open parent run ${run.parent_run_id}`}
                  onClick={() =>
                    run.parent_run_id && selectRun(run.parent_run_id)
                  }
                >
                  {run.parent_run_id.slice(0, 8)}
                </button>
              </dd>
            </>
          )}

          {run.execute_from_block_id && (
            <>
              <dt className="text-stone-500">Run-from block</dt>
              <dd>
                <code className="text-stone-700">
                  {run.execute_from_block_id}
                </code>
              </dd>
            </>
          )}
        </dl>
      </header>

      {/*
       * ADR-038 §3.6a — Partial re-run banner.
       *
       * When this run started mid-DAG via "Run from here", only blocks at or
       * downstream of execute_from_block_id actually executed. Upstream blocks
       * were reused from the parent run's checkpoint and therefore have NO
       * row in block_executions for this run. The banner makes that explicit
       * so the user does not assume the blocks list is incomplete due to a
       * bug.
       *
       * Per ADR §3.6a the canvas DAG renderer is the surface that greys out
       * the skipped upstream blocks; here in the run-detail panel we surface
       * the same information textually next to the blocks list header.
       */}
      {run.execute_from_block_id && (
        <div
          className="mx-4 mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
          data-testid="run-detail-partial-rerun-banner"
          role="note"
        >
          <strong className="font-semibold">Partial re-run.</strong> Only
          blocks at or downstream of{" "}
          <code className="text-amber-900">{run.execute_from_block_id}</code>{" "}
          executed in this run. Upstream block outputs were reused from
          {run.parent_run_id ? (
            <>
              {" "}
              parent run{" "}
              <button
                type="button"
                className="underline decoration-dotted underline-offset-2 hover:text-amber-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
                data-testid="run-detail-partial-rerun-parent-link"
                onClick={() =>
                  run.parent_run_id && selectRun(run.parent_run_id)
                }
              >
                {run.parent_run_id.slice(0, 8)}
              </button>
              .
            </>
          ) : (
            " the previous run's checkpoint."
          )}
        </div>
      )}

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
         */}
        <RestoreWorkflowButton run={run} />
      </footer>
    </section>
  );
}

// ===========================================================================
// ADR-039 §6 Phase 4 — Restore-this-run helpers
// ===========================================================================
//
// Phase 3.5 integration audit P1-4 (H-D1): these helpers were authored on
// `track/adr-039/git-versioning` and are now overlaid into the ADR-038
// full-body `RunDetail.tsx` so both surfaces co-exist:
//
//   - The default ADR-038 `RunDetail` (named export above) renders the
//     full right pane (header, blocks list, Re-run, Export methods,
//     Restore — the latter mounted inline above via `<RestoreWorkflowButton run={run} />`).
//   - These three named exports remain stable so the Phase 3.5 split
//     `RunDetail.restore.test.tsx` (the ADR-039 test file moved out of
//     the ADR-038 `RunDetail.test.tsx` per audit P2-3) keeps compiling.
//
// `RunRecordForRestore` is a STRUCTURAL SUBSET of `LineageRunSummary`
// (run_id, workflow_id, workflow_git_commit are all present in the
// ADR-038 wire type), so callers can pass either. We keep the narrow
// interface so the helpers stay testable without pulling the full
// lineage type graph.

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
): Promise<{ status: "ok" | "stashed"; stash_id?: string }> {
  if (!run.workflow_git_commit) {
    throw new Error(
      "This run has no recorded git commit (degraded mode). Restore unavailable.",
    );
  }
  // Hotfix #997: forward the backend's `status` / `stash_id` so the UI
  // can surface "Your unsaved changes were stashed as <id>" when the
  // working tree was dirty. Pre-fix the helper returned `void` and the
  // stash entry accumulated invisibly — repeat clicks under a dirty
  // tree piled up stash refs that confused users with "lots of new
  // commits" (stash refs render as commit nodes in the graph).
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
  // Hotfix #997: surface backend's stash status so dirty-tree restores
  // are not silent. The hint clears on the next click.
  const [stashHint, setStashHint] = useState<string | null>(null);

  const disabled = busy || !run.workflow_git_commit;

  const handleClick = async () => {
    setError(null);
    setStashHint(null);
    setBusy(true);
    try {
      const result = await runRestoreWorkflow(run);
      if (result.status === "stashed" && result.stash_id) {
        setStashHint(
          `Your unsaved changes were stashed as ${result.stash_id} — recover via Git tab → Stashes.`,
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
      {stashHint && !error && (
        <div
          className="run-detail__restore-stash-hint mt-1 text-xs text-amber-700"
          role="status"
          data-testid="run-detail-restore-stash-hint"
        >
          {stashHint}
        </div>
      )}
    </div>
  );
}
