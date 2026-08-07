// Data types tab model — tier grouping, ordering, empty states, facets, and
// the popover's derived rows.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §9.2 (FR-039 – FR-043),
//       §7.2 (FR-054 – FR-056), §10.1 (FR-047).

import { describe, expect, it } from "vitest";

import { makeType } from "./fixtures";
import { sectionIdFor } from "../../BlockPalette.parts/paletteModel";
import type { BlockSummary } from "../../../types/api";
import {
  buildTypeSections,
  CORE_SECTION_ID,
  extensionRows,
  filterTypes,
  isFilteringTypes,
  MY_LIBRARY_EMPTY_HINT,
  originLabel,
  PACKAGES_SECTION_ID,
  parentRow,
  PROJECT_LIBRARY_SECTION_ID,
  THIS_PROJECT_EMPTY_HINT,
  typeFamilies,
  typeFamily,
  typeHierarchyFrom,
  typeSectionIdFor,
  USER_LIBRARY_SECTION_ID,
} from "../typeModel";

const dataObject = makeType({ name: "DataObject", base_type: "" });
const array = makeType({ name: "Array" });
const image = makeType({ name: "Image", base_type: "Array" });
const series = makeType({
  name: "Series",
  save_extensions: [".json"],
});
const myType = makeType({ name: "MyDenoised", base_type: "Image", origin: "user" });
const projectType = makeType({ name: "ProjectScan", base_type: "Array", origin: "project" });
const customType = makeType({ name: "Stray", base_type: "Array", origin: "custom" });
/** A packaged type the backend could not attribute — the FR-040 fallback. */
const packageType = makeType({ name: "SRSImage", base_type: "Image", origin: "package" });
const srsType = makeType({
  name: "SRSStack",
  base_type: "Array",
  origin: "package",
  package_name: "scistudio-blocks-srs",
});
const imagingType = makeType({
  name: "FluorImage",
  base_type: "Image",
  origin: "package",
  package_name: "scistudio-blocks-imaging",
});

const ALL = [dataObject, array, image, series, myType, projectType, customType, packageType];

describe("typeSectionIdFor — origin tier grouping (FR-040, FR-005)", () => {
  it("routes each origin to its tier section", () => {
    expect(typeSectionIdFor(array)).toBe(CORE_SECTION_ID);
    expect(typeSectionIdFor(myType)).toBe(USER_LIBRARY_SECTION_ID);
    expect(typeSectionIdFor(projectType)).toBe(PROJECT_LIBRARY_SECTION_ID);
  });

  it("files the FR-002 `custom` fallback under This Project, not My Library", () => {
    // An unresolvable drop-in is not known to be reusable across projects, so
    // it must not claim a section that promises cross-project reuse.
    expect(typeSectionIdFor(customType)).toBe(PROJECT_LIBRARY_SECTION_ID);
  });

  it("groups a packaged type under the distribution the backend named", () => {
    expect(typeSectionIdFor(srsType)).toBe("scistudio-blocks-srs");
    expect(typeSectionIdFor(imagingType)).toBe("scistudio-blocks-imaging");
  });

  it("keeps an unattributed packaged type in the lumped Packages section", () => {
    // The backend says `null` rather than guessing a name that could contradict
    // the Blocks tab; the type must still be reachable somewhere.
    expect(typeSectionIdFor(packageType)).toBe(PACKAGES_SECTION_ID);
  });

  it("titles a package exactly as the Blocks tab titles the same distribution", () => {
    // The one acceptance check FR-040 turns on. The backend reports one string
    // on both summaries (it reads the block registry rather than deriving a
    // second name), so the two surfaces must resolve to the same section id —
    // a packaged type and a packaged block from one distribution sit under one
    // heading, spelled one way.
    for (const packageName of ["scistudio-blocks-srs", "scistudio-blocks-imaging"]) {
      const block = {
        name: "Probe",
        type_name: "probe",
        base_category: "process",
        subcategory: "",
        description: "",
        version: "0.1.0",
        input_ports: [],
        output_ports: [],
        origin: "package",
        package_name: packageName,
      } as BlockSummary;
      const type = makeType({ name: "Probe", origin: "package", package_name: packageName });
      expect(typeSectionIdFor(type)).toBe(sectionIdFor(block));
    }
  });
});

describe("buildTypeSections — order and empty states (FR-040, FR-037)", () => {
  it("orders Core (pinned) → My Library → This Project → Packages", () => {
    const sections = buildTypeSections(ALL, "", []);
    expect(sections.map((section) => section.title)).toEqual([
      "Core",
      "My Library",
      "This Project",
      "Packages",
    ]);
    expect(sections[0].pinned).toBe(true);
  });

  it("splits one section per package, A→Z, after the tier sections", () => {
    const sections = buildTypeSections([array, myType, srsType, imagingType], "", []);
    expect(sections.map((section) => section.title)).toEqual([
      "Core",
      "My Library",
      "This Project",
      "scistudio-blocks-imaging",
      "scistudio-blocks-srs",
    ]);
  });

  it("keeps an unnamed package alongside the named ones instead of dropping it", () => {
    const sections = buildTypeSections([srsType, packageType], "", []);
    const lumped = sections.find((section) => section.id === PACKAGES_SECTION_ID);
    expect(lumped?.items.map((type) => type.name)).toEqual(["SRSImage"]);
    expect(sections.some((section) => section.id === "scistudio-blocks-srs")).toBe(true);
  });

  it("sorts types by name inside a section", () => {
    const sections = buildTypeSections(ALL, "", []);
    const core = sections.find((section) => section.id === CORE_SECTION_ID);
    expect(core?.items.map((type) => type.name)).toEqual([
      "Array",
      "DataObject",
      "Image",
      "Series",
    ]);
  });

  it("renders both tier sections with their teaching copy when empty", () => {
    const sections = buildTypeSections([array], "", []);
    const user = sections.find((section) => section.id === USER_LIBRARY_SECTION_ID);
    const project = sections.find((section) => section.id === PROJECT_LIBRARY_SECTION_ID);
    expect(user?.items).toEqual([]);
    expect(user?.emptyHint).toBe(MY_LIBRARY_EMPTY_HINT);
    expect(project?.emptyHint).toBe(THIS_PROJECT_EMPTY_HINT);
  });

  it("drops the teaching copy while a filter is active", () => {
    const sections = buildTypeSections(ALL, "Array", []);
    for (const section of sections) {
      expect(section.emptyHint).toBeUndefined();
    }
  });

  it("omits a package section that has no types", () => {
    const sections = buildTypeSections([array], "", []);
    expect(sections.some((section) => section.id === PACKAGES_SECTION_ID)).toBe(false);
  });
});

describe("filterTypes — search AND family chips", () => {
  it("matches name, description, and base type case-insensitively", () => {
    expect(filterTypes(ALL, "image", []).map((type) => type.name)).toEqual([
      "Image",
      "MyDenoised",
      "SRSImage",
    ]);
  });

  it("matches a registered extension, so `.json` finds the type that saves it", () => {
    expect(filterTypes(ALL, ".json", []).map((type) => type.name)).toEqual(["Series"]);
  });

  it("composes the family chip filter with the text search (AND)", () => {
    const arrayFamily = filterTypes(ALL, "", ["Array"]).map((type) => type.name);
    expect(arrayFamily).toContain("Image");
    expect(arrayFamily).not.toContain("Series");
    expect(filterTypes(ALL, "SRS", ["Array"]).map((type) => type.name)).toEqual(["SRSImage"]);
  });

  it("treats an empty chip set as 'all'", () => {
    expect(filterTypes(ALL, "", []).length).toBe(ALL.length);
  });

  it("reports when a filter is active", () => {
    expect(isFilteringTypes("", [])).toBe(false);
    expect(isFilteringTypes("  ", [])).toBe(false);
    expect(isFilteringTypes("a", [])).toBe(true);
    expect(isFilteringTypes("", ["Array"])).toBe(true);
  });
});

describe("typeFamily / typeFamilies — the type-side facet vocabulary", () => {
  const hierarchy = typeHierarchyFrom(ALL);

  it("resolves a subtype to its core base", () => {
    expect(typeFamily(packageType, hierarchy)).toBe("Array");
    expect(typeFamily(image, hierarchy)).toBe("Array");
  });

  it("treats a core base as its own family", () => {
    expect(typeFamily(array, hierarchy)).toBe("Array");
    expect(typeFamily(series, hierarchy)).toBe("Series");
  });

  it("gives DataObject no family", () => {
    expect(typeFamily(dataObject, hierarchy)).toBeNull();
  });

  it("lists the distinct families A→Z", () => {
    expect(typeFamilies(ALL)).toEqual(["Array", "Series"]);
  });
});

describe("parentRow — the chain position (FR-042, FR-043)", () => {
  const hierarchy = typeHierarchyFrom(ALL);

  it("appends the core base when it differs from the immediate parent", () => {
    expect(parentRow(packageType, hierarchy)).toEqual({ parent: "Image", coreBase: "Array" });
  });

  it("does not render a redundant `Array (Array)`", () => {
    expect(parentRow(image, hierarchy)).toEqual({ parent: "Array", coreBase: null });
    expect(parentRow(array, hierarchy)).toEqual({ parent: "DataObject", coreBase: null });
  });

  it("omits the row entirely for a type with no parent", () => {
    expect(parentRow(dataObject, hierarchy)).toBeNull();
  });
});

describe("extensionRows — load and save reported separately (FR-054 – FR-056)", () => {
  it("reports a real load/save asymmetry rather than collapsing it", () => {
    expect(extensionRows(series)).toEqual([
      { label: "Load", extensions: null },
      { label: "Save", extensions: [".json"] },
    ]);
  });

  it("keeps both directions when both are populated", () => {
    const both = makeType({
      name: "DataFrame",
      load_extensions: [".csv"],
      save_extensions: [".csv", ".parquet"],
    });
    expect(extensionRows(both)).toEqual([
      { label: "Load", extensions: [".csv"] },
      { label: "Save", extensions: [".csv", ".parquet"] },
    ]);
  });

  it("signals the FR-056 no-formats case with null", () => {
    expect(extensionRows(dataObject)).toBeNull();
  });
});

describe("originLabel", () => {
  it("names every tier", () => {
    expect(originLabel("core")).toBe("Core");
    expect(originLabel("user")).toBe("My Library");
    expect(originLabel("project")).toBe("This Project");
    expect(originLabel("package")).toBe("Package");
    expect(originLabel("custom")).toBe("Custom");
  });
});
