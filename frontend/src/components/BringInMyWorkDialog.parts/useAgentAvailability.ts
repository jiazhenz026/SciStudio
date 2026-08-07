/**
 * ADR-053 spec 2 (#2001) — the dialog's agent-availability probe.
 *
 * This module is the ONLY place that touches `lib/api/agentAvailability.ts`.
 * That module is owned by the availability track (#2000) and its interface is
 * fixed by contract C1 (`docs/planning/adr-053-work-import-checklist.md` §7.1):
 *
 *   fetchAgentAvailability(): Promise<AgentAvailabilityResponse>
 *   AgentAvailabilityResponse = {state, providers: [{key, label, state, cause}]}
 *   state ∈ not_installed | not_authenticated | call_failed | ready
 *
 * Keeping the import in one file means the whole dialog consumes the contract
 * through a single seam, and the C1 types are re-exported from here so nothing
 * else in the dialog reaches across to another track's module.
 *
 * FR-035 — the probe MUST NOT block the dialog from rendering. Two things
 * follow. The dialog renders immediately with `loading: true` rather than
 * waiting, and a probe that never comes back is capped by the timeout below and
 * degrades to a REPORTED state. A slow provider must never produce a stuck
 * surface; it produces a sentence.
 */
import { useEffect, useRef, useState } from "react";

import {
  fetchAgentAvailability,
  type AgentAvailabilityResponse,
} from "../../lib/api/agentAvailability";

export type {
  AgentAvailabilityResponse,
  AgentAvailabilityState,
  ProviderAvailability,
} from "../../lib/api/agentAvailability";

/**
 * FR-035 — the client-side cap on a hanging probe.
 *
 * The backend probe is itself non-blocking (#2000), so this is the second line
 * of defence rather than the first: it covers a wedged request or a stalled
 * connection, where no backend guarantee can help. Ten seconds is long enough
 * that a merely slow answer still arrives and short enough that a user does not
 * conclude the dialog is broken.
 */
export const PROBE_TIMEOUT_MS = 10_000;

export const PROBE_TIMEOUT_CAUSE =
  "The check did not answer within 10 seconds, so we could not confirm the agent works.";

export interface AgentAvailabilityProbe {
  /** True while the probe is in flight. Never gates rendering — only the copy. */
  loading: boolean;
  /** The C1 payload, or null when the probe itself failed. */
  availability: AgentAvailabilityResponse | null;
  /**
   * Set when the probe request failed or timed out. Reported as a `call_failed`
   * cause, because that is what it is: we could not establish that a call
   * succeeds. It is deliberately NOT folded into a synthetic provider row —
   * inventing registry entries the backend never reported would misreport the
   * user's setup.
   */
  probeError: string | null;
}

/**
 * Probe agent availability once, when the dialog opens.
 *
 * `fetcher` exists so tests can supply a local double for contract C1 while
 * that module is authored on another branch. It is read through a ref, so an
 * unstable caller-side reference cannot re-fire the probe on every render.
 */
export function useAgentAvailability(
  fetcher: () => Promise<AgentAvailabilityResponse> = fetchAgentAvailability,
): AgentAvailabilityProbe {
  const [loading, setLoading] = useState(true);
  const [availability, setAvailability] = useState<AgentAvailabilityResponse | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let settled = false;
    const finish = (next: AgentAvailabilityResponse | null, error: string | null) => {
      if (settled) return;
      settled = true;
      setAvailability(next);
      setProbeError(error);
      setLoading(false);
    };

    const timer = setTimeout(() => finish(null, PROBE_TIMEOUT_CAUSE), PROBE_TIMEOUT_MS);

    void fetcherRef
      .current()
      .then((response) => finish(response, null))
      .catch((error: unknown) => {
        finish(null, error instanceof Error ? error.message : String(error));
      })
      .finally(() => clearTimeout(timer));

    return () => {
      settled = true;
      clearTimeout(timer);
    };
  }, []);

  return { loading, availability, probeError };
}
