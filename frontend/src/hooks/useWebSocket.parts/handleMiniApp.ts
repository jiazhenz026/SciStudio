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
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

/**
 * How long a burst of panel-directory writes is allowed to settle (FR-022).
 *
 * The reload is not cheap — a new frame, context, and process on the same
 * source — and a single editor save can produce several inotify events (the
 * write, the rename of a temporary file, an asset rewritten beside it). 500 ms
 * is the spec's number.
 */
export const MINIAPP_RELOAD_DEBOUNCE_MS = 500;

/** The store actions these handlers drive. All are owned by the store slice. */
export interface MiniAppRealtimeDeps {
  /** Remember the id the backend knows this browser by; ``null`` clears it. */
  setWsClientId: (id: string | null) => void;
  /** Open the MiniApp tab, or focus it when its id is already open (FR-018). */
  openMiniAppTab: (input: { panelId: string; name: string; target: MiniAppTarget }) => void;
  /** Reload every open MiniApp tab on this panel (FR-022). */
  reloadMiniApp: (panelId: string) => void;
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

/** Pending reloads, one timer per panel id. */
const reloadTimers = new Map<string, ReturnType<typeof setTimeout>>();

/**
 * FR-022 — the panel directory changed; reload the MiniApp after it settles.
 *
 * Debounced here rather than in the tab: this is where the burst arrives, and
 * coalescing at the source means one reload per burst no matter how many tabs
 * are open on the panel. Keyed by panel id so a save in one MiniApp never
 * delays the reload of another.
 */
export function handlePanelFilesChanged(
  payload: WorkflowEventMessage,
  deps: Pick<MiniAppRealtimeDeps, "reloadMiniApp">,
): void {
  const panelId = field(payload, "panel_id");
  if (panelId === null) {
    console.warn("[panel.files_changed] frame carries no panel_id; ignoring", payload);
    return;
  }
  const pending = reloadTimers.get(panelId);
  if (pending !== undefined) clearTimeout(pending);
  reloadTimers.set(
    panelId,
    setTimeout(() => {
      reloadTimers.delete(panelId);
      deps.reloadMiniApp(panelId);
    }, MINIAPP_RELOAD_DEBOUNCE_MS),
  );
}

/**
 * Drop every pending reload without running it.
 *
 * For tests, and for a caller that knows the tabs are gone. A timer that fires
 * into a closed workspace reloads nothing, so this is tidiness rather than
 * correctness.
 */
export function cancelPendingMiniAppReloads(): void {
  for (const timer of reloadTimers.values()) clearTimeout(timer);
  reloadTimers.clear();
}
