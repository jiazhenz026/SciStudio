/**
 * Agent settings panel.
 *
 * Provides:
 *  - Provider selector ("claude-code" / "codex"; codex lands Phase 4)
 *  - Permission mode (strict / bypass)
 *  - Future: concurrent-chat cap input
 *
 * Persisted via the central store's `partialize`.
 */

import { useAppStore } from "../../store";

export function SettingsPanel() {
  const providerName = useAppStore((s) => s.providerName);
  const setProviderName = useAppStore((s) => s.setProviderName);
  const permissionMode = useAppStore((s) => s.permissionMode);
  const setPermissionMode = useAppStore((s) => s.setPermissionMode);

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
          <option value="codex">Codex (Phase 4)</option>
        </select>
      </label>
      <label className="flex items-center gap-2">
        <span className="w-28">Permission mode:</span>
        <select
          data-testid="settings-permission-mode"
          value={permissionMode}
          onChange={(e) => setPermissionMode(e.target.value as "strict" | "bypass")}
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
