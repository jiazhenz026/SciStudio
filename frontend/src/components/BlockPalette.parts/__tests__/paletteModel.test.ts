import { describe, expect, it } from "vitest";

import type { BlockSummary } from "../../../types/api";
import {
  buildPaletteSections,
  DATA_IO_SECTION_ID,
  derivePackage,
  filterBlocks,
  isDataIoBlock,
  isIoSink,
  isIoSource,
  portSignature,
} from "../paletteModel";

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

const load = makeBlock({
  type_name: "load_data",
  name: "Load",
  base_category: "io",
  direction: "input",
  input_ports: [],
  output_ports: [port("data", ["Image"])],
});
const save = makeBlock({
  type_name: "save_data",
  name: "Save",
  base_category: "io",
  direction: "output",
  input_ports: [port("data", ["Image"])],
  output_ports: [],
});

describe("Load/Save detection by structural signal", () => {
  it("detects io source (Load) and io sink (Save) by zero-port shape, not by name", () => {
    expect(isIoSource(load)).toBe(true);
    expect(isIoSink(save)).toBe(true);
    expect(isDataIoBlock(load)).toBe(true);
    expect(isDataIoBlock(save)).toBe(true);
  });

  it("a process block is never a Data I/O block", () => {
    const filter = makeBlock({ type_name: "filter", name: "Filter", base_category: "process" });
    expect(isDataIoBlock(filter)).toBe(false);
  });

  it("an io block with both ports is not pinned (mid-pipeline io)", () => {
    const passthrough = makeBlock({
      type_name: "io.passthrough",
      name: "Passthrough",
      base_category: "io",
      input_ports: [port("in")],
      output_ports: [port("out")],
    });
    expect(isDataIoBlock(passthrough)).toBe(false);
  });
});

describe("derivePackage", () => {
  it("maps builtin (no dot) to SciStudio Core and custom source to Custom", () => {
    expect(derivePackage(load)).toBe("SciStudio Core");
    expect(derivePackage(makeBlock({ type_name: "x", name: "X", source: "custom" }))).toBe(
      "Custom",
    );
  });

  it("uppercases short prefixes and title-cases longer ones", () => {
    expect(derivePackage(makeBlock({ type_name: "lcms.peak", name: "Peak" }))).toBe("LCMS");
    expect(derivePackage(makeBlock({ type_name: "imaging.seg", name: "Seg" }))).toBe("Imaging");
  });

  it("treats the core ai namespace as Built-in (not a plugin package)", () => {
    expect(
      derivePackage(makeBlock({ type_name: "ai.agent", name: "Agent", base_category: "ai" })),
    ).toBe("SciStudio Core");
  });
});

describe("buildPaletteSections ordering", () => {
  const blocks: BlockSummary[] = [
    makeBlock({ type_name: "spectroscopy.baseline", name: "Baseline" }),
    makeBlock({ type_name: "imaging.cellpose", name: "Cellpose", base_category: "process" }),
    makeBlock({ type_name: "filter", name: "Filter", base_category: "process" }),
    makeBlock({ type_name: "custom_x", name: "My Custom", source: "custom" }),
    load,
    save,
  ];

  it("orders Data I/O → Built-in → Custom → plugin packages A→Z", () => {
    const sections = buildPaletteSections(blocks, "", []);
    expect(sections.map((s) => s.title)).toEqual([
      "Data I/O",
      "Built-in",
      "Custom",
      "Imaging",
      "Spectroscopy",
    ]);
    expect(sections[0].id).toBe(DATA_IO_SECTION_ID);
    expect(sections[0].pinned).toBe(true);
  });

  it("lifts Load/Save into Data I/O and out of their package group (no duplicate)", () => {
    const sections = buildPaletteSections(blocks, "", []);
    const dataIo = sections.find((s) => s.id === DATA_IO_SECTION_ID)!;
    expect(dataIo.blocks.map((b) => b.name)).toEqual(["Load", "Save"]);
    const builtin = sections.find((s) => s.title === "Built-in")!;
    expect(builtin.blocks.some((b) => b.name === "Load" || b.name === "Save")).toBe(false);
  });

  it("omits empty sections", () => {
    const sections = buildPaletteSections([load], "", []);
    expect(sections.map((s) => s.title)).toEqual(["Data I/O"]);
  });
});

describe("filterBlocks — search AND category chips", () => {
  const blocks: BlockSummary[] = [
    makeBlock({ type_name: "imaging.cellpose", name: "Cellpose", base_category: "process" }),
    makeBlock({ type_name: "ai.annotate", name: "Annotate", base_category: "ai" }),
    load,
  ];

  it("text search alone filters by name/description", () => {
    expect(filterBlocks(blocks, "cellpose", []).map((b) => b.name)).toEqual(["Cellpose"]);
  });

  it("category chips alone filter by base_category", () => {
    expect(filterBlocks(blocks, "", ["ai"]).map((b) => b.name)).toEqual(["Annotate"]);
  });

  it("composes search AND category (both must pass)", () => {
    expect(filterBlocks(blocks, "annotate", ["process"])).toEqual([]);
    expect(filterBlocks(blocks, "annotate", ["ai"]).map((b) => b.name)).toEqual(["Annotate"]);
  });

  it("empty category set means all categories", () => {
    expect(filterBlocks(blocks, "", []).length).toBe(3);
  });
});

describe("portSignature", () => {
  it("renders name : primary type, falling back to Any when untyped", () => {
    expect(portSignature([port("image", ["Image", "Array"]), port("mask", [])])).toEqual([
      { name: "image", type: "Image" },
      { name: "mask", type: "Any" },
    ]);
  });
});
