/**
 * Zero-install guidance notice for SetupScreen.
 *
 * ADR-034 FR-021c: when the status payload has loaded and no agent provider
 * reports `available: true`, this notice REPLACES the provider picker. Without
 * it a first-run user meets an empty, all-disabled picker with no explanation —
 * the first-run dead end this closes.
 *
 * FR-021d: the caller renders this only in the loaded-and-all-unavailable
 * branch. Unknown availability (status in flight, or the status request failed)
 * is not confirmed absence and keeps its own loading / error treatment.
 *
 * Deliberately carries NO per-provider install commands. The owner's position is
 * that people who use these CLIs know how to install them; the gap being closed
 * is discoverability of the supported set, not per-provider onboarding.
 *
 * The supported agents are named from the status payload's backend-supplied
 * `label` values (FR-020b), so this file holds no hand-maintained list of
 * provider names.
 */
import type { ProviderStatus } from "./types";

export interface NoProvidersNoticeProps {
  /** Every supported agent as `GET /api/ai/status` reported it, in registry order. */
  providers: readonly ProviderStatus[];
}

export function NoProvidersNotice({ providers }: NoProvidersNoticeProps) {
  const names = providers.map((p) => p.label || p.name);

  return (
    <div
      className="grid gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900"
      data-testid="setup-no-providers-notice"
    >
      <span className="font-medium">No coding agent found</span>
      <p className="text-xs">
        SciStudio chat runs a coding-agent CLI that you install yourself. Install one of the
        supported agents, then open a new chat tab.
      </p>
      {names.length > 0 ? (
        <ul className="list-disc pl-5 text-xs" data-testid="setup-no-providers-list">
          {names.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
