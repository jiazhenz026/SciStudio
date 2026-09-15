// #2415 — the activity bar order preference: merge rules and storage.

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  ACTIVITY_BAR_ORDER_STORAGE_KEY,
  mergeActivityBarOrder,
  moveActivityBarKey,
  saveActivityBarOrder,
  useActivityBarOrder,
} from "./activityBarOrder";

const DEFAULTS = ["a", "b", "c", "d"] as const;

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe("mergeActivityBarOrder", () => {
  it("returns the defaults for anything that is not a saved array", () => {
    for (const saved of [null, undefined, "a,b", 3, { a: 1 }]) {
      expect(mergeActivityBarOrder(saved, DEFAULTS)).toEqual(["a", "b", "c", "d"]);
    }
  });

  it("keeps a complete saved order as is", () => {
    expect(mergeActivityBarOrder(["d", "c", "b", "a"], DEFAULTS)).toEqual(["d", "c", "b", "a"]);
  });

  it("drops unknown, non-string, and repeated keys", () => {
    expect(mergeActivityBarOrder(["d", "x", 7, "c", "d", "b", "a"], DEFAULTS)).toEqual([
      "d",
      "c",
      "b",
      "a",
    ]);
  });

  it("inserts a missing key after its nearest kept default predecessor", () => {
    // `c` follows `b` in the defaults, so it lands right after `b`.
    expect(mergeActivityBarOrder(["d", "b", "a"], DEFAULTS)).toEqual(["d", "b", "c", "a"]);
    // `a` has no predecessor, so it goes first.
    expect(mergeActivityBarOrder(["c", "b", "d"], DEFAULTS)).toEqual(["a", "c", "b", "d"]);
    // An empty saved order is the default order.
    expect(mergeActivityBarOrder([], DEFAULTS)).toEqual(["a", "b", "c", "d"]);
  });
});

describe("moveActivityBarKey", () => {
  it("moves a key to the target index, clamping out-of-range targets", () => {
    expect(moveActivityBarKey(["a", "b", "c"], "a", 2)).toEqual(["b", "c", "a"]);
    expect(moveActivityBarKey(["a", "b", "c"], "c", 0)).toEqual(["c", "a", "b"]);
    expect(moveActivityBarKey(["a", "b", "c"], "b", 99)).toEqual(["a", "c", "b"]);
    expect(moveActivityBarKey(["a", "b", "c"], "b", -3)).toEqual(["b", "a", "c"]);
    expect(moveActivityBarKey(["a", "b"], "z" as "a", 0)).toEqual(["a", "b"]);
  });
});

describe("useActivityBarOrder", () => {
  it("reads, updates on save, and resets when cleared", () => {
    const { result } = renderHook(() => useActivityBarOrder(DEFAULTS));
    expect(result.current).toEqual(["a", "b", "c", "d"]);
    act(() => saveActivityBarOrder(["b", "a", "d", "c"]));
    expect(result.current).toEqual(["b", "a", "d", "c"]);
    expect(window.localStorage.getItem(ACTIVITY_BAR_ORDER_STORAGE_KEY)).toBe('["b","a","d","c"]');
    act(() => saveActivityBarOrder(null));
    expect(result.current).toEqual(["a", "b", "c", "d"]);
    expect(window.localStorage.getItem(ACTIVITY_BAR_ORDER_STORAGE_KEY)).toBeNull();
  });
});
