import { describe, expect, it } from "vitest";

import type { BlockSummary } from "../../../types/api";
import {
  BUILTIN_PACKAGE,
  buildPaletteSections,
  DATA_IO_SECTION_ID,
  derivePackage,
  filterBlocks,
  isDataIoBlock,
  isIoSink,
  isIoSource,
  MY_LIBRARY_EMPTY_HINT,
  portSignature,
  PROJECT_LIBRARY_SECTION_ID,
  resolveBlockOrigin,
  sectionIdFor,
  THIS_PROJECT_EMPTY_HINT,
  USER_LIBRARY_SECTION_ID,
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
    origin: overrides.origin,
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
  origin: "builtin",
  input_ports: [],
  output_ports: [port("data", ["Image"])],
});
const save = makeBlock({
  type_name: "save_data",
  name: "Save",
  base_category: "io",
  direction: "output",
  origin: "builtin",
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
  it("maps builtin (no dot) to SciStudio Core", () => {
    expect(derivePackage(load)).toBe(BUILTIN_PACKAGE);
  });

  it("uppercases short prefixes and title-cases longer ones", () => {
    expect(derivePackage(makeBlock({ type_name: "lcms.peak", name: "Peak" }))).toBe("LCMS");
    expect(derivePackage(makeBlock({ type_name: "imaging.seg", name: "Seg" }))).toBe("Imaging");
  });

  it("treats the core ai namespace as Built-in (not a plugin package)", () => {
    expect(
      derivePackage(makeBlock({ type_name: "ai.agent", name: "Agent", base_category: "ai" })),
    ).toBe(BUILTIN_PACKAGE);
  });

  it("prefers an explicit package_name over the type_name prefix", () => {
    expect(
      derivePackage(makeBlock({ type_name: "imaging.seg", name: "Seg", package_name: "Vision" })),
    ).toBe("Vision");
  });
});

describe("resolveBlockOrigin — ADR-053 FR-001/FR-002/FR-004", () => {
  it("passes the backend-resolved origin through", () => {
    for (const origin of ["builtin", "user", "project", "package", "custom"] as const) {
      expect(resolveBlockOrigin(makeBlock({ type_name: "x", name: "X", origin }))).toBe(origin);
    }
  });

  it("falls back to the legacy `source` label when no origin is present", () => {
    expect(resolveBlockOrigin(makeBlock({ type_name: "x", name: "X", source: "custom" }))).toBe(
      "custom",
    );
    expect(resolveBlockOrigin(makeBlock({ type_name: "filter", name: "Filter" }))).toBe("package");
  });

  it("treats an unrecognised origin value as absent rather than trusting it", () => {
    const rogue = makeBlock({ type_name: "x", name: "X", source: "custom" });
    (rogue as { origin?: string }).origin = "not-a-tier";
    expect(resolveBlockOrigin(rogue)).toBe("custom");
  });
});

describe("sectionIdFor — origin tier first, package second (FR-038)", () => {
  it("routes the user tier to My Library and the project tier to This Project", () => {
    expect(sectionIdFor(makeBlock({ type_name: "mine", name: "Mine", origin: "user" }))).toBe(
      USER_LIBRARY_SECTION_ID,
    );
    expect(sectionIdFor(makeBlock({ type_name: "local", name: "Local", origin: "project" }))).toBe(
      PROJECT_LIBRARY_SECTION_ID,
    );
  });

  it("files the FR-002 `custom` fallback under This Project so it never vanishes", () => {
    expect(sectionIdFor(makeBlock({ type_name: "orphan", name: "Orphan", origin: "custom" }))).toBe(
      PROJECT_LIBRARY_SECTION_ID,
    );
  });

  it("splits the package family by package, not by origin", () => {
    expect(
      sectionIdFor(makeBlock({ type_name: "filter", name: "Filter", origin: "builtin" })),
    ).toBe(BUILTIN_PACKAGE);
    expect(
      sectionIdFor(makeBlock({ type_name: "imaging.seg", name: "Seg", origin: "package" })),
    ).toBe("Imaging");
  });

  it("pins Data I/O above the tier split whatever the block's origin", () => {
    expect(sectionIdFor(load)).toBe(DATA_IO_SECTION_ID);
    expect(sectionIdFor({ ...save, origin: "user" })).toBe(DATA_IO_SECTION_ID);
  });
});

describe("buildPaletteSections ordering", () => {
  const blocks: BlockSummary[] = [
    makeBlock({ type_name: "spectroscopy.baseline", name: "Baseline", origin: "package" }),
    makeBlock({ type_name: "imaging.cellpose", name: "Cellpose", origin: "package" }),
    makeBlock({ type_name: "filter", name: "Filter", origin: "builtin" }),
    makeBlock({ type_name: "my_tool", name: "My Tool", origin: "user" }),
    makeBlock({ type_name: "project_tool", name: "Project Tool", origin: "project" }),
    load,
    save,
  ];

  it("orders Data I/O → Built-in → My Library → This Project → plugin packages A→Z", () => {
    const sections = buildPaletteSections(blocks, "", []);
    expect(sections.map((s) => s.title)).toEqual([
      "Data I/O",
      "Built-in",
      "My Library",
      "This Project",
      "Imaging",
      "Spectroscopy",
    ]);
    expect(sections[0].id).toBe(DATA_IO_SECTION_ID);
    expect(sections[0].pinned).toBe(true);
    expect(sections.slice(1).some((s) => s.pinned)).toBe(false);
  });

  it("groups by origin tier, not by package (FR-038)", () => {
    // Two tier-1 blocks that would previously have shared one `Custom` section
    // — and whose dotted names would otherwise pull them into plugin sections.
    const tiered = buildPaletteSections(
      [
        makeBlock({ type_name: "imaging.mine", name: "Mine", origin: "user" }),
        makeBlock({ type_name: "imaging.theirs", name: "Theirs", origin: "project" }),
      ],
      "",
      [],
    );
    expect(tiered.map((s) => s.title)).toEqual(["My Library", "This Project"]);
    expect(tiered[0].items.map((b) => b.name)).toEqual(["Mine"]);
    expect(tiered[1].items.map((b) => b.name)).toEqual(["Theirs"]);
  });

  it("no longer renders a single collapsed `Custom` section", () => {
    const sections = buildPaletteSections(blocks, "", []);
    expect(sections.map((s) => s.title)).not.toContain("Custom");
  });

  it("lifts Load/Save into Data I/O and out of their tier group (no duplicate)", () => {
    const sections = buildPaletteSections(blocks, "", []);
    const dataIo = sections.find((s) => s.id === DATA_IO_SECTION_ID)!;
    expect(dataIo.items.map((b) => b.name)).toEqual(["Load", "Save"]);
    const builtin = sections.find((s) => s.title === "Built-in")!;
    expect(builtin.items.some((b) => b.name === "Load" || b.name === "Save")).toBe(false);
  });

  it("sorts each section alphabetically by block name", () => {
    const sections = buildPaletteSections(
      [
        makeBlock({ type_name: "z", name: "Zeta", origin: "user" }),
        makeBlock({ type_name: "a", name: "Alpha", origin: "user" }),
      ],
      "",
      [],
    );
    const library = sections.find((s) => s.id === USER_LIBRARY_SECTION_ID)!;
    expect(library.items.map((b) => b.name)).toEqual(["Alpha", "Zeta"]);
  });

  it("omits empty sections that carry no teaching copy", () => {
    const sections = buildPaletteSections([load], "", []);
    expect(sections.map((s) => s.title)).toEqual(["Data I/O", "My Library", "This Project"]);
  });
});

describe("tier empty states — FR-037", () => {
  it("renders My Library and This Project even with no blocks at all", () => {
    const sections = buildPaletteSections([], "", []);
    expect(sections.map((s) => s.id)).toEqual([
      USER_LIBRARY_SECTION_ID,
      PROJECT_LIBRARY_SECTION_ID,
    ]);
    expect(sections[0].emptyHint).toBe(MY_LIBRARY_EMPTY_HINT);
    expect(sections[1].emptyHint).toBe(THIS_PROJECT_EMPTY_HINT);
    expect(sections.every((s) => s.items.length === 0)).toBe(true);
  });

  it("states in one line what each section is for", () => {
    expect(MY_LIBRARY_EMPTY_HINT).toBe(
      "No blocks of your own yet. Save a block here and every project can use it.",
    );
    expect(THIS_PROJECT_EMPTY_HINT).toBe(
      "No blocks in this project yet. Blocks you add here stay with this project.",
    );
  });

  it("keeps the teaching copy off a section that merely has content", () => {
    const sections = buildPaletteSections(
      [makeBlock({ type_name: "mine", name: "Mine", origin: "user" })],
      "",
      [],
    );
    const library = sections.find((s) => s.id === USER_LIBRARY_SECTION_ID)!;
    expect(library.items.map((b) => b.name)).toEqual(["Mine"]);
  });

  it("drops the empty sections while a search is narrowing the grid", () => {
    // An empty section under an active query says nothing about the library and
    // everything about the query, so it behaves like every other section.
    const sections = buildPaletteSections(
      [makeBlock({ type_name: "filter", name: "Filter", origin: "builtin" })],
      "filter",
      [],
    );
    expect(sections.map((s) => s.title)).toEqual(["Built-in"]);
  });

  it("drops the empty sections while a category chip is active", () => {
    const sections = buildPaletteSections(
      [makeBlock({ type_name: "filter", name: "Filter", origin: "builtin" })],
      "",
      ["process"],
    );
    expect(sections.map((s) => s.title)).toEqual(["Built-in"]);
  });
});

describe("filterBlocks — search AND category chips", () => {
  const blocks: BlockSummary[] = [
    makeBlock({ type_name: "imaging.cellpose", name: "Cellpose", origin: "package" }),
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

describe("filtering the new tier sections behaves like every other section", () => {
  const tiered: BlockSummary[] = [
    makeBlock({
      type_name: "my_denoise",
      name: "My Denoise",
      origin: "user",
      description: "Rolling-ball denoise I reuse everywhere",
    }),
    makeBlock({
      type_name: "project_qc",
      name: "Project QC",
      origin: "project",
      base_category: "code",
      description: "One-off QC for this dataset",
    }),
  ];

  it("text search narrows the tier sections", () => {
    const sections = buildPaletteSections(tiered, "denoise", []);
    expect(sections.map((s) => s.title)).toEqual(["My Library"]);
    expect(sections[0].items.map((b) => b.name)).toEqual(["My Denoise"]);
  });

  it("a category chip narrows the tier sections", () => {
    const sections = buildPaletteSections(tiered, "", ["code"]);
    expect(sections.map((s) => s.title)).toEqual(["This Project"]);
    expect(sections[0].items.map((b) => b.name)).toEqual(["Project QC"]);
  });

  it("search AND chip compose across tiers exactly as they do for packages", () => {
    expect(buildPaletteSections(tiered, "denoise", ["code"])).toEqual([]);
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
