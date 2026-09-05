/**
 * ADR-054 FR-030 — the packaged block's notebook badge.
 *
 * The badge marks exactly the nodes whose double-click reopens a notebook
 * (FR-004), because both read the same predicate,
 * `explore/packagedBlock.ts::isPackagedNotebookBlock`. Asserting "on a
 * packaged block and not on others" is therefore also asserting that the two
 * cannot drift apart.
 *
 * Note what the second case really covers: as the backend stands,
 * `BlockSummary` does not carry `notebook_filename` at all (S4-A1's F-A1-001),
 * so *every* node today takes the "not on others" branch. The badge lights up
 * the moment the backend surfaces the marker, and nothing else has to change.
 */

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BlockSummary } from "../../../../types/api";

import { renderNode } from "./test-utils";

function summary(overrides: Partial<BlockSummary> = {}): BlockSummary {
  return {
    name: "Segment Cells",
    type_name: "segment_cells",
    base_category: "process",
    subcategory: "",
    description: "",
    version: "1.0",
    input_ports: [],
    output_ports: [],
    ...overrides,
  };
}

afterEach(cleanup);

describe("the notebook badge (FR-030)", () => {
  it("renders on a block packaged from a notebook", () => {
    renderNode({ summary: summary({ notebook_filename: "segment_cells.ipynb" }) });
    const badge = screen.getByTestId("block-node-notebook-badge");
    expect(badge).toBeTruthy();
    expect(badge.getAttribute("title")).toContain("segment_cells.ipynb");
  });

  it("does not render on a hand-written block", () => {
    renderNode({ summary: summary() });
    expect(screen.queryByTestId("block-node-notebook-badge")).toBeNull();
  });

  it("does not render on a node whose block did not resolve at all", () => {
    renderNode({ summary: undefined, unresolved: true });
    expect(screen.queryByTestId("block-node-notebook-badge")).toBeNull();
  });

  it("changes no measured geometry (ADR-050 FR-011)", () => {
    const { unmount } = renderNode({ summary: summary() });
    const plain = screen.getByTestId("block-node-body").getAttribute("style");
    unmount();
    renderNode({ summary: summary({ notebook_filename: "segment_cells.ipynb" }) });
    expect(screen.getByTestId("block-node-body").getAttribute("style")).toBe(plain);
  });
});
