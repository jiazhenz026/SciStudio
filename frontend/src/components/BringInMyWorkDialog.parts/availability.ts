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
import type { ProviderOptionOverride } from "../AIChat/SetupScreen.parts/ProviderPicker";
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
 * Every provider in the report is listed, usable or not, which is what the AI
 * chat does and what the owner asked for on 2026-08-08: one dropdown, the
 * usable ones selectable, the rest greyed with a short suffix naming why. The
 * dialog used to offer only the usable ones and explain the rest in a paragraph
 * beside the picker; that paragraph is gone.
 *
 * `available` carries "can this run a session" rather than "is the CLI on
 * disk", because that is what the picker's own fallback derivation means by it
 * — so if `optionOverrides` were ever dropped, the ordering and the disabled
 * set would still be right and only the wording would coarsen. The wording is
 * supplied separately by `providerOptionOverrides`, precisely because
 * `available`/`logged_in` cannot express four states.
 */
export function toProviderStatuses(providers: ProviderAvailability[]): ProviderStatus[] {
  return providers.map((p) => ({
    name: p.key,
    available: isUsable(p),
    version: null,
    logged_in: true,
    label: p.label || p.key,
  }));
}

/**
 * The suffix each availability state puts after a provider's name in the list.
 *
 * As short as the AI chat's own `(not installed)` / `(not logged in)`, because
 * this is an annotation on a menu entry and not guidance. When NO provider is
 * usable the user gets `AvailabilityGuidance` instead, which is where FR-031's
 * per-state instructions and SC-002's specific next action live. That split is
 * deliberate: a user who has a working agent does not need to be told how to
 * repair one they are not using, and a user who has none needs exactly that.
 *
 * FR-034 constrains one entry here directly. `call_failed` must never be
 * reported as an install problem, so it says a call failed and nothing else —
 * the cause it also requires is in the guidance branch, which is the branch a
 * user who needs the cause is in.
 */
export const PROVIDER_STATE_HINT: Record<AgentAvailabilityState, string | null> = {
  ready: null,
  not_installed: "(not installed)",
  not_authenticated: "(not signed in)",
  call_failed: "(call failed)",
};

/** Suffix for a provider that works but cannot be handed a task (FR-029). */
export const SESSION_UNSUPPORTED_HINT = "(not available)";

/**
 * Per-provider hint and selectability for `ProviderPicker.optionOverrides`.
 *
 * WHY `not_authenticated` IS NOT SELECTABLE HERE, when the AI chat lets a user
 * launch a signed-out CLI on purpose.
 *
 * The AI chat's case is a hand-launched chat tab with no opening message: the
 * CLI drops into its own login flow inside the PTY, the user finishes it, and
 * types their first message afterwards. Nothing was at stake because nothing
 * had been said yet.
 *
 * A work-import session has exactly one delivery attempt and it happens at
 * `execve` time. `spawn_agent` appends the opening line as a POSITIONAL
 * ARGUMENT (`terminal.py::_initial_prompt_argv`, the `[-- <prompt>]` tail), and
 * that line — "Read the file … and follow the instructions in it" — is the
 * agent's only route to the brief, which is its only source of instructions
 * (FR-024, FR-028). Nothing types it into the PTY afterwards, and there is no
 * retry. A CLI that answers that argv by starting a login flow either consumes
 * the argument or drops it, and either way the session comes up with an agent
 * that never read its brief and a user who cannot tell.
 *
 * It is also what the rest of the stack already believes: contract C1 grades
 * `ready` only on a LIVE MINIMAL CALL succeeding (FR-033), which a signed-out
 * CLI cannot do, so `isUsable` excludes it and `canStart` would refuse it. A
 * selectable option the dialog then refuses to start on is worse than a greyed
 * one that says why.
 */
export function providerOptionOverrides(
  availability: AgentAvailabilityResponse | null,
): Record<string, ProviderOptionOverride> {
  const overrides: Record<string, ProviderOptionOverride> = {};
  for (const provider of availability?.providers ?? []) {
    overrides[provider.key] = {
      hint: provider.session_unsupported_reason
        ? SESSION_UNSUPPORTED_HINT
        : PROVIDER_STATE_HINT[provider.state],
      selectable: isUsable(provider),
    };
  }
  return overrides;
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
