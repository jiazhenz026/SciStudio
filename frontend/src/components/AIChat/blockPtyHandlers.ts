/**
 * ADR-035 §3.10 — engine-initiated PTY tab event handlers.
 *
 * Extracted from TerminalTabs.tsx into its own module to break the import
 * cycle between `hooks/useWebSocket` and `components/AIChat/TerminalTabs`:
 *   - `useWebSocket.ts` dispatches incoming WS frames here.
 *   - `TerminalTabs.tsx` consumes `sendWebSocketMessage` from `useWebSocket.ts`.
 * If both handlers lived in TerminalTabs.tsx, Rollup's circular-import
 * resolution returned `undefined` for the lazily-bound exports at runtime
 * (verified empirically — neither `addAiBlockTerminalTab` nor `appendLog`
 * fired even though the WS message was correctly parsed and routed).
 */
import { useAppStore } from "../../store";
import type { AiBlockStatus } from "../../store/types";

/**
 * Handle the `block_pty_opened` WS event.
 *
 * The engine emits this after :func:`scistudio.api.routes.ai_pty.open_engine_initiated_tab`
 * spawns a PTY for an AI Block worker. We register the tab in the store with
 * `source="ai-block"`, `state="running"` (skipping SetupScreen), and
 * `blockStatus="paused"`. The matching TerminalView mounts and connects to
 * the existing `/api/ai/pty/{tab_id}` route, joining the pre-spawned PTY.
 *
 * Field-name compatibility: the dispatch (I35c) pins the payload to
 * `{tab_id, block_run_id, block_name, status}`; the skeleton stub for
 * `open_engine_initiated_tab` mentions `title` instead of `block_name`. We
 * accept either to keep the handler resilient against either backend choice.
 * Title prefix `🤖` is added here so I35a/I35b don't have to remember it.
 *
 * References: ADR-035 §3.9, §3.10
 */
export function handleBlockPtyOpened(payload: {
  tab_id: string;
  block_run_id: string;
  /** Either field is accepted; `block_name` wins if both present. */
  block_name?: string;
  title?: string;
  /** Optional initial status. Defaults to "paused" per §3.9. */
  status?: AiBlockStatus;
  permission_mode?: "safe" | "bypass" | "dangerous";
}): void {
  const { tab_id, block_run_id } = payload;
  if (!tab_id || !block_run_id) {
    // eslint-disable-next-line no-console
    console.warn("[block_pty_opened] missing tab_id / block_run_id; ignoring", payload);
    return;
  }
  const rawName = payload.block_name ?? payload.title ?? "AI Block";
  const title = rawName.startsWith("🤖") ? rawName : `🤖 ${rawName}`;
  // Normalise permission_mode: backend uses "bypass", frontend tab uses "dangerous".
  const permissionMode: "safe" | "dangerous" =
    payload.permission_mode === "bypass" || payload.permission_mode === "dangerous"
      ? "dangerous"
      : "safe";
  useAppStore.getState().addAiBlockTerminalTab({
    tabId: tab_id,
    title,
    blockRunId: block_run_id,
    permissionMode,
  });
  if (payload.status && payload.status !== "paused") {
    useAppStore.getState().updateAiBlockStatus(tab_id, payload.status);
  }
}

/** Map a backend close result to the corresponding `AiBlockStatus`. */
function mapCloseResult(
  result: "completed" | "cancelled" | "error" | "done" | string | undefined,
): AiBlockStatus {
  switch (result) {
    case "completed":
    case "done":
      return "done";
    case "cancelled":
      return "cancelled";
    case "error":
      return "error";
    default:
      return "error"; // conservative default — better an ✗ than silent
  }
}

/**
 * Handle the `block_pty_closed` WS event.
 *
 * Engine emits this after the worker calls
 * :func:`scistudio.engine.pty_control.notify_block_pty_event`. We update the
 * matching tab's `blockStatus` to done / error / cancelled. Per §3.9, the
 * TerminalView stays mounted — the tab remains interactive so the user can
 * keep chatting with the agent (e.g. to debug a failed output).
 *
 * Idempotent: unknown tab_id is a no-op (e.g. tab was closed before the
 * close event arrived).
 *
 * References: ADR-035 §3.9, §3.10
 */
export function handleBlockPtyClosed(payload: {
  tab_id: string;
  block_run_id?: string;
  /** Dispatch-pinned status union; legacy `result` accepted too. */
  status?: "done" | "error" | "cancelled";
  result?: "completed" | "cancelled" | "error";
  detail?: Record<string, unknown>;
}): void {
  const tabId = payload.tab_id;
  if (!tabId) {
    // eslint-disable-next-line no-console
    console.warn("[block_pty_closed] missing tab_id; ignoring", payload);
    return;
  }
  const status = mapCloseResult(payload.status ?? payload.result);
  useAppStore.getState().updateAiBlockStatus(tabId, status);
}
