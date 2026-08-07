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
 */
import {
  CALL_FAILED_BODY,
  CALL_FAILED_FOOTER,
  CALL_FAILED_HEADING,
  NOT_AUTHENTICATED_BODY,
  NOT_AUTHENTICATED_HEADING,
  NOT_INSTALLED_BODY,
  NOT_INSTALLED_HEADING,
} from "./copy";
import { guidanceGroups } from "./availability";
import type { AgentAvailabilityResponse, AgentAvailabilityState } from "./useAgentAvailability";
import type { ProviderAvailability } from "./useAgentAvailability";

const HEADINGS: Record<AgentAvailabilityState, string> = {
  not_installed: NOT_INSTALLED_HEADING,
  not_authenticated: NOT_AUTHENTICATED_HEADING,
  call_failed: CALL_FAILED_HEADING,
  ready: "",
};

const BODIES: Record<AgentAvailabilityState, string> = {
  not_installed: NOT_INSTALLED_BODY,
  not_authenticated: NOT_AUTHENTICATED_BODY,
  call_failed: CALL_FAILED_BODY,
  ready: "",
};

function providerLine(provider: ProviderAvailability): string {
  // FR-034 — the cause is the whole point of the `call_failed` state: quota,
  // network, a provider outage. Reporting the provider without it would send
  // the user looking for a fault with no description of it.
  return provider.cause ? `${provider.label} — ${provider.cause}` : provider.label;
}

function GuidanceBlock({
  state,
  providers,
}: {
  state: AgentAvailabilityState;
  providers: ProviderAvailability[];
}) {
  return (
    <div
      className="grid gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900"
      data-testid={`work-import-guidance-${state}`}
      data-state={state}
    >
      <span className="font-medium">{HEADINGS[state]}</span>
      <p className="text-xs">{BODIES[state]}</p>
      {providers.length > 0 ? (
        <ul className="list-disc pl-5 text-xs" data-testid={`work-import-guidance-list-${state}`}>
          {providers.map((provider) => (
            <li key={provider.key || provider.label}>{providerLine(provider)}</li>
          ))}
        </ul>
      ) : null}
      {state === "call_failed" ? <p className="text-xs">{CALL_FAILED_FOOTER}</p> : null}
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
}

/**
 * Renders one guidance block per non-ready state present. Returns null when
 * every provider is ready and the probe succeeded — in that case the caller
 * shows the picker and the start action instead.
 */
export function AvailabilityGuidance({ availability, probeError }: AvailabilityGuidanceProps) {
  const groups = guidanceGroups(availability);
  if (groups.length === 0 && !probeError) return null;

  return (
    <div className="grid gap-2" data-testid="work-import-availability-guidance">
      {probeError ? (
        <GuidanceBlock
          state="call_failed"
          providers={[{ key: "", label: "Agent check", state: "call_failed", cause: probeError }]}
        />
      ) : null}
      {groups.map((group) => (
        <GuidanceBlock key={group.state} state={group.state} providers={group.providers} />
      ))}
    </div>
  );
}
