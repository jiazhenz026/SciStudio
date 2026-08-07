/**
 * ADR-053 spec 2 (#2001) — per-state agent guidance (FR-005, FR-031, FR-034).
 *
 * User Story 3: a user who activates this feature without a working agent must
 * be told the ACTUAL cause and the ACTUAL next step. The revised ADR-053 §4.1
 * makes an agent mandatory, so without accurate guidance this state is a dead
 * end rather than a setup step.
 *
 * SC-002 — no state may present guidance for a different state's cause. Each
 * block below renders only its own providers and only its own next step, so an
 * authenticated user whose call failed is never told to install anything.
 *
 * SC-002 also requires each block to name "a specific next action", and that
 * is what `next_step` on the provider row carries: the executable to install
 * and where SciStudio searched, or the command that signs that CLI in. It is
 * composed on the backend from the ADR-034 registry rather than restated here,
 * so a provider added to the registry cannot arrive with guidance nobody wrote.
 */
import {
  CALL_FAILED_BODY,
  CALL_FAILED_FOOTER,
  CALL_FAILED_HEADING,
  CHECK_AGAIN_LABEL,
  CHECKING_AGAIN_LABEL,
  NO_PROVIDERS_BODY,
  NOT_AUTHENTICATED_BODY,
  NOT_AUTHENTICATED_FOOTER,
  NOT_AUTHENTICATED_HEADING,
  NOT_INSTALLED_BODY,
  NOT_INSTALLED_FOOTER,
  NOT_INSTALLED_HEADING,
  SESSION_UNSUPPORTED_BODY,
  SESSION_UNSUPPORTED_FOOTER,
  SESSION_UNSUPPORTED_HEADING,
} from "./copy";
import { emptyReportGuidance, guidanceGroups, type GuidanceKind } from "./availability";
import type { AgentAvailabilityResponse } from "./useAgentAvailability";
import type { ProviderAvailability } from "./useAgentAvailability";

const HEADINGS: Record<GuidanceKind, string> = {
  not_installed: NOT_INSTALLED_HEADING,
  not_authenticated: NOT_AUTHENTICATED_HEADING,
  call_failed: CALL_FAILED_HEADING,
  session_unsupported: SESSION_UNSUPPORTED_HEADING,
  ready: "",
};

const BODIES: Record<GuidanceKind, string> = {
  not_installed: NOT_INSTALLED_BODY,
  not_authenticated: NOT_AUTHENTICATED_BODY,
  call_failed: CALL_FAILED_BODY,
  session_unsupported: SESSION_UNSUPPORTED_BODY,
  ready: "",
};

/**
 * The closing line of each block. `call_failed` is handled separately because
 * its footer sits next to the retry control it refers to.
 */
const FOOTERS: Partial<Record<GuidanceKind, string>> = {
  not_installed: NOT_INSTALLED_FOOTER,
  not_authenticated: NOT_AUTHENTICATED_FOOTER,
  session_unsupported: SESSION_UNSUPPORTED_FOOTER,
};

/**
 * What each provider's line says, which differs by why it is unusable.
 *
 * FR-034 — for `call_failed` the cause is the whole point of the state: quota,
 * network, a provider outage. Reporting the provider without it would send the
 * user looking for a fault with no description of it, and `next_step` is
 * deliberately null there because SciStudio does not know what would fix it.
 *
 * For the two states FR-031 gives a guidance column to, `next_step` IS the
 * guidance, and a line without it would be the bare provider name the audits
 * found — a list of things that are wrong with no way to act on any of them.
 */
function providerDetail(provider: ProviderAvailability): string | null {
  if (provider.session_unsupported_reason) return provider.session_unsupported_reason;
  if (provider.state === "call_failed") return provider.cause;
  return provider.next_step;
}

function providerLine(provider: ProviderAvailability): string {
  const detail = providerDetail(provider);
  return detail ? `${provider.label} — ${detail}` : provider.label;
}

function GuidanceBlock({
  state,
  providers,
  body,
  onRetry,
  retrying,
}: {
  state: GuidanceKind;
  providers: ProviderAvailability[];
  /** Overrides the per-state body; used for the empty-registry case. */
  body?: string;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  return (
    <div
      className="grid gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900"
      data-testid={`work-import-guidance-${state}`}
      data-state={state}
    >
      <span className="font-medium">{HEADINGS[state]}</span>
      <p className="text-xs">{body ?? BODIES[state]}</p>
      {providers.length > 0 ? (
        <ul className="list-disc pl-5 text-xs" data-testid={`work-import-guidance-list-${state}`}>
          {providers.map((provider) => (
            <li key={provider.key || provider.label}>{providerLine(provider)}</li>
          ))}
        </ul>
      ) : null}
      {FOOTERS[state] ? <p className="text-xs">{FOOTERS[state]}</p> : null}
      {state === "call_failed" ? (
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs">{CALL_FAILED_FOOTER}</p>
          {/*
           * The control the footer refers to. Without it "check again" is an
           * instruction the UI cannot carry out: the only other way to re-probe
           * is to close and reopen the dialog, and inside the backend's
           * 60-second memoisation window that re-serves the same failure to a
           * user who has just fixed it. `onRetry` passes `refresh=true`, which
           * is what that cache exists to be bypassed by.
           */}
          {onRetry ? (
            <button
              type="button"
              className="shrink-0 rounded-full border border-amber-300 px-3 py-1 text-xs font-medium disabled:opacity-50"
              data-testid="work-import-availability-retry"
              disabled={retrying}
              onClick={onRetry}
            >
              {retrying ? CHECKING_AGAIN_LABEL : CHECK_AGAIN_LABEL}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export interface AvailabilityGuidanceProps {
  availability: AgentAvailabilityResponse | null;
  /**
   * FR-035 — set when the probe itself failed or timed out. We could not
   * establish that a call succeeds, which is exactly `call_failed`. It renders
   * as its own block with the real cause rather than as an invented provider
   * row, because the backend never reported one.
   */
  probeError: string | null;
  /** Re-probe with `refresh=true`, bypassing the server-side memoisation. */
  onRetry?: () => void;
  /** True while a retry is in flight. */
  retrying?: boolean;
}

/**
 * Renders one guidance block per unusable kind present. Returns null when every
 * provider is usable and the probe succeeded — in that case the caller shows
 * the picker and the start action instead.
 */
export function AvailabilityGuidance({
  availability,
  probeError,
  onRetry,
  retrying,
}: AvailabilityGuidanceProps) {
  const groups = guidanceGroups(availability);
  // Contract C1's empty-registry case: no rows to group, but the user still
  // needs to be told why there is no start action.
  const empty = groups.length === 0 && !probeError ? emptyReportGuidance(availability) : null;
  if (groups.length === 0 && !probeError && !empty) return null;

  return (
    <div className="grid gap-2" data-testid="work-import-availability-guidance">
      {probeError ? (
        <GuidanceBlock
          state="call_failed"
          providers={[
            {
              key: "",
              label: "Agent check",
              state: "call_failed",
              cause: probeError,
              next_step: null,
              session_unsupported_reason: null,
            },
          ]}
          onRetry={onRetry}
          retrying={retrying}
        />
      ) : null}
      {empty ? <GuidanceBlock state={empty.state} providers={[]} body={NO_PROVIDERS_BODY} /> : null}
      {groups.map((group) => (
        <GuidanceBlock
          key={group.state}
          state={group.state}
          providers={group.providers}
          onRetry={group.state === "call_failed" ? onRetry : undefined}
          retrying={group.state === "call_failed" ? retrying : undefined}
        />
      ))}
    </div>
  );
}
