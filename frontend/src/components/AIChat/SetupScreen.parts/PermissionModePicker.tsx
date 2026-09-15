/**
 * Permission-mode picker fieldset for SetupScreen and Bring In My Work.
 *
 * Extracted in #1413 to keep SetupScreen under the 150-line function limit.
 *
 * ADR-034 Addendum 1 (#2379), superseding FR-021e's two-label wording: one row
 * of three segmented buttons labelled exactly `Manual`, `Auto` and
 * `Yolo/Bypass`, with no explanatory text. The labels are the whole UI; what
 * each mode does per provider lives in the registry, not in copy here. No CLI
 * flag name appears in the rendered output — `SetupScreen.test.tsx` asserts
 * the text contains no `--` substring.
 *
 * `Auto` is disabled when the selected provider's CLI has no auto mode
 * (`autoSupported`, read off the backend registry). If the provider changes to
 * one without it while `Auto` is selected, the picker falls back to `Manual`
 * so a launch can never carry a mode the CLI cannot honour.
 *
 * FR-021f still holds for the existing values: each button is a native radio
 * input (visually a segment), and `safe` / `dangerous` keep their values and
 * test ids. `auto` is the only new value.
 */
import { useEffect } from "react";

import type { PermissionMode } from "./types";

export interface PermissionModePickerProps {
  tabId: string;
  permissionMode: PermissionMode | null;
  onChange: (mode: PermissionMode) => void;
  /** Whether the selected provider's CLI has an Auto mode. */
  autoSupported: boolean;
}

const OPTIONS: ReadonlyArray<{ mode: PermissionMode; label: string }> = [
  { mode: "safe", label: "Manual" },
  { mode: "auto", label: "Auto" },
  { mode: "dangerous", label: "Yolo/Bypass" },
];

export function PermissionModePicker({
  tabId,
  permissionMode,
  onChange,
  autoSupported,
}: PermissionModePickerProps) {
  useEffect(() => {
    if (!autoSupported && permissionMode === "auto") onChange("safe");
  }, [autoSupported, permissionMode, onChange]);

  return (
    // #2083: core tutorial 3 rings the row while naming what each mode means.
    <fieldset
      className="grid gap-2"
      data-testid="setup-permission-group"
      data-tutorial-target="ai_permission_modes"
    >
      <legend className="text-sm font-medium text-ink">Permission mode</legend>
      <div className="flex w-full overflow-hidden rounded-2xl border border-stone-300">
        {OPTIONS.map(({ mode, label }, index) => {
          const disabled = mode === "auto" && !autoSupported;
          const checked = permissionMode === mode;
          return (
            <label
              key={mode}
              className={`flex flex-1 items-center justify-center px-3 py-2 text-sm ${
                index > 0 ? "border-l border-stone-300" : ""
              } ${
                disabled
                  ? "cursor-not-allowed bg-stone-100 text-stone-400"
                  : checked
                    ? "cursor-pointer bg-ink font-medium text-white"
                    : "cursor-pointer text-ink hover:bg-stone-50"
              } has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-inset has-[:focus-visible]:ring-stone-500`}
            >
              <input
                type="radio"
                name={`setup-permission-${tabId}`}
                value={mode}
                checked={checked}
                disabled={disabled}
                onChange={() => onChange(mode)}
                data-testid={`setup-permission-${mode}`}
                className="sr-only"
              />
              {label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
