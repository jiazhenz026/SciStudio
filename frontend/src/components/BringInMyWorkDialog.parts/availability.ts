/**
 * ADR-053 spec 2 (#2001) — pure helpers over the contract C1 payload.
 *
 * "Usable" means two things, and it needs both.
 *
 * `state === "ready"`, and only that, for the availability half. FR-031's table
 * is explicit about what the other three states mean: no CLI found, no valid
 * credentials, or a live call that failed. A work-import session is long,
 * autonomous, and writes into the user's project — starting one on a provider
 * that cannot complete a single minimal call is not a degraded experience, it
 * is a session that dies partway through with files half written.
 *
 * `session_unsupported_reason === null` for the other half. "Installed and
 * signed in and a live call works" is not the same capability as "can be handed
 * an opening instruction on its command line", and a session needs both: the
 * brief is delivered by a one-line pointer passed as a positional argument
 * (FR-029), and a CLI that parses its first positional as a subcommand never
 * receives it. Grading that provider `ready` is correct — it answers calls —
 * but offering it here would mean FR-043 silently auto-selects an agent that
 * cannot start, which is what the 2026-08-07 no-context audit found.
 *
 * Why the capability arrives on the availability payload rather than being
 * decided here: it is a fact about the ADR-034 registry, and the registry lives
 * on the backend. A list of provider keys in this file would have to be edited
 * every time a provider is added, by someone who may never see this file, and
 * nothing would fail until a user pressed Start. The backend already answers
 * "can this provider be launched with an opening instruction" in one place
 * (`availability.session_unsupported_reason`) for the AI Block's sake, and the
 * availability report is already the shared carrier every agent-dependent
 * surface reads (FR-036) — so the fact travels with the grade that is fetched
 * at the same moment, for the same decision.
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

/** Whether this provider can actually run a session — both halves of "usable". */
export function isUsable(provider: ProviderAvailability): boolean {
  return provider.state === "ready" && !provider.session_unsupported_reason;
}

export function usableProviders(
  availability: AgentAvailabilityResponse | null,
): ProviderAvailability[] {
  return (availability?.providers ?? []).filter(isUsable);
}

export function unusableProviders(
  availability: AgentAvailabilityResponse | null,
): ProviderAvailability[] {
  return (availability?.providers ?? []).filter((p) => !isUsable(p));
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
 * The kinds of guidance block the dialog can render.
 *
 * Three of them are FR-031 states. `session_unsupported` is the fourth reason a
 * provider is not usable here, and it is deliberately NOT a fifth availability
 * state: contract C1's `state` answers "will a call work right now?", and the
 * answer for such a provider is genuinely "yes". Mixing the two would make
 * `ready` mean something different to this dialog than to every other consumer
 * of the shared report.
 */
export type GuidanceKind = AgentAvailabilityState | "session_unsupported";

/**
 * Order the guidance blocks by how actionable they are, matching C1's aggregate
 * ranking. Guidance is rendered per kind, so a user with one signed-out agent
 * and one out-of-quota agent reads two accurate blocks rather than one that
 * describes the wrong cause (SC-002).
 *
 * `session_unsupported` sits last because it is the only kind the user cannot
 * resolve for that provider at all — every other block names something they can
 * do to the agent they already have.
 */
export const GUIDANCE_STATE_ORDER: GuidanceKind[] = [
  "call_failed",
  "not_authenticated",
  "not_installed",
  "session_unsupported",
];

export interface GuidanceGroup {
  state: GuidanceKind;
  providers: ProviderAvailability[];
}

/**
 * Which block a provider belongs in.
 *
 * `session_unsupported` wins over the provider's state, and that ordering is
 * the point rather than an accident: a Kimi Code that is merely not installed
 * would otherwise be listed under "install this", and installing it would not
 * make it usable here. The dialog must not name an action that does not work.
 */
function guidanceKind(provider: ProviderAvailability): GuidanceKind {
  return provider.session_unsupported_reason ? "session_unsupported" : provider.state;
}

export function guidanceGroups(availability: AgentAvailabilityResponse | null): GuidanceGroup[] {
  const unusable = unusableProviders(availability);
  return GUIDANCE_STATE_ORDER.map((state) => ({
    state,
    providers: unusable.filter((p) => guidanceKind(p) === state),
  })).filter((group) => group.providers.length > 0);
}

/**
 * Guidance for a report that names no providers at all (contract C1's
 * empty-registry case, `aggregate_state([]) === "not_installed"`).
 *
 * `guidanceGroups` derives from provider ROWS, which is right for every other
 * case — a payload whose aggregate and rows disagree must not be able to offer
 * a start action with nothing behind it. But with no rows it yields nothing,
 * and the dialog rendered no agent section, no guidance, and no start action:
 * a form the user can fill in and never submit, with no explanation. C1 names
 * this case explicitly, so it gets an answer rather than a blank.
 *
 * Unreachable in production today — `agent_descriptors()` always yields the
 * five registered providers, pinned by `test_every_registry_agent_has_a_minimal_call`
 * — so this is the floor under a payload that should not exist, not a path
 * anyone is expected to take.
 */
export function emptyReportGuidance(
  availability: AgentAvailabilityResponse | null,
): GuidanceGroup | null {
  if (!availability || availability.providers.length > 0) return null;
  const state: GuidanceKind = availability.state === "ready" ? "not_installed" : availability.state;
  return { state, providers: [] };
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
