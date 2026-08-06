/**
 * Permission-mode picker fieldset for SetupScreen.
 *
 * Extracted in #1413 to keep SetupScreen under the 150-line function limit.
 *
 * ADR-034 FR-021e: the two options are labelled `Manual Approve` and
 * `Bypass Permission`, and no CLI flag name appears anywhere in the rendered
 * output. The old copy leaked `--dangerously-skip-permissions` and
 * `--dangerously-bypass-approvals-and-sandbox` into the UI: those are per
 * provider, so the text was wrong for three of the five supported agents and
 * meaningless to a scientist choosing between "ask me" and "do not ask me".
 * `SetupScreen.test.tsx` asserts the rendered text contains no `--` substring so
 * a future edit cannot reintroduce one.
 *
 * FR-021f: this change is presentational only. The stored `safe` / `dangerous`
 * values, the radio `value` attributes, the test ids, and the launch payload are
 * all unchanged.
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
          <span className="font-medium">Manual Approve</span> — the agent asks you before it runs
          a command or changes a file.
          <span className="block text-xs">Recommended. You stay in control of every step.</span>
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
          <span className="font-medium">Bypass Permission</span> — the agent runs commands and
          changes files without asking.
          <span className="block text-xs">
            Use only in a sandbox you can throw away. This cannot be changed once the session
            starts.
          </span>
        </span>
      </label>
    </fieldset>
  );
}
