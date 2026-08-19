// #1997 — the visibility clock. The overlay covers part of the panel while it
// is up, so the timings and the two-step dismissal are the whole reason it is
// tolerable; they are pinned here rather than left to manual observation.

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TIP_HIDDEN_MS, TIP_SNOOZE_MS, TIP_VISIBLE_MS, useTipRotation } from "../useTipRotation";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

describe("useTipRotation", () => {
  it("stays down until the first quiet gap has passed", () => {
    const { result } = renderHook(() => useTipRotation(true));

    expect(result.current.visible).toBe(false);
    advance(TIP_HIDDEN_MS - 1);
    expect(result.current.visible).toBe(false);
    advance(1);
    expect(result.current.visible).toBe(true);
  });

  it("alternates visible and hidden on the fixed cycle", () => {
    const { result } = renderHook(() => useTipRotation(true));

    advance(TIP_HIDDEN_MS);
    expect(result.current.visible).toBe(true);
    const shown = result.current.index;

    advance(TIP_VISIBLE_MS);
    expect(result.current.visible).toBe(false);

    advance(TIP_HIDDEN_MS);
    expect(result.current.visible).toBe(true);
    // A new cycle advances the rotation, so the next tip is a different one.
    expect(result.current.index).toBe(shown + 1);
  });

  it("does not count an expiring tip as a dismissal", () => {
    const { result } = renderHook(() => useTipRotation(true));

    for (let cycle = 0; cycle < 3; cycle += 1) {
      advance(TIP_HIDDEN_MS);
      advance(TIP_VISIBLE_MS);
    }
    expect(result.current.silenced).toBe(false);
  });

  it("buys five quiet minutes on the first dismissal", () => {
    const { result } = renderHook(() => useTipRotation(true));

    advance(TIP_HIDDEN_MS);
    act(() => result.current.dismiss());
    expect(result.current.visible).toBe(false);
    expect(result.current.silenced).toBe(false);

    advance(TIP_HIDDEN_MS);
    expect(result.current.visible).toBe(false);

    advance(TIP_SNOOZE_MS - TIP_HIDDEN_MS);
    expect(result.current.visible).toBe(true);
  });

  it("resumes the ordinary cycle after the snooze", () => {
    const { result } = renderHook(() => useTipRotation(true));

    advance(TIP_HIDDEN_MS);
    act(() => result.current.dismiss());
    advance(TIP_SNOOZE_MS);
    expect(result.current.visible).toBe(true);

    advance(TIP_VISIBLE_MS);
    expect(result.current.visible).toBe(false);
    advance(TIP_HIDDEN_MS);
    expect(result.current.visible).toBe(true);
  });

  it("stops for the session on the second dismissal", () => {
    const { result } = renderHook(() => useTipRotation(true));

    advance(TIP_HIDDEN_MS);
    act(() => result.current.dismiss());
    advance(TIP_SNOOZE_MS);
    act(() => result.current.dismiss());

    expect(result.current.silenced).toBe(true);
    advance(TIP_SNOOZE_MS * 10);
    expect(result.current.visible).toBe(false);
    expect(result.current.silenced).toBe(true);
  });

  it("holds still when there is nothing to show", () => {
    const { result } = renderHook(() => useTipRotation(false));

    advance(TIP_HIDDEN_MS * 10);
    expect(result.current.visible).toBe(false);
  });
});
