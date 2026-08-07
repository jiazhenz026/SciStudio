/**
 * Graded agent availability — ADR-053 spec 2, FR-031 to FR-036.
 *
 * `GET /api/ai/status` answers whether each agent CLI is installed and logged
 * in. That is not the question a surface about to start an agent session has.
 * A user whose CLI is installed, whose credentials are on disk, and whose
 * account is out of quota passes every presence check and then fails several
 * steps into the session, where recovery costs the most. This endpoint grades
 * the same providers into four states by making a real minimal call, so the
 * failure surfaces before the user commits.
 *
 * Availability is shared, not private to one dialog (FR-036): Bring In My Work
 * is the first consumer and the Learning Center agent-setup entry is another,
 * so every availability type lives here rather than in the global store types.
 */

import { apiFetch } from "./core";

/**
 * The four states of FR-031, in increasing order of usability.
 *
 * - `not_installed` — no agent CLI found; installation instructions apply.
 * - `not_authenticated` — installed, no valid credentials; login instructions apply.
 * - `call_failed` — authenticated, but a live call failed; show `cause`.
 * - `ready` — a live call succeeded; this provider works right now.
 */
export type AgentAvailabilityState =
  | "not_installed"
  | "not_authenticated"
  | "call_failed"
  | "ready";

/** One provider's graded availability. */
export interface ProviderAvailability {
  /** Provider-registry key, e.g. `claude-code`. Stable across releases. */
  key: string;
  /** User-facing product name, supplied by the backend so no label map is needed here. */
  label: string;
  state: AgentAvailabilityState;
  /**
   * Why the live call failed — quota, network, provider outage.
   *
   * Populated only when `state` is `call_failed`, and guaranteed free of
   * reinstall guidance (FR-034): telling a user whose CLI demonstrably runs to
   * reinstall it sends them to fix something that is not broken.
   */
  cause: string | null;
}

/** The full report returned by `GET /api/ai/availability`. */
export interface AgentAvailabilityResponse {
  /**
   * The aggregate state a surface renders its guidance from.
   *
   * `ready` when **any** provider is ready — one unconfigured CLI must not
   * block a user who has a working one (FR-005). Otherwise the most actionable
   * state present, ranked `call_failed` > `not_authenticated` >
   * `not_installed`, so the guidance shown is the one closest to a working
   * setup.
   */
  state: AgentAvailabilityState;
  /** Every registered agent provider, in registry order. */
  providers: ProviderAvailability[];
}

/**
 * Fetch graded agent availability.
 *
 * Each live call is a real billed request to the provider, so the backend
 * memoises the report briefly and shares it across surfaces. Pass
 * `{ refresh: true }` only behind an explicit user-facing retry control — a
 * user who has just fixed their quota should not have to wait out a cache.
 *
 * The probe is bounded on the backend and never hangs, but it is not instant:
 * a live call takes seconds. Callers must render first and fill this in when it
 * resolves (FR-035), never block a surface on the result.
 */
export async function fetchAgentAvailability(
  options: { refresh?: boolean } = {},
): Promise<AgentAvailabilityResponse> {
  const path = options.refresh ? "/api/ai/availability?refresh=true" : "/api/ai/availability";
  return apiFetch<AgentAvailabilityResponse>(path);
}
