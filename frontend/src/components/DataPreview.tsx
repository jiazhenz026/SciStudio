import { Maximize2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAppStore } from "../store";
import { buildPreviewCacheKey } from "../store/previewSlice";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  PreviewTarget,
  ResolvedSubworkflowPort,
} from "../types/api";

import { NodePortPanel } from "./DataPreview.parts/NodePortPanel";
import { PreviewHost } from "./DataPreview.parts/PreviewHost";
import { extractRefEntries, type RefEntry } from "./DataPreview.parts/refEntries";

// Re-exports preserve the public surface of DataPreview.tsx for existing
// consumers (LossySaveWarning.tsx mirrors `extractRefEntries`).
export { extractRefEntries } from "./DataPreview.parts/refEntries";
export type { RefEntry } from "./DataPreview.parts/refEntries";

// ADR-048 SPEC 1 — the routed PreviewHost container and core fallback viewers.
// As of #1592 the live DataPreview mounts PreviewHost directly: every selected
// output ref creates a routed preview session (POST /api/previews/sessions) and
// renders either a validated dynamic panel (package/project) or the core
// fallback viewer for the envelope kind. The legacy one-shot `previewCache`
// path is gone.
export { PreviewHost } from "./DataPreview.parts/PreviewHost";
export type { PreviewHostProps } from "./DataPreview.parts/PreviewHost";
export {
  PANEL_HOST_API_VERSION,
  isApiVersionCompatible,
  isPanelModule,
} from "./DataPreview.parts/panelHostApi";
export type {
  PreviewHostApi,
  PreviewProviderIdentity,
  PreviewExportRequest,
  PanelInstance,
  PanelModule,
} from "./DataPreview.parts/panelHostApi";

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
  // #2113 — the routing epoch: a per-type panel choice change bumps it,
  // and PreviewHost re-creates the open session so the new choice applies to
  // the preview already on screen rather than only to the next one.
  const panelChoiceVersion = useAppStore((s) => s.panelChoiceVersion);

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

  useEffect(() => {
    setPickedEntryId(null);
  }, [selectedNodeId]);

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

  // Hotfix 2026-05-23 — the port section reserves ~38% of the right column with
  // its own internal scroll, split from the preview so it never steals vertical
  // space. NodePortPanel owns the subworkflow-vs-generic branch (ADR-044) and
  // returns null when there is nothing to show.
  const portPanel = selectedNodeId ? (
    <NodePortPanel
      subworkflowPorts={subworkflowPorts}
      inputPorts={selectedInputPorts ?? []}
      outputPorts={selectedOutputPorts ?? []}
      schema={selectedSchema}
    />
  ) : null;

  // #1795 — the output/plot pills gate the maximize control too: there is
  // nothing to enlarge until an output exists.
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

  // ADR-048 / #1592 — the single routed PreviewHost for the active output or
  // the plot Run result. The host owns the query / drill-down state and
  // creates its preview session on mount; it adapts to its container, which
  // is also why the maximize action (#2112) can hand a frozen target to a
  // second host in a main-stage tab without any host changes.
  const host = (
    <PreviewHost
      target={activePlot ?? target}
      initialQuery={activePlot ? undefined : activeEntry?.initialQuery}
      routingEpoch={panelChoiceVersion}
      getCachedEnvelope={(key) => previewEnvelopeCache[key]}
      cacheEnvelope={cachePreviewEnvelope}
      buildCacheKey={(t, q, opts) => buildPreviewCacheKey(t, q, opts)}
    />
  );

  const previewSurface = (
    <div className="mt-4 flex min-h-0 flex-1 flex-col">
      {pillsRow ? <div className="mb-3 shrink-0">{pillsRow}</div> : null}
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">{host}</div>
    </div>
  );

  return (
    <aside
      className="flex h-full flex-col overflow-hidden border-l border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.94),_rgba(245,241,232,0.98))] p-4"
      // ADR-053 (#2057) — tutorial highlight target.
      data-tutorial-target="data_preview"
    >
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
            onClick={() => {
              /*
               * #2112 — maximizing opens the FROZEN active target as a
               * transient preview tab on the main stage (beside the file and
               * workflow tabs) instead of restyling this panel into an
               * overlay. The tab is dropped as soon as focus moves elsewhere.
               */
              const expandTarget = activePlot ?? target;
              if (!expandTarget) return;
              useAppStore
                .getState()
                .openPreviewTab(
                  expandTarget,
                  activePlot ? "Plot artifact" : (activeEntry?.displayName ?? selectedNodeLabel),
                  activePlot ? undefined : activeEntry?.initialQuery,
                );
              /*
               * ADR-053 FR-052 (#2057) — `preview_expanded`, one of the two
               * names in the closed `UI_EVENT_NAMES` set. Enlarging the preview
               * leaves no backend state behind, so a step waiting on it has no
               * other way to finish. A no-op when no tutorial is running.
               */
              void useAppStore.getState().reportTutorialUiEvent("preview_expanded");
            }}
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
