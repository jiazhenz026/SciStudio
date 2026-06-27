import { describe, expect, it } from "vitest";

import { isInteractiveBlock, readInteractiveMemory } from "./interactiveMemory";

describe("readInteractiveMemory (ADR-051 Addendum 1)", () => {
  it("reads the record from config.params", () => {
    const rec = { enabled: true, decision: { x: 1 }, signature: { p: ["a.txt"] } };
    expect(readInteractiveMemory({ params: { interactive_memory: rec } })).toEqual(rec);
  });

  it("reads the record from the top level", () => {
    const rec = { enabled: false };
    expect(readInteractiveMemory({ interactive_memory: rec })).toEqual(rec);
  });

  it("returns null when absent or config is nullish", () => {
    expect(readInteractiveMemory({ params: {} })).toBeNull();
    expect(readInteractiveMemory(undefined)).toBeNull();
    expect(readInteractiveMemory(null)).toBeNull();
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
