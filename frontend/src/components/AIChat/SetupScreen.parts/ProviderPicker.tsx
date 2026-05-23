/**
 * Provider picker fieldset for SetupScreen.
 *
 * Extracted in #1413 to keep SetupScreen under the 150-line function limit.
 * Pure presentational; status info flows in from the parent.
 */
import type { ProviderStatus, ProviderName } from "./types";

export interface ProviderPickerProps {
  tabId: string;
  claudeStatus: ProviderStatus | undefined;
  codexStatus: ProviderStatus | undefined;
  statusLoading: boolean;
  provider: ProviderName | null;
  onChange: (provider: ProviderName) => void;
}

function renderProviderHint(s: ProviderStatus | undefined, statusLoading: boolean): string | null {
  if (!s) return statusLoading ? null : "(not installed)";
  if (!s.available) return "(not installed)";
  if (!s.logged_in) return "(not logged in)";
  return null;
}

export function ProviderPicker({
  tabId,
  claudeStatus,
  codexStatus,
  statusLoading,
  provider,
  onChange,
}: ProviderPickerProps) {
  const options = [
    { value: "claude-code" as const, label: "Claude Code", s: claudeStatus },
    { value: "codex" as const, label: "Codex", s: codexStatus },
  ];
  return (
    <fieldset className="grid gap-2" data-testid="setup-provider-group">
      <legend className="text-sm font-medium text-ink">Provider</legend>
      {options.map((opt) => {
        const hint = renderProviderHint(opt.s, statusLoading);
        const disabled = !!opt.s && !opt.s.available;
        return (
          <label
            key={opt.value}
            className={`flex items-center gap-2 rounded-2xl border px-3 py-2 text-sm ${
              disabled
                ? "border-stone-200 text-stone-400"
                : "border-stone-300 text-ink hover:bg-stone-50"
            }`}
          >
            <input
              type="radio"
              name={`setup-provider-${tabId}`}
              value={opt.value}
              checked={provider === opt.value}
              disabled={disabled}
              onChange={() => onChange(opt.value)}
              data-testid={`setup-provider-${opt.value}`}
            />
            <span>{opt.label}</span>
            {opt.s?.version ? (
              <span className="text-xs text-stone-400">v{opt.s.version}</span>
            ) : null}
            {hint ? (
              <span
                className="text-xs italic text-stone-500"
                data-testid={`setup-provider-${opt.value}-hint`}
              >
                {hint}
              </span>
            ) : null}
          </label>
        );
      })}
    </fieldset>
  );
}
