/**
 * A failed git log load must not be retried forever (#2057).
 *
 * `GitHistoryList` and `useGraphData` both auto-fetch on
 * `commits === null && !loading`. That guard reads state the failure path used
 * to leave untouched: the cache stays undefined and the loading flag returns to
 * false, so a failure looks identical to "never attempted". The `set()` that
 * recorded the failure re-renders the consumer, the consumer asks again, and
 * the loop runs as fast as the network allows.
 *
 * It was reached by clearing tutorial data while the tutorial project was open.
 * The backend deletes the project and correctly stops treating it as active, so
 * every git call answers 409 — and a live session produced 159,353 requests to
 * `/api/git/log` and an unusable window.
 *
 * The trigger was the Learning Center; the defect was not. Any persistent git
 * failure reached it, which is why the fix and these tests sit at the slice
 * rather than at the feature that exposed it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "../../lib/api";
import { createGitSlice } from "../gitSlice";

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof ApiModule>("../../lib/api");
  return {
    ...actual,
    api: {
      gitLog: vi.fn(),
      gitBranches: vi.fn().mockRejectedValue(new Error("No active project")),
      gitStatus: vi.fn().mockRejectedValue(new Error("No active project")),
    },
  };
});

const { api } = await import("../../lib/api");

function makeSlice() {
  let state: Record<string, unknown> = {};
  const set = (partial: unknown) => {
    state =
      typeof partial === "function"
        ? { ...state, ...(partial as (s: unknown) => object)(state) }
        : { ...state, ...(partial as object) };
  };
  const get = () => state;
  const slice = createGitSlice(set as never, get as never, {} as never);
  state = { ...state, ...slice };
  return { get: get as () => Record<string, unknown>, slice: state as never };
}

describe("a failing git log stops asking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.gitBranches).mockRejectedValue(new Error("No active project"));
    vi.mocked(api.gitStatus).mockRejectedValue(new Error("No active project"));
  });

  it("does not re-request after a failure", async () => {
    vi.mocked(api.gitLog).mockRejectedValue(new Error("No active project"));
    const { slice } = makeSlice();

    // Three attempts, exactly as the consumer's effect would make them: each
    // re-render sees no cache and no in-flight load.
    await (slice as never as { loadLog: (b?: string) => Promise<void> }).loadLog();
    await (slice as never as { loadLog: (b?: string) => Promise<void> }).loadLog();
    await (slice as never as { loadLog: (b?: string) => Promise<void> }).loadLog();

    expect(api.gitLog).toHaveBeenCalledTimes(1);
  });

  it("still surfaces the error to the user", async () => {
    vi.mocked(api.gitLog).mockRejectedValue(new Error("No active project"));
    const { get, slice } = makeSlice();

    await (slice as never as { loadLog: () => Promise<void> }).loadLog();

    expect(get().lastError).toBeTruthy();
  });

  it("retries when git state actually changed", async () => {
    // invalidateHistory is what `git.head_changed`, commit, switch, restore and
    // merge-resolve all call. Something really moved, so the previous failure
    // says nothing about the next attempt.
    vi.mocked(api.gitLog).mockRejectedValue(new Error("No active project"));
    const { get, slice } = makeSlice();

    await (slice as never as { loadLog: () => Promise<void> }).loadLog();
    expect(api.gitLog).toHaveBeenCalledTimes(1);

    (get() as { invalidateHistory: () => void }).invalidateHistory();
    await (slice as never as { loadLog: () => Promise<void> }).loadLog();

    expect(vi.mocked(api.gitLog).mock.calls.length).toBeGreaterThan(1);
  });

  it("retries when the user asks explicitly", async () => {
    vi.mocked(api.gitLog).mockRejectedValue(new Error("No active project"));
    const { slice } = makeSlice();
    const loadLog = (
      slice as never as {
        loadLog: (b?: string, o?: { force?: boolean }) => Promise<void>;
      }
    ).loadLog;

    await loadLog();
    await loadLog(undefined, { force: true });

    expect(api.gitLog).toHaveBeenCalledTimes(2);
  });

  it("clears the block once a load succeeds", async () => {
    vi.mocked(api.gitLog)
      .mockRejectedValueOnce(new Error("No active project"))
      .mockResolvedValue([]);
    const { get, slice } = makeSlice();
    const loadLog = (
      slice as never as {
        loadLog: (b?: string, o?: { force?: boolean }) => Promise<void>;
      }
    ).loadLog;

    await loadLog();
    await loadLog(undefined, { force: true });
    // The success re-opens the key, so an ordinary consumer fetch works again.
    await loadLog();

    expect(api.gitLog).toHaveBeenCalledTimes(3);
    expect(get().lastError).toBeNull();
  });

  it("blocks only the branch that failed", async () => {
    vi.mocked(api.gitLog).mockImplementation(async (options?: { branch?: string }) => {
      if (options?.branch === "broken") throw new Error("No active project");
      return [];
    });
    const { slice } = makeSlice();
    const loadLog = (slice as never as { loadLog: (b?: string) => Promise<void> }).loadLog;

    await loadLog("broken");
    await loadLog("broken");
    await loadLog("fine");

    const calls = vi.mocked(api.gitLog).mock.calls;
    expect(calls.filter((c) => c[0]?.branch === "broken")).toHaveLength(1);
    expect(calls.filter((c) => c[0]?.branch === "fine")).toHaveLength(1);
  });
});
