// #1997 — the tip pool is the only thing the overlay says, and it is meant to
// grow by editing this one module. These tests are the contract every future
// entry has to satisfy, so a malformed tip fails here instead of rendering a
// blank card in front of a user.

import { describe, expect, it } from "vitest";

import { PALETTE_TIPS, resolveTip } from "../tipPool";

describe("palette tip pool", () => {
  it("is non-empty", () => {
    expect(PALETTE_TIPS.length).toBeGreaterThan(0);
  });

  it("gives every tip a unique id", () => {
    const ids = PALETTE_TIPS.map((tip) => tip.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("gives every tip a title and a body", () => {
    for (const tip of PALETTE_TIPS) {
      expect(tip.title.trim()).not.toBe("");
      expect(tip.body.trim()).not.toBe("");
    }
  });
});

describe("ADR-054 FR-038 — the MiniApps chapter", () => {
  const ids = new Set(PALETTE_TIPS.map((tip) => tip.id));

  it("says what a MiniApp is", () => {
    // FR-031 gave MiniApps a permanent sidebar tab. The tip overlay is the only
    // surface that reaches a user who has never opened it.
    expect(ids.has("what-is-a-miniapp")).toBe(true);
  });

  it("says where the previewer list went", () => {
    // FR-033 moved a surface users already knew out of the sidebar. Without a
    // tip naming its new home, the move reads as a removal.
    expect(ids.has("all-previewers-in-the-preview")).toBe(true);
    const tip = PALETTE_TIPS.find((entry) => entry.id === "all-previewers-in-the-preview")!;
    expect(tip.body).toContain("All Previewers");
  });
});

describe("resolveTip", () => {
  it("resolves an unbounded rotation index against the pool", () => {
    const first = resolveTip(0);
    expect(first).not.toBeNull();
    // The rotation index only ever grows; wrapping is the pool's job.
    expect(resolveTip(PALETTE_TIPS.length * 7)).toEqual(first);
  });

  it("shows every tip once before any of them repeats", () => {
    const seen = new Set<string>();
    for (let index = 0; index < PALETTE_TIPS.length; index += 1) {
      seen.add(resolveTip(index)!.id);
    }
    expect(seen.size).toBe(PALETTE_TIPS.length);
  });

  it("does not walk the pool in authoring order", () => {
    // The pool is grouped by chapter, so a plain +1 walk would spend a whole
    // session inside one chapter (owner directive, #1997).
    const adjacent = PALETTE_TIPS.filter((tip, position) => resolveTip(position)!.id === tip.id);
    expect(adjacent.length).toBeLessThan(PALETTE_TIPS.length / 2);
  });
});
