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
    {
      key: "claude-code",
      label: "Claude Code",
      state: "ready",
      cause: null,
      next_step: null,
      session_unsupported_reason: null,
    },
    {
      key: "codex",
      label: "Codex",
      state: "call_failed",
      cause: "quota exceeded",
      next_step: null,
      session_unsupported_reason: null,
    },
  ],
};

const NEEDS_SETUP: AgentAvailabilityResponse = {
  state: "not_authenticated",
  providers: [
    {
      key: "claude-code",
      label: "Claude Code",
      state: "not_installed",
      cause: null,
      next_step:
        "Install the Claude Code CLI so that `claude` is on your PATH and in ~/.local/bin.",
      session_unsupported_reason: null,
    },
    {
      key: "codex",
      label: "Codex",
      state: "not_authenticated",
      cause: null,
      next_step: "Sign in by running `codex login` in a terminal.",
      session_unsupported_reason: null,
    },
    {
      key: "kimi-code",
      label: "Kimi Code",
      state: "ready",
      cause: null,
      next_step: null,
      session_unsupported_reason: "Kimi Code has no positional prompt argument.",
    },
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
      next_step: null,
      session_unsupported_reason: null,
    }));
    expect(providers.map((p) => p.state)).toEqual(states);
    // @ts-expect-error — a fifth state is not part of the contract.
    const invalid: AgentAvailabilityState = "maybe";
    expect(invalid).toBe("maybe");
  });

  it("carries a per-provider next step for the two states FR-031 gives guidance to", async () => {
    // SC-002 requires guidance "naming a specific next action", and the facts
    // it is made of — binary names, search directories, sign-in commands — live
    // in the ADR-034 registry. The client must carry them through rather than
    // let a consumer reinvent them per surface.
    mockFetch(NEEDS_SETUP);
    const report = await fetchAgentAvailability();

    const notInstalled = report.providers.find((p) => p.state === "not_installed");
    expect(notInstalled?.next_step).toContain("`claude`");
    const notAuthenticated = report.providers.find((p) => p.state === "not_authenticated");
    expect(notAuthenticated?.next_step).toContain("codex login");
    // Populated for exactly those two: `call_failed` carries a cause instead,
    // and a ready provider needs no action.
    expect(report.providers.find((p) => p.state === "ready")?.next_step).toBeNull();
  });

  it("carries the session capability separately from the availability grade", async () => {
    // A provider can be `ready` — installed, signed in, answering calls — and
    // still be unable to run a SciStudio-started session, because the opening
    // instruction is a positional command-line argument some CLIs cannot take.
    // Collapsing the two would make `ready` mean something different to this
    // dialog than to every other consumer of the shared report.
    mockFetch(NEEDS_SETUP);
    const report = await fetchAgentAvailability();

    const kimi = report.providers.find((p) => p.key === "kimi-code");
    expect(kimi?.state).toBe("ready");
    expect(kimi?.session_unsupported_reason).toContain("no positional prompt argument");
    expect(report.providers.find((p) => p.key === "codex")?.session_unsupported_reason).toBeNull();
  });
});
