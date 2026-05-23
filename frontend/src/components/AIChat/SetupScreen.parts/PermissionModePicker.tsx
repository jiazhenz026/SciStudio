/**
 * Permission-mode picker fieldset for SetupScreen.
 *
 * Extracted in #1413 to keep SetupScreen under the 150-line function limit.
 */
import type { PermissionMode } from "./types";

export interface PermissionModePickerProps {
  tabId: string;
  permissionMode: PermissionMode | null;
  onChange: (mode: PermissionMode) => void;
}

export function PermissionModePicker({
  tabId,
  permissionMode,
  onChange,
}: PermissionModePickerProps) {
  return (
    <fieldset className="grid gap-2" data-testid="setup-permission-group">
      <legend className="text-sm font-medium text-ink">Permission mode</legend>
      <label className="flex items-start gap-2 rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink hover:bg-stone-50">
        <input
          type="radio"
          name={`setup-permission-${tabId}`}
          value="safe"
          checked={permissionMode === "safe"}
          onChange={() => onChange("safe")}
          data-testid="setup-permission-safe"
          className="mt-1"
        />
        <span>
          <span className="font-medium">Ask</span> — default; the CLI prompts for tool use
          (Shift+Tab / /permissions).
        </span>
      </label>
      <label className="flex items-start gap-2 rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink hover:bg-stone-50">
        <input
          type="radio"
          name={`setup-permission-${tabId}`}
          value="dangerous"
          checked={permissionMode === "dangerous"}
          onChange={() => onChange("dangerous")}
          data-testid="setup-permission-dangerous"
          className="mt-1"
        />
        <span>
          <span className="font-medium">Bypass</span> — skips all approvals
          (--dangerously-skip-permissions / --dangerously-bypass-approvals-and-sandbox).
          <span className="block text-xs">
            Use only in ephemeral sandboxes. Cannot be toggled mid-session.
          </span>
        </span>
      </label>
    </fieldset>
  );
}
