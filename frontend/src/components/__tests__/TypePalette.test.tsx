// The Data types tab (ADR-053 §9.2, FR-039 – FR-043).
//
// Structure mirrors the Blocks tab, the row swatch follows the FR-051
// precedence, and the popover carries the FR-042 rows — including the FR-043
// parent chain and the FR-056 explicit no-formats line.
//
// The cell is a list row, not a tile (FR-041): the Blocks tab's grid reads as
// "drag me onto the canvas" and a type cannot be dragged anywhere.

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

function rows(): HTMLElement[] {
  return screen.queryAllByTestId("palette-type-row");
}

/**
 * Match on the name cell rather than the row's text, because the row now also
 * carries a parent: `within(imageRow).queryByText("Array")` would otherwise
 * hand back Image's row when asked for Array's.
 */
function rowNamed(name: string): HTMLElement {
  const row = rows().find(
    (element) => within(element).queryByTestId("palette-type-row-name")?.textContent === name,
  );
  if (!row) {
    throw new Error(`no row for ${name}`);
  }
  return row;
}

/** The right-hand parent cell of one row, or `null` when it is suppressed. */
function parentOf(name: string): string | null {
  return within(rowNamed(name)).queryByTestId("palette-type-row-parent")?.textContent ?? null;
}

function openPopoverFor(name: string): void {
  vi.useFakeTimers();
  fireEvent.mouseEnter(rowNamed(name));
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

  it("renders a row per registered type", () => {
    renderPalette();
    expect(rows()).toHaveLength(CATALOGUE.length);
  });

  it("renders both tier sections with their teaching copy when empty (FR-037)", () => {
    renderPalette([array]);
    const hints = screen.getAllByTestId("palette-section-empty").map((node) => node.textContent);
    expect(hints).toHaveLength(2);
    expect(hints[0]).toMatch(/type here and every project can use it/);
    expect(hints[1]).toMatch(/stay with this project/);
  });

  it("filters rows by the search input", () => {
    renderPalette();
    fireEvent.change(screen.getByPlaceholderText("Search data types"), {
      target: { value: "denois" },
    });
    expect(rows()).toHaveLength(1);
    expect(within(rows()[0]).getByText("MyDenoised")).toBeInTheDocument();
  });

  it("filters rows by a family chip", () => {
    renderPalette();
    fireEvent.click(within(screen.getByTestId("type-family-chips")).getByText("Series"));
    expect(rows().map((row) => row.textContent)).toEqual(["Series"]);
  });
});

describe("Data types tab — row shape (FR-041)", () => {
  it("lists one row per type rather than a grid of draggable tiles", () => {
    renderPalette();
    // The affordance is the point: the Blocks tab marks its cells `draggable`
    // and types were never draggable, so nothing here may claim to be.
    for (const row of rows()) {
      expect(row.getAttribute("draggable")).toBeNull();
    }
  });

  it("sets the immediate parent beside the name", () => {
    renderPalette();
    expect(parentOf("MyDenoised")).toBe("Image");
    expect(parentOf("Image")).toBe("Array");
  });

  it("suppresses `DataObject`, which every core base type would otherwise repeat", () => {
    renderPalette();
    expect(parentOf("Array")).toBeNull();
    expect(parentOf("Series")).toBeNull();
    // `DataObject` itself has no parent at all.
    expect(parentOf("DataObject")).toBeNull();
  });
});

describe("Data types tab — row swatch (FR-041, FR-051)", () => {
  it("renders a solid fill plus ring resolved through the precedence", () => {
    renderPalette();
    const swatch = rowNamed("Image").querySelector("span[aria-hidden='true']") as HTMLElement;
    // Image is a `typeColorMap` entry with a manual contrasting ring — the
    // same pair its canvas port handle draws.
    expect(swatch.style.backgroundColor).toBe("rgb(59, 130, 246)");
    expect(swatch.style.boxShadow).toContain("#ef4444");
  });

  it("gives a declared colour priority over the map and the hash fallback", () => {
    renderPalette();
    const swatch = rowNamed("Declared").querySelector("span[aria-hidden='true']") as HTMLElement;
    expect(swatch.style.backgroundColor).toBe("rgb(79, 142, 247)");
  });

  it("leaves an undeclared type on today's colour", () => {
    renderPalette();
    const swatch = rowNamed("Array").querySelector("span[aria-hidden='true']") as HTMLElement;
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

    fireEvent.mouseLeave(rowNamed("Image"));
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
    fireEvent.mouseLeave(rowNamed("MyDenoised"));
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
    expect(rows().map((row) => row.textContent)).toEqual(["Array"]);
  });

  it("renders no rows and no crash before the listing lands", () => {
    render(<TypePalette />);
    expect(rows()).toHaveLength(0);
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
    expect(rows()).toHaveLength(2);
  });
});
