import { isRecord, PanelError } from "./types";
interface DecisionIdentity {
  context_id: string;
  workflow_id: string;
  block_id: string;
}
const pending = new Map<string, { identity: DecisionIdentity; settle: (error?: Error) => void }>();

/** Register before sending so even an immediate server acknowledgement is observed. */
export function submitPanelDecision(
  identity: DecisionIdentity,
  send: () => void,
  signal?: AbortSignal,
): Promise<void> {
  if (pending.has(identity.context_id))
    return Promise.reject(
      new PanelError("already_used", "A decision is already awaiting acknowledgement"),
    );
  return new Promise((resolve, reject) => {
    const settle = (error?: Error) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      pending.delete(identity.context_id);
      if (error) reject(error);
      else resolve();
    };
    const abort = () => settle(new DOMException("Panel closed", "AbortError"));
    const timer = setTimeout(
      () =>
        settle(
          new PanelError(
            "timeout",
            "The server did not acknowledge the decision. Remount to check the waiting interaction.",
          ),
        ),
      30000,
    );
    pending.set(identity.context_id, { identity, settle });
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) {
      abort();
      return;
    }
    try {
      send();
    } catch (error) {
      settle(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

/** Only the workflow socket dispatcher may deliver server decision acknowledgements. */
export function receivePanelDecision(payload: unknown): boolean {
  if (!isRecord(payload) || (payload.type !== "panel_accepted" && payload.type !== "panel_error"))
    return false;
  const error = isRecord(payload.error) ? payload.error : {};
  const item = typeof payload.context_id === "string" ? pending.get(payload.context_id) : undefined;
  if (
    item &&
    payload.workflow_id === item.identity.workflow_id &&
    payload.block_id === item.identity.block_id
  ) {
    item.settle(
      payload.type === "panel_error"
        ? new PanelError(
            typeof error.code === "string" ? error.code : "decision_rejected",
            typeof error.message === "string"
              ? error.message
              : "The server rejected the decision. Remount the panel to retry.",
          )
        : undefined,
    );
  }
  return true;
}
