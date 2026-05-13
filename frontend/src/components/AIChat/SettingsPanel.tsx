/**
 * Agent settings panel.
 *
 * Provides:
 *  - Provider selector ("claude-code" / "codex")
 *  - Permission mode (strict / bypass)
 *  - Future: concurrent-chat cap input
 *
 * Persisted via the central store's `partialize`.
 *
 * Issue #791: changing the permission mode while a chat session is
 * active triggers a confirm dialog. Confirming the change updates the
 * Zustand store, which causes ``useAgentWebSocket`` to tear down and
 * reopen the WS with the new ``permission_mode`` query parameter (the
 * backend reads it on connect and constructs a session with the
 * corresponding ``PermissionMode``). Cancelling reverts the dropdown.
 */

import { useAppStore } from "../../store";
import type { PermissionMode } from "../../types/agentEvents";

export function SettingsPanel() {
  const providerName = useAppStore((s) => s.providerName);
  const setProviderName = useAppStore((s) => s.setProviderName);
  const permissionMode = useAppStore((s) => s.permissionMode);
  const setPermissionMode = useAppStore((s) => s.setPermissionMode);
  const activeChatId = useAppStore((s) => s.activeChatId);

  const handlePermissionModeChange = (next: PermissionMode) => {
    if (next === permissionMode) return;
    // If no active session, the WS isn't open yet — just update.
    if (activeChatId === null) {
      setPermissionMode(next);
      return;
    }
    // Issue #791: the permission mode is fixed at WS-open time. To
    // change it mid-session we must reconnect, which from the user's
    // perspective is a fresh chat lifecycle on the same chat_id.
    const ok = window.confirm(
      "Changing permission mode requires restarting the agent session.\n\n" +
        `New mode: ${next === "strict" ? "Strict (prompt for every tool)" : "Bypass (auto-approve everything)"}\n\n` +
        "Continue?",
    );
    if (ok) {
      setPermissionMode(next);
    }
    // On cancel: do nothing; the <select> value is controlled by the
    // store so the dropdown snaps back to its previous value.
  };

  return (
    <div data-testid="settings-panel" className="flex flex-col gap-3 p-3 text-sm">
      <label className="flex items-center gap-2">
        <span className="w-28">Provider:</span>
        <select
          data-testid="settings-provider"
          value={providerName}
          onChange={(e) => setProviderName(e.target.value)}
          className="rounded border border-gray-300 px-2 py-1"
        >
          <option value="claude-code">Claude Code</option>
          <option value="codex">Codex</option>
        </select>
      </label>
      <label className="flex items-center gap-2">
        <span className="w-28">Permission mode:</span>
        <select
          data-testid="settings-permission-mode"
          value={permissionMode}
          onChange={(e) => handlePermissionModeChange(e.target.value as PermissionMode)}
          className="rounded border border-gray-300 px-2 py-1"
        >
          <option value="strict">Strict (prompt for every tool)</option>
          <option value="bypass">Bypass (auto-approve everything)</option>
        </select>
      </label>
      {permissionMode === "bypass" && (
        <p data-testid="settings-bypass-warning" className="rounded bg-red-50 px-2 py-1 text-xs text-red-800">
          ⚠ Bypass mode disables permission prompts. The agent will execute
          every tool call without confirmation. Only use this in trusted,
          ephemeral workspaces.
        </p>
      )}
    </div>
  );
}
