import { ChevronLeft, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import type { PanelSnapshot } from "../panels/types";

import { useAppStore } from "../store";
import { buildPreviewCacheKey } from "../store/previewSlice";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  PreviewTarget,
  ResolvedSubworkflowPort,
} from "../types/api";

import { PreviewerPalette } from "./PreviewerPalette";

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

// ADR-054 FR-033 — All Previewers.
//
// The Previewers tab left the sidebar (FR-031). The list itself did not go
// anywhere: it opens *inside the preview column*, in place of the preview,
// which is where a list of "how is my data drawn" belongs — next to the
// drawing it governs. No dialog, and nothing else on screen moves.
//
// It is the same `PreviewerPalette` component, mounted unchanged, with its
// reload action, its registry diagnostics and its per-type choice controls.
// Two things about it are wrong for this column and both are fixed from
// outside, by the wrapper below, rather than by editing the pane:
//
//   - its root `<aside>` carries left-panel chrome (`border-r`, its own
//     gradient, `p-4`). In the right-hand column the divider would land on the
//     wrong edge, the column's own surface would be painted over, and the
//     padding would be applied twice. The wrapper neutralises all three;
//     editing the class would change the left panel too.
//   - it rescans the previewer registries once per mount (#2151: mounting the
//     pane *is* switching to its section). Conditionally mounting it here would
//     POST a registry reload on every single open, so it is mounted lazily on
//     the first open and then kept mounted and hidden. One rescan per session,
//     and the Reload button inside it is still the way to ask for another.
//
// `DataPreview` is one node rendered in two mutually exclusive places — the
// workbench's right column and, in the AI-host presentation, the sidebar's
// Preview card — so putting the control here satisfies both halves of FR-033
// at once.

let allPreviewersToken = 0;
// The last request a mounted column acted on. A request is one-shot: a column
// mounted later (the next project, the next tutorial) must not replay it.
let allPreviewersHandled = 0;
const allPreviewersListeners = new Set<() => void>();

/**
 * Open All Previewers from outside the preview column.
 *
 * The tutorial route target `previewers` (FR-040) has to reach this list
 * without a pointer, and FR-033 says the column expands first when it is
 * collapsed — so this clears `previewCollapsed` on the way, the same two-step
 * `promotion/revealInLibrary` performs for the left panel (clear the collapse
 * flag, then publish the instruction). `ProjectWorkspace` owns the panel handle
 * that turns that flag into an expanded column.
 *
 * A module-level channel rather than store state for the instruction itself,
 * for the same reason `revealInLibrary` is one: it is transient and one-shot,
 * and a persisted copy would resurrect a stale "show the previewer list" on the
 * next launch.
 */
export function openAllPreviewers(): void {
  useAppStore.setState({ previewCollapsed: false });
  allPreviewersToken += 1;
  for (const listener of allPreviewersListeners) listener();
}

function subscribeAllPreviewers(listener: () => void): () => void {
  allPreviewersListeners.add(listener);
  return () => {
    allPreviewersListeners.delete(listener);
  };
}

/** Test seam — forget any pending request so each test starts clean. */
export function resetAllPreviewersRequests(): void {
  allPreviewersToken = 0;
  allPreviewersHandled = 0;
  for (const listener of allPreviewersListeners) listener();
}

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
  const panelSnapshot = useRef<PanelSnapshot | null>(null);
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
  // #2113 — the routing epoch: a per-type previewer choice change bumps it,
  // and PreviewHost re-creates the open session so the new choice applies to
  // the preview already on screen rather than only to the next one.

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

  // FR-033 — All Previewers. `listMounted` latches on the first open and never
  // unlatches: see the module comment for why the pane is hidden rather than
  // unmounted when the user goes back to the preview.
  const [showPreviewerList, setShowPreviewerList] = useState(false);
  const [listMounted, setListMounted] = useState(false);
  const openRequest = useSyncExternalStore(
    subscribeAllPreviewers,
    () => allPreviewersToken,
    () => 0,
  );
  const openPreviewerList = () => {
    setListMounted(true);
    setShowPreviewerList(true);
  };
  // The list yields to anything new to preview: another block, a fresh plot
  // result, or a different output of this block. Declared before the open
  // request below, so a request pending at mount still opens the list.
  const shownTargetRef = (plotPreviewTarget ?? activeEntry?.target)?.ref;
  useEffect(() => {
    setShowPreviewerList(false);
  }, [selectedNodeId, plotPreviewTarget, shownTargetRef]);
  useEffect(() => {
    if (openRequest <= allPreviewersHandled) return;
    allPreviewersHandled = openRequest;
    setListMounted(true);
    setShowPreviewerList(true);
  }, [openRequest]);

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
  // #2362 — and to the workflow that node lives in. A node id is not unique
  // across a project and `plotPreviewTarget` survives a tab switch, so matching
  // on the id alone presented a figure rendered in another workflow as this
  // node's result: the "Plot artifact" pill, the preview, and a working
  // Maximize. The source carries `workflow_id` — this component stamps it
  // itself when it builds a target above — so the match now reads it.
  const plotBelongsToSelected =
    plotPreviewTarget != null &&
    plotPreviewTarget.source?.node_id === selectedNodeId &&
    (plotPreviewTarget.source?.workflow_id ?? null) === workflowId;
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
  const selectedTargetRef = (activePlot ?? target)?.ref;
  useEffect(() => {
    panelSnapshot.current = null;
  }, [selectedTargetRef]);
  const host = (
    <PreviewHost
      target={activePlot ?? target}
      initialQuery={activePlot ? undefined : activeEntry?.initialQuery}
      onPanelSnapshot={(snapshot) => {
        panelSnapshot.current = snapshot;
      }}
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
      data-testid="data-preview-column"
      // ADR-053 (#2057) — tutorial highlight target.
      data-tutorial-target="data_preview"
    >
      <div className="flex items-start justify-between gap-3">
        {showPreviewerList ? (
          // FR-033 — the control that returns to the preview. It replaces the
          // block title rather than sitting beside it: the pane below is now
          // the previewer list, which carries its own `Previewers` heading, and
          // a block name over it would be labelling the wrong thing.
          <button
            className="-ml-1 flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-stone-600 transition hover:bg-white hover:text-ink"
            data-testid="all-previewers-back"
            onClick={() => setShowPreviewerList(false)}
            type="button"
          >
            <ChevronLeft aria-hidden="true" className="h-4 w-4" />
            Back to preview
          </button>
        ) : (
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Preview</p>
            <h2 className="mt-2 font-display text-2xl text-ink">
              {selectedNodeId ? selectedNodeLabel : "Select a block"}
            </h2>
          </div>
        )}
        {showPreviewerList ? null : (
          <button
            className="mt-1 shrink-0 rounded-full border border-stone-300 bg-white/70 px-2.5 py-1 text-[11px] font-medium text-stone-600 transition hover:border-ink hover:text-ink"
            data-testid="all-previewers-open"
            onClick={openPreviewerList}
            title="Every previewer registered, and which one draws each data type"
            type="button"
          >
            All Previewers
          </button>
        )}
        {hasPreviewContent && !showPreviewerList ? (
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
              const expandTarget = panelSnapshot.current?.target ?? activePlot ?? target;
              if (!expandTarget) return;
              useAppStore
                .getState()
                .openPreviewTab(
                  expandTarget,
                  activePlot ? "Plot artifact" : (activeEntry?.displayName ?? selectedNodeLabel),
                  activePlot ? undefined : activeEntry?.initialQuery,
                  undefined,
                  panelSnapshot.current ?? undefined,
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

      {/* FR-033 — the previewer list, mounted unchanged. The wrapper strips the
          left-panel chrome the pane carries (`border-r`, its own gradient, its
          own padding) so it sits inside this column instead of drawing a second
          divider down the middle of it; `hidden` rather than unmounted keeps
          the pane's mount-time registry rescan to once per session. */}
      {listMounted ? (
        <div
          className={
            showPreviewerList
              ? "mt-4 flex min-h-0 flex-1 flex-col [&>aside]:border-r-0 [&>aside]:bg-none [&>aside]:p-0"
              : "hidden"
          }
          data-testid="all-previewers-pane"
        >
          <PreviewerPalette />
        </div>
      ) : null}

      {/* #1713 — the workflow-wide plot list moved to the dedicated Plots tab
          (BottomPanel). This panel renders preview content: the selected node's
          outputs and/or the persisted plot Run result, toggled by the "Plot
          artifact" pill. The result stays put when switching blocks. */}
      {showPreviewerList ? null : (
        <>
          {!selectedNodeId ? (
            <div className="mt-6 rounded-[1.8rem] border border-dashed border-stone-300 px-4 py-6 text-sm text-stone-500">
              Pick a block to inspect its latest outputs and cached previews.
            </div>
          ) : (
            previewSurface
          )}
          {portPanel}
        </>
      )}
    </aside>
  );
}
