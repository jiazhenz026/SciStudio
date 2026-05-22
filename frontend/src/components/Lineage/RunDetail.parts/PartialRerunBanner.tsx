/**
 * ADR-038 §3.6a — Partial re-run banner.
 *
 * Extracted from `RunDetail.tsx` (#1422).
 *
 * When a run starts mid-DAG via "Run from here", only blocks at or
 * downstream of `execute_from_block_id` actually executed. Upstream
 * blocks were reused from the parent run's checkpoint and therefore
 * have NO row in block_executions for this run. This banner makes that
 * explicit so the user does not assume the blocks list is incomplete
 * due to a bug. The canvas DAG renderer surfaces the same information
 * visually (per ADR §3.6a) by greying out the skipped upstream blocks.
 */

import type { ReactElement } from "react";

import type { LineageRunSummary } from "../../../types/lineage";

interface PartialRerunBannerProps {
  run: LineageRunSummary;
  selectRun: (runId: string) => void;
}

export function PartialRerunBanner({
  run,
  selectRun,
}: PartialRerunBannerProps): ReactElement | null {
  if (!run.execute_from_block_id) {
    return null;
  }
  return (
    <div
      className="mx-4 mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
      data-testid="run-detail-partial-rerun-banner"
      role="note"
    >
      <strong className="font-semibold">Partial re-run.</strong> Only blocks at or downstream of{" "}
      <code className="text-amber-900">{run.execute_from_block_id}</code> executed in this run.
      Upstream block outputs were reused from
      {run.parent_run_id ? (
        <>
          {" "}
          parent run{" "}
          <button
            type="button"
            className="underline decoration-dotted underline-offset-2 hover:text-amber-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
            data-testid="run-detail-partial-rerun-parent-link"
            onClick={() => run.parent_run_id && selectRun(run.parent_run_id)}
          >
            {run.parent_run_id.slice(0, 8)}
          </button>
          .
        </>
      ) : (
        " the previous run's checkpoint."
      )}
    </div>
  );
}
