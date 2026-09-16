/**
 * ADR-054 FR-018..FR-022 — the MiniApp centre tab.
 *
 * Three rules shape this component:
 *
 *  - **It stays mounted while another tab is active** (FR-019). The context,
 *    and therefore the `panel.py` process, lives exactly as long as the frame
 *    is mounted: `PanelFrame`'s effect cleanup DELETEs the context, which
 *    stops the process. So the layer below keeps every open MiniApp mounted
 *    and merely hides the ones that are not on screen. Teardown is
 *    unmount-driven for the same reason — closing the tab, and closing or
 *    switching the project (which empties the tab list wholesale), both
 *    unmount this component and both must end the process.
 *  - **A reload replaces the frame** (FR-022). The entry handshake is
 *    proof-bound and one-shot, so a page change reloads `PanelFrame` on a new
 *    context, a new frame and a new process. The shared panel host does this
 *    for every context kind (#2465); this tab only follows the new context.
 *  - **The context renews itself.** A MiniApp tab is long-lived and a context
 *    expires after 600 s; `PanelFrame` already heartbeats `renew` every 240 s
 *    for as long as it is mounted, which is what makes staying mounted enough.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import { PanelFrame } from "../panels/PanelFrame";
import type { PanelContext, PanelProcessStatus } from "../panels/types";
import { useAppStore } from "../store";
import type { MiniAppTab as MiniAppTabState } from "../store/types";
import { MiniAppToolbar } from "./MiniAppToolbar";
import { useMiniAppProcess } from "./useMiniAppProcess";

export interface MiniAppTabPaneProps {
  tab: MiniAppTabState;
  /** FR-036 — the Convert dialog is mounted by the workspace, not here. */
  onConvert: (panelId: string) => void;
}

export function MiniAppTabPane({ tab, onConvert }: MiniAppTabPaneProps) {
  const wsClientId = useAppStore((s) => s.wsClientId);
  // A reload (FR-022) or a revoked context (#2465) remounts the frame on a new
  // context; `onContext` hands this tab the new one.
  const [context, setContext] = useState<PanelContext | null>(null);

  const initial: PanelProcessStatus | null = context?.process ?? null;
  const process = useMiniAppProcess(context?.context_id ?? null, initial);

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="miniapp-tab-pane"
      data-gui-miniapp
      data-panel-id={tab.panelId}
      data-context-id={context?.context_id}
      data-process-state={process.status?.state ?? "absent"}
    >
      <MiniAppToolbar
        name={tab.displayName}
        status={process.status}
        processAbsent={process.absent}
        busy={process.busy}
        onRestart={process.restart}
        onStop={process.stop}
        onConvert={() => onConvert(tab.panelId)}
      />
      {process.error ? (
        <p role="alert" className="px-4 py-1 text-xs text-red-700">
          {process.error}
        </p>
      ) : null}
      {process.status?.error ? (
        <p role="alert" className="px-4 py-1 text-xs text-red-700">
          {process.status.error.type}: {process.status.error.message}
        </p>
      ) : null}
      {/* FR-014 — a crash shows the exit code (toolbar) and the log tail. */}
      {process.status?.log_tail ? (
        <pre
          className="max-h-32 overflow-auto border-b border-stone-200 px-4 py-2 text-[11px] text-stone-600"
          data-testid="miniapp-log-tail"
        >
          {process.status.log_tail}
        </pre>
      ) : null}
      <div className="flex min-h-0 flex-1 flex-col">
        {wsClientId ? (
          <PanelFrame
            key={tab.id}
            request={{
              kind: "miniapp",
              panel_id: tab.panelId,
              source: tab.source,
              // FR-013 — binds the context to this workspace connection so the
              // backend ends the process when the workspace goes away.
              ...(wsClientId ? { ws_client_id: wsClientId } : {}),
            }}
            onContext={setContext}
          />
        ) : (
          <p className="p-4 text-sm text-stone-500">Connecting to the workspace…</p>
        )}
      </div>
    </div>
  );
}

export interface MiniAppTabLayerProps {
  tabs: MiniAppTabState[];
  activeTabId: string | null;
  onConvert: (panelId: string) => void;
  /** #2482 — the reader clicked inside the active MiniApp. */
  onSurfaceInteract?: () => void;
}

/**
 * FR-019 — every open MiniApp, mounted. Only the active one is on screen; the
 * rest are hidden with their frames, contexts and processes intact, which is
 * what "stays open when another tab becomes active" means for a tab whose
 * lifetime owns a subprocess.
 */
export function MiniAppTabLayer({
  tabs,
  activeTabId,
  onConvert,
  onSurfaceInteract,
}: MiniAppTabLayerProps) {
  const activeRef = useRef<HTMLDivElement>(null);
  const hasActive = tabs.some((tab) => tab.id === activeTabId);
  useMiniAppSurfaceInteraction(activeRef, hasActive, onSurfaceInteract);
  if (tabs.length === 0) return null;
  return (
    <>
      {tabs.map((tab) => {
        const active = tab.id === activeTabId;
        return (
          <div
            key={tab.id}
            ref={active ? activeRef : undefined}
            className={active ? "absolute inset-0" : "hidden"}
            data-testid={`miniapp-tab-${tab.id}`}
            onPointerDown={active ? onSurfaceInteract : undefined}
          >
            <MiniAppTabPane tab={tab} onConvert={onConvert} />
          </div>
        );
      })}
    </>
  );
}

/**
 * #2482 — a click inside the active MiniApp's frame.
 *
 * The frame is a sandboxed cross-origin iframe, so its pointer events never
 * reach this document and a `pointerdown` listener sees only the host chrome
 * around it (handled by the layer's own `onPointerDown`). What the host does
 * see is focus: a click in the frame moves focus into it, which blurs this
 * window and leaves `document.activeElement` on the iframe. Reading focus
 * keeps the panel SDK and its bridge contract untouched.
 *
 * Focus only moves once, so a second click in a frame that already has focus
 * is not seen. That is enough here: reopening the bottom panel is itself a
 * click in the host, which takes focus back, so the next click in the frame
 * blurs the window again.
 */
export function useMiniAppSurfaceInteraction(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  onInteract: (() => void) | undefined,
): void {
  const callback = useRef(onInteract);
  callback.current = onInteract;
  useEffect(() => {
    if (!active) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onBlur = () => {
      // Some engines move `activeElement` only after `blur` has dispatched.
      clearTimeout(timer);
      timer = setTimeout(() => {
        const focused = document.activeElement;
        if (focused instanceof HTMLIFrameElement && containerRef.current?.contains(focused)) {
          callback.current?.();
        }
      }, 0);
    };
    window.addEventListener("blur", onBlur);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("blur", onBlur);
    };
  }, [active, containerRef]);
}

/**
 * #2482 — what a click in the active MiniApp does to the bottom panel: fold it
 * away for more room, under the same pin rule as a click on the empty canvas.
 * A panel that is already collapsed is left alone.
 */
export function collapseBottomPanelForMiniApp(
  panel: PanelImperativeHandle | null,
  pinned: boolean,
): void {
  if (!panel || pinned || panel.isCollapsed()) return;
  panel.collapse();
}

/**
 * ADR-054 FR-020 — the right preview column while a MiniApp is active.
 *
 * A MiniApp takes the stage, so the column folds away when its tab becomes
 * active and comes back at the width it had when a tab of another kind takes
 * over. Three rules keep the reader in charge:
 *
 *  - a column they had already collapsed is left alone, and nothing is
 *    remembered to restore;
 *  - a column they drag open while the MiniApp is active keeps the width they
 *    dragged it to — the restore fires only on a column still collapsed here;
 *  - the AI host renders no right column at all, so `panelRef.current` is null
 *    there and this collapses nothing.
 *
 * The pre-collapse width is read off the panel handle rather than the store's
 * `panelSizes.preview`: that writer skips anything under 4%, so it holds a
 * stale number exactly when the column is narrow.
 *
 * #2456 — the collapse is transient layout. It is flagged with
 * `previewCollapsedByMiniApp` before the panel folds, so the persisted
 * preference keeps the column the user left open; the flag clears once the
 * column opens again, by the restore or by the user, and an unmount with the
 * flag still set (closing or switching the project on a MiniApp) hands the
 * next workspace an open column.
 */
export function useMiniAppPreviewColumn(
  panelRef: RefObject<PanelImperativeHandle | null>,
  miniAppActive: boolean,
): void {
  const [restoreTo] = useState<{ percentage: number | null }>(() => ({ percentage: null }));
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    if (miniAppActive) {
      if (panel.isCollapsed()) {
        restoreTo.percentage = null;
        return;
      }
      restoreTo.percentage = panel.getSize().asPercentage;
      useAppStore.setState({ previewCollapsedByMiniApp: true });
      panel.collapse();
      return;
    }
    const percentage = restoreTo.percentage;
    restoreTo.percentage = null;
    // A column the user opened while the MiniApp was active cleared the flag:
    // whatever they did with it since is theirs, so nothing is restored.
    const stillMiniAppCollapse = useAppStore.getState().previewCollapsedByMiniApp;
    if (stillMiniAppCollapse) useAppStore.setState({ previewCollapsedByMiniApp: false });
    if (percentage === null || !stillMiniAppCollapse || !panel.isCollapsed()) return;
    panel.expand();
    panel.resize(`${percentage}%`);
  }, [miniAppActive, panelRef, restoreTo]);
  useEffect(
    () => () => {
      if (useAppStore.getState().previewCollapsedByMiniApp) {
        useAppStore.setState({ previewCollapsed: false, previewCollapsedByMiniApp: false });
      }
    },
    [],
  );
}

/**
 * The preview panel's `onResize` writer: `previewCollapsed` mirrors the panel.
 * Any size above zero ends a MiniApp's transient collapse (#2456), so a later
 * collapse, by drag or shortcut, is the user's and is persisted.
 */
export function recordPreviewColumnSize(size: { asPercentage: number }): void {
  const collapsed = size.asPercentage === 0;
  const state = useAppStore.getState();
  if (collapsed !== state.previewCollapsed) useAppStore.setState({ previewCollapsed: collapsed });
  if (!collapsed && state.previewCollapsedByMiniApp) {
    useAppStore.setState({ previewCollapsedByMiniApp: false });
  }
}

/** Apply explicit preview visibility requests, including the tutorial route. */
export function usePreviewColumnState(panelRef: RefObject<PanelImperativeHandle | null>): void {
  const collapsed = useAppStore((s) => s.previewCollapsed);
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    if (collapsed && !panel.isCollapsed()) panel.collapse();
    if (!collapsed && panel.isCollapsed()) panel.expand();
  }, [collapsed, panelRef]);
}
