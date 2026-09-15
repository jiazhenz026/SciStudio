import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api/core";
import { panelsApi } from "../lib/api/panels";
import type { PanelProcessStatus } from "../panels/types";
import { MINIAPP_PROCESS_POLL_MS, useMiniAppProcess } from "./useMiniAppProcess";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const running: PanelProcessStatus = { state: "running", pid: 42 };
const stopped: PanelProcessStatus = { state: "stopped", pid: 42, exit_code: 0 };

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("MiniApp process response ordering", () => {
  it.each(["status", "no_process", "error"])(
    "discards an old poll %s after Stop and resumes fresh polling",
    async (answer) => {
      const poll = deferred<PanelProcessStatus>();
      const read = vi.spyOn(panelsApi, "processStatus").mockReturnValue(poll.promise);
      const stop = deferred<Awaited<ReturnType<typeof panelsApi.stopProcess>>>();
      vi.spyOn(panelsApi, "stopProcess").mockReturnValue(stop.promise);
      const { result } = renderHook(() => useMiniAppProcess("pc-1", running));

      act(() => result.current.stop());
      await act(async () => vi.advanceTimersByTimeAsync(MINIAPP_PROCESS_POLL_MS));
      expect(read).toHaveBeenCalledTimes(1);
      await act(async () => stop.resolve({ process: stopped } as Awaited<typeof stop.promise>));
      await act(async () => {
        if (answer === "status") poll.resolve(running);
        else
          poll.reject(
            answer === "no_process" ? new ApiError("no_process", 404) : new Error("old error"),
          );
      });
      expect(result.current.status).toEqual(stopped);
      expect(result.current.absent).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.busy).toBe(false);

      read.mockResolvedValue({ state: "starting", pid: 43 });
      await act(async () => vi.advanceTimersByTimeAsync(MINIAPP_PROCESS_POLL_MS));
      expect(result.current.status).toEqual({ state: "starting", pid: 43 });
    },
  );

  it("discards a completed action from the previous context", async () => {
    vi.spyOn(panelsApi, "processStatus").mockResolvedValue(running);
    const stop = deferred<Awaited<ReturnType<typeof panelsApi.stopProcess>>>();
    vi.spyOn(panelsApi, "stopProcess").mockReturnValue(stop.promise);
    const { result, rerender } = renderHook(({ id }) => useMiniAppProcess(id), {
      initialProps: { id: "pc-1" },
    });
    await act(async () => {});
    act(() => result.current.stop());
    rerender({ id: "pc-2" });
    await act(async () => {});
    expect(result.current.busy).toBe(false);
    await act(async () => stop.resolve({ process: stopped } as Awaited<typeof stop.promise>));
    expect(result.current.status).toEqual(running);
  });
});
