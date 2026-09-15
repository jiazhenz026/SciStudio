/**
 * ADR-054 MiniApps (#2354) — the three realtime frames a MiniApp needs.
 *
 * ``hello`` (CONTRACT §2.1) is the first frame the backend sends on ``/ws``. It
 * carries the id the backend knows this browser by, and every MiniApp context
 * create sends that id back as ``ws_client_id``. Without it the backend cannot
 * tell which workspace opened a MiniApp, and FR-013's "the process ends when
 * the workspace that opened it is gone" has nothing to key on — every MiniApp
 * process would outlive the tab that opened it.
 *
 * ``panel.open_miniapp`` (FR-030) is the agent asking the workspace to open a
 * MiniApp on one output. ``panel.files_changed`` (FR-022) is the panel
 * directory of an open MiniApp having changed on disk.
 *
 * The handlers take their store actions as dependencies rather than reaching
 * for ``useAppStore`` themselves: the dispatcher already owns the wiring, and a
 * handler that reaches for global state cannot be tested without standing the
 * whole store up.
 */
import type { MiniAppTarget } from "../../miniapps/types";
import type { PreviewRerouteSignal } from "../../panels/panelEvents";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

/**
 * How long a burst of panel-directory writes is allowed to settle (FR-022).
 *
 * The reload is not cheap — a new frame, context, and process on the same
 * source — and a single editor save can produce several inotify events (the
 * write, the rename of a temporary file, an asset rewritten beside it). 500 ms
 * is the spec's number.
 */

/** The store actions these handlers drive. All are owned by the store slice. */
export interface MiniAppRealtimeDeps {
  /** Remember the id the backend knows this browser by; ``null`` clears it. */
  setWsClientId: (id: string | null) => void;
  /** Open the MiniApp tab, or focus it when its id is already open (FR-018). */
  openMiniAppTab: (input: { panelId: string; name: string; target: MiniAppTarget }) => void;
  /** Reload every open mount of this panel, whatever its context kind (FR-022). */
  notifyPanelFilesChanged: (panelId: string) => void;
  /** Remount the mounts holding these revoked contexts (#2465). */
  notifyPanelContextsRevoked: (contextIds: readonly string[]) => void;
  /** Re-read the MiniApp catalog (the block catalog counter drives it). */
  bumpBlockCatalogRefresh: () => void;
  /** Re-read the Previewers listing and choices. */
  invalidatePreviewerCatalog: () => void;
  /** Re-route the open previews the signal concerns. */
  requestPreviewReroute: (signal: PreviewRerouteSignal) => void;
  appendLog: (entry: LogEntry) => void;
}

/**
 * Read a field that may sit at the frame's top level or inside ``data``.
 *
 * ``serialise_event`` lifts ``workflow_id`` out of the event data onto the
 * frame, so a ``panel.open_miniapp`` payload carries that one field at both
 * levels and the rest at one. The same tolerance ``handleBlockPty`` applies.
 */
function field(payload: WorkflowEventMessage, name: string): string | null {
  const top = payload as unknown as Record<string, unknown>;
  const data = (payload.data ?? {}) as Record<string, unknown>;
  const value = top[name] ?? data[name];
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * CONTRACT §2.1 — bind this browser to the id the backend minted for it.
 *
 * The frame is ``{"type": "hello", "client_id": "<id>"}`` and carries no event
 * data envelope, so it is read off the top level.
 */
export function handleWsHello(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "setWsClientId">,
): void {
  const clientId = field(payload, "client_id");
  if (clientId === null) {
    console.warn("[ws hello] frame carries no client_id; ignoring", payload);
    return;
  }
  deps.setWsClientId(clientId);
}

/**
 * The socket is gone: the id the backend minted is no longer ours.
 *
 * Clearing matters more than remembering. A context created with a client id
 * the backend has already retired is bound to a workspace that is not there,
 * and the backend closes it after FR-013's grace period — a MiniApp that opens
 * and then dies half a minute later. A reconnect sends a fresh ``hello``.
 */
export function handleWsDisconnected(deps: Pick<MiniAppRealtimeDeps, "setWsClientId">): void {
  deps.setWsClientId(null);
}

/**
 * FR-030 — the agent asked the workspace to open a MiniApp on one output.
 *
 * Opening an id that is already open focuses it rather than opening a second
 * tab; that guarantee belongs to ``openMiniAppTab`` (FR-018) and is not
 * re-implemented here, so an agent repeating the tool call cannot end up with
 * two tabs on one target through one path and one through the other.
 */
export function handleOpenMiniApp(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "openMiniAppTab" | "appendLog">,
): void {
  const panelId = field(payload, "panel_id");
  const workflowId = field(payload, "workflow_id");
  const blockId = field(payload, "block_id");
  const port = field(payload, "port");
  if (panelId === null || workflowId === null || blockId === null || port === null) {
    console.error("[panel.open_miniapp] frame is missing its panel or target; ignoring", payload);
    deps.appendLog({
      timestamp: payload.timestamp,
      level: "error",
      message:
        "[MiniApp] tab not opened: panel.open_miniapp carried no panel id or an " +
        "incomplete target (ADR-054 FR-030).",
      workflow_id: payload.workflow_id ?? null,
      block_id: payload.block_id ?? null,
    });
    return;
  }
  // The event's contract carries the target, not a display name. A name is
  // welcome when the emitter has one and the panel id is a perfectly good
  // label when it does not — this is the tab strip, not a validation surface.
  const name = field(payload, "name") ?? panelId;
  deps.openMiniAppTab({
    panelId,
    name,
    target: { workflow_id: workflowId, block_id: blockId, port },
  });
  deps.appendLog({
    timestamp: payload.timestamp,
    level: "info",
    message: `[MiniApp] opened ${name}`,
    workflow_id: workflowId,
    block_id: blockId,
  });
}

/**
 * FR-022 — a page file of an open panel changed; tell every mount of it.
 *
 * Deliberately NOT debounced here. FR-022's 500 ms window is a window on the
 * *reload*, and the reload happens in the shared panel host (`PanelFrame`),
 * which is where the timer lives and where unmounting cancels it. Coalescing
 * here as well would stack the two windows into one second.
 */
export function handlePanelFilesChanged(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "notifyPanelFilesChanged">,
): void {
  const panelId = field(payload, "panel_id");
  if (panelId === null) {
    console.warn("[panel.files_changed] frame carries no panel_id; ignoring", payload);
    return;
  }
  deps.notifyPanelFilesChanged(panelId);
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/**
 * #2465 Q3-a — the panel service revoked contexts whose panel was removed,
 * changed or shadowed, or whose project was left. Only their mounts remount.
 */
export function handlePanelContextsRevoked(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "notifyPanelContextsRevoked">,
): void {
  const data = (payload.data ?? {}) as Record<string, unknown>;
  deps.notifyPanelContextsRevoked(strings(data.context_ids));
}

/**
 * #2465 — the panel service's catalog diff (``blocks.reloaded`` with
 * ``registry: "panels"``).
 *
 *  - A MiniApp was added, changed or removed: re-read the MiniApp catalog.
 *  - Preview candidates changed: re-read the Previewers listing, and re-route
 *    only the open previews whose type the changed claims concern (Q3-y), plus
 *    every legacy-rendered preview when the legacy previewers were reloaded
 *    (Q5-b). Nothing else remounts.
 */
export function handlePanelCatalogChanged(
  payload: WorkflowEventMessage,
  deps: Pick<
    MiniAppRealtimeDeps,
    "bumpBlockCatalogRefresh" | "invalidatePreviewerCatalog" | "requestPreviewReroute"
  >,
): void {
  const data = (payload.data ?? {}) as Record<string, unknown>;
  if (data.miniapps_changed === true) deps.bumpBlockCatalogRefresh();
  if (data.preview_candidates_changed !== true) return;
  deps.invalidatePreviewerCatalog();
  deps.requestPreviewReroute({
    types: strings(data.preview_types),
    legacy: data.legacy_reloaded === true,
  });
}

/** #2465 Q6-b — a previewer choice changed; only previews of that type re-route. */
export function handlePanelChoicesChanged(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "invalidatePreviewerCatalog" | "requestPreviewReroute">,
): void {
  // Read from the event data only: the frame's own top-level `type` is the
  // event name.
  const raw = ((payload.data ?? {}) as Record<string, unknown>).type;
  const type = typeof raw === "string" && raw !== "" ? raw : null;
  if (type === null) {
    console.warn("[panel.choices_changed] frame carries no type; ignoring", payload);
    return;
  }
  deps.invalidatePreviewerCatalog();
  deps.requestPreviewReroute({ choiceType: type });
}
