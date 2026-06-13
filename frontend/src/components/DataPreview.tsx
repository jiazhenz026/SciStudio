import { useEffect, useMemo, useState, type FormEvent } from "react";

import { api } from "../lib/api";
import { plotTargetFromRunResponse } from "../lib/api/data";
import { useAppStore } from "../store";
import { buildPreviewCacheKey } from "../store/previewSlice";
import type { BlockPortResponse, BlockSchemaResponse, PreviewTarget } from "../types/api";

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
  const outputRefs = useMemo(() => refEntries.map((e) => e.ref), [refEntries]);

  // Local active-ref selection. The effective ref defaults to the first output
  // and stays valid as the selected node's outputs change (no effect needed).
  const [pickedRef, setPickedRef] = useState<string | null>(null);
  const activeRef =
    pickedRef && outputRefs.includes(pickedRef) ? pickedRef : (outputRefs[0] ?? null);

  // ADR-048 FR-021 — the routed-preview envelope cache lives in the Zustand
  // preview slice; the host reads/writes it through these callbacks.
  const previewEnvelopeCache = useAppStore((s) => s.previewEnvelopeCache);
  const cachePreviewEnvelope = useAppStore((s) => s.cachePreviewEnvelope);

  // The frontend has no authoritative type chain; it sends a minimal data_ref
  // target and the backend rebuilds the routed target from its catalog (#1592).
  const target: PreviewTarget | null = activeRef ? { kind: "data_ref", ref: activeRef } : null;
  const [plotId, setPlotId] = useState("");
  const [plotTarget, setPlotTarget] = useState<PreviewTarget | null>(null);
  const [plotRunError, setPlotRunError] = useState<string | null>(null);
  const [plotRunning, setPlotRunning] = useState(false);

  useEffect(() => {
    setPlotTarget(null);
    setPlotRunError(null);
    setPlotRunning(false);
  }, [selectedNodeId]);

  async function handlePlotRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestedPlotId = plotId.trim();
    if (!requestedPlotId) {
      setPlotRunError("Enter a plot id.");
      return;
    }
    setPlotRunning(true);
    setPlotRunError(null);
    try {
      const result = await api.runPlotJob({ plot_id: requestedPlotId });
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
      setPlotRunning(false);
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
      ) : outputRefs.length === 0 ? (
        <div className="mt-6 min-h-0 flex-1 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
          This block has no previewable outputs yet.
        </div>
      ) : (
        <>
          <div className="mt-5 flex flex-wrap gap-2">
            {refEntries.map((entry) => (
              <button
                className={`rounded-full px-3 py-1 text-xs ${!plotTarget && activeRef === entry.ref ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={entry.ref}
                onClick={() => {
                  setPickedRef(entry.ref);
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
          <form className="mt-3 flex items-center gap-2" onSubmit={handlePlotRun}>
            <label className="sr-only" htmlFor="data-preview-plot-id">
              Plot id
            </label>
            <input
              className="min-w-0 flex-1 rounded border border-stone-300 bg-white px-3 py-1 text-xs text-stone-700 outline-none focus:border-ink"
              disabled={plotRunning}
              id="data-preview-plot-id"
              onChange={(event) => setPlotId(event.target.value)}
              placeholder="plot_id"
              value={plotId}
            />
            <button
              aria-label="Run plot"
              className="rounded border border-stone-300 bg-white px-3 py-1 text-xs text-stone-700 disabled:opacity-50"
              disabled={plotRunning}
              type="submit"
            >
              {plotRunning ? "Running" : "Run"}
            </button>
          </form>
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
              getCachedEnvelope={(key) => previewEnvelopeCache[key]}
              cacheEnvelope={cachePreviewEnvelope}
              buildCacheKey={(t, q) => buildPreviewCacheKey(t, q)}
            />
          </div>
        </>
      )}
      {portPanel}
    </aside>
  );
}
