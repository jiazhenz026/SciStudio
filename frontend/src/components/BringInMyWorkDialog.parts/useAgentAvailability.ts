/**
 * ADR-053 spec 2 (#2001) — the dialog's agent-availability probe.
 *
 * This module is the ONLY place that touches `lib/api/agentAvailability.ts`.
 * That module is owned by the availability track (#2000) and its interface is
 * fixed by contract C1 (`docs/planning/adr-053-work-import-checklist.md` §7.1):
 *
 *   fetchAgentAvailability({refresh?}): Promise<AgentAvailabilityResponse>
 *   AgentAvailabilityResponse = {state, providers: [{key, label, state, cause,
 *                                next_step, session_unsupported_reason}]}
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
import { useCallback, useEffect, useRef, useState } from "react";

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
 * The server's own ceiling on a whole availability report, in milliseconds.
 *
 * Mirrors `REPORT_BUDGET_SECONDS` in `scistudio/ai/agent/availability.py`:
 * 15 s per live call plus 5 s of slack, after which the backend gives up on any
 * outstanding provider and reports it as timed out. Duplicated here because
 * this is TypeScript and that is Python; `tests/api/test_agent_availability.py`
 * reads this file and fails if the two stop agreeing.
 */
export const SERVER_REPORT_BUDGET_MS = 20_000;

/**
 * FR-035 — the client-side cap on a hanging probe.
 *
 * The backend probe is itself non-blocking (#2000), so this is the second line
 * of defence rather than the first: it covers a wedged request or a stalled
 * connection, where no backend guarantee can help.
 *
 * It therefore has to be LONGER than the server's own budget, and this was the
 * bug the 2026-08-07 no-context audit found: at 10 s the client gave up while
 * the server was still legitimately working, reported `call_failed` for an
 * agent that was about to answer, and withheld the start action. The slowest
 * successful call measured on the owner's workstation was Qoder at 8.3 s, which
 * left 1.7 s of margin on a machine with the provider installed and working.
 *
 * The margin above the server budget is for the round trip either side of it —
 * request queueing, JSON, a busy renderer — not for the probe, which the server
 * has already bounded. Reaching this timeout now means the *request* is wedged,
 * which is exactly what this cap is for.
 */
export const PROBE_TIMEOUT_MS = SERVER_REPORT_BUDGET_MS + 5_000;

export const PROBE_TIMEOUT_CAUSE = `The check did not answer within ${Math.round(
  PROBE_TIMEOUT_MS / 1000,
)} seconds, so we could not confirm the agent works.`;

/** The fetcher shape this hook drives, matching contract C1's client module. */
export type AvailabilityFetcher = (options?: {
  refresh?: boolean;
}) => Promise<AgentAvailabilityResponse>;

export interface AgentAvailabilityProbe {
  /** True while the initial probe is in flight. Never gates rendering — only the copy. */
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
  /**
   * Re-probe, bypassing the backend's memoised report.
   *
   * The report is memoised for 60 seconds because every live call is a real
   * billed request, which is right for a dialog being reopened and wrong for a
   * user who has just fixed the thing that failed: without `refresh` they are
   * re-served the same failure and told to try again. This is the control the
   * `call_failed` guidance refers to.
   */
  retry: () => void;
  /** True while a `retry()` is in flight. */
  retrying: boolean;
}

/**
 * Probe agent availability when the dialog opens, and on demand after that.
 *
 * `fetcher` exists so tests can supply a local double for contract C1. It is
 * read through a ref, so an unstable caller-side reference cannot re-fire the
 * probe on every render.
 */
export function useAgentAvailability(
  fetcher: AvailabilityFetcher = fetchAgentAvailability,
): AgentAvailabilityProbe {
  const [loading, setLoading] = useState(true);
  const [availability, setAvailability] = useState<AgentAvailabilityResponse | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  /** Guards against a result landing after the dialog closed. */
  const mountedRef = useRef(true);

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

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const retry = useCallback(() => {
    setRetrying(true);
    let settled = false;
    const finish = (next: AgentAvailabilityResponse | null, error: string | null) => {
      if (settled || !mountedRef.current) return;
      settled = true;
      clearTimeout(timer);
      setAvailability(next);
      setProbeError(error);
      setRetrying(false);
    };
    const timer = setTimeout(() => finish(null, PROBE_TIMEOUT_CAUSE), PROBE_TIMEOUT_MS);

    void fetcherRef
      .current({ refresh: true })
      .then((response) => finish(response, null))
      .catch((error: unknown) => {
        finish(null, error instanceof Error ? error.message : String(error));
      });
  }, []);

  return { loading, availability, probeError, retry, retrying };
}
