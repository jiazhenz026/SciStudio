// The Data types tab (ADR-053 §9.2, FR-039 – FR-043).
//
// Structure mirrors the Blocks tab, tile colour follows the FR-051 precedence,
// and the popover carries the FR-042 rows — including the FR-043 parent chain
// and the FR-056 explicit no-formats line.

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveTypeColor } from "../../config/typeColorMap";
import { useAppStore } from "../../store";
import { resetTypeCatalogLoader } from "../../store/useTypeCatalog";
import { resetAppStore } from "../../testUtils";
import { makeType } from "../TypePalette.parts/__tests__/fixtures";
import { POPOVER_OPEN_DELAY_MS } from "../palette/hoverPopover";
import { TypePalette } from "../TypePalette";
import type { TypeSummary } from "../../types/api";

const listTypes = vi.fn();
vi.mock("../../lib/api/code", () => ({
  codeApi: {
    listTypes: () => listTypes(),
  },
}));

const dataObject = makeType({ name: "DataObject", base_type: "" });
const array = makeType({ name: "Array", description: "N-dimensional numeric array." });
const image = makeType({
  name: "Image",
  base_type: "Array",
  load_extensions: [".png", ".tif"],
  save_extensions: [".png"],
});
const series = makeType({ name: "Series", save_extensions: [".json"] });
const myType = makeType({
  name: "MyDenoised",
  base_type: "Image",
  origin: "user",
  description: "A denoised image of my own.",
});
const declaring = makeType({
  name: "Declared",
  base_type: "Array",
  origin: "project",
  ui_color: "#4f8ef7",
});

const CATALOGUE: TypeSummary[] = [dataObject, array, image, series, myType, declaring];

/** Render the tab with `types` already in the store (listing landed). */
function renderPalette(types: TypeSummary[] = CATALOGUE) {
  const result = render(<TypePalette />);
  act(() => {
    useAppStore.getState().setTypes(types);
  });
  return result;
}

function tiles(): HTMLElement[] {
  return screen.queryAllByTestId("palette-type-tile");
}

function tileNamed(name: string): HTMLElement {
  const tile = tiles().find((element) => within(element).queryByText(name) !== null);
  if (!tile) {
    throw new Error(`no tile for ${name}`);
  }
  return tile;
}

function openPopoverFor(name: string): void {
  vi.useFakeTimers();
  fireEvent.mouseEnter(tileNamed(name));
  act(() => {
    vi.advanceTimersByTime(POPOVER_OPEN_DELAY_MS + 1);
  });
  vi.useRealTimers();
}

beforeEach(() => {
  resetAppStore();
  resetTypeCatalogLoader();
  listTypes.mockResolvedValue({ types: [] });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  listTypes.mockReset();
});

describe("Data types tab — structure (FR-039, FR-040)", () => {
  it("titles the panel `Data types`, matching its tab label", () => {
    renderPalette();
    expect(screen.getByText("Data types")).toBeInTheDocument();
  });

  it("mirrors the Blocks tab: search input, filter chips, tier sections", () => {
    renderPalette();
    expect(screen.getByPlaceholderText("Search data types")).toBeInTheDocument();
    expect(screen.getByTestId("type-family-chips")).toBeInTheDocument();
    const headings = screen.getAllByText(/^(Core|My Library|This Project)$/);
    expect(headings.map((node) => node.textContent)).toEqual([
      "Core",
      "My Library",
      "This Project",
    ]);
  });

  it("renders a tile per registered type", () => {
    renderPalette();
    expect(tiles()).toHaveLength(CATALOGUE.length);
  });

  it("renders both tier sections with their teaching copy when empty (FR-037)", () => {
    renderPalette([array]);
    const hints = screen.getAllByTestId("palette-section-empty").map((node) => node.textContent);
    expect(hints).toHaveLength(2);
    expect(hints[0]).toMatch(/type here and every project can use it/);
    expect(hints[1]).toMatch(/stay with this project/);
  });

  it("filters tiles by the search input", () => {
    renderPalette();
    fireEvent.change(screen.getByPlaceholderText("Search data types"), {
      target: { value: "denois" },
    });
    expect(tiles()).toHaveLength(1);
    expect(within(tiles()[0]).getByText("MyDenoised")).toBeInTheDocument();
  });

  it("filters tiles by a family chip", () => {
    renderPalette();
    fireEvent.click(within(screen.getByTestId("type-family-chips")).getByText("Series"));
    expect(tiles().map((tile) => tile.textContent)).toEqual(["Series"]);
  });
});

describe("Data types tab — tile colour (FR-041, FR-051)", () => {
  it("renders a solid fill plus ring resolved through the precedence", () => {
    renderPalette();
    const swatch = tileNamed("Image").querySelector("span[aria-hidden='true']") as HTMLElement;
    // Image is a `typeColorMap` entry with a manual contrasting ring — the
    // same pair its canvas port handle draws.
    expect(swatch.style.backgroundColor).toBe("rgb(59, 130, 246)");
    expect(swatch.style.boxShadow).toContain("#ef4444");
  });

  it("gives a declared colour priority over the map and the hash fallback", () => {
    renderPalette();
    const swatch = tileNamed("Declared").querySelector("span[aria-hidden='true']") as HTMLElement;
    expect(swatch.style.backgroundColor).toBe("rgb(79, 142, 247)");
  });

  it("leaves an undeclared type on today's colour", () => {
    renderPalette();
    const swatch = tileNamed("Array").querySelector("span[aria-hidden='true']") as HTMLElement;
    expect(swatch.style.backgroundColor).toBe("rgb(59, 130, 246)");
    expect(resolveTypeColor(["Array"])).toBe("#3b82f6");
  });
});

describe("Data types tab — hover popover (FR-042, FR-043, FR-056)", () => {
  it("opens after the shared dwell delay and shows name and description", () => {
    renderPalette();
    expect(screen.queryByTestId("type-detail-popover")).toBeNull();
    openPopoverFor("MyDenoised");
    const popover = screen.getByTestId("type-detail-popover");
    expect(within(popover).getByText("MyDenoised")).toBeInTheDocument();
    expect(within(popover).getByText("A denoised image of my own.")).toBeInTheDocument();
  });

  it("shows the chain position when the core base differs from the parent", () => {
    renderPalette();
    openPopoverFor("MyDenoised");
    expect(screen.getByTestId("type-detail-parent")).toHaveTextContent("Image (Array)");
  });

  it("does not render a redundant `Array (Array)`", () => {
    renderPalette();
    openPopoverFor("Image");
    expect(screen.getByTestId("type-detail-parent")).toHaveTextContent("Array");
    expect(screen.getByTestId("type-detail-parent").textContent).not.toContain("(");
  });

  it("reports load and save separately, including a save-only asymmetry", () => {
    renderPalette();
    openPopoverFor("Image");
    expect(screen.getByTestId("type-detail-load")).toHaveTextContent(".png .tif");
    expect(screen.getByTestId("type-detail-save")).toHaveTextContent(".png");

    fireEvent.mouseLeave(tileNamed("Image"));
    openPopoverFor("Series");
    // FR-055: a type saveable to a format it cannot be loaded from renders the
    // absence rather than hiding the direction.
    expect(screen.getByTestId("type-detail-load")).toHaveTextContent("—");
    expect(screen.getByTestId("type-detail-save")).toHaveTextContent(".json");
  });

  it("states the FR-056 no-formats case outright", () => {
    renderPalette();
    openPopoverFor("Array");
    expect(screen.getByTestId("type-detail-no-formats")).toHaveTextContent(
      "No file formats registered",
    );
    expect(screen.queryByTestId("type-detail-load")).toBeNull();
  });

  it("names the origin tier", () => {
    renderPalette();
    openPopoverFor("MyDenoised");
    expect(screen.getByTestId("type-detail-origin")).toHaveTextContent("My Library");
  });

  it("is interactive and survives the tile→popover gap (FR-044)", () => {
    renderPalette();
    openPopoverFor("MyDenoised");
    const popover = screen.getByTestId("type-detail-popover");
    expect(popover.className).not.toContain("pointer-events-none");

    vi.useFakeTimers();
    fireEvent.mouseLeave(tileNamed("MyDenoised"));
    fireEvent.mouseEnter(popover);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    vi.useRealTimers();
    // The card cancelled the pending close, so a promotion button inside it
    // (B5, entry point E5) is reachable.
    expect(screen.getByTestId("type-detail-popover")).toBeInTheDocument();
  });
});

describe("Data types tab — loading and reload (FR-027, FR-067)", () => {
  it("fetches the catalogue itself rather than taking blocks as props", async () => {
    listTypes.mockResolvedValue({ types: [array] });
    render(<TypePalette />);
    await act(async () => {});
    expect(listTypes).toHaveBeenCalledTimes(1);
    expect(tiles().map((tile) => tile.textContent)).toEqual(["Array"]);
  });

  it("renders no tiles and no crash before the listing lands", () => {
    render(<TypePalette />);
    expect(tiles()).toHaveLength(0);
    expect(screen.getByText("Data types")).toBeInTheDocument();
  });

  it("Reload re-fetches, bypassing the cache", async () => {
    listTypes.mockResolvedValue({ types: [array] });
    render(<TypePalette />);
    await act(async () => {});
    listTypes.mockResolvedValue({ types: [array, series] });
    await act(async () => {
      fireEvent.click(screen.getByText("Reload"));
    });
    expect(listTypes).toHaveBeenCalledTimes(2);
    expect(tiles()).toHaveLength(2);
  });
});
