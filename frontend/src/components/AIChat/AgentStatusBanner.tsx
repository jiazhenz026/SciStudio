/**
 * Banner showing the active provider's discovery state.
 *
 * Polls `GET /api/ai/status` on mount and every 60s. Renders one of:
 *  - hidden (provider available + logged in + not in bypass mode)
 *  - "not installed" (with install hint)
 *  - "not logged in"
 *  - "bypass mode active" (always visible when set)
 *
 * Per ADR-033 §3 D4: bypass-mode banner stays visible at all times.
 */

import { useEffect, useState } from "react";

import { api, type AIProviderStatus } from "../../lib/api";
import { useAppStore } from "../../store";

const POLL_INTERVAL_MS = 60_000;

export function AgentStatusBanner() {
  const providerName = useAppStore((s) => s.providerName);
  const permissionMode = useAppStore((s) => s.permissionMode);
  const [status, setStatus] = useState<AIProviderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const resp = await api.getAIStatus();
        if (cancelled) return;
        const match = resp.providers.find((p) => p.name === providerName) ?? null;
        setStatus(match);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "status fetch failed");
        }
      }
    };
    poll();
    timer = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timer !== null) {
        clearInterval(timer);
      }
    };
  }, [providerName]);

  const bypassActive = permissionMode === "bypass";

  // Bypass-mode banner always visible (per ADR-033 §3 D4).
  if (bypassActive) {
    return (
      <div
        data-testid="banner-bypass"
        className="bg-red-100 px-3 py-1 text-sm text-red-800 border-b border-red-200"
      >
        ⚠ Bypass mode active — tool calls execute without confirmation
      </div>
    );
  }

  if (error !== null) {
    return (
      <div data-testid="banner-error" className="bg-orange-100 px-3 py-1 text-sm text-orange-800">
        Could not check provider status: {error}
      </div>
    );
  }

  if (status === null) {
    return null;
  }

  if (!status.available) {
    return (
      <div
        data-testid="banner-not-installed"
        className="bg-yellow-100 px-3 py-1 text-sm text-yellow-900"
      >
        {status.name} is not installed.{" "}
        {status.install_hint !== null && (
          <span className="font-mono">{status.install_hint}</span>
        )}
      </div>
    );
  }

  if (!status.logged_in) {
    return (
      <div
        data-testid="banner-not-logged-in"
        className="bg-yellow-100 px-3 py-1 text-sm text-yellow-900"
      >
        {status.name} is installed but not logged in. Run{" "}
        <span className="font-mono">{status.name} login</span> in a terminal.
      </div>
    );
  }

  return null;
}
