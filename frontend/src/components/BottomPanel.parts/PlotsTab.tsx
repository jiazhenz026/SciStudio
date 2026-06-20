import { AlertTriangle, Plus, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../../lib/api";
import { plotTargetFromRunResponse } from "../../lib/api/data";
import { useAppStore } from "../../store";
import type { PlotListItem } from "../../types/api";
import { NewPlotDialog } from "../NewPlotDialog";
import { RelinkPlotDialog } from "../RelinkPlotDialog";

/**
 * #1713 — dedicated Plots panel.
 *
 * Renders the workflow-wide plot list (previously a cramped chip row atop the
 * Preview panel, PR #1712) as card entries: name, linked block, language,
 * broken/needs-relink badge, Run, and Relink — plus a New plot action. This is
 * a presentation refactor: the relink + broken-detection backend
 * (`GET /api/plots`, `POST /api/plots/{id}/relink`) is unchanged.
 *
 * Running a plot publishes its result to `plotPreviewTarget` in the store so it
 * still renders in the right-hand Preview panel (`DataPreview`), keeping the
 * Run behavior identical to the pre-#1713 chip row.
 */
export function PlotsTab() {
  const workflowId = useAppStore((s) => s.workflowId);
  const selectedNodeId = useAppStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const setPlotPreviewTarget = useAppStore((s) => s.setPlotPreviewTarget);
  const openFileTab = useAppStore((s) => s.openFileTab);
  const bumpProjectTreeRefresh = useAppStore((s) => s.bumpProjectTreeRefresh);
  const setLastError = useAppStore((s) => s.setLastError);

  const [plots, setPlots] = useState<PlotListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  // #1713 — run errors are shown inline on the failing plot's card banner, so
  // the error is tied to a specific plot_id rather than a single global string.
  const [runError, setRunError] = useState<{ plotId: string; message: string } | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [relinkTarget, setRelinkTarget] = useState<PlotListItem | null>(null);
  const [newPlotOpen, setNewPlotOpen] = useState(false);
  // Bumped after relink / create so the list re-fetches. Also re-runs whenever
  // the tab is (re)mounted — BottomPanel unmounts inactive tabs, so switching
  // to Plots refreshes the list.
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setListError(null);
    api
      .listPlots({ workflowId })
      .then((result) => {
        if (!cancelled) setPlots(result.plots);
      })
      .catch((error: unknown) => {
        if (!cancelled) setListError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId, refreshToken]);

  async function handleRun(plot: PlotListItem) {
    setRunningId(plot.plot_id);
    setRunError(null);
    try {
      const result = await api.runPlotJob({ plot_id: plot.plot_id });
      const nextTarget = plotTargetFromRunResponse(result);
      if (!nextTarget) {
        setRunError({
          plotId: plot.plot_id,
          message: result.errors[0] ?? `Plot run ${result.status}.`,
        });
        return;
      }
      setPlotPreviewTarget(nextTarget);
      // #1713 followup — select the plot's linked block so the Preview header
      // shows the block name (not "Select a node") and the result sits beside
      // its source. Skip broken plots: the bound node no longer exists.
      if (!plot.broken) {
        setSelectedNodeId(plot.node_id);
      }
    } catch (error) {
      setRunError({
        plotId: plot.plot_id,
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setRunningId(null);
    }
  }

  const showEmpty = !loading && !listError && plots.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-[0.65rem] uppercase tracking-[0.25em] text-stone-400">
          Plots — this workflow
        </p>
        <button
          className="inline-flex items-center gap-1 rounded-full border border-stone-300 bg-white px-3 py-1 text-xs font-medium text-stone-700 hover:border-ink disabled:opacity-50"
          disabled={!workflowId}
          onClick={() => setNewPlotOpen(true)}
          title="Create a new plot"
          type="button"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          New plot
        </button>
      </div>

      {loading ? <p className="text-xs text-stone-500">Loading plots...</p> : null}

      {showEmpty ? (
        <div className="rounded-[1.4rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
          No plots in this workflow yet. Use “New plot” to bind one to a block output.
        </div>
      ) : null}

      {/* #1713 — 4 cards per row (grid). Cards are near-square (a bit taller
          than the chip row, still rectangular); title and link text wrap
          instead of truncating. language + Run + Relink sit on the bottom row. */}
      <div className="grid grid-cols-4 gap-3">
        {plots.map((plot) => {
          const linkLabel = plot.display_label || `${plot.node_id} / ${plot.output_port}`;
          const name = plot.title || plot.plot_id;
          return (
            <div
              className={`flex min-h-[9rem] flex-col gap-1.5 rounded-2xl border p-3 shadow-sm ${
                plot.broken ? "border-amber-400 bg-amber-50/50" : "border-stone-200 bg-white"
              }`}
              data-testid={`plot-card-${plot.plot_id}`}
              key={plot.plot_id}
            >
              <div className="flex min-w-0 items-start gap-1.5">
                {plot.broken ? (
                  <AlertTriangle
                    aria-label="Broken target — needs relink"
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
                  />
                ) : null}
                <span className="break-words text-sm font-medium text-ink" title={name}>
                  {name}
                </span>
              </div>

              <p className="break-words text-xs text-stone-500" title={linkLabel}>
                → {linkLabel}
              </p>

              {/* #1713 — language on its own row, Run/Relink right-aligned
                  below it, so a wide language label (e.g. "python") never
                  pushes the buttons out of a narrow 4-up card. */}
              <div className="mt-auto flex flex-col gap-2 pt-1">
                <span className="self-start rounded bg-stone-100 px-2 py-0.5 text-[0.65rem] uppercase tracking-wide text-stone-500">
                  {plot.language}
                </span>
                <div className="flex items-center justify-end gap-1.5">
                  <button
                    aria-label={`Run plot ${name}`}
                    className="shrink-0 rounded-full bg-ink px-2.5 py-1 text-xs text-white disabled:opacity-50"
                    disabled={runningId !== null}
                    onClick={() => void handleRun(plot)}
                    type="button"
                  >
                    {runningId === plot.plot_id ? "Running" : "Run"}
                  </button>
                  <button
                    aria-label={`Relink data source for plot ${name}`}
                    className="shrink-0 rounded-full border border-stone-300 px-2.5 py-1 text-xs text-stone-600 hover:text-ink disabled:opacity-50"
                    disabled={runningId !== null}
                    onClick={() => setRelinkTarget(plot)}
                    title="Relink data source"
                    type="button"
                  >
                    Relink
                  </button>
                </div>
              </div>

              {/* #1713 — narrow status banner under the buttons: amber relink
                  prompt for a broken target, red banner for a failed Run. */}
              {plot.broken ? (
                <div className="flex items-center gap-1 rounded-md bg-amber-100 px-2 py-1 text-[0.65rem] text-amber-700">
                  <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                  <span>Needs relink — reconnect the data source</span>
                </div>
              ) : null}
              {runError?.plotId === plot.plot_id ? (
                <div
                  className="flex items-start gap-1 rounded-md bg-red-100 px-2 py-1 text-[0.65rem] text-red-700"
                  role="alert"
                >
                  <XCircle className="mt-px h-3 w-3 shrink-0" aria-hidden="true" />
                  <span className="break-words">{runError.message}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {listError ? (
        <div
          className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
          role="status"
        >
          {listError}
        </div>
      ) : null}

      <RelinkPlotDialog
        open={relinkTarget !== null}
        plot={relinkTarget}
        workflowId={workflowId}
        onClose={() => setRelinkTarget(null)}
        onRelinked={(result) => {
          if (!result.valid && relinkTarget) {
            setRunError({
              plotId: relinkTarget.plot_id,
              message: result.errors[0] ?? "Relinked plot did not validate.",
            });
          } else {
            setRunError(null);
          }
          setRefreshToken((token) => token + 1);
        }}
      />
      <NewPlotDialog
        open={newPlotOpen}
        workflowId={workflowId}
        selectedNodeId={selectedNodeId}
        onClose={() => setNewPlotOpen(false)}
        onCreated={(created) => {
          bumpProjectTreeRefresh();
          openFileTab(created.script_path);
          setLastError(created.warnings.length > 0 ? created.warnings.join("\n") : null);
          setRefreshToken((token) => token + 1);
        }}
      />
    </div>
  );
}
