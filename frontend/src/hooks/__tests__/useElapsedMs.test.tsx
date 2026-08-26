import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { formatElapsed, useElapsedMs } from "../useElapsedMs";

// #1974/#2190 — the elapsed-timer contract is shared by the block node status
// surface and the plot card pill, so the format + tick rules are pinned here
// once rather than per consumer.
describe("formatElapsed (#1974)", () => {
  it("renders seconds under a minute, m:ss under an hour, h:mm:ss beyond", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(7_000)).toBe("7s");
    expect(formatElapsed(59_999)).toBe("59s");
    expect(formatElapsed(60_000)).toBe("1:00");
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(3_600_000)).toBe("1:00:00");
    expect(formatElapsed(3_849_000)).toBe("1:04:09");
  });

  it("floors sub-second precision and clamps negative drift to 0s", () => {
    expect(formatElapsed(999)).toBe("0s");
    expect(formatElapsed(-5_000)).toBe("0s");
  });
});

describe("useElapsedMs (#1974)", () => {
  const START = Date.parse("2026-05-22T00:00:00Z");

  afterEach(() => {
    vi.useRealTimers();
  });

  it("ticks once a second while startedAt is set", () => {
    vi.useFakeTimers();
    vi.setSystemTime(START);
    const { result } = renderHook(() => useElapsedMs(START));
    expect(result.current).toBe(0);
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(result.current).toBe(3_000);
  });

  it("returns 0 and holds no timer when startedAt is null", () => {
    vi.useFakeTimers();
    vi.setSystemTime(START);
    const { result } = renderHook(() => useElapsedMs(null));
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current).toBe(0);
  });

  it("stops ticking when startedAt clears, leaving no final duration", () => {
    vi.useFakeTimers();
    vi.setSystemTime(START);
    const { result, rerender } = renderHook(
      ({ startedAt }: { startedAt: number | null }) => useElapsedMs(startedAt),
      { initialProps: { startedAt: START as number | null } },
    );
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(result.current).toBe(2_000);
    rerender({ startedAt: null });
    expect(result.current).toBe(0);
    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current).toBe(0);
  });
});
