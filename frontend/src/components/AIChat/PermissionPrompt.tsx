/**
 * Modal prompt for tool-permission decisions.
 *
 * Rendered when the active chat has a pending permission request in the
 * `aiChatSlice`. Offers Approve / Deny / Approve+Always. The caller
 * (AIChat) wires `onDecide` to the WS hook's `sendPermissionDecision`.
 *
 * NOTE on diff preview: Monaco diff is not currently a project
 * dependency. We render `tool_input` as JSON; if a future PR adds
 * Monaco it can replace the `<pre>` block. Diff is not a release
 * blocker — the user can read the JSON args.
 */

import { useAppStore } from "../../store";
import type { PermissionDecision } from "../../types/agentEvents";

export interface PermissionPromptProps {
  chatId: string;
  /**
   * Returns true if the decision was successfully sent. When false, the
   * modal stays open so the user can retry once the WS reconnects.
   * See PR #745 Codex P1 — clearing on send-failure left the backend
   * waiting on a decision that was never delivered.
   */
  onDecide: (requestId: string, decision: PermissionDecision) => boolean;
}

export function PermissionPrompt({ chatId, onDecide }: PermissionPromptProps) {
  const pending = useAppStore((s) => s.pendingPermissions[chatId] ?? null);
  const setPendingPermission = useAppStore((s) => s.setPendingPermission);
  const markAlwaysAllowed = useAppStore((s) => s.markAlwaysAllowed);

  if (pending === null) {
    return null;
  }

  const finalize = (decision: PermissionDecision) => {
    const sent = onDecide(pending.requestId, decision);
    if (sent) {
      setPendingPermission(chatId, null);
    }
  };

  const finalizeAlwaysAllow = () => {
    // Record the always-allow choice eagerly so that even if the send
    // fails right now and the user retries later, the policy is already
    // persisted. The modal only clears once the send succeeds.
    markAlwaysAllowed(pending.toolName);
    finalize("approve");
  };

  return (
    <div
      data-testid="permission-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="permission-prompt-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-[28rem] max-w-[90vw] rounded bg-white p-4 shadow-lg">
        <h3 id="permission-prompt-title" className="mb-2 text-base font-semibold">
          Allow agent to use{" "}
          <span className="font-mono text-blue-700">{pending.toolName}</span>?
        </h3>
        <pre className="mb-3 max-h-48 overflow-auto rounded bg-gray-50 p-2 text-xs">
          {JSON.stringify(pending.toolInput, null, 2)}
        </pre>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            data-testid="permission-deny"
            onClick={() => finalize("deny")}
            className="rounded border px-3 py-1 text-sm hover:bg-gray-100"
          >
            Deny
          </button>
          <button
            type="button"
            data-testid="permission-allow-once"
            onClick={() => finalize("approve")}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
          >
            Approve
          </button>
          <button
            type="button"
            data-testid="permission-allow-always"
            onClick={finalizeAlwaysAllow}
            className="rounded bg-green-600 px-3 py-1 text-sm text-white hover:bg-green-700"
          >
            Always allow this tool
          </button>
        </div>
      </div>
    </div>
  );
}
