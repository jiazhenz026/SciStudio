import { Maximize2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAppStore } from "../store";
import { buildPreviewCacheKey } from "../store/previewSlice";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  PreviewTarget,
  ResolvedSubworkflowPort,
} from "../types/api";

import { PortInfoPanel } from "./DataPreview.parts/PortInfoPanel";
import { SubworkflowPortPanel } from "./DataPreview.parts/SubworkflowPortPanel";
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
  /** ADR-044 — when the selected node is a subworkflow container, its exposed
   *  port surface (with owning-block provenance). Renders the
   *  SubworkflowPortPanel in place of the #1326 PortInfoPanel so the user can
   *  see which inner block each opaque "<block>.<port>" port belongs to. */
  subworkflowPorts?: {
    inputs: ResolvedSubworkflowPort[];
    outputs: ResolvedSubworkflowPort[];
    typeHierarchy?: BlockSchemaResponse["type_hierarchy"];
  };
}

export function DataPreview({
  selectedNodeId,
  selectedNodeLabel,
  blockOutputs,
  selectedInputPorts,
  selectedOutputPorts,
  selectedSchema,
  subworkflowPorts,
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
  // ADR-044 — a subworkflow node exposes opaque "<block>.<port>" ports; show the
  // provenance panel instead of the generic #1326 PortInfoPanel (subworkflow
  // nodes have no schema-static ports, so selectedInput/OutputPorts are empty).
  const hasSubworkflowPorts =
    (subworkflowPorts?.inputs.length ?? 0) > 0 || (subworkflowPorts?.outputs.length ?? 0) > 0;
  const portPanelBody = hasSubworkflowPorts ? (
    <SubworkflowPortPanel
      inputs={subworkflowPorts?.inputs ?? []}
      outputs={subworkflowPorts?.outputs ?? []}
      typeHierarchy={subworkflowPorts?.typeHierarchy}
    />
  ) : (selectedInputPorts?.length ?? 0) > 0 || (selectedOutputPorts?.length ?? 0) > 0 ? (
    <PortInfoPanel
      inputPorts={selectedInputPorts ?? []}
      outputPorts={selectedOutputPorts ?? []}
      schema={selectedSchema}
    />
  ) : null;
  const portPanel =
    selectedNodeId && portPanelBody ? (
      <div className="flex shrink-0 basis-[38%] flex-col overflow-y-auto scrollbar-thin">
        {portPanelBody}
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

  // #1795 — a SINGLE PreviewHost instance backs both the inline panel and the
  // maximized window. PreviewHost owns the query / drill-down state and creates
  // the preview session on mount, so it is rendered exactly once at a stable
  // position in the element tree. Maximizing only restyles its wrapper (inline
  // flow ⇄ fixed overlay window); the host is never unmounted, so the active
  // preview (table paging/sort, array slice, child-resource drill-down, dynamic
  // previewer state, session) is preserved when popping out instead of reset.
  const host = (
    <PreviewHost
      target={activePlot ?? target}
      initialQuery={activePlot ? undefined : activeEntry?.initialQuery}
      getCachedEnvelope={(key) => previewEnvelopeCache[key]}
      cacheEnvelope={cachePreviewEnvelope}
      buildCacheKey={(t, q, opts) => buildPreviewCacheKey(t, q, opts)}
    />
  );

  // The preview surface keeps an identical element structure in both modes so
  // React reconciles in place and never remounts the host. Only class names and
  // the maximize chrome change. Stable keys keep the host's identity even if the
  // pills row appears/disappears as outputs arrive. When maximized the surface
  // itself becomes the fixed backdrop (reusing the DataRouterModal /
  // PairEditorModal overlay pattern); backdrop click, the close control, and
  // Escape all dismiss it. The aside ancestors are flexbox panels with no
  // transform, so the fixed overlay positions against the viewport correctly.
  const previewSurface = (
    <div
      className={
        isMaximized
          ? "fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 p-6"
          : "mt-4 flex min-h-0 flex-1 flex-col"
      }
      data-testid={isMaximized ? "preview-maximized-overlay" : undefined}
      onClick={isMaximized ? () => setIsMaximized(false) : undefined}
    >
      <div
        className={
          isMaximized
            ? "flex h-[88vh] w-[88vw] flex-col rounded-2xl border border-stone-200 bg-white shadow-2xl"
            : "flex min-h-0 flex-1 flex-col"
        }
        onClick={isMaximized ? (event) => event.stopPropagation() : undefined}
      >
        <div
          key="max-header"
          className={
            isMaximized
              ? "flex items-center justify-between gap-3 border-b border-stone-100 px-5 py-3"
              : "hidden"
          }
        >
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
          <div
            key="pills"
            className={
              isMaximized ? "shrink-0 border-b border-stone-100 px-5 py-3" : "mb-3 shrink-0"
            }
          >
            {pillsRow}
          </div>
        ) : null}
        <div
          key="host"
          className={
            isMaximized
              ? "min-h-0 flex-1 overflow-y-auto scrollbar-thin p-5"
              : "min-h-0 flex-1 overflow-y-auto scrollbar-thin"
          }
        >
          {host}
        </div>
      </div>
    </div>
  );

  return (
    <aside className="flex h-full flex-col overflow-hidden border-l border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(245,241,232,0.98))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</p>
          <h2 className="mt-2 font-display text-2xl text-ink">
            {selectedNodeId ? selectedNodeLabel : "Select a block"}
          </h2>
        </div>
        {hasPreviewContent && !isMaximized ? (
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
        previewSurface
      )}
      {portPanel}
    </aside>
  );
}
