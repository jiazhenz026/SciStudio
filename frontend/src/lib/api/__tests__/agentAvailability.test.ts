/**
 * `fetchAgentAvailability` — ADR-053 spec 2, FR-031 to FR-036.
 *
 * This client is a fixed interface contract between two surfaces built in
 * parallel: the backend owns the shape, the Bring In My Work dialog consumes
 * it, and the Learning Center agent-setup entry will consume it too. The tests
 * below pin the request path and the field names, because a rename here is a
 * break neither consumer can see until runtime.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchAgentAvailability,
  type AgentAvailabilityResponse,
  type AgentAvailabilityState,
  type ProviderAvailability,
} from "../agentAvailability";

function mockFetch(body: unknown, ok = true, status = 200): { url: string }[] {
  const calls: { url: string }[] = [];
  const mock = vi.fn((url: string) => {
    calls.push({ url });
    return Promise.resolve({
      ok,
      status,
      json: () => Promise.resolve(body),
    } as unknown as Response);
  });
  vi.stubGlobal("fetch", mock);
  return calls;
}

const READY: AgentAvailabilityResponse = {
  state: "ready",
  providers: [
    { key: "claude-code", label: "Claude Code", state: "ready", cause: null },
    { key: "codex", label: "Codex", state: "call_failed", cause: "quota exceeded" },
  ],
};

describe("fetchAgentAvailability", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GETs /api/ai/availability and returns the report unchanged", async () => {
    const calls = mockFetch(READY);
    const report = await fetchAgentAvailability();

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/ai/availability");
    expect(report).toEqual(READY);
  });

  it("omits the refresh parameter by default so surfaces share the cached report", async () => {
    // Every live call behind this endpoint is a billed request; an unconditional
    // refresh would charge the user once per surface per open (FR-036).
    const calls = mockFetch(READY);
    await fetchAgentAvailability({ refresh: false });
    expect(calls[0].url).toBe("/api/ai/availability");
  });

  it("passes refresh=true for an explicit retry", async () => {
    // A user who has just topped up their quota must not have to wait out a cache.
    const calls = mockFetch(READY);
    await fetchAgentAvailability({ refresh: true });
    expect(calls[0].url).toBe("/api/ai/availability?refresh=true");
  });

  it("surfaces the per-provider fields a guidance renderer needs", async () => {
    mockFetch(READY);
    const report = await fetchAgentAvailability();

    const failing = report.providers.find((p) => p.state === "call_failed");
    expect(failing?.key).toBe("codex");
    expect(failing?.label).toBe("Codex");
    expect(failing?.cause).toBe("quota exceeded");
    // ``cause`` is populated only for ``call_failed``.
    expect(report.providers.find((p) => p.state === "ready")?.cause).toBeNull();
  });

  it("reports ready in aggregate while a provider is failing", async () => {
    // One unusable provider must never block a user who has a working one
    // (FR-005). The backend decides this; the client must not re-derive it.
    mockFetch(READY);
    const report = await fetchAgentAvailability();
    expect(report.state).toBe("ready");
    expect(report.providers.map((p) => p.state)).toContain("call_failed");
  });

  it("propagates a failed request rather than inventing an availability state", async () => {
    // A network failure is not "no agent installed"; guessing would send a user
    // to install software they already have.
    mockFetch({ detail: "boom" }, false, 500);
    await expect(fetchAgentAvailability()).rejects.toThrow();
  });

  it("accepts every state of FR-031 and nothing else", () => {
    const states: AgentAvailabilityState[] = [
      "not_installed",
      "not_authenticated",
      "call_failed",
      "ready",
    ];
    const providers: ProviderAvailability[] = states.map((state, index) => ({
      key: `p${index}`,
      label: `P${index}`,
      state,
      cause: state === "call_failed" ? "network unreachable" : null,
    }));
    expect(providers.map((p) => p.state)).toEqual(states);
    // @ts-expect-error — a fifth state is not part of the contract.
    const invalid: AgentAvailabilityState = "maybe";
    expect(invalid).toBe("maybe");
  });
});
