/**
 * ADR-053 spec 2 (#2001) — pure helpers over the contract C1 payload.
 *
 * "Usable" means `state === "ready"`, and only that. FR-031's table is explicit
 * about what the other three states mean: no CLI found, no valid credentials,
 * or a live call that failed. A work-import session is long, autonomous, and
 * writes into the user's project — starting one on a provider that cannot
 * complete a single minimal call is not a degraded experience, it is a session
 * that dies partway through with files half written.
 *
 * FR-005 then follows from that definition: no usable provider means guidance
 * in place of a start action; SOME usable providers means the user proceeds
 * with one of them and is told, without being blocked, why the others are out.
 */
import type { ProviderStatus } from "../../store/types";

import type {
  AgentAvailabilityResponse,
  AgentAvailabilityState,
  ProviderAvailability,
} from "./useAgentAvailability";

export function usableProviders(
  availability: AgentAvailabilityResponse | null,
): ProviderAvailability[] {
  return (availability?.providers ?? []).filter((p) => p.state === "ready");
}

export function unusableProviders(
  availability: AgentAvailabilityResponse | null,
): ProviderAvailability[] {
  return (availability?.providers ?? []).filter((p) => p.state !== "ready");
}

/**
 * FR-005 — the start action exists only when at least one provider is usable.
 *
 * Derived from the provider rows rather than from the aggregate `state` field,
 * so a payload whose aggregate and rows disagree still cannot offer a start
 * action with nothing behind it.
 */
export function hasUsableProvider(availability: AgentAvailabilityResponse | null): boolean {
  return usableProviders(availability).length > 0;
}

/**
 * FR-042 — feed the EXISTING `ProviderPicker` without forking it.
 *
 * The picker speaks `GET /api/ai/status`'s two-boolean shape
 * (`available` / `logged_in`), which cannot express `call_failed`. Rather than
 * squeeze four states into two booleans — where `call_failed` would render as
 * "(not installed)", the exact misreport FR-034 exists to prevent — only the
 * usable providers are offered as options, and every non-usable one is
 * reported separately with its real state and its real cause.
 */
export function toProviderStatuses(providers: ProviderAvailability[]): ProviderStatus[] {
  return providers.map((p) => ({
    name: p.key,
    available: true,
    version: null,
    logged_in: true,
    label: p.label || p.key,
  }));
}

/**
 * Order the non-ready states by how actionable they are, matching C1's
 * aggregate ranking. Guidance is rendered per state, so a user with one
 * signed-out agent and one out-of-quota agent reads two accurate blocks rather
 * than one that describes the wrong cause (SC-002).
 */
export const GUIDANCE_STATE_ORDER: AgentAvailabilityState[] = [
  "call_failed",
  "not_authenticated",
  "not_installed",
];

export interface GuidanceGroup {
  state: AgentAvailabilityState;
  providers: ProviderAvailability[];
}

export function guidanceGroups(availability: AgentAvailabilityResponse | null): GuidanceGroup[] {
  const unusable = unusableProviders(availability);
  return GUIDANCE_STATE_ORDER.map((state) => ({
    state,
    providers: unusable.filter((p) => p.state === state),
  })).filter((group) => group.providers.length > 0);
}

/**
 * FR-043 — with exactly one usable provider, select it rather than presenting a
 * one-option choice. Most users have a single agent installed and there is no
 * decision behind that menu; the control still renders, so the user can see
 * which agent is about to run.
 *
 * Returns the currently selected key when it is still usable, so a re-probe
 * cannot silently move the user's choice.
 */
export function resolveSelectedProvider(
  availability: AgentAvailabilityResponse | null,
  current: string | null,
): string | null {
  const usable = usableProviders(availability);
  if (current && usable.some((p) => p.key === current)) return current;
  if (usable.length === 1) return usable[0].key;
  return null;
}
