/**
 * ADR-054 spec 4 (T-012) — packaging, its report, and the confirm (FR-028).
 *
 * The toolbar's package control does not package. It asks
 * `POST /api/explore/sessions/{id}/packaging/check` — the route that writes
 * nothing — and renders the answer: for a clean notebook the slice cells and
 * the ports packaging would infer, and for a refused one the offending cells
 * and the names they read, with confirm disabled.
 *
 * **The report is the runtime's, in full.** `PackagingCheckResponse` carries
 * `is_packageable`, and `check_packaging` is the only thing entitled to decide
 * it: `PackagingPlan.is_packageable` is "no problem refuses", and packaging
 * itself re-checks on the confirm. Nothing here re-derives that answer. The
 * refusal *list* is filtered out of `problems` only to say which entries to
 * put first — a duplicate output declaration is reported and resolved rather
 * than refused, and burying it among refusals would misreport it.
 *
 * **Confirm is the second request.** `POST .../package` is what writes the
 * block; the runtime publishes `explore.packaged`, the slice stores it, and
 * the palette refreshes off that event (FR-029). This module writes no block
 * into any local list — the packaged block appears because the runtime said it
 * exists.
 *
 * TODO(#2253): the report card dismisses on its own control and on a successful
 *   package, not on an outside click or Escape.
 *   Out of scope per the ADR-054 assembly dispatch: the palette's shared
 *   popover closes on pointer-leave, which is the wrong gesture for a card
 *   carrying a text field, so this wants a helper neither surface has yet.
 *   Followup: docs/planning/adr-054-assembly-followups.md, `F-A4-009`.
 */

import { useCallback, useState } from "react";

import { exploreApi } from "../lib/api/explore";
import { useAppStore } from "../store";
import type { ExploreSessionState } from "../store/types";
import type {
  ExplorePackagedPort,
  ExplorePackagingCheckResponse,
  ExplorePackagingProblem,
} from "../types/api";

/** How a packaged block answers a new input: replay the notebook, or ask. */
export type OnNewInput = "replay" | "ask";

/**
 * The problems that stop the notebook being packaged.
 *
 * `refuses` is the runtime's own flag; this only partitions the list so the
 * report can lead with the refusals and still show the rest.
 */
export function refusalsOf(report: ExplorePackagingCheckResponse): ExplorePackagingProblem[] {
  return report.problems.filter((problem) => problem.refuses);
}

/** The problems packaging resolved on the way past rather than refused. */
export function noticesOf(report: ExplorePackagingCheckResponse): ExplorePackagingProblem[] {
  return report.problems.filter((problem) => !problem.refuses);
}

/**
 * Whether confirm may be pressed.
 *
 * Two conditions, and both are the runtime's: `is_packageable` is its verdict,
 * and an empty refusal list is that verdict's evidence. They agree for every
 * response the backend builds; requiring both means a response that somehow
 * disagreed with itself refuses rather than packages.
 */
export function canConfirmPackaging(
  report: ExplorePackagingCheckResponse | null,
  blockName: string,
): boolean {
  if (!report) return false;
  if (!report.is_packageable) return false;
  if (refusalsOf(report).length > 0) return false;
  return blockName.trim().length > 0;
}

/**
 * A stable React key for one problem.
 *
 * `check_packaging` reports at most one problem per kind, so the kind alone
 * would do; the cells and names are folded in anyway so a future second entry
 * of the same kind does not silently share a key with the first.
 */
function problemKey(problem: ExplorePackagingProblem): string {
  return `${problem.kind}:${problem.cell_ids.join(",")}:${problem.names.join(",")}`;
}

function PortRow({ port }: { port: ExplorePackagedPort }) {
  return (
    <li className="font-mono text-[11px] text-stone-600" data-testid="explore-packaging-port">
      <span className={port.direction === "input" ? "text-pine" : "text-ember"}>
        {port.direction}
      </span>{" "}
      {port.name} : <span className="text-ink">{port.data_type}</span>
      <span className="text-stone-400"> ← {port.bound_name}</span>
    </li>
  );
}

function ProblemRow({ problem }: { problem: ExplorePackagingProblem }) {
  return (
    <li
      className={`text-[11px] leading-snug ${problem.refuses ? "text-red-700" : "text-stone-500"}`}
      data-problem-kind={problem.kind}
      data-refuses={problem.refuses ? "true" : "false"}
      data-testid="explore-packaging-problem"
    >
      <span className="font-medium">{problem.message}</span>
      {problem.cell_ids.length > 0 ? (
        <span
          className="ml-1 font-mono text-stone-500"
          data-testid="explore-packaging-problem-cells"
        >
          cells: {problem.cell_ids.join(", ")}
        </span>
      ) : null}
      {problem.names.length > 0 ? (
        <span
          className="ml-1 font-mono text-stone-500"
          data-testid="explore-packaging-problem-names"
        >
          reads: {problem.names.join(", ")}
        </span>
      ) : null}
    </li>
  );
}

export interface PackagingReportProps {
  report: ExplorePackagingCheckResponse;
  blockName: string;
  onBlockName: (value: string) => void;
  onNewInput: OnNewInput;
  onOnNewInput: (value: OnNewInput) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  /** A request is in flight; confirm is held rather than sent twice. */
  busy: boolean;
  /** The refusal the confirm came back with, when one did. */
  error: string | null;
}

/** The rendered report. Presentational: it decides nothing the runtime decided. */
export function PackagingReport({
  report,
  blockName,
  onBlockName,
  onNewInput,
  onOnNewInput,
  onConfirm,
  onDismiss,
  busy,
  error,
}: PackagingReportProps) {
  const refusals = refusalsOf(report);
  const notices = noticesOf(report);
  const confirmable = canConfirmPackaging(report, blockName);

  return (
    <div
      className="absolute z-30 mt-1 w-[26rem] rounded-lg border border-stone-300 bg-white p-3 shadow-panel"
      data-packageable={report.is_packageable ? "true" : "false"}
      data-testid="explore-packaging-report"
    >
      <div className="flex items-center justify-between">
        <p className="font-display text-sm text-ink">Package this notebook</p>
        <button
          className="toolbar-button"
          data-testid="explore-packaging-dismiss"
          onClick={onDismiss}
          type="button"
        >
          Close
        </button>
      </div>

      {refusals.length > 0 ? (
        <div className="mt-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-red-700">
            Cannot package
          </p>
          <ul className="mt-1 space-y-1" data-testid="explore-packaging-refusals">
            {refusals.map((problem) => (
              <ProblemRow key={problemKey(problem)} problem={problem} />
            ))}
          </ul>
        </div>
      ) : (
        <div className="mt-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
            The slice
          </p>
          <ul className="mt-1 flex flex-wrap gap-1" data-testid="explore-packaging-slice">
            {report.cells.map((cellId) => (
              <li
                className="rounded border border-stone-300 px-1.5 py-0.5 font-mono text-[11px] text-stone-600"
                data-testid="explore-packaging-slice-cell"
                key={cellId}
              >
                {cellId}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-stone-500">
            The ports
          </p>
          <ul className="mt-1 space-y-0.5" data-testid="explore-packaging-ports">
            {report.inputs.map((port) => (
              <PortRow key={`in-${port.name}`} port={port} />
            ))}
            {report.outputs.map((port) => (
              <PortRow key={`out-${port.name}`} port={port} />
            ))}
          </ul>
        </div>
      )}

      {notices.length > 0 ? (
        <ul className="mt-2 space-y-1" data-testid="explore-packaging-notices">
          {notices.map((problem) => (
            <ProblemRow key={problemKey(problem)} problem={problem} />
          ))}
        </ul>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        <input
          aria-label="Block name"
          className="min-w-0 flex-1 rounded border border-stone-300 px-2 py-1 text-xs outline-none focus:border-ember"
          data-testid="explore-packaging-name"
          onChange={(event) => onBlockName(event.target.value)}
          placeholder="Block name"
          value={blockName}
        />
        <select
          aria-label="On new input"
          className="rounded border border-stone-300 px-1 py-1 text-xs"
          data-testid="explore-packaging-on-new-input"
          onChange={(event) => onOnNewInput(event.target.value as OnNewInput)}
          value={onNewInput}
        >
          <option value="replay">Replay</option>
          <option value="ask">Ask</option>
        </select>
        <button
          className="toolbar-button"
          data-testid="explore-packaging-confirm"
          disabled={!confirmable || busy}
          onClick={onConfirm}
          type="button"
        >
          {busy ? "Packaging…" : "Package"}
        </button>
      </div>

      {error ? (
        <p className="mt-2 text-[11px] text-red-700" data-testid="explore-packaging-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface PackagingControlProps {
  /** `undefined` until the open lands; the control waits rather than guesses. */
  session: ExploreSessionState | undefined;
}

/**
 * The toolbar's package control (FR-014's `package`, FR-028's flow).
 *
 * Pressing it requests the check first, every time: a report held from a
 * previous press would describe a notebook that has since been edited, and
 * FR-028's whole point is that the person decides against the current one.
 */
export function PackagingControl({ session }: PackagingControlProps) {
  const applyExplorePackagingReport = useAppStore((state) => state.applyExplorePackagingReport);
  const report = session?.lastReport ?? null;

  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [packaging, setPackaging] = useState(false);
  const [blockName, setBlockName] = useState("");
  const [onNewInput, setOnNewInput] = useState<OnNewInput>("replay");
  const [error, setError] = useState<string | null>(null);

  const sessionId = session?.sessionId ?? "";

  const requestCheck = useCallback(async () => {
    if (!sessionId) return;
    setChecking(true);
    setError(null);
    try {
      const response = await exploreApi.checkExplorePackaging(sessionId);
      applyExplorePackagingReport(sessionId, response);
      setOpen(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setOpen(true);
    } finally {
      setChecking(false);
    }
  }, [applyExplorePackagingReport, sessionId]);

  const confirm = useCallback(async () => {
    if (!sessionId || !canConfirmPackaging(report, blockName)) return;
    setPackaging(true);
    setError(null);
    try {
      await exploreApi.packageExploreSession(sessionId, {
        block_name: blockName.trim(),
        on_new_input: onNewInput,
      });
      // Nothing is written here. The runtime publishes `explore.packaged`, the
      // slice records it, and the palette refreshes off that event (FR-029).
      setOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPackaging(false);
    }
  }, [blockName, onNewInput, report, sessionId]);

  return (
    <span className="relative inline-flex items-center">
      <button
        className="toolbar-button"
        data-testid="explore-package-button"
        disabled={!sessionId || checking}
        onClick={() => void requestCheck()}
        type="button"
      >
        {checking ? "Checking…" : "Package"}
      </button>
      {open && report ? (
        <PackagingReport
          blockName={blockName}
          busy={packaging}
          error={error}
          onBlockName={setBlockName}
          onConfirm={() => void confirm()}
          onDismiss={() => setOpen(false)}
          onNewInput={onNewInput}
          onOnNewInput={setOnNewInput}
          report={report}
        />
      ) : null}
      {open && !report && error ? (
        <span className="ml-2 text-[11px] text-red-700" data-testid="explore-packaging-error">
          {error}
        </span>
      ) : null}
    </span>
  );
}
