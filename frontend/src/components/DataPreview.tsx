import { Maximize2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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
  // #1713 — the workflow-wide plot list (run / relink / new) moved to the
  // dedicated Plots tab in the BottomPanel. The Preview panel only renders the
  // Run result, shared through the store so the Plots tab (bottom panel) can
  // publish it while the result still appears in this right-hand panel.
  const plotPreviewTarget = useAppStore((s) => s.plotPreviewTarget);
  // #1713 — `showPlotResult` toggles whether the Preview shows the plot Run
  // result vs. the selected node's outputs. A fresh Run turns it on; the output
  // pills turn it off; the "Plot artifact" pill turns it back on.
  const [showPlotResult, setShowPlotResult] = useState(false);

  // #1795 — maximize the active preview into a floating window over the canvas
  // so a cramped right-sidebar preview can be inspected at a larger size.
  // PreviewHost adapts to its container, so the larger window renders a
  // correspondingly larger preview with no host changes.
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    setPickedEntryId(null);
    // A new selection retargets the preview; close any stale maximized window.
    setIsMaximized(false);
  }, [selectedNodeId]);

  // #1795 — close the maximized window on Escape. The listener is attached only
  // while maximized so it never shadows canvas/editor shortcuts otherwise.
  useEffect(() => {
    if (!isMaximized) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsMaximized(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isMaximized]);

  // A fresh plot Run (new plotPreviewTarget) switches the view to the result.
  useEffect(() => {
    if (plotPreviewTarget) setShowPlotResult(true);
  }, [plotPreviewTarget]);

  // #1713 — the plot result belongs to its linked block: only surface it when
  // that block is selected (never in the "Select a block" empty state, and not
  // while a different block is selected). `activePlot` is derived, so it stays
  // correct regardless of the order in which a Run updates the node + result.
  const plotBelongsToSelected =
    plotPreviewTarget != null && plotPreviewTarget.source?.node_id === selectedNodeId;
  const activePlot = showPlotResult && plotBelongsToSelected ? plotPreviewTarget : null;

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

  // #1795 — the output/plot pills are shared by the inline panel and the
  // maximized window, so extract them once. ``hasPreviewContent`` also gates
  // the maximize control: there is nothing to enlarge until an output exists.
  const hasPreviewContent = outputEntryIds.length > 0 || plotBelongsToSelected;
  const pillsRow = hasPreviewContent ? (
    <div className="flex flex-wrap gap-2">
      {refEntries.map((entry) => (
        <button
          className={`rounded-full px-3 py-1 text-xs ${!activePlot && activeEntry?.id === entry.id ? "bg-ink text-white" : "bg-white text-stone-600"}`}
          key={entry.id}
          onClick={() => {
            setPickedEntryId(entry.id);
            setShowPlotResult(false);
          }}
          title={entry.ref}
          type="button"
        >
          {entry.displayName}
        </button>
      ))}
      {plotBelongsToSelected ? (
        <button
          className={`rounded-full px-3 py-1 text-xs ${showPlotResult ? "bg-ink text-white" : "bg-white text-stone-600"}`}
          onClick={() => setShowPlotResult(true)}
          title={plotPreviewTarget?.ref}
          type="button"
        >
          Plot artifact
        </button>
      ) : null}
    </div>
  ) : null;

  // The routed preview host. Only one instance mounts at a time (inline OR the
  // maximized window) so a single preview session is active.
  const renderHost = () => (
    <PreviewHost
      target={activePlot ?? target}
      initialQuery={activePlot ? undefined : activeEntry?.initialQuery}
      getCachedEnvelope={(key) => previewEnvelopeCache[key]}
      cacheEnvelope={cachePreviewEnvelope}
      buildCacheKey={(t, q, opts) => buildPreviewCacheKey(t, q, opts)}
    />
  );

  return (
    <>
      <aside className="flex h-full flex-col overflow-hidden border-l border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(245,241,232,0.98))] p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</p>
            <h2 className="mt-2 font-display text-2xl text-ink">
              {selectedNodeId ? selectedNodeLabel : "Select a block"}
            </h2>
          </div>
          {hasPreviewContent ? (
            <button
              aria-label="Maximize preview"
              className="mt-1 shrink-0 rounded-full p-1.5 text-stone-500 hover:bg-white hover:text-ink"
              onClick={() => setIsMaximized(true)}
              title="Maximize preview"
              type="button"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        {/* #1713 — the workflow-wide plot list moved to the dedicated Plots tab
            (BottomPanel). This panel renders preview content: the selected node's
            outputs and/or the persisted plot Run result, toggled by the "Plot
            artifact" pill. The result stays put when switching blocks. */}
        {!selectedNodeId ? (
          <div className="mt-6 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
            Pick a block to inspect its latest outputs and cached previews.
          </div>
        ) : (
          <>
            {pillsRow ? <div className="mt-5">{pillsRow}</div> : null}
            <div className="mt-4 min-h-0 flex-1 overflow-y-auto scrollbar-thin">
              {isMaximized ? (
                <div className="flex h-full items-center justify-center px-4 text-center text-sm text-stone-400">
                  Preview opened in a separate window.
                </div>
              ) : (
                renderHost()
              )}
            </div>
          </>
        )}
        {portPanel}
      </aside>

      {/* #1795 — maximized preview window. Reuses the shared overlay pattern
          (DataRouterModal / PairEditorModal). Backdrop click, the close
          control, and Escape all dismiss it. */}
      {isMaximized ? (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-6"
          onClick={() => setIsMaximized(false)}
          data-testid="preview-maximized-overlay"
        >
          <div
            className="flex h-[88vh] w-[88vw] flex-col rounded-2xl border border-stone-200 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-stone-100 px-5 py-3">
              <div className="flex min-w-0 flex-col">
                <span className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</span>
                <span className="truncate font-display text-lg text-ink">{selectedNodeLabel}</span>
              </div>
              <button
                aria-label="Close preview window"
                className="shrink-0 rounded-full p-1.5 text-stone-500 hover:bg-stone-100 hover:text-ink"
                onClick={() => setIsMaximized(false)}
                title="Close (Esc)"
                type="button"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {pillsRow ? (
              <div className="border-b border-stone-100 px-5 py-3">{pillsRow}</div>
            ) : null}
            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin p-5">{renderHost()}</div>
          </div>
        </div>
      ) : null}
    </>
  );
}
