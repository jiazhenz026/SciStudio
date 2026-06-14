import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import { plotTargetFromRunResponse } from "../lib/api/data";
import { useAppStore } from "../store";
import { buildPreviewCacheKey } from "../store/previewSlice";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  PlotListItem,
  PreviewTarget,
} from "../types/api";

import { PortInfoPanel } from "./DataPreview.parts/PortInfoPanel";
import { PreviewHost } from "./DataPreview.parts/PreviewHost";
import { extractRefEntries, type RefEntry } from "./DataPreview.parts/refEntries";

// Re-exports preserve the public surface of DataPreview.tsx for existing
// consumers (LossySaveWarning.tsx mirrors `extractRefEntries`).
export { extractRefEntries } from "./DataPreview.parts/refEntries";
export type { RefEntry } from "./DataPreview.parts/refEntries";

// ADR-048 SPEC 1 — the routed PreviewHost container and core fallback viewers.
// As of #1592 the live DataPreview mounts PreviewHost directly: every selected
// output ref creates a routed preview session (POST /api/previews/sessions) and
// renders either a validated dynamic previewer (package/project) or the core
// fallback viewer for the envelope kind. The legacy one-shot `previewCache`
// path is gone.
export { PreviewHost } from "./DataPreview.parts/PreviewHost";
export type { PreviewHostProps } from "./DataPreview.parts/PreviewHost";
export {
  PREVIEWER_HOST_API_VERSION,
  isApiVersionCompatible,
  isPreviewerModule,
} from "./DataPreview.parts/previewerHostApi";
export type {
  PreviewHostApi,
  PreviewProviderIdentity,
  PreviewExportRequest,
  PreviewerInstance,
  PreviewerModule,
} from "./DataPreview.parts/previewerHostApi";

interface DataPreviewProps {
  selectedNodeId: string | null;
  selectedNodeLabel: string;
  blockOutputs: Record<string, Record<string, unknown>>;
  /** Effective per-instance input ports of the selected node (after
   *  resolveVariadicPorts + computeEffectivePorts). Empty / undefined
   *  when no node is selected or the block has no input ports.
   *  Drives the #1326 PortInfoPanel. */
  selectedInputPorts?: BlockPortResponse[];
  /** Effective per-instance output ports of the selected node. */
  selectedOutputPorts?: BlockPortResponse[];
  /** Schema of the selected block. Used by PortInfoPanel for the
   *  type-hierarchy → color lookup and the declared-port-name set that
   *  distinguishes static vs user-added variadic rows (#1326 §3). */
  selectedSchema?: BlockSchemaResponse;
}

export function DataPreview({
  selectedNodeId,
  selectedNodeLabel,
  blockOutputs,
  selectedInputPorts,
  selectedOutputPorts,
  selectedSchema,
}: DataPreviewProps) {
  // #898 — pill labels become source filenames (with truncated-ref fallback).
  const refEntries: RefEntry[] = useMemo(() => {
    if (!selectedNodeId) return [];
    return extractRefEntries(blockOutputs[selectedNodeId] ?? {});
  }, [blockOutputs, selectedNodeId]);
  const outputEntryIds = useMemo(() => refEntries.map((e) => e.id), [refEntries]);

  // Local active-output selection. It defaults to the first output and stays
  // valid as the selected node's outputs change (no effect needed).
  const [pickedEntryId, setPickedEntryId] = useState<string | null>(null);
  const activeEntry =
    (pickedEntryId ? refEntries.find((entry) => entry.id === pickedEntryId) : null) ??
    refEntries[0] ??
    null;

  // ADR-048 FR-021 — the routed-preview envelope cache lives in the Zustand
  // preview slice; the host reads/writes it through these callbacks.
  const previewEnvelopeCache = useAppStore((s) => s.previewEnvelopeCache);
  const cachePreviewEnvelope = useAppStore((s) => s.cachePreviewEnvelope);
  const workflowId = useAppStore((s) => s.workflowId);

  const target: PreviewTarget | null = activeEntry
    ? {
        ...activeEntry.target,
        source: activeEntry.target.source ?? {
          workflow_id: workflowId,
          node_id: selectedNodeId,
          output_port: activeEntry.outputPort ?? null,
        },
      }
    : null;
  const [availablePlots, setAvailablePlots] = useState<PlotListItem[]>([]);
  const [plotTarget, setPlotTarget] = useState<PreviewTarget | null>(null);
  const [plotRunError, setPlotRunError] = useState<string | null>(null);
  const [plotListError, setPlotListError] = useState<string | null>(null);
  const [plotLoading, setPlotLoading] = useState(false);
  const [plotRunningId, setPlotRunningId] = useState<string | null>(null);

  useEffect(() => {
    setPickedEntryId(null);
    setPlotTarget(null);
    setPlotRunError(null);
    setPlotRunningId(null);
  }, [selectedNodeId]);

  useEffect(() => {
    let cancelled = false;
    setAvailablePlots([]);
    setPlotListError(null);
    if (!selectedNodeId) {
      setPlotLoading(false);
      return;
    }
    setPlotLoading(true);
    api
      .listPlots({ workflowId, nodeId: selectedNodeId })
      .then((result) => {
        if (cancelled) return;
        setAvailablePlots(result.plots);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setPlotListError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setPlotLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedNodeId, workflowId]);

  async function handlePlotRun(plot: PlotListItem) {
    setPlotRunningId(plot.plot_id);
    setPlotRunError(null);
    try {
      const result = await api.runPlotJob({ plot_id: plot.plot_id });
      const nextTarget = plotTargetFromRunResponse(result);
      if (!nextTarget) {
        setPlotTarget(null);
        setPlotRunError(result.errors[0] ?? `Plot run ${result.status}.`);
        return;
      }
      setPlotTarget(nextTarget);
    } catch (error) {
      setPlotTarget(null);
      setPlotRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setPlotRunningId(null);
    }
  }

  // Hotfix 2026-05-23 — split the preview region from the port-description
  // panel so the panel no longer steals vertical space from the active
  // preview. The panel reserves ~38% of the right column with its own
  // internal scroll. ``shrink-0`` keeps the panel from collapsing when
  // the preview content is tall. The single divider above the panel is
  // owned by PortInfoPanel's own ``border-t``.
  const portPanel =
    selectedNodeId &&
    ((selectedInputPorts?.length ?? 0) > 0 || (selectedOutputPorts?.length ?? 0) > 0) ? (
      <div className="flex shrink-0 basis-[38%] flex-col overflow-y-auto scrollbar-thin">
        <PortInfoPanel
          inputPorts={selectedInputPorts ?? []}
          outputPorts={selectedOutputPorts ?? []}
          schema={selectedSchema}
        />
      </div>
    ) : null;

  return (
    <aside className="flex h-full flex-col overflow-hidden border-l border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</p>
          <h2 className="mt-2 font-display text-2xl text-ink">
            {selectedNodeId ? selectedNodeLabel : "Select a node"}
          </h2>
        </div>
      </div>

      {!selectedNodeId ? (
        <div className="mt-6 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
          Pick a block to inspect its latest outputs and cached previews.
        </div>
      ) : (
        <>
          {outputEntryIds.length > 0 ? (
            <div className="mt-5 flex flex-wrap gap-2">
              {refEntries.map((entry) => (
                <button
                  className={`rounded-full px-3 py-1 text-xs ${!plotTarget && activeEntry?.id === entry.id ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                  key={entry.id}
                  onClick={() => {
                    setPickedEntryId(entry.id);
                    setPlotTarget(null);
                    setPlotRunError(null);
                  }}
                  title={entry.ref}
                  type="button"
                >
                  {entry.displayName}
                </button>
              ))}
              {plotTarget ? (
                <button
                  className="rounded-full bg-ink px-3 py-1 text-xs text-white"
                  onClick={() => setPlotTarget(plotTarget)}
                  title={plotTarget.ref}
                  type="button"
                >
                  Plot artifact
                </button>
              ) : null}
            </div>
          ) : null}
          {availablePlots.length > 0 || plotLoading || plotListError ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {plotLoading ? (
                <span className="text-xs text-stone-500">Loading plots...</span>
              ) : null}
              {availablePlots.map((plot) => (
                <button
                  aria-label={`Run plot ${plot.title || plot.plot_id}`}
                  className="rounded border border-stone-300 bg-white px-3 py-1 text-xs text-stone-700 disabled:opacity-50"
                  disabled={plotRunningId !== null}
                  key={plot.plot_id}
                  onClick={() => void handlePlotRun(plot)}
                  title={plot.display_label || plot.plot_id}
                  type="button"
                >
                  {plotRunningId === plot.plot_id
                    ? "Running"
                    : `Plot: ${plot.title || plot.plot_id}`}
                </button>
              ))}
              {plotTarget && outputEntryIds.length === 0 ? (
                <button
                  className="rounded-full bg-ink px-3 py-1 text-xs text-white"
                  onClick={() => setPlotTarget(plotTarget)}
                  title={plotTarget.ref}
                  type="button"
                >
                  Plot artifact
                </button>
              ) : null}
            </div>
          ) : null}
          {plotListError ? (
            <div
              className="mt-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
              role="status"
            >
              {plotListError}
            </div>
          ) : null}
          {plotRunError ? (
            <div
              className="mt-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800"
              role="alert"
            >
              {plotRunError}
            </div>
          ) : null}
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <PreviewHost
              target={plotTarget ?? target}
              initialQuery={plotTarget ? undefined : activeEntry?.initialQuery}
              getCachedEnvelope={(key) => previewEnvelopeCache[key]}
              cacheEnvelope={cachePreviewEnvelope}
              buildCacheKey={(t, q, opts) => buildPreviewCacheKey(t, q, opts)}
            />
          </div>
        </>
      )}
      {portPanel}
    </aside>
  );
}
