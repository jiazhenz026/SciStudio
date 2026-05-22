/**
 * Compact metadata header for the `RunDetail` right pane (ADR-038 §3.8).
 *
 * Extracted from `RunDetail.tsx` (#1422). Pure presentational — no fetch
 * calls, no store mutations beyond `selectRun` (parent-run navigation).
 *
 * Hotfix #999 narrative: the 4-column `auto/1fr/auto/1fr` grid was
 * chosen so the metadata block collapses to ~3-4 rows and the Blocks
 * section (which `RunDetail` mounts with `flex-1 overflow-y-auto`)
 * absorbs the freed vertical space. Keeping this section in its own
 * file makes the layout intent legible.
 */

import type { ReactElement } from "react";

import type { LineageRunSummary } from "../../../types/lineage";
import { formatDuration, formatLocalDateTime } from "./format";

interface RunDetailHeaderProps {
  run: LineageRunSummary;
  inlineError: string | null;
  selectRun: (runId: string) => void;
}

export function RunDetailHeader({
  run,
  inlineError,
  selectRun,
}: RunDetailHeaderProps): ReactElement {
  return (
    <header className="border-b border-stone-200 px-4 py-2">
      <h3 className="text-sm font-semibold leading-tight text-ink">Run {run.run_id.slice(0, 8)}</h3>
      {inlineError && (
        <p className="mt-1 text-xs text-rose-700" data-testid="run-detail-stale-error">
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
                onClick={() => run.parent_run_id && selectRun(run.parent_run_id)}
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
              <code className="text-stone-700">{run.execute_from_block_id}</code>
            </dd>
          </>
        )}
      </dl>
    </header>
  );
}
