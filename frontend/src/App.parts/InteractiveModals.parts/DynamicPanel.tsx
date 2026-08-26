/**
 * ADR-051 — host React component for a package-provided interactive panel.
 *
 * The core panels in {@link ../InteractiveModals.tsx} resolve from the built-in
 * `PANEL_REGISTRY`. A package-provided interactive block instead ships its
 * window as a same-origin ESM module referenced by `panelManifest.module_url`.
 * This component bridges that module into the React tree:
 *
 *   1. Builds a constrained {@link PanelHostApi} whose `confirm`/`cancel` drive
 *      the SAME `onConfirm`/`onCancel` the core panels use (so the run-scoped
 *      `interactive_complete` / `cancel_block` frames are sent unchanged).
 *   2. Calls {@link mountDynamicPanel} into a host-owned container ref and keeps
 *      the returned {@link PanelInstance} for unmount-on-cleanup.
 *   3. On ANY load failure renders a small, visible error surface with a Cancel
 *      button wired to `onCancel`. The user is NEVER left on a paused block with
 *      no window and no exit (the P1 this change closes). It never renders a
 *      silent `null` on failure.
 *   4. Draws a host-owned title bar above the panel's mount container carrying
 *      the block's name and a close (X) control, and listens for ESC (#2195).
 *      Both drive the SAME `onCancel`, so the escape hatch exists even when the
 *      module mounts fine and wires no exit of its own — the overlay covers the
 *      Toolbar's Stop button, so without this the app is unreachable. The
 *      panel's own content area is untouched: a module that draws its own
 *      Cancel keeps it, one control in the title bar and one in the content.
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "../../components/ui/button";
import type { PanelManifestDescriptor } from "../../store/types";
import {
  PANEL_HOST_API_VERSION,
  type LoadFailure,
  type ModuleImporter,
  type PanelHostApi,
  type PanelInstance,
  mountDynamicPanel,
} from "./panelModuleLoader";

export interface DynamicPanelProps {
  /** The block's panel manifest (carries the same-origin `module_url`). */
  manifest: PanelManifestDescriptor;
  /** The paused block id the panel resolves. */
  blockId: string;
  /** The block-built, window-sized JSON view the panel renders from. */
  panelPayload: Record<string, unknown>;
  /** Send the panel's JSON-safe decision back to the backend (run-scoped). */
  onConfirm: (responseData: Record<string, unknown>) => void;
  /** Cancel the interactive block (run-scoped). */
  onCancel: () => void;
  /**
   * #2195 — what the host-drawn title bar calls this window. The block's type
   * name when the prompt carries one; falls back to {@link blockId} so the bar
   * always names something the reader can match to a node on the canvas.
   */
  blockName?: string;
  /** Test seam: inject a fake dynamic-module importer. */
  importer?: ModuleImporter;
}

/** Stable identity key for the manifest so the mount effect re-runs only when
 *  the panel module actually changes. */
function manifestKey(manifest: PanelManifestDescriptor): string {
  return [
    manifest.panel_id,
    manifest.module_url ?? "",
    manifest.export_name ?? "",
    manifest.api_version ?? "",
  ].join("|");
}

export function DynamicPanel({
  manifest,
  blockId,
  panelPayload,
  onConfirm,
  onCancel,
  blockName,
  importer,
}: DynamicPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<PanelInstance | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);

  // Keep the latest confirm/cancel without re-running the mount effect (the
  // parent re-creates these each render). The host always calls through to the
  // current handlers via these refs.
  const onConfirmRef = useRef(onConfirm);
  const onCancelRef = useRef(onCancel);
  onConfirmRef.current = onConfirm;
  onCancelRef.current = onCancel;

  const key = manifestKey(manifest);

  // The constrained host API handed to the package module. Stable for a given
  // block + payload so the mount effect does not re-fire on every render.
  const host: PanelHostApi = useMemo(
    () => ({
      apiVersion: PANEL_HOST_API_VERSION,
      blockId,
      panelPayload,
      confirm: (response: Record<string, unknown>) => onConfirmRef.current(response),
      cancel: () => onCancelRef.current(),
    }),
    [blockId, panelPayload],
  );

  useEffect(() => {
    setFailure(null);
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;
    const unmountQuietly = (instance: PanelInstance) => {
      try {
        instance.unmount();
      } catch {
        /* ignore unmount errors */
      }
    };
    void mountDynamicPanel(manifest, container, host, importer).then((result) => {
      if (disposed) {
        // The effect was torn down while the module was still loading, so the
        // cleanup below found `instanceRef.current` still null and unmounted
        // nothing — but `mount()` has since put the panel's DOM in the
        // container. Dropping the instance here would leave it there, and
        // StrictMode's second pass would mount a second copy on top: the
        // reader sees the panel twice. Unmount what arrived late.
        if (result.ok) unmountQuietly(result.instance);
        return;
      }
      if (result.ok) {
        instanceRef.current = result.instance;
      } else {
        setFailure(result);
      }
    });
    return () => {
      disposed = true;
      if (instanceRef.current) {
        unmountQuietly(instanceRef.current);
        instanceRef.current = null;
      }
    };
    // `key` captures the manifest identity; `manifest` is stable per prompt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, host, importer]);

  // #2195 — ESC is the host's second escape hatch. It is bound while ANY
  // dynamic panel is open, whether the module mounted or the error surface is
  // showing, because the overlay covers the Toolbar's Stop button and a module
  // that wires no exit would otherwise leave the whole app unreachable.
  //
  // Bubble phase on `window`, deliberately: a capture listener would swallow
  // ESC before the package module's own DOM ever saw it. A panel that handles
  // ESC itself (and stops propagation) keeps winning; one that does not gets
  // the host's cancel. `useAppKeyboardShortcuts` also listens on this target
  // and only clears the canvas selection, which is harmless while a panel is
  // open — note it calls `preventDefault()`, so `defaultPrevented` cannot be
  // used here to tell "someone handled it" apart from "nobody did".
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onCancelRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleClose = useCallback(() => onCancelRef.current(), []);

  // The block's own name when the prompt carried one, else its id — the title
  // bar always names the node the reader is being asked about.
  const title = blockName?.trim() ? blockName.trim() : blockId;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      data-testid="dynamic-panel"
      data-block-id={blockId}
      role="dialog"
      aria-modal="true"
      aria-label={`${title} — interactive block`}
    >
      <div className="flex max-h-[85vh] w-[900px] flex-col overflow-hidden rounded-xl border border-ink/10 bg-white shadow-panel">
        {/* #2195 — host-drawn title bar. This is chrome the host owns, never the
            package module's DOM, so the exit exists no matter what the module
            renders below it. */}
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b border-ink/10 bg-ink/[0.03] px-4 py-2"
          data-testid="dynamic-panel-titlebar"
        >
          <div className="truncate text-sm font-medium text-ink/80" title={title}>
            {title}
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="-mr-1 rounded p-1 text-ink/50 transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30"
            aria-label="Close panel and cancel this block"
            title="Close and cancel (Esc)"
            data-testid="dynamic-panel-close"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Mount point for the package panel module. Always present in the DOM so
            the mount effect has a stable container; hidden when we show the
            error surface instead. Scrolls on its own so the title bar above it
            stays reachable for a panel taller than the modal. */}
        <div
          ref={containerRef}
          className="min-h-0 overflow-auto"
          data-testid="dynamic-panel-mount"
          style={{ display: failure ? "none" : "block" }}
        />

        {failure ? (
          <div className="p-5" role="alert" data-testid="dynamic-panel-error">
            <div className="text-sm font-semibold text-destructive">
              Couldn’t load this interactive panel
            </div>
            <div className="mt-1 break-words text-xs text-ink/70">{failure.message}</div>
            <div className="mt-4 flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onCancel}
                data-testid="dynamic-panel-cancel"
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
