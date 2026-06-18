/**
 * ADR-039 Addendum 1 audit P3-2 (#1394): focusing a graph row scrolls it
 * into view.
 *
 * Regression: clicking a commit dot (or keyboard-navigating) whose row is
 * virtualized out used to set `focusedRow` with no visible effect. The
 * pane now scrolls the focused row into view (centered) whenever it
 * changes.
 */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";
import { resetAppStore } from "../../../testUtils";
import type { GitCommit } from "../../../types/api";

import { GitGraphPane } from "./GitGraphPane";

function makeCommits(n: number): GitCommit[] {
  return Array.from({ length: n }, (_, i) => ({
    sha: `sha${i}`.padEnd(40, "0"),
    short_sha: `sha${i}`,
    parents: i + 1 < n ? [`sha${i + 1}`.padEnd(40, "0")] : [],
    author_name: "Tester",
    author_email: "t@example.com",
    author_date: "2026-06-10T00:00:00Z",
    subject: `commit ${i}`,
    body: "",
    branches: [],
  }));
}

describe("GitGraphPane focused-row scrollIntoView (#1394 P3-2)", () => {
  let scrollToSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetAppStore();
    scrollToSpy = vi.fn();
    // jsdom does not implement scrollTo / layout metrics.
    Element.prototype.scrollTo = scrollToSpy as unknown as Element["scrollTo"];
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get: () => 200,
    });
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
      configurable: true,
      get: () => 5000,
    });
    // Seed the gitSlice log cache the graph reads from.
    useAppStore.setState({ logCache: { "<all>": makeCommits(100) } });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("scrolls the focused row into view on keyboard navigation", () => {
    const { getByTestId } = render(<GitGraphPane />);
    const scrollEl = getByTestId("git-graph-scroll");

    // ArrowDown focuses row 0 — effect fires scrollTo (centered).
    fireEvent.keyDown(scrollEl, { key: "ArrowDown" });
    expect(scrollToSpy).toHaveBeenCalled();
    const calls = scrollToSpy.mock.calls;
    const call = calls[calls.length - 1]?.[0] as { top: number; behavior: string };
    expect(call.behavior).toBe("smooth");
    expect(call.top).toBe(0); // row 0 centered clamps to 0
  });

  it("scrolls to a deeper row when navigating down", () => {
    const { getByTestId } = render(<GitGraphPane />);
    const scrollEl = getByTestId("git-graph-scroll");

    for (let i = 0; i < 30; i++) {
      fireEvent.keyDown(scrollEl, { key: "ArrowDown" });
    }
    const calls = scrollToSpy.mock.calls;
    const call = calls[calls.length - 1]?.[0] as { top: number };
    // Row 29 center (29*22 + 11 = 649) minus half-viewport (100) = 549.
    expect(call.top).toBeGreaterThan(0);
  });
});
