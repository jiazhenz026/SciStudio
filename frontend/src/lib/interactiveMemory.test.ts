import { describe, expect, it } from "vitest";

import {
  isInteractiveBlock,
  isPromptOutsideCanvas,
  readInteractiveMemory,
} from "./interactiveMemory";

describe("readInteractiveMemory (ADR-051 Addendum 1)", () => {
  it("reads the record from config.params", () => {
    const rec = { enabled: true, decision: { x: 1 }, signature: { p: ["a.txt"] } };
    expect(readInteractiveMemory({ params: { interactive_memory: rec } })).toEqual(rec);
  });

  it("reads a legacy top-level record when params has none", () => {
    const rec = { enabled: false };
    expect(readInteractiveMemory({ interactive_memory: rec })).toEqual(rec);
    expect(readInteractiveMemory({ interactive_memory: rec, params: {} })).toEqual(rec);
  });

  it("prefers the params record over a legacy top-level one (#2412)", () => {
    const legacy = { enabled: true, decision: null, signature: null };
    const saved = { enabled: true, decision: { routes: [1] }, signature: { x: ["a.tif"] } };
    expect(
      readInteractiveMemory({ interactive_memory: legacy, params: { interactive_memory: saved } }),
    ).toEqual(saved);
    const disabled = { enabled: false };
    expect(
      readInteractiveMemory({
        interactive_memory: legacy,
        params: { interactive_memory: disabled },
      }),
    ).toEqual(disabled);
  });

  it("returns null when absent or config is nullish", () => {
    expect(readInteractiveMemory({ params: {} })).toBeNull();
    expect(readInteractiveMemory(undefined)).toBeNull();
    expect(readInteractiveMemory(null)).toBeNull();
  });
});

describe("isPromptOutsideCanvas (#2412)", () => {
  it("is true for a flattened subworkflow block id the canvas does not hold", () => {
    const nodes = [{ id: "sw1" }, { id: "pick" }];
    expect(isPromptOutsideCanvas("sw1__pick", nodes)).toBe(true);
    expect(isPromptOutsideCanvas("pick", nodes)).toBe(false);
  });
});

describe("isInteractiveBlock", () => {
  it("is true only for execution_mode 'interactive'", () => {
    expect(isInteractiveBlock("interactive")).toBe(true);
    expect(isInteractiveBlock("auto")).toBe(false);
    expect(isInteractiveBlock(undefined)).toBe(false);
    expect(isInteractiveBlock(null)).toBe(false);
  });
});
