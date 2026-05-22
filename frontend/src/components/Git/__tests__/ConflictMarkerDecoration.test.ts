/**
 * Unit tests for the post-#1422 split `ConflictMarkerDecoration` modules.
 *
 * Pre-split, `parseConflictRegions` + `resolveRegionText` only had
 * coverage via `ConflictResolveView.test.tsx`'s integration scenarios.
 * After the split they live in `ConflictMarkerDecoration.parts/parser.ts`
 * and `ConflictMarkerDecoration.parts/decorations.ts`; this file pins
 * direct coverage on the pure helpers so a future refactor can't quietly
 * regress the conflict-resolution paths.
 *
 * The public `parseConflictRegions` / `resolveRegionText` are still
 * imported via `ConflictMarkerDecoration` (the re-export shell) to also
 * verify the public surface stays intact.
 */
import { describe, expect, it } from "vitest";

import { parseConflictRegions, resolveRegionText } from "../ConflictMarkerDecoration";
import { buildDecorations } from "../ConflictMarkerDecoration.parts/decorations";
import type { ConflictRegion } from "../ConflictMarkerDecoration.parts/types";

const TWO_WAY_FIXTURE = [
  "line above",
  "<<<<<<< HEAD",
  "current 1",
  "current 2",
  "=======",
  "incoming 1",
  ">>>>>>> source-branch",
  "line below",
].join("\n");

const DIFF3_FIXTURE = [
  "<<<<<<< HEAD",
  "current",
  "||||||| merged common ancestors",
  "base",
  "=======",
  "incoming",
  ">>>>>>> other",
].join("\n");

describe("parseConflictRegions", () => {
  it("returns [] when content has no markers", () => {
    expect(parseConflictRegions("just some text\nno markers")).toEqual([]);
  });

  it("returns [] for empty content", () => {
    expect(parseConflictRegions("")).toEqual([]);
  });

  it("parses a default 2-way conflict region with branch labels", () => {
    const regions = parseConflictRegions(TWO_WAY_FIXTURE);
    expect(regions).toHaveLength(1);
    const r = regions[0];
    expect(r.startLine).toBe(2);
    expect(r.currentEndLine).toBe(5);
    expect(r.baseEndLine).toBeNull();
    expect(r.incomingEndLine).toBe(7);
    expect(r.currentLabel).toBe("HEAD");
    expect(r.incomingLabel).toBe("source-branch");
  });

  it("parses a diff3-style conflict region", () => {
    const regions = parseConflictRegions(DIFF3_FIXTURE);
    expect(regions).toHaveLength(1);
    const r = regions[0];
    expect(r.startLine).toBe(1);
    expect(r.currentEndLine).toBe(3); // `|||||||` line
    expect(r.baseEndLine).toBe(5); // `=======` line
    expect(r.incomingEndLine).toBe(7);
  });

  it("falls back to 'current' / 'incoming' when marker labels are absent", () => {
    const content = ["<<<<<<<", "a", "=======", "b", ">>>>>>>"].join("\n");
    const [r] = parseConflictRegions(content);
    expect(r.currentLabel).toBe("current");
    expect(r.incomingLabel).toBe("incoming");
  });

  it("discards an unclosed region at EOF (defensive)", () => {
    const content = ["<<<<<<< HEAD", "a", "======="].join("\n");
    expect(parseConflictRegions(content)).toEqual([]);
  });
});

describe("resolveRegionText", () => {
  const r = parseConflictRegions(TWO_WAY_FIXTURE)[0];

  it("accept_current keeps the current section only", () => {
    const out = resolveRegionText(TWO_WAY_FIXTURE, r, { type: "accept_current" });
    expect(out).toBe(["line above", "current 1", "current 2", "line below"].join("\n"));
  });

  it("accept_incoming keeps the incoming section only", () => {
    const out = resolveRegionText(TWO_WAY_FIXTURE, r, { type: "accept_incoming" });
    expect(out).toBe(["line above", "incoming 1", "line below"].join("\n"));
  });

  it("accept_both concatenates current + incoming", () => {
    const out = resolveRegionText(TWO_WAY_FIXTURE, r, { type: "accept_both" });
    expect(out).toBe(
      ["line above", "current 1", "current 2", "incoming 1", "line below"].join("\n"),
    );
  });

  it("manual_edit returns the input unchanged", () => {
    const out = resolveRegionText(TWO_WAY_FIXTURE, r, { type: "manual_edit" });
    expect(out).toBe(TWO_WAY_FIXTURE);
  });

  it("diff3: accept_current does NOT splice the base block (PR #952 regression)", () => {
    const region = parseConflictRegions(DIFF3_FIXTURE)[0];
    const out = resolveRegionText(DIFF3_FIXTURE, region, { type: "accept_current" });
    expect(out).toBe("current");
    expect(out).not.toContain("base");
    expect(out).not.toContain("|||||||");
    expect(out).not.toContain("=======");
  });

  it("diff3: accept_incoming returns only the incoming section", () => {
    const region = parseConflictRegions(DIFF3_FIXTURE)[0];
    const out = resolveRegionText(DIFF3_FIXTURE, region, { type: "accept_incoming" });
    expect(out).toBe("incoming");
  });
});

describe("buildDecorations", () => {
  // Minimal Monaco stub: `monaco.Range` constructor stores fields.
  class FakeRange {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  }
  const fakeMonaco = { Range: FakeRange };

  function mkRegion(over: Partial<ConflictRegion> = {}): ConflictRegion {
    return {
      startLine: 10,
      currentEndLine: 14,
      baseEndLine: null,
      incomingEndLine: 18,
      currentLabel: "HEAD",
      incomingLabel: "feature",
      ...over,
    };
  }

  it("emits current + incoming + glyph descriptors for a 2-way region", () => {
    const decorations = buildDecorations([mkRegion()], fakeMonaco);
    expect(decorations).toHaveLength(3);
    // current section range: lines 11..13
    expect(decorations[0].range.startLineNumber).toBe(11);
    expect(decorations[0].range.endLineNumber).toBe(13);
    expect(decorations[0].options.className).toBe("conflict-current");
    // incoming section range: lines 15..17
    expect(decorations[1].range.startLineNumber).toBe(15);
    expect(decorations[1].range.endLineNumber).toBe(17);
    expect(decorations[1].options.className).toBe("conflict-incoming");
    // glyph marker on the `<<<<<<<` line
    expect(decorations[2].range.startLineNumber).toBe(10);
    expect(decorations[2].options.glyphMarginClassName).toBe("conflict-marker-glyph");
  });

  it("uses baseEndLine as the incoming start in diff3 mode", () => {
    const decorations = buildDecorations(
      [mkRegion({ currentEndLine: 12, baseEndLine: 14, incomingEndLine: 18 })],
      fakeMonaco,
    );
    // incoming range now starts after baseEndLine, not currentEndLine.
    const incoming = decorations.find((d) => d.options.className === "conflict-incoming");
    expect(incoming?.range.startLineNumber).toBe(15);
  });
});
