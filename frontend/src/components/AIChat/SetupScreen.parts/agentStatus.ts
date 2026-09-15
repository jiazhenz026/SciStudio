/**
 * The one provider-status source for every surface that starts an agent session.
 *
 * #2454 (owner directive): the AI Chat setup screen and the dialogs that start
 * a session — New MiniApp, Convert to interactive block, Bring in my work — and
 * the Learning Center's provider introduction read the same payload, through the
 * same hook, with the same launch rule. There is no second, graded availability
 * report and no live model call: `GET /api/ai/status` answers installed, signed
 * in, version and Auto support, and the backend's launch check
 * (`validate_agent_launch`) refuses what the spawn could not honour.
 */
import { useEffect, useState } from "react";

import { apiFetch } from "../../../lib/api/core";

import type { AiStatusResponse, PermissionMode, ProviderStatus } from "./types";

// Module-level cache (30s TTL). Every surface mounted within 30s shares the same
// in-flight / cached payload.
let _statusCache: { at: number; data: AiStatusResponse } | null = null;
let _statusInflight: Promise<AiStatusResponse> | null = null;

export async function fetchAgentStatus(force = false): Promise<AiStatusResponse> {
  const now = Date.now();
  if (!force && _statusCache && now - _statusCache.at < 30_000) {
    return _statusCache.data;
  }
  if (_statusInflight) return _statusInflight;
  _statusInflight = (async () => {
    try {
      // apiFetch routes through the base-path helper (ADR-055 Spec 0 FR-004)
      // and throws ApiError for non-2xx, so no manual r.ok check is needed.
      const data = await apiFetch<AiStatusResponse>("/api/ai/status");
      _statusCache = { at: Date.now(), data };
      return data;
    } finally {
      _statusInflight = null;
    }
  })();
  return _statusInflight;
}

/** Test-only: reset the shared status cache. */
export function _resetAgentStatusCache(): void {
  _statusCache = null;
  _statusInflight = null;
}

export interface AgentStatus {
  status: AiStatusResponse | null;
  statusError: string | null;
  statusLoading: boolean;
  /** `status.providers`, or empty while loading / on error. Registry order. */
  providers: ProviderStatus[];
}

export function useAgentStatus(): AgentStatus {
  const [status, setStatus] = useState<AiStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchAgentStatus();
        if (!cancelled) {
          setStatus(data);
          setStatusError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setStatusError(err instanceof Error ? err.message : "status unavailable");
        }
      } finally {
        if (!cancelled) setStatusLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, statusError, statusLoading, providers: status?.providers ?? [] };
}

/** Why a launch cannot happen yet, or `null` when it can. */
export type AgentLaunchProblem = "no_provider" | "provider_unavailable" | "no_permission_mode";

/**
 * The AI Chat launch rule: a provider is chosen, that provider is installed, and
 * a permission mode is chosen. `(not logged in)` does not block — the CLI runs
 * its own sign-in inside the session.
 */
export function agentLaunchProblem(
  providers: readonly ProviderStatus[],
  provider: string | null,
  permissionMode: PermissionMode | null,
): AgentLaunchProblem | null {
  const selected = providers.find((p) => p.name === provider);
  if (!provider || selected === undefined) return "no_provider";
  if (!selected.available) return "provider_unavailable";
  if (!permissionMode) return "no_permission_mode";
  return null;
}
