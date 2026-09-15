/**
 * #2454 — the provider status every agent-session surface reads, faked once.
 *
 * Not a test file. AI Chat and the session dialogs share `useAgentStatus`, so
 * their tests share this fake of the one endpoint behind it. It answers
 * `GET /api/ai/status`, lets every other request through to whatever `fetch`
 * the test already installed, and FAILS any request to the removed
 * `/api/ai/availability` endpoint, so no surface can quietly grow a second
 * provider report again.
 */
import { onTestFinished, vi } from "vitest";

import { _resetAgentStatusCache } from "../SetupScreen.parts/agentStatus";
import type { ProviderStatus } from "../SetupScreen.parts/types";

export function providerStatus(
  overrides: Partial<ProviderStatus> & { name: string },
): ProviderStatus {
  return {
    available: true,
    version: "9.9.9",
    logged_in: true,
    label: overrides.name,
    supports_auto_mode: true,
    ...overrides,
  };
}

export const CLAUDE_STATUS = providerStatus({ name: "claude-code", label: "Claude Code" });
export const CODEX_STATUS = providerStatus({ name: "codex", label: "Codex" });

export interface AgentStatusMock {
  /** URLs of every `/api/ai/status` request. */
  statusCalls: string[];
  /** URLs of any `/api/ai/availability` request (always a test failure). */
  availabilityCalls: string[];
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

/**
 * Answer `GET /api/ai/status` with `providers`, a rejection, or never.
 * Restored automatically when the test finishes.
 */
export function mockAgentStatus(
  providers: readonly ProviderStatus[] | Error | "pending" = [CLAUDE_STATUS],
): AgentStatusMock {
  _resetAgentStatusCache();
  const previous = globalThis.fetch;
  const record: AgentStatusMock = { statusCalls: [], availabilityCalls: [] };
  const fake = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = urlOf(input);
    if (url.includes("/api/ai/availability")) {
      record.availabilityCalls.push(url);
      throw new Error(`removed endpoint requested: ${url}`);
    }
    if (url.includes("/api/ai/status")) {
      record.statusCalls.push(url);
      if (providers === "pending") return new Promise<Response>(() => {});
      if (providers instanceof Error) {
        return new Response(JSON.stringify({ detail: providers.message }), { status: 503 });
      }
      return new Response(JSON.stringify({ providers }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return previous(input, init);
  });
  globalThis.fetch = fake as unknown as typeof fetch;
  onTestFinished(() => {
    globalThis.fetch = previous;
    _resetAgentStatusCache();
  });
  return record;
}
