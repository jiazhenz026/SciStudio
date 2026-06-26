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
 */

import { useEffect, useMemo, useRef, useState } from "react";

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
    void mountDynamicPanel(manifest, container, host, importer).then((result) => {
      if (disposed) return;
      if (result.ok) {
        instanceRef.current = result.instance;
      } else {
        setFailure(result);
      }
    });
    return () => {
      disposed = true;
      if (instanceRef.current) {
        try {
          instanceRef.current.unmount();
        } catch {
          /* ignore unmount errors */
        }
        instanceRef.current = null;
      }
    };
    // `key` captures the manifest identity; `manifest` is stable per prompt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, host, importer]);

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
      data-testid="dynamic-panel"
      data-block-id={blockId}
    >
      <div className="flex max-h-[85vh] w-[900px] flex-col overflow-hidden rounded-xl border border-stone-200 bg-white shadow-xl">
        {/* Mount point for the package panel module. Always present in the DOM so
            the mount effect has a stable container; hidden when we show the
            error surface instead. */}
        <div
          ref={containerRef}
          data-testid="dynamic-panel-mount"
          style={{ display: failure ? "none" : "block" }}
        />

        {failure ? (
          <div className="p-5" role="alert" data-testid="dynamic-panel-error">
            <div className="text-sm font-semibold text-red-700">
              Couldn’t load this interactive panel
            </div>
            <div className="mt-1 break-words text-xs text-stone-600">{failure.message}</div>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                className="rounded border border-stone-200 px-4 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
                onClick={onCancel}
                data-testid="dynamic-panel-cancel"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
