/**
 * Provider picker for SetupScreen.
 *
 * Extracted in #1413 to keep SetupScreen under the 150-line function limit.
 * Pure presentational; status info flows in from the parent.
 *
 * ADR-034 FR-021: a single `select` driven entirely by the `GET /api/ai/status`
 * payload. There is deliberately no hand-maintained list of provider keys and no
 * frontend label map here — the option list, its order, and every display label
 * come from the payload (FR-020a / FR-020b), so a provider added to the backend
 * registry appears here with no frontend edit (User Story 7).
 */
import { isKnownAgentProvider } from "./types";
import type { ProviderStatus, TerminalProvider } from "./types";

/**
 * ADR-034 FR-021i — the initial, non-selectable value. There is no preselected
 * provider: registry order is arbitrary and would silently bias the choice.
 */
export const PROVIDER_PLACEHOLDER_LABEL = "Choose provider…";

export interface ProviderPickerProps {
  tabId: string;
  /** Status entries exactly as `GET /api/ai/status` returned them (registry order). */
  providers: readonly ProviderStatus[];
  statusLoading: boolean;
  provider: TerminalProvider | null;
  onChange: (provider: TerminalProvider) => void;
}

/**
 * ADR-034 FR-021a — annotation for a listed provider.
 *
 * `(not installed)` marks an option the user cannot launch but should still see,
 * so the supported set stays discoverable. `(not logged in)` is NOT disqualifying:
 * the CLI runs its own login flow inside the PTY, so the user can launch it and
 * finish authenticating there.
 */
function providerHint(s: ProviderStatus): string | null {
  if (!s.available) return "(not installed)";
  if (!s.logged_in) return "(not logged in)";
  return null;
}

function optionText(s: ProviderStatus): string {
  // FR-020b: the backend owns the display name. Falling back to the raw key is a
  // visible degradation, not a label map — it never invents a nicer name.
  const parts = [s.label || s.name];
  if (s.version) parts.push(`v${s.version}`);
  const hint = providerHint(s);
  if (hint) parts.push(hint);
  return parts.join(" ");
}

/**
 * ADR-034 FR-021b — available providers first, registry order preserved within
 * each group. `filter` is order-preserving, so two passes give a stable list and
 * the user never scans past a disabled entry to reach a selectable one.
 */
function orderedProviders(providers: readonly ProviderStatus[]): ProviderStatus[] {
  return [...providers.filter((p) => p.available), ...providers.filter((p) => !p.available)];
}

export function ProviderPicker({
  tabId,
  providers,
  statusLoading,
  provider,
  onChange,
}: ProviderPickerProps) {
  const options = orderedProviders(providers);
  const awaitingStatus = statusLoading && options.length === 0;
  const selectId = `setup-provider-select-${tabId}`;

  return (
    <div className="grid gap-2" data-testid="setup-provider-group">
      <label className="text-sm font-medium text-ink" htmlFor={selectId}>
        Provider
      </label>
      <select
        id={selectId}
        className="rounded-2xl border border-stone-300 px-3 py-2 text-sm text-ink disabled:text-stone-400"
        data-testid="setup-provider-select"
        value={provider ?? ""}
        disabled={awaitingStatus}
        onChange={(event) => {
          const value = event.target.value;
          // FR-020a: agent provider keys are opaque strings, so the selected key
          // is validated at runtime against the status payload rather than by a
          // TypeScript literal union. An unknown key is dropped, never defaulted.
          if (isKnownAgentProvider(value, providers)) onChange(value);
        }}
      >
        <option value="" disabled data-testid="setup-provider-placeholder">
          {PROVIDER_PLACEHOLDER_LABEL}
        </option>
        {options.map((s) => (
          <option
            key={s.name}
            value={s.name}
            disabled={!s.available}
            data-testid={`setup-provider-option-${s.name}`}
          >
            {optionText(s)}
          </option>
        ))}
      </select>
      {awaitingStatus ? (
        <span className="text-xs italic text-stone-500" data-testid="setup-provider-loading">
          Checking which agents are installed…
        </span>
      ) : null}
    </div>
  );
}
