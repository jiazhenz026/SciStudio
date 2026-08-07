/**
 * #2019: `apiFetch` request deadlines.
 *
 * The project-switch calls gate a modal and the global busy flag, and both are
 * only cleared from a `finally`. A request that never settles therefore wedges
 * the GUI permanently — which is exactly what a deadlocked backend did. These
 * tests pin that the deadline exists, that it aborts (rather than merely
 * racing) the request, and that it stays opt-in for every other call.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, ApiTimeoutError } from "../core";
import { projectsApi } from "../projects";

/** A fetch that never resolves unless its abort signal fires. */
function mockHangingFetch(): { signals: (AbortSignal | undefined)[] } {
  const signals: (AbortSignal | undefined)[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      signals.push(init?.signal ?? undefined);
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    }),
  );
  return { signals };
}

function mockFetchOk(): { signals: (AbortSignal | undefined)[] } {
  const signals: (AbortSignal | undefined)[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      signals.push(init?.signal ?? undefined);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: "p1" }),
      } as unknown as Response);
    }),
  );
  return { signals };
}

describe("apiFetch timeouts (#2019)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("rejects with ApiTimeoutError once the deadline passes", async () => {
    vi.useFakeTimers();
    mockHangingFetch();

    const pending = apiFetch("/api/slow", { timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });

  it("aborts the underlying request rather than leaving it running", async () => {
    vi.useFakeTimers();
    const { signals } = mockHangingFetch();

    const pending = apiFetch("/api/slow", { timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;

    expect(signals[0]?.aborted).toBe(true);
  });

  it("names the elapsed budget in the message so the banner is actionable", async () => {
    vi.useFakeTimers();
    mockHangingFetch();

    const pending = apiFetch("/api/slow", { timeoutMs: 60_000 });
    const assertion = expect(pending).rejects.toThrow(/timed out after 60s/);
    await vi.advanceTimersByTimeAsync(60_000);
    await assertion;
  });

  it("leaves requests without timeoutMs unbounded and unsignalled", async () => {
    const { signals } = mockFetchOk();
    await apiFetch("/api/fast");
    expect(signals[0]).toBeUndefined();
  });

  it("does not forward timeoutMs to fetch as a request field", async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit & { timeoutMs?: number }) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      } as unknown as Response),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/fast", { timeoutMs: 5000, method: "POST" });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.timeoutMs).toBeUndefined();
    expect(init?.method).toBe("POST");
  });

  it("bounds createProject and openProject — the two calls that gate the modal", async () => {
    const { signals } = mockFetchOk();
    await projectsApi.createProject({ name: "p", description: "", path: "/tmp" });
    await projectsApi.openProject("p1");

    // Both carry a signal, which only the timeout path installs.
    expect(signals[0]).toBeDefined();
    expect(signals[1]).toBeDefined();
  });

  it("leaves listProjects unbounded — it does not gate any modal", async () => {
    const { signals } = mockFetchOk();
    await projectsApi.listProjects();
    expect(signals[0]).toBeUndefined();
  });
});
