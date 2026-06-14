import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api";
import type { PlotCreateResponse, PlotLanguage, PlotTargetItem } from "../types/api";

interface NewPlotDialogProps {
  open: boolean;
  workflowId?: string | null;
  selectedNodeId?: string | null;
  saveWorkflow?: () => Promise<void>;
  onClose: () => void;
  onCreated: (created: PlotCreateResponse) => void;
}

function slugifyPlotId(raw: string): string {
  return raw
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^A-Za-z0-9_-]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^[^A-Za-z0-9]+/, "")
    .slice(0, 64);
}

function describePlotTarget(target: PlotTargetItem): string {
  const nodeLabel = target.node_label || target.node_id;
  const workflowLabel = target.workflow_id || target.workflow_path;
  const typeLabel = target.output_type ? ` (${target.output_type})` : "";
  const pendingLabel = target.latest_output_available ? "" : " [run workflow first]";
  return `${nodeLabel} / ${target.output_port}${typeLabel} - ${workflowLabel}${pendingLabel}`;
}

function orderedPlotTargets(targets: PlotTargetItem[], selectedNodeId?: string | null) {
  return [...targets].sort((a, b) => {
    const aSelected = selectedNodeId && a.node_id === selectedNodeId ? 0 : 1;
    const bSelected = selectedNodeId && b.node_id === selectedNodeId ? 0 : 1;
    if (aSelected !== bSelected) return aSelected - bSelected;
    return describePlotTarget(a).localeCompare(describePlotTarget(b));
  });
}

export function NewPlotDialog({
  open,
  workflowId,
  selectedNodeId,
  saveWorkflow,
  onClose,
  onCreated,
}: NewPlotDialogProps) {
  const [title, setTitle] = useState("my_plot");
  const [language, setLanguage] = useState<PlotLanguage>("python");
  const [targets, setTargets] = useState<PlotTargetItem[]>([]);
  const [targetId, setTargetId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const saveWorkflowRef = useRef(saveWorkflow);

  useEffect(() => {
    saveWorkflowRef.current = saveWorkflow;
  }, [saveWorkflow]);

  const orderedTargets = useMemo(
    () => orderedPlotTargets(targets, selectedNodeId),
    [selectedNodeId, targets],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setTitle("my_plot");
    setLanguage("python");
    setTargetId("");
    setError(null);
    setLoading(true);

    async function loadTargets() {
      try {
        if (workflowId && saveWorkflowRef.current) {
          await saveWorkflowRef.current();
        }
        const response = await api.listPlotTargets({
          workflowId,
          includeUnavailable: true,
        });
        if (cancelled) return;
        const ordered = orderedPlotTargets(response.targets, selectedNodeId);
        setTargets(response.targets);
        const selected =
          ordered.find((target) => selectedNodeId && target.node_id === selectedNodeId) ??
          ordered[0];
        setTargetId(selected?.target_id ?? "");
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
  }, [open, selectedNodeId, workflowId]);

  if (!open) return null;

  async function handleSubmit() {
    const trimmed = title.trim();
    const plotId = slugifyPlotId(trimmed);
    if (!trimmed) {
      setError("Plot name must not be empty.");
      return;
    }
    if (!plotId) {
      setError("Plot name must start with a letter or digit.");
      return;
    }
    if (!targetId) {
      setError("Choose a block output.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createPlot({
        plot_id: plotId,
        target_id: targetId,
        title: trimmed,
        language,
      });
      onCreated(created);
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
            <h2 className="mt-2 font-display text-2xl text-ink">New plot</h2>
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
            Name
            <input
              autoFocus
              className="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              onChange={(event) => setTitle(event.currentTarget.value)}
              value={title}
            />
          </label>

          <label className="block text-sm font-medium text-stone-700">
            Language
            <select
              className="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-ink"
              onChange={(event) => setLanguage(event.currentTarget.value as PlotLanguage)}
              value={language}
            >
              <option value="python">Python</option>
              <option value="r">R</option>
            </select>
          </label>

          <label className="block text-sm font-medium text-stone-700">
            Bind to
            <select
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
            {submitting ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
