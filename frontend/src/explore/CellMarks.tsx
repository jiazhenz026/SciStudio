/**
 * ADR-054 spec 4 (T-006) — the three marks, drawn (FR-012, FR-013).
 *
 * **This module computes nothing.** It is handed a `CellView` and renders the
 * `marks` array the runtime put there, in the runtime's own vocabulary —
 * `never_run`, `stale`, `out_of_order` — and the `outOfOrderReads` the runtime
 * named as the reason. There is no graph here, no comparison of sources, no
 * "this cell looks stale to me".
 *
 * FR-034 is why, and spec §4.5 states the failure it prevents: a mark computed
 * in the frontend and a mark computed in the session runtime would agree on
 * every easy notebook and disagree on exactly the ambiguous ones — a cell that
 * reads a name bound in two places, a cell disabled between runs — which are
 * the cases a person opens the notebook to understand.
 *
 * The one control here is FR-013's run-with-upstream, offered only on a cell
 * the runtime marked out of order, and it sends one command when clicked and
 * nothing at any other time.
 */

import type { CellView } from "../store/types";
import type { ExploreCellMarkKind } from "../types/ui";

/** How each of the runtime's three marks is worded and coloured. */
const MARK_PRESENTATION: Record<
  ExploreCellMarkKind,
  { label: string; className: string; title: string }
> = {
  never_run: {
    label: "never run",
    className: "border-stone-300 bg-stone-100 text-stone-600",
    title: "This kernel has not run this cell.",
  },
  stale: {
    label: "stale",
    className: "border-amber-300 bg-amber-50 text-amber-800",
    title: "A cell this one depends on has run since this cell last did.",
  },
  out_of_order: {
    label: "out of order",
    className: "border-rose-300 bg-rose-50 text-rose-800",
    title: "This cell read a name that a later cell bound.",
  },
};

/** The order marks are shown in, so two cells never disagree on arrangement. */
const MARK_ORDER: ExploreCellMarkKind[] = ["never_run", "stale", "out_of_order"];

export interface CellMarksProps {
  /** The cell as the slice holds it; `marks` is the runtime's own array. */
  cell: CellView;
  /** FR-013 — send run-with-upstream for this cell. */
  onRunWithUpstream: (cellId: string) => void;
  /** `true` while there is no session to send to. */
  disabled?: boolean;
}

/**
 * The marks on one cell, with the reason and the control an out-of-order mark
 * carries.
 *
 * Renders `null` for an unmarked cell rather than an empty strip: most cells in
 * a healthy notebook carry no mark, and a row of empty badge frames down the
 * whole notebook would be noise.
 */
export function CellMarks({ cell, onRunWithUpstream, disabled = false }: CellMarksProps) {
  const marks = MARK_ORDER.filter((mark) => cell.marks.includes(mark));
  if (marks.length === 0) return null;
  const outOfOrder = marks.includes("out_of_order");
  return (
    <div
      className="flex flex-wrap items-center gap-2 py-1"
      data-marks={marks.join(" ")}
      data-testid={`explore-cell-marks-${cell.cellId}`}
    >
      {marks.map((mark) => (
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${MARK_PRESENTATION[mark].className}`}
          data-testid={`explore-cell-mark-${mark}-${cell.cellId}`}
          key={mark}
          title={MARK_PRESENTATION[mark].title}
        >
          {MARK_PRESENTATION[mark].label}
        </span>
      ))}

      {outOfOrder ? (
        <>
          <span
            className="text-[11px] text-rose-800"
            data-testid={`explore-out-of-order-reason-${cell.cellId}`}
          >
            {cell.outOfOrderReads.length === 0
              ? "The runtime named no reads for this mark."
              : cell.outOfOrderReads
                  .map((read) =>
                    read.last_binder
                      ? `${read.name} (last bound by ${read.last_binder})`
                      : read.name,
                  )
                  .join(", ")}
          </span>
          <button
            className="rounded border border-rose-300 px-2 py-0.5 text-[11px] text-rose-800 hover:bg-rose-100 disabled:opacity-50"
            data-testid={`explore-run-with-upstream-${cell.cellId}`}
            disabled={disabled}
            onClick={() => onRunWithUpstream(cell.cellId)}
            type="button"
          >
            Run with upstream
          </button>
        </>
      ) : null}
    </div>
  );
}

export default CellMarks;
