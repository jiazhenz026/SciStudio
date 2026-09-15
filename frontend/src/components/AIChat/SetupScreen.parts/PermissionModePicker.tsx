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
 * FR-021f still holds for the existing values: each segment is a button with
 * `role="radio"`, and `safe` / `dangerous` keep their values (`data-value`) and
 * test ids. `auto` is the only new value. Buttons rather than hidden radio
 * inputs, so the picker contributes no form display values to the panel it
 * sits in; the native radio-group keyboard behaviour is restored by hand: one
 * Tab stop (the selected, else first enabled, segment) and arrow keys that
 * move to and select the next enabled segment, wrapping, skipping a disabled
 * Auto.
 */
import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";

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

  const buttonsRef = useRef<Array<HTMLButtonElement | null>>([]);
  const enabled = OPTIONS.map(({ mode }) => mode !== "auto" || autoSupported);
  const selectedIndex = OPTIONS.findIndex(({ mode }) => mode === permissionMode);
  const tabStop =
    selectedIndex >= 0 && enabled[selectedIndex] ? selectedIndex : enabled.indexOf(true);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === "ArrowRight" || event.key === "ArrowDown"
        ? 1
        : event.key === "ArrowLeft" || event.key === "ArrowUp"
          ? -1
          : 0;
    if (step === 0) return;
    event.preventDefault();
    let next = index;
    for (let i = 0; i < OPTIONS.length; i += 1) {
      next = (next + step + OPTIONS.length) % OPTIONS.length;
      if (enabled[next]) break;
    }
    onChange(OPTIONS[next].mode);
    buttonsRef.current[next]?.focus();
  };

  return (
    // #2083: core tutorial 3 rings the row while naming what each mode means.
    <fieldset
      className="grid gap-2"
      data-testid="setup-permission-group"
      data-tutorial-target="ai_permission_modes"
    >
      <legend className="text-sm font-medium text-ink">Permission mode</legend>
      <div
        id={`setup-permission-${tabId}`}
        role="radiogroup"
        aria-label="Permission mode"
        className="flex w-full overflow-hidden rounded-2xl border border-stone-300"
      >
        {OPTIONS.map(({ mode, label }, index) => {
          const disabled = mode === "auto" && !autoSupported;
          const checked = permissionMode === mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={disabled}
              tabIndex={index === tabStop ? 0 : -1}
              ref={(el) => {
                buttonsRef.current[index] = el;
              }}
              onKeyDown={(event) => onKeyDown(event, index)}
              data-value={mode}
              data-testid={`setup-permission-${mode}`}
              onClick={() => onChange(mode)}
              className={`flex flex-1 items-center justify-center px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-stone-500 ${
                index > 0 ? "border-l border-stone-300" : ""
              } ${
                disabled
                  ? "cursor-not-allowed bg-stone-100 text-stone-400"
                  : checked
                    ? "bg-ink font-medium text-white"
                    : "text-ink hover:bg-stone-50"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
