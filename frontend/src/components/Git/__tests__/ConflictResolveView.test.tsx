/**
 * D39-2.4a SKELETON tests for `ConflictResolveView.tsx` and the
 * conflict-region parser in `ConflictMarkerDecoration.ts`.
 *
 * The parser is implemented in the skeleton (no Monaco dependency); we
 * fully test it here. The view itself is a stub; its tests are
 * `it.skip(...)` for D39-2.4b.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConflictResolveView } from "../ConflictResolveView";
import { parseConflictRegions } from "../ConflictMarkerDecoration";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("parseConflictRegions (pure helper)", () => {
  it("returns [] for empty content", () => {
    expect(parseConflictRegions("")).toEqual([]);
  });

  it("returns [] when no markers are present", () => {
    expect(parseConflictRegions("hello\nworld\n")).toEqual([]);
  });

  it("parses a single 2-way conflict region", () => {
    const content = [
      "line0",
      "<<<<<<< HEAD",
      "ours",
      "=======",
      "theirs",
      ">>>>>>> feature-x",
      "after",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(1);
    expect(regions[0]).toMatchObject({
      startLine: 2,
      currentEndLine: 4,
      baseEndLine: null,
      incomingEndLine: 6,
      currentLabel: "HEAD",
      incomingLabel: "feature-x",
    });
  });

  it("parses two consecutive 2-way regions", () => {
    const content = [
      "<<<<<<< HEAD",
      "a1",
      "=======",
      "a2",
      ">>>>>>> source",
      "middle",
      "<<<<<<< HEAD",
      "b1",
      "=======",
      "b2",
      ">>>>>>> source",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(2);
    expect(regions[0].startLine).toBe(1);
    expect(regions[1].startLine).toBe(7);
  });

  it("parses a diff3-style region (records baseEndLine)", () => {
    const content = [
      "<<<<<<< HEAD",
      "ours",
      "||||||| base",
      "common",
      "=======",
      "theirs",
      ">>>>>>> source",
    ].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(1);
    expect(regions[0].currentEndLine).toBe(3); // |||||||
    expect(regions[0].baseEndLine).toBe(5); // =======
    expect(regions[0].incomingEndLine).toBe(7); // >>>>>>>
  });

  it("falls back to default labels when marker has no label", () => {
    const content = ["<<<<<<<", "x", "=======", "y", ">>>>>>>", ""].join("\n");
    const regions = parseConflictRegions(content);
    expect(regions[0].currentLabel).toBe("current");
    expect(regions[0].incomingLabel).toBe("incoming");
  });

  it("discards an unclosed region at EOF", () => {
    const content = ["<<<<<<< HEAD", "ours", "======="].join("\n");
    // No >>>>>>> → unclosed; the parser drops the partial region.
    expect(parseConflictRegions(content)).toEqual([]);
  });

  it("recovers from a nested '<<<<<<<' marker (defensive)", () => {
    const content = [
      "<<<<<<< HEAD",
      "x",
      "<<<<<<< NESTED", // unexpected nest; parser warns + restarts
      "y",
      "=======",
      "z",
      ">>>>>>> source",
    ].join("\n");
    // Only the inner region (started at line 3) is fully closed.
    const regions = parseConflictRegions(content);
    expect(regions).toHaveLength(1);
    expect(regions[0].startLine).toBe(3);
  });

  it("strips trailing CR (Windows CRLF) from labels", () => {
    const content = ["<<<<<<< HEAD\r", "x", "=======", "y", ">>>>>>> src\r"].join(
      "\n",
    );
    const regions = parseConflictRegions(content);
    expect(regions[0].currentLabel).toBe("HEAD");
    expect(regions[0].incomingLabel).toBe("src");
  });
});

describe("ConflictResolveView (SKELETON — wiring deferred to D39-2.4b)", () => {
  const noop = async () => {};
  it("renders the empty-state when no conflicted files", () => {
    render(
      <ConflictResolveView
        conflictedFiles={[]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    expect(screen.getByText(/No conflicted files/i)).toBeDefined();
  });

  it("renders each conflicted file as a list item", () => {
    render(
      <ConflictResolveView
        conflictedFiles={["src/a.py", "src/b.py"]}
        onOpenFile={() => {}}
        onResolveAll={noop}
        onAbort={noop}
      />,
    );
    expect(screen.getByText("src/a.py")).toBeDefined();
    expect(screen.getByText("src/b.py")).toBeDefined();
  });

  /*
   * D39-2.4b test plan: cover the action-button wiring.
   *
   * - Click "Open in editor" → asserts `onOpenFile(path)` is called.
   * - Click "Mark Resolved" → asserts `api.gitMergeStageFile(path)` is
   *   called; status badge flips to "Resolved".
   * - "Complete Merge" button is `aria-disabled=true` until all files
   *   are Resolved; click after the flip → asserts `onResolveAll` is
   *   called.
   * - "Abort Merge" button shows a confirm dialog; OK fires `onAbort`.
   * - Defensive: invoking actions after `gitSlice.mergeInProgress` is
   *   externally cleared is a no-op (e.g. external `git commit` from
   *   CLI fires `git.head_changed` → component unmounts before action
   *   completes).
   */
  it.skip("wires Open / Mark Resolved / Complete / Abort buttons (D39-2.4b)", () => {
    // D39-2.4b: implement per docstring above.
  });
});
