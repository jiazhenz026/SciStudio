/*
 * frontend/src/components/Lineage/RunsList.tsx — ADR-038 §3.8 left pane
 * =====================================================================
 *
 * SKELETON ONLY. Function body throws `new Error("TODO: D38-2.4c — ...")`.
 *
 * Purpose
 * -------
 * Reverse-chronological list of runs (per ADR-038 §3.8 mock). Each row
 * surfaces enough info to identify a run at a glance, supports click-to-
 * select (which drives the right pane), and visually distinguishes the
 * selected row, running rows (per OQ-3 — tentative show-all-states-with-
 * spinner), and re-run children (parent_run_id !== null).
 *
 * Props
 * -----
 * Accepts NO props. Reads/writes via useAppStore().lineageSlice.
 *
 * State consumed
 * --------------
 *   - runs (LineageRunSummary[])
 *   - runsLoading
 *   - runsError
 *   - selectedRunId
 *   - selectRun(runId)
 *
 * Sort policy
 * -----------
 * Display order is `runs` AS-RECEIVED from the server. The backend route
 * `/api/runs` (D38-2.4a) is responsible for sorting by `started_at DESC`
 * per ADR-038 §3.1 (`idx_runs_workflow` is `workflow_id, started_at DESC`).
 * The client does NOT re-sort — that would mask a server contract bug.
 *
 * Layout markup pseudocode (vitest selectors)
 * -------------------------------------------
 *
 *   <ul
 *     className="flex h-full flex-col overflow-y-auto"
 *     role="listbox"
 *     aria-label="Run history"
 *     data-testid="runs-list"
 *   >
 *     {runs.map((run) => (
 *       <li
 *         key={run.run_id}
 *         role="option"
 *         aria-selected={run.run_id === selectedRunId}
 *         data-testid={`runs-list-row-${run.run_id}`}
 *         className={cx(
 *           "cursor-pointer border-b border-stone-200 px-4 py-3",
 *           run.run_id === selectedRunId && "bg-stone-100",
 *         )}
 *         onClick={() => selectRun(run.run_id)}
 *         onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") selectRun(run.run_id); }}
 *         tabIndex={0}
 *       >
 *         <div className="flex items-center gap-2">
 *           <StatusIcon status={run.status} />  // ✓ / ✗ / ⟳ / ⊘
 *           <span className="text-sm font-medium text-ink">
 *             {formatLocalDateTime(run.started_at)}
 *           </span>
 *           <span className="text-xs text-stone-500">{run.status}</span>
 *         </div>
 *         <p className="mt-1 text-xs text-stone-600">
 *           {run.workflow_id} · {formatDuration(run)} · {run.block_count} block(s)
 *         </p>
 *         {run.workflow_git_commit && (
 *           <p className="text-[11px] text-stone-500">
 *             git: {run.workflow_git_commit.slice(0, 7)}
 *             {run.workflow_dirty && " (dirty)"}
 *           </p>
 *         )}
 *         {run.parent_run_id && (
 *           <p className="text-[11px] text-stone-500" data-testid="rerun-marker">
 *             ↳ Re-run of {run.parent_run_id.slice(0, 8)}
 *             {run.execute_from_block_id && ` (from ${run.execute_from_block_id})`}
 *           </p>
 *         )}
 *       </li>
 *     ))}
 *   </ul>
 *
 * Status icon mapping
 * -------------------
 *   completed  → "✓" (text-emerald-600)
 *   failed     → "✗" (text-rose-600)
 *   cancelled  → "⊘" (text-stone-500)
 *   running    → "⟳" (text-amber-600, animated spin class)
 *
 *   Icons MUST be wrapped in <span aria-hidden="true"> with a sibling
 *   <span className="sr-only"> carrying the textual status, so screen
 *   readers announce "completed run" / "failed run" / etc.
 *
 * Duration formatting
 * -------------------
 *   formatDuration(run):
 *     - if run.duration_ms !== null:
 *         "<n>ms" if <1s, "<n.n>s" if <60s, "<n>m <n>s" otherwise
 *     - if run.status === "running":
 *         compute live elapsed = now - parseISO(started_at);
 *         render with a 1s tick (useEffect setInterval); cleanup on unmount.
 *     - else (running but no started_at?): render "—"
 *
 *   The 1s tick only runs while at least one row has status="running" to
 *   avoid wasted re-renders on a 100-run list.
 *
 * Date formatting
 * ---------------
 *   formatLocalDateTime(iso):
 *     - Today:        "14:30:42"
 *     - Yesterday:    "yesterday 14:30"
 *     - This year:    "May 13, 14:30"
 *     - Older:        "2025-12-04 14:30"
 *
 *   Implementation hint: use Intl.DateTimeFormat with locale="en-US".
 *
 * Copy strings (English, freeze)
 * ------------------------------
 *   Empty state: "No runs yet. Run a workflow to populate this view."
 *   Loading state: "Loading runs…"
 *   Re-run row prefix: "↳ Re-run of "
 *   "Re-run of {parent} (from {block})" when execute_from_block_id is set
 *
 * Accessibility
 * -------------
 *   - role="listbox" + role="option" pattern (NOT a <button> list — the
 *     ARIA listbox spec maps to a single selection model exactly like this)
 *   - aria-selected on each option reflects selectedRunId
 *   - tabIndex={0} on each row so arrow-keys can move focus (ADR keyboard
 *     shortcut is owned by LineageTab; this component just makes rows
 *     focusable)
 *   - sr-only text for the status icon
 *
 * Edge cases
 * ----------
 *   1. Empty (runs.length === 0): render <p data-testid="runs-list-empty">
 *      with copy "No runs yet. Run a workflow to populate this view."
 *   2. Initial load (runsLoading && runs.length === 0): render <p
 *      data-testid="runs-list-loading"> with "Loading runs…"
 *   3. Refresh (runsLoading && runs.length > 0): keep rows visible; no
 *      blocking overlay. A subtle top-of-list spinner is acceptable but not
 *      required.
 *   4. Error (runsError): rendered by LineageTab as a banner; RunsList
 *      itself just shows whatever rows it has.
 *   5. Selected run got deleted: selectedRunId might not match any row.
 *      RunsList renders unchanged (no row is selected); RunDetail handles
 *      the "Run not found" case.
 *   6. >500 runs: v1 renders all rows. List virtualization (@tanstack/
 *      react-virtual) is a future polish issue if 500+ becomes common.
 *      Do NOT add virtualization in this skeleton.
 *
 * Test plan (RunsList.test.tsx)
 * -----------------------------
 *   1. renders one row per run with [data-testid=runs-list-row-{run_id}]
 *   2. clicking a row dispatches selectRun(run_id)
 *   3. selected row has aria-selected="true"
 *   4. empty state renders [data-testid=runs-list-empty]
 *   5. parent_run_id renders [data-testid=rerun-marker]
 *   6. status icon has sr-only text matching run.status
 *   7. running row updates duration once per second (use vi.useFakeTimers)
 */

import { useEffect, useState, type ReactElement } from "react";

import { useAppStore } from "../../store";
import type {
  LineageRunStatus,
  LineageRunSummary,
} from "../../types/lineage";

const STATUS_LABEL: Record<LineageRunStatus, string> = {
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
  running: "running",
};

const STATUS_GLYPH: Record<LineageRunStatus, string> = {
  completed: "✓",
  failed: "✗",
  cancelled: "⊘",
  running: "⟳",
};

const STATUS_COLOR: Record<LineageRunStatus, string> = {
  completed: "text-emerald-600",
  failed: "text-rose-600",
  cancelled: "text-stone-500",
  running: "text-amber-600",
};

/**
 * Hotfix #998: solid background pill colors for the RunsList status
 * pill. The pill is the primary visual content of each row; timestamp
 * is demoted to a small right-aligned label. The text-color variant
 * (`STATUS_COLOR` above) is retained for RunDetail.tsx's header which
 * uses StatusIcon's glyph + text-color pair.
 */
const STATUS_PILL_BG: Record<LineageRunStatus, string> = {
  completed: "bg-emerald-600 text-white",
  failed: "bg-rose-600 text-white",
  cancelled: "bg-slate-500 text-white",
  running: "bg-amber-500 text-white",
};

function StatusIcon({ status }: { status: LineageRunStatus }): ReactElement {
  return (
    <>
      <span aria-hidden="true" className={STATUS_COLOR[status]}>
        {STATUS_GLYPH[status]}
      </span>
      <span className="sr-only">{STATUS_LABEL[status]}</span>
    </>
  );
}

function formatLocalDateTime(iso: string, now: Date): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  const sameDay =
    parsed.getFullYear() === now.getFullYear() &&
    parsed.getMonth() === now.getMonth() &&
    parsed.getDate() === now.getDate();
  if (sameDay) {
    return parsed.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    parsed.getFullYear() === yesterday.getFullYear() &&
    parsed.getMonth() === yesterday.getMonth() &&
    parsed.getDate() === yesterday.getDate();
  if (isYesterday) {
    const time = parsed.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return `yesterday ${time}`;
  }
  if (parsed.getFullYear() === now.getFullYear()) {
    return parsed.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  const date = parsed.toISOString().slice(0, 10);
  const time = parsed.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} ${time}`;
}

function formatDuration(
  run: LineageRunSummary,
  nowMs: number,
): string {
  let ms: number | null = run.duration_ms;
  if (ms === null && run.status === "running" && run.started_at) {
    const started = Date.parse(run.started_at);
    if (!Number.isNaN(started)) {
      ms = Math.max(0, nowMs - started);
    }
  }
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSeconds = Math.floor(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${s}s`;
}

export function RunsList(): ReactElement {
  const runs = useAppStore((s) => s.runs);
  const runsLoading = useAppStore((s) => s.runsLoading);
  const selectedRunId = useAppStore((s) => s.selectedRunId);
  const selectRun = useAppStore((s) => s.selectRun);

  // Live tick once per second while any row is running. Skip otherwise.
  const hasRunning = runs.some((r) => r.status === "running");
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!hasRunning) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [hasRunning]);
  const now = new Date(nowMs);

  if (runsLoading && runs.length === 0) {
    return (
      <p
        className="px-4 py-3 text-xs text-stone-500"
        data-testid="runs-list-loading"
      >
        Loading runs…
      </p>
    );
  }

  if (runs.length === 0) {
    return (
      <p
        className="px-4 py-3 text-xs text-stone-500"
        data-testid="runs-list-empty"
      >
        No runs yet. Run a workflow to populate this view.
      </p>
    );
  }

  return (
    <ul
      className="flex h-full flex-col overflow-y-auto"
      role="listbox"
      aria-label="Run history"
      data-testid="runs-list"
    >
      {runs.map((run) => {
        const selected = run.run_id === selectedRunId;
        const rowClass = [
          "cursor-pointer border-b border-stone-200 px-4 py-3",
          selected ? "bg-stone-100" : "hover:bg-stone-50",
        ].join(" ");
        return (
          <li
            key={run.run_id}
            role="option"
            aria-selected={selected}
            data-testid={`runs-list-row-${run.run_id}`}
            className={rowClass}
            onClick={() => selectRun(run.run_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                selectRun(run.run_id);
              }
            }}
            tabIndex={0}
          >
            {/*
              Hotfix #998: status pill becomes the row's primary visual
              content. Timestamp moves to the right as a small grey
              label. The pill carries the status text directly so
              screen readers read e.g. "completed" without the icon
              fallback.
            */}
            <div className="flex items-center justify-between gap-3">
              <span
                className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide ${
                  STATUS_PILL_BG[run.status]
                }`}
                data-testid={`runs-list-row-${run.run_id}-status-pill`}
              >
                {STATUS_LABEL[run.status]}
              </span>
              <span
                className="text-xs text-stone-500"
                data-testid={`runs-list-row-${run.run_id}-timestamp`}
              >
                {formatLocalDateTime(run.started_at, now)}
              </span>
            </div>
            <p className="mt-1 text-xs text-stone-600">
              {run.workflow_id} · {formatDuration(run, nowMs)}
              {run.block_count !== null && ` · ${run.block_count} block(s)`}
            </p>
            {run.workflow_git_commit && (
              <p className="text-[11px] text-stone-500">
                git: {run.workflow_git_commit.slice(0, 7)}
                {run.workflow_dirty && " (dirty)"}
              </p>
            )}
            {run.parent_run_id && (
              <p
                className="text-[11px] text-stone-500"
                data-testid="rerun-marker"
              >
                ↳ Re-run of {run.parent_run_id.slice(0, 8)}
                {run.execute_from_block_id &&
                  ` (from ${run.execute_from_block_id})`}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
