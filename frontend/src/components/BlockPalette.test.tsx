import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BlockPalette } from "./BlockPalette";
import type { BlockSummary } from "../types/api";

afterEach(() => {
  cleanup();
});

function makeBlock(
  overrides: Partial<BlockSummary> & { type_name: string; name: string },
): BlockSummary {
  const base_category = overrides.base_category ?? "process";
  const subcategory = overrides.subcategory ?? "";
  return {
    name: overrides.name,
    type_name: overrides.type_name,
    base_category,
    subcategory,
    description: overrides.description ?? "A block",
    version: "0.1.0",
    input_ports: [],
    output_ports: [],
    source: overrides.source,
    package_name: overrides.package_name,
    direction: overrides.direction,
  };
}

const defaultProps = {
  search: "",
  collapsed: false,
  onSearch: vi.fn(),
  onReload: vi.fn(),
  onAddBlock: vi.fn(),
};

describe("BlockPalette — Stage 10.1 Part 2", () => {
  it("renders a 3-level tree (package -> category -> block)", () => {
    const blocks: BlockSummary[] = [
      makeBlock({
        type_name: "imaging.cellpose_segment",
        name: "Cellpose Segment",
        base_category: "process",
        subcategory: "segmentation",
      }),
      makeBlock({
        type_name: "lcms.load_peak_table",
        name: "Load Peak Table",
        base_category: "io",
        subcategory: "io",
      }),
      makeBlock({ type_name: "load_data", name: "Load", base_category: "io" }),
    ];

    render(<BlockPalette {...defaultProps} blocks={blocks} />);

    // Package headers — CSS uppercases visually; text in DOM is as-derived.
    expect(screen.getByText("Imaging")).toBeInTheDocument();
    expect(screen.getByText("LCMS")).toBeInTheDocument();
    expect(screen.getByText("SciStudio Core")).toBeInTheDocument();

    // Category headers nested under packages (lowercase in DOM, uppercase via CSS)
    expect(screen.getByText("segmentation")).toBeInTheDocument();

    // Block cards
    expect(screen.getByText("Cellpose Segment")).toBeInTheDocument();
    expect(screen.getByText("Load Peak Table")).toBeInTheDocument();
  });

  it('"Custom" package always sorts to the bottom', () => {
    const blocks: BlockSummary[] = [
      makeBlock({ type_name: "imaging.foo", name: "Foo", source: undefined }),
      makeBlock({ type_name: "custom_block", name: "My Custom Block", source: "custom" }),
    ];

    render(<BlockPalette {...defaultProps} blocks={blocks} />);

    const allButtons = Array.from(document.querySelectorAll("button"));
    const imagingIndex = allButtons.findIndex((btn) => btn.textContent?.includes("Imaging"));
    const customIndex = allButtons.findIndex((btn) => btn.textContent?.includes("Custom"));
    expect(imagingIndex).toBeGreaterThanOrEqual(0);
    expect(customIndex).toBeGreaterThanOrEqual(0);
    expect(imagingIndex).toBeLessThan(customIndex);
  });

  it("packages and categories are collapsible", () => {
    const blocks: BlockSummary[] = [
      makeBlock({
        type_name: "imaging.segment",
        name: "Segment Block",
        base_category: "process",
        subcategory: "segmentation",
      }),
    ];

    render(<BlockPalette {...defaultProps} blocks={blocks} />);

    // Block is visible initially
    expect(screen.getByText("Segment Block")).toBeInTheDocument();

    // Collapse the package by clicking the package header button.
    const allButtons = screen.getAllByRole("button");
    const packageButton = allButtons.find((btn) => btn.textContent?.includes("Imaging"));
    expect(packageButton).toBeDefined();
    fireEvent.click(packageButton!);

    // Block should no longer be visible
    expect(screen.queryByText("Segment Block")).not.toBeInTheDocument();

    // Re-expand
    fireEvent.click(packageButton!);
    expect(screen.getByText("Segment Block")).toBeInTheDocument();
  });

  it("search expands matching branches automatically", () => {
    const blocks: BlockSummary[] = [
      makeBlock({
        type_name: "imaging.cellpose_segment",
        name: "Cellpose Segment",
        base_category: "process",
        subcategory: "segmentation",
      }),
      makeBlock({
        type_name: "lcms.load_peak",
        name: "Load Peak",
        base_category: "io",
        subcategory: "io",
      }),
    ];

    // With a search filter that only matches the imaging block, the lcms block
    // should not appear. Both matching blocks and their parents are rendered.
    render(<BlockPalette {...defaultProps} blocks={blocks} search="cellpose" />);

    expect(screen.getByText("Cellpose Segment")).toBeInTheDocument();
    expect(screen.queryByText("Load Peak")).not.toBeInTheDocument();
    // Parent package header still rendered
    expect(screen.getAllByText("Imaging").length).toBeGreaterThan(0);
  });

  it("empty categories are hidden when filtered", () => {
    const blocks: BlockSummary[] = [
      makeBlock({
        type_name: "imaging.cellpose_segment",
        name: "Cellpose Segment",
        base_category: "process",
        subcategory: "segmentation",
      }),
      makeBlock({
        type_name: "imaging.load_image",
        name: "Load Image",
        base_category: "io",
        subcategory: "io",
      }),
    ];

    // Search that matches only the io category block
    render(<BlockPalette {...defaultProps} blocks={blocks} search="load image" />);

    expect(screen.getByText("Load Image")).toBeInTheDocument();
    expect(screen.queryByText("Cellpose Segment")).not.toBeInTheDocument();
    // segmentation category should not appear
    expect(screen.queryByText("segmentation")).not.toBeInTheDocument();
  });

  it("blocks render as-is without IO expansion", () => {
    const blocks: BlockSummary[] = [
      makeBlock({ type_name: "load_data", name: "Load", base_category: "io", direction: "input" }),
      makeBlock({ type_name: "save_data", name: "Save", base_category: "io", direction: "output" }),
    ];

    render(<BlockPalette {...defaultProps} blocks={blocks} />);

    // Blocks render with their actual names — no expansion
    expect(screen.getAllByText("Load").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Save").length).toBeGreaterThan(0);
  });
});
