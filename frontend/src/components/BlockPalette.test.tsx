import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BlockPalette, paletteColumns } from "./BlockPalette";
import type { BlockSummary } from "../types/api";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function port(name: string, types: string[] = []): BlockSummary["input_ports"][number] {
  return {
    name,
    direction: "input",
    accepted_types: types,
    required: true,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

function makeBlock(
  overrides: Partial<BlockSummary> & { type_name: string; name: string },
): BlockSummary {
  return {
    name: overrides.name,
    type_name: overrides.type_name,
    base_category: overrides.base_category ?? "process",
    subcategory: overrides.subcategory ?? "",
    description: overrides.description ?? "A block",
    version: "0.1.0",
    input_ports: overrides.input_ports ?? [],
    output_ports: overrides.output_ports ?? [],
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

const load = makeBlock({
  type_name: "load_data",
  name: "Load",
  base_category: "io",
  direction: "input",
  output_ports: [port("data", ["Image"])],
});
const save = makeBlock({
  type_name: "save_data",
  name: "Save",
  base_category: "io",
  direction: "output",
  input_ports: [port("data", ["Image"])],
});
const cellpose = makeBlock({
  type_name: "imaging.cellpose_segment",
  name: "Cellpose Segment",
  base_category: "process",
  description: "Run Cellpose model on an image to produce instance masks.",
  input_ports: [port("image", ["Image"])],
  output_ports: [port("masks", ["Mask"])],
});
const annotate = makeBlock({
  type_name: "ai.annotate",
  name: "Annotate",
  base_category: "ai",
});

describe("BlockPalette — grid redesign (#1797)", () => {
  it("renders blocks as grid tiles with name but no always-on description or in/out text", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);

    const tiles = screen.getAllByTestId("palette-block-tile");
    expect(tiles).toHaveLength(1);
    expect(screen.getByText("Cellpose Segment")).toBeInTheDocument();
    // Description is hover-only now, not rendered inline.
    expect(
      screen.queryByText("Run Cellpose model on an image to produce instance masks."),
    ).not.toBeInTheDocument();
    // No "X in / Y out" text line on the tile.
    expect(screen.queryByText(/\bin\s*\/\s*\d+\s*out\b/i)).not.toBeInTheDocument();
  });

  it("pins Load and Save in a Data I/O section at the top", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose, load, save]} />);

    const dataIoHeader = screen.getByText("Data I/O");
    expect(dataIoHeader).toBeInTheDocument();

    const section = dataIoHeader.closest("section")!;
    expect(within(section).getByText("Load")).toBeInTheDocument();
    expect(within(section).getByText("Save")).toBeInTheDocument();

    // Data I/O appears before the Built-in section in DOM order.
    const headers = screen.getAllByText(/Data I\/O|Built-in/);
    expect(headers[0].textContent).toBe("Data I/O");
  });

  it("renders the category filter chips (no Subworkflow chip)", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);
    const chips = screen.getByTestId("palette-category-chips");
    ["IO", "Process", "Code", "App", "AI"].forEach((label) => {
      expect(within(chips).getByText(label)).toBeInTheDocument();
    });
    expect(within(chips).queryByText("Subworkflow")).not.toBeInTheDocument();
  });

  it("activating a category chip filters the visible tiles", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose, annotate]} />);
    expect(screen.getByText("Cellpose Segment")).toBeInTheDocument();
    expect(screen.getByText("Annotate")).toBeInTheDocument();

    const chips = screen.getByTestId("palette-category-chips");
    fireEvent.click(within(chips).getByText("AI"));

    expect(screen.queryByText("Cellpose Segment")).not.toBeInTheDocument();
    expect(screen.getByText("Annotate")).toBeInTheDocument();
  });

  it("hovering a tile opens the detail popover with description and typed ports", () => {
    vi.useFakeTimers();
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);

    expect(screen.queryByTestId("block-detail-popover")).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId("palette-block-tile"));
    act(() => {
      vi.advanceTimersByTime(200);
    });

    const popover = screen.getByTestId("block-detail-popover");
    expect(
      within(popover).getByText("Run Cellpose model on an image to produce instance masks."),
    ).toBeInTheDocument();
    // Typed port signature is split across text nodes; check the type names.
    expect(within(popover).getByText("Image")).toBeInTheDocument();
    expect(within(popover).getByText("Mask")).toBeInTheDocument();
  });

  it("pulses the whole palette content after a Reload resolves into a refreshed catalog", () => {
    const animateMock = vi.fn();
    const original = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateMock as unknown as typeof original;
    try {
      const { rerender } = render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);
      fireEvent.click(screen.getByText("Reload"));
      expect(defaultProps.onReload).toHaveBeenCalled();
      expect(animateMock).not.toHaveBeenCalled();

      // Parent's refreshBlocks resolved -> a new blocks array is passed down.
      rerender(<BlockPalette {...defaultProps} blocks={[{ ...cellpose }]} />);

      expect(animateMock).toHaveBeenCalledTimes(1);
      // Opacity keyframes pulse the whole content element.
      const keyframes = animateMock.mock.calls[0][0];
      expect(keyframes).toEqual([{ opacity: 1 }, { opacity: 0 }, { opacity: 1 }]);
    } finally {
      HTMLElement.prototype.animate = original;
    }
  });

  it("does not pulse when the catalog changes without a Reload click", () => {
    const animateMock = vi.fn();
    const original = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animateMock as unknown as typeof original;
    try {
      const { rerender } = render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);
      rerender(<BlockPalette {...defaultProps} blocks={[{ ...cellpose }]} />);
      expect(animateMock).not.toHaveBeenCalled();
    } finally {
      HTMLElement.prototype.animate = original;
    }
  });

  it("collapsed (rail) mode renders icon-only swatches", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} collapsed />);
    // No grid tiles / chips in rail mode.
    expect(screen.queryByTestId("palette-block-tile")).not.toBeInTheDocument();
    expect(screen.queryByTestId("palette-category-chips")).not.toBeInTheDocument();
    // The block is still reachable by its title attribute.
    expect(screen.getByTitle("Cellpose Segment")).toBeInTheDocument();
  });

  it("renders the tile grid via a width-driven column count, not a fixed 2-col class (#1857)", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);
    const grid = screen.getByTestId("palette-block-tile").parentElement!;
    // No hardcoded Tailwind 2-column class anymore.
    expect(grid.className).not.toContain("grid-cols-2");
    expect(grid.className).toContain("grid");
    // Column count is driven by an inline grid-template-columns. jsdom has no
    // layout / ResizeObserver, so the component keeps the default 2 columns.
    expect(grid.style.gridTemplateColumns).toBe("repeat(2, minmax(0, 1fr))");
  });
});

describe("paletteColumns — width → column count (#1857)", () => {
  it("keeps the default 2 columns before the grid has been measured", () => {
    expect(paletteColumns(0)).toBe(2);
    expect(paletteColumns(-50)).toBe(2);
  });

  it("falls back to 1 column only when too narrow for two 80px tiles", () => {
    expect(paletteColumns(100)).toBe(1);
    expect(paletteColumns(163)).toBe(1); // just under 2*80 + gap
    expect(paletteColumns(164)).toBe(2); // exactly two tiles + gap fit
  });

  it("prefers 2 columns at a typical default panel width", () => {
    expect(paletteColumns(184)).toBe(2);
  });

  it("expands to 3 columns when the panel is dragged wide, capped at 3", () => {
    expect(paletteColumns(247)).toBe(2); // just under 3 tiles
    expect(paletteColumns(248)).toBe(3); // three tiles + gaps fit
    expect(paletteColumns(1000)).toBe(3); // never exceeds the 3-column cap
  });
});
