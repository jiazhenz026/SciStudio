import { useMemo } from "react";

import type { BlockPortResponse, BlockSchemaResponse, DataPreviewResponse } from "../types/api";

import { OMEMetadataPanel } from "./OutputPreview/OMEMetadataPanel";
import { PortInfoPanel } from "./DataPreview.parts/PortInfoPanel";
import { PreviewRenderer } from "./DataPreview.parts/PreviewRenderer";
import { extractRefEntries, type RefEntry } from "./DataPreview.parts/refEntries";
import { useOmeMetadata } from "./DataPreview.parts/useOmeMetadata";
import { useSlicePreview } from "./DataPreview.parts/useSlicePreview";

// Re-exports preserve the public surface of DataPreview.tsx for existing
// consumers (LossySaveWarning.tsx mirrors `extractRefEntries`).
export { extractRefEntries } from "./DataPreview.parts/refEntries";
export type { RefEntry } from "./DataPreview.parts/refEntries";

// ADR-048 SPEC 1 — the routed PreviewHost container and core fallback viewers.
// This DataPreview component keeps the LEGACY one-shot `previewCache` rendering
// path (FR-008 compatibility / US5) for its current callers; PreviewHost is the
// new session-API surface that mounts validated dynamic previewers or core
// fallbacks. New preview surfaces should mount PreviewHost directly.
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
  previewCache: Record<string, DataPreviewResponse>;
  previewLoading: Record<string, boolean>;
  onLoadPreview: (dataRef: string) => Promise<void>;
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
  previewCache,
  previewLoading,
  onLoadPreview,
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

  const { activeRef, setActiveRef, activeSlice, handleSliceChange, preview, isLoadingActive } =
    useSlicePreview({ outputRefs, previewCache, previewLoading, onLoadPreview });

  const { omeOpen, setOmeOpen, activeOme, omeAvailable, handleOpenOme } = useOmeMetadata({
    activeRef,
    preview,
  });

  // Hotfix 2026-05-23 — split the preview region from the port-description
  // panel so the panel no longer steals vertical space from the active
  // preview. The panel reserves ~38% of the right column (matches the
  // center column's BottomPanel initial visual ratio) with its own
  // internal scroll. ``shrink-0`` keeps the panel from collapsing when
  // the preview content is tall. The single divider above the panel is
  // owned by PortInfoPanel's own ``border-t``; we deliberately do NOT
  // add another ``border-t`` here so the user does not see two parallel
  // lines with dead space between them.
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
                className={`rounded-full px-3 py-1 text-xs ${activeRef === entry.ref ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={entry.ref}
                onClick={() => setActiveRef(entry.ref)}
                title={entry.ref}
                type="button"
              >
                {entry.displayName}
              </button>
            ))}
          </div>
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            {isLoadingActive ? (
              <div className="rounded-[1.6rem] border border-stone-200 bg-white p-4 text-sm text-stone-500">
                Loading preview…
              </div>
            ) : preview && activeRef ? (
              <>
                <PreviewRenderer
                  preview={preview.preview}
                  dataRef={activeRef}
                  currentSlice={activeSlice}
                  onSliceChange={handleSliceChange}
                />
                {/* ADR-043 FR-013 — OME metadata browser. Always render the
                    button when a ref is active; the panel itself surfaces
                    a "No OME metadata" message when the underlying object
                    has none. */}
                {omeAvailable ? (
                  <div className="mt-3">
                    {!omeOpen ? (
                      <button
                        type="button"
                        className="rounded-full border border-stone-300 bg-white px-3 py-1 text-xs text-stone-600 hover:bg-stone-50"
                        onClick={handleOpenOme}
                        data-testid="open-ome-metadata"
                      >
                        OME metadata
                      </button>
                    ) : (
                      <OMEMetadataPanel ome={activeOme} onClose={() => setOmeOpen(false)} />
                    )}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="rounded-[1.6rem] border border-stone-200 bg-white p-4 text-sm text-stone-500">
                Preview not loaded yet.
              </div>
            )}
          </div>
        </>
      )}
      {portPanel}
    </aside>
  );
}
