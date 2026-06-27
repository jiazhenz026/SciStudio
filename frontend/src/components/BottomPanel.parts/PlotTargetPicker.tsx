import { ArrowLeft } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../lib/api";
import { describeReadableTargets } from "../../lib/plotTargetLabel";
import { useAppStore } from "../../store";
import type {
  PlotCreateResponse,
  PlotLanguage,
  PlotListItem,
  PlotRelinkResponse,
  PlotTargetItem,
} from "../../types/api";

/**
 * #1799 — in-panel plot target picker.
 *
 * Replaces the centered-modal NewPlotDialog / RelinkPlotDialog. It renders as a
 * content mode of the bottom Plots panel (cards ↔ picker) so the canvas stays
 * visible above it. Rows are a custom hoverable list (a native `<select>`
 * cannot emit per-option hover events); hovering or selecting a row sets the
 * shared `highlightedNodeId`, which the canvas rings and auto-centers.
 */
interface PlotTargetPickerProps {
  mode: "new" | "relink";
  /** Relink only: the plot whose data source is being repointed. */
  plot?: PlotListItem | null;
  workflowId?: string | null;
  /** New only: preselect the target bound to this node (the canvas selection). */
  defaultNodeId?: string | null;
  onClose: () => void;
  onCreated?: (created: PlotCreateResponse) => void;
  onRelinked?: (result: PlotRelinkResponse) => void;
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

/**
 * Order targets for display: the preferred node (relink current binding, or the
 * new-plot default selection) first, then by readable label. The disambiguation
 * index is computed separately and is stable against this sort.
 */
function orderedTargets(
  targets: PlotTargetItem[],
  preferredNodeId: string | null | undefined,
  labelOf: (target: PlotTargetItem) => string,
): PlotTargetItem[] {
  return [...targets].sort((a, b) => {
    const aPreferred = preferredNodeId && a.node_id === preferredNodeId ? 0 : 1;
    const bPreferred = preferredNodeId && b.node_id === preferredNodeId ? 0 : 1;
    if (aPreferred !== bPreferred) return aPreferred - bPreferred;
    return labelOf(a).localeCompare(labelOf(b));
  });
}

export function PlotTargetPicker({
  mode,
  plot,
  workflowId,
  defaultNodeId,
  onClose,
  onCreated,
  onRelinked,
}: PlotTargetPickerProps) {
  const blocks = useAppStore((s) => s.blocks);
  const blockSchemas = useAppStore((s) => s.blockSchemas);
  const setHighlightedNodeId = useAppStore((s) => s.setHighlightedNodeId);

  const [title, setTitle] = useState("my_plot");
  const [language, setLanguage] = useState<PlotLanguage>("python");
  const [targets, setTargets] = useState<PlotTargetItem[]>([]);
  const [targetId, setTargetId] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The node the picker preferences/preselects: relink → the plot's current
  // binding; new → the canvas selection.
  const preferredNodeId = mode === "relink" ? (plot?.node_id ?? null) : (defaultNodeId ?? null);

  const readable = useMemo(
    () => describeReadableTargets(targets, blocks, blockSchemas),
    [targets, blocks, blockSchemas],
  );
  const ordered = useMemo(
    () => orderedTargets(targets, preferredNodeId, (t) => readable.get(t.target_id)?.primary ?? ""),
    [targets, preferredNodeId, readable],
  );

  // node_id of the currently-selected target, so list mouse-leave can rest the
  // canvas highlight on the chosen block rather than clearing it.
  const selectedNodeId = useMemo(
    () => ordered.find((t) => t.target_id === targetId)?.node_id ?? null,
    [ordered, targetId],
  );

  // Clear the transient highlight when the picker unmounts.
  const setHighlightRef = useRef(setHighlightedNodeId);
  useEffect(() => {
    setHighlightRef.current = setHighlightedNodeId;
  }, [setHighlightedNodeId]);
  useEffect(() => () => setHighlightRef.current(null), []);

  useEffect(() => {
    let cancelled = false;
    setTitle("my_plot");
    setLanguage("python");
    setTargetId("");
    setError(null);
    setLoading(true);

    async function loadTargets() {
      try {
        const response = await api.listPlotTargets({ workflowId, includeUnavailable: true });
        if (cancelled) return;
        setTargets(response.targets);
        // Default to the preferred node when it resolves, else the first target.
        const labels = describeReadableTargets(response.targets, blocks, blockSchemas);
        const sorted = orderedTargets(
          response.targets,
          preferredNodeId,
          (t) => labels.get(t.target_id)?.primary ?? "",
        );
        // Relink defaults to the exact current binding (node + port); new-plot
        // defaults to any target on the canvas-selected node, else the first.
        const exact =
          mode === "relink" && plot
            ? sorted.find((t) => t.node_id === plot.node_id && t.output_port === plot.output_port)
            : undefined;
        const current =
          exact ??
          sorted.find((t) => preferredNodeId && t.node_id === preferredNodeId) ??
          sorted[0];
        setTargetId(current?.target_id ?? "");
        // Surface the default selection on the canvas immediately.
        setHighlightedNodeId(current?.node_id ?? null);
        if (sorted.length === 0) {
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
    // blocks/blockSchemas are only used to seed the default label sort; re-running
    // on every catalog change would reset the user's in-progress selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, plot?.plot_id, workflowId, preferredNodeId]);

  async function handleSubmit() {
    if (!targetId) {
      setError("Choose a block output.");
      return;
    }
    if (mode === "new") {
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
      setSubmitting(true);
      setError(null);
      try {
        const created = await api.createPlot({
          plot_id: plotId,
          target_id: targetId,
          title: trimmed,
          language,
        });
        onCreated?.(created);
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (!plot) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.relinkPlot(plot.plot_id, { target_id: targetId });
      onRelinked?.(result);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const heading = mode === "new" ? "New plot" : "Relink data source";
  const subheading = mode === "relink" ? plot?.title || plot?.plot_id : undefined;
  const submitLabel =
    mode === "new" ? (submitting ? "Creating…" : "Create") : submitting ? "Relinking…" : "Relink";

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <button
            aria-label="Back to plots"
            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-stone-300 bg-white px-2.5 py-1 text-xs text-stone-600 hover:border-ink"
            onClick={onClose}
            type="button"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Back
          </button>
          <p className="truncate text-[0.65rem] uppercase tracking-[0.25em] text-stone-400">
            {heading}
            {subheading ? (
              <span className="ml-2 normal-case tracking-normal text-stone-500">{subheading}</span>
            ) : null}
          </p>
        </div>
        <button
          className="shrink-0 rounded-full bg-ink px-4 py-1.5 text-xs font-medium text-stone-50 transition hover:bg-pine disabled:opacity-50"
          disabled={loading || submitting || ordered.length === 0}
          onClick={() => void handleSubmit()}
          type="button"
        >
          {submitLabel}
        </button>
      </div>

      {mode === "new" ? (
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs font-medium text-stone-600">
            Name
            <input
              autoFocus
              className="mt-1 w-48 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-ink"
              onChange={(event) => setTitle(event.currentTarget.value)}
              value={title}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-stone-600">
            Language
            <select
              className="mt-1 w-28 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-ink"
              onChange={(event) => setLanguage(event.currentTarget.value as PlotLanguage)}
              value={language}
            >
              <option value="python">Python</option>
              <option value="r">R</option>
            </select>
          </label>
        </div>
      ) : null}

      <p className="mb-1.5 text-[0.65rem] uppercase tracking-[0.2em] text-stone-400">
        Bind to a block output — hover to locate it on the canvas
      </p>

      {loading ? <p className="text-xs text-stone-500">Loading outputs…</p> : null}

      {/* Custom hoverable list (a native <select> cannot emit per-row hover).
          Resting the highlight on the selected node when the cursor leaves the
          list keeps the chosen block lit between interactions. */}
      <div
        className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1"
        onMouseLeave={() => setHighlightedNodeId(selectedNodeId)}
        role="listbox"
        aria-label="Block outputs"
      >
        {ordered.map((target) => {
          const desc = readable.get(target.target_id);
          const active = target.target_id === targetId;
          return (
            <button
              aria-selected={active}
              className={`flex w-full items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition ${
                active
                  ? "border-ink bg-stone-100"
                  : "border-stone-200 bg-white hover:border-stone-400 hover:bg-stone-50"
              }`}
              key={target.target_id}
              onClick={() => {
                setTargetId(target.target_id);
                setHighlightedNodeId(target.node_id);
              }}
              onMouseEnter={() => setHighlightedNodeId(target.node_id)}
              role="option"
              type="button"
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">
                {desc?.primary ?? target.output_port}
              </span>
              {desc?.outputType ? (
                <span className="shrink-0 rounded bg-stone-100 px-1.5 py-0.5 text-[0.65rem] uppercase tracking-wide text-stone-500">
                  {desc.outputType}
                </span>
              ) : null}
              {desc?.pending ? (
                <span className="shrink-0 text-[0.65rem] text-amber-600">run first</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
