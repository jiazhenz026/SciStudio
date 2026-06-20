import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import type { PlotListItem, PlotRelinkResponse, PlotTargetItem } from "../types/api";

interface RelinkPlotDialogProps {
  open: boolean;
  /** The plot whose data source is being relinked. */
  plot: PlotListItem | null;
  workflowId?: string | null;
  onClose: () => void;
  onRelinked: (result: PlotRelinkResponse) => void;
}

function describePlotTarget(target: PlotTargetItem): string {
  const nodeLabel = target.node_label || target.node_id;
  const workflowLabel = target.workflow_id || target.workflow_path;
  const typeLabel = target.output_type ? ` (${target.output_type})` : "";
  const pendingLabel = target.latest_output_available ? "" : " [run workflow first]";
  return `${nodeLabel} / ${target.output_port}${typeLabel} - ${workflowLabel}${pendingLabel}`;
}

function orderedPlotTargets(targets: PlotTargetItem[]): PlotTargetItem[] {
  return [...targets].sort((a, b) =>
    describePlotTarget(a).localeCompare(describePlotTarget(b)),
  );
}

/**
 * Relink a plot's data source (bug#7). A plot binds 1:1 to one node_id +
 * output_port. When the original block is deleted and re-created it gets a new
 * node id, leaving the plot's target broken. This dialog lists the current
 * workflow output targets and re-points the plot at the one the user picks via
 * `POST /api/plots/{plot_id}/relink`.
 */
export function RelinkPlotDialog({
  open,
  plot,
  workflowId,
  onClose,
  onRelinked,
}: RelinkPlotDialogProps) {
  const [targets, setTargets] = useState<PlotTargetItem[]>([]);
  const [targetId, setTargetId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const orderedTargets = useMemo(() => orderedPlotTargets(targets), [targets]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setTargetId("");
    setError(null);
    setLoading(true);

    async function loadTargets() {
      try {
        const response = await api.listPlotTargets({
          workflowId,
          includeUnavailable: true,
        });
        if (cancelled) return;
        const ordered = orderedPlotTargets(response.targets);
        setTargets(response.targets);
        // Default to the plot's current binding when it still resolves,
        // otherwise the first available target.
        const current = ordered.find(
          (target) =>
            plot != null &&
            target.node_id === plot.node_id &&
            target.output_port === plot.output_port,
        );
        setTargetId((current ?? ordered[0])?.target_id ?? "");
        if (ordered.length === 0) {
          setError("No block outputs are available to bind this plot.");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadTargets();
    return () => {
      cancelled = true;
    };
  }, [open, plot, workflowId]);

  if (!open || !plot) return null;

  async function handleSubmit() {
    if (!plot) return;
    if (!targetId) {
      setError("Choose a block output.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.relinkPlot(plot.plot_id, { target_id: targetId });
      onRelinked(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/55 p-4 backdrop-blur-sm">
      <div
        aria-modal="true"
        role="dialog"
        className="w-full max-w-xl rounded-[1.5rem] border border-stone-200 bg-stone-50 p-6 shadow-panel"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Plots</p>
            <h2 className="mt-2 font-display text-2xl text-ink">Relink data source</h2>
            <p className="mt-1 text-sm text-stone-500">{plot.title || plot.plot_id}</p>
          </div>
          <button
            className="rounded-full border border-stone-300 px-3 py-1 text-sm"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>

        <div className="space-y-4">
          <label className="block text-sm font-medium text-stone-700">
            Bind to
            <select
              aria-label="Bind to"
              className="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink disabled:bg-stone-100"
              disabled={loading || orderedTargets.length === 0}
              onChange={(event) => setTargetId(event.currentTarget.value)}
              value={targetId}
            >
              {loading ? <option value="">Loading...</option> : null}
              {!loading && orderedTargets.length === 0 ? (
                <option value="">No outputs</option>
              ) : null}
              {orderedTargets.map((target) => (
                <option key={target.target_id} value={target.target_id}>
                  {describePlotTarget(target)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-full border border-stone-300 px-4 py-2 text-sm"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-full bg-ink px-5 py-2 text-sm font-medium text-stone-50 transition hover:bg-pine disabled:opacity-50"
            disabled={loading || submitting || orderedTargets.length === 0}
            onClick={() => void handleSubmit()}
            type="button"
          >
            {submitting ? "Relinking..." : "Relink"}
          </button>
        </div>
      </div>
    </div>
  );
}
