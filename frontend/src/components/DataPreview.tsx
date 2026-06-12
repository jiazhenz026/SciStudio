import { useMemo, useState } from "react";

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
  /** Legacy one-shot preview plumbing (previewCache/onLoadPreview). No longer
   *  consumed now that the routed PreviewHost owns loading (#1592); accepted as
   *  optional so the ProjectWorkspace call site stays valid until the legacy
   *  cache plumbing is removed in the #1594 delete pass. */
  previewCache?: Record<string, unknown>;
  previewLoading?: Record<string, boolean>;
  onLoadPreview?: (dataRef: string) => Promise<void> | void;
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
                className={`rounded-full px-3 py-1 text-xs ${activeRef === entry.ref ? "bg-ink text-white" : "bg-white text-stone-600"}`}
                key={entry.ref}
                onClick={() => setPickedRef(entry.ref)}
                title={entry.ref}
                type="button"
              >
                {entry.displayName}
              </button>
            ))}
          </div>
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <PreviewHost
              target={target}
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
