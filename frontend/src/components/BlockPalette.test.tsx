import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BlockPalette } from "./BlockPalette";
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

  it("renders the six category filter chips", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} />);
    const chips = screen.getByTestId("palette-category-chips");
    ["IO", "Process", "Code", "App", "AI", "Subworkflow"].forEach((label) => {
      expect(within(chips).getByText(label)).toBeInTheDocument();
    });
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

    expect(screen.queryByTestId("palette-detail-popover")).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId("palette-block-tile"));
    act(() => {
      vi.advanceTimersByTime(200);
    });

    const popover = screen.getByTestId("palette-detail-popover");
    expect(
      within(popover).getByText("Run Cellpose model on an image to produce instance masks."),
    ).toBeInTheDocument();
    // Typed port signature is split across text nodes; check the type names.
    expect(within(popover).getByText("Image")).toBeInTheDocument();
    expect(within(popover).getByText("Mask")).toBeInTheDocument();
  });

  it("collapsed (rail) mode renders icon-only swatches", () => {
    render(<BlockPalette {...defaultProps} blocks={[cellpose]} collapsed />);
    // No grid tiles / chips in rail mode.
    expect(screen.queryByTestId("palette-block-tile")).not.toBeInTheDocument();
    expect(screen.queryByTestId("palette-category-chips")).not.toBeInTheDocument();
    // The block is still reachable by its title attribute.
    expect(screen.getByTitle("Cellpose Segment")).toBeInTheDocument();
  });
});
