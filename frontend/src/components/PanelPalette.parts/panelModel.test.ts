// Unit tests for the pure Panels tab model (#2113) — tier grouping,
// ordering, search, and the choice lookups. Mirrors
// `TypePalette.parts/__tests__/typeModel.test.ts`: the model carries every
// rule so the component carries none.

import { describe, expect, it } from "vitest";

import type { PanelChoice, PanelSpecSummary } from "../../types/api";
import {
  buildPanelSections,
  choiceForType,
  CORE_SECTION_ID,
  filterPanels,
  isFilteringPanels,
  MY_LIBRARY_EMPTY_HINT,
  ownerKindLabel,
  PACKAGES_SECTION_ID,
  PROJECT_SECTION_ID,
  panelSectionIdFor,
  staleChoices,
  THIS_PROJECT_EMPTY_HINT,
  USER_LIBRARY_SECTION_ID,
} from "./panelModel";

function makePanel(overrides: Partial<PanelSpecSummary> = {}): PanelSpecSummary {
  return {
    previewer_id: "test.panel",
    owner_kind: "core",
    owner_name: "scistudio",
    target_type: "DataObject",
    supports_collection: false,
    priority: 0,
    features: [],
    backend_provider: null,
    frontend_manifest: null,
    api_version: "1",
    ...overrides,
  };
}

function makeChoice(overrides: Partial<PanelChoice> = {}): PanelChoice {
  return {
    target_type: "Spectrum",
    previewer_id: "pkg.spectrum.plot",
    scope: "user",
    available: true,
    ...overrides,
  };
}

const project = makePanel({
  previewer_id: "project.my.view",
  owner_kind: "project",
  owner_name: "demo",
  target_type: "Spectrum",
});
const user = makePanel({
  previewer_id: "user.my.view",
  owner_kind: "user",
  owner_name: "library",
  target_type: "Spectrum",
});
const pkgB = makePanel({
  previewer_id: "pkgb.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-b",
});
const pkgA = makePanel({
  previewer_id: "pkga.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-a",
});
const unnamed = makePanel({
  previewer_id: "orphan.view",
  owner_kind: "package",
  owner_name: "",
});
const core = makePanel({ previewer_id: "core.table" });

describe("panelSectionIdFor", () => {
  it("groups by tier, and by package name inside the package tier", () => {
    expect(panelSectionIdFor(project)).toBe(PROJECT_SECTION_ID);
    expect(panelSectionIdFor(user)).toBe(USER_LIBRARY_SECTION_ID);
    expect(panelSectionIdFor(core)).toBe(CORE_SECTION_ID);
    expect(panelSectionIdFor(pkgA)).toBe("scistudio-blocks-a");
  });

  it("collects a package-tier panel with no owner name rather than dropping it", () => {
    expect(panelSectionIdFor(unnamed)).toBe(PACKAGES_SECTION_ID);
  });
});

describe("buildPanelSections", () => {
  it("orders This Project, My Library, Core, then packages A→Z", () => {
    const sections = buildPanelSections([pkgB, core, user, pkgA, project], "");
    expect(sections.map((s) => s.title)).toEqual([
      "This Project",
      "My Library",
      "Core",
      "scistudio-blocks-a",
      "scistudio-blocks-b",
    ]);
  });

  it("keeps both drop-in tier sections with their teaching copy when empty", () => {
    const sections = buildPanelSections([core], "");
    const byId = new Map(sections.map((s) => [s.id, s]));
    expect(byId.get(PROJECT_SECTION_ID)?.emptyHint).toBe(THIS_PROJECT_EMPTY_HINT);
    expect(byId.get(USER_LIBRARY_SECTION_ID)?.emptyHint).toBe(MY_LIBRARY_EMPTY_HINT);
  });

  it("omits core when no core panel is registered", () => {
    const sections = buildPanelSections([user], "");
    expect(sections.map((s) => s.id)).not.toContain(CORE_SECTION_ID);
  });

  it("sorts cards inside a section by panel id", () => {
    const a = makePanel({ previewer_id: "core.alpha" });
    const z = makePanel({ previewer_id: "core.zulu" });
    const sections = buildPanelSections([z, a], "");
    const coreSection = sections.find((s) => s.id === CORE_SECTION_ID);
    expect(coreSection?.items.map((item) => item.previewer_id)).toEqual([
      "core.alpha",
      "core.zulu",
    ]);
  });

  it("drops the teaching empty hints while a search is active", () => {
    const sections = buildPanelSections([core], "zzz-no-match");
    expect(sections.every((s) => s.emptyHint === undefined)).toBe(true);
    expect(sections).toHaveLength(0);
  });
});

describe("filterPanels / isFilteringPanels", () => {
  it("matches on id, target type, owner, and features", () => {
    const cap = makePanel({ previewer_id: "core.plot", features: ["interactive"] });
    expect(filterPanels([project, cap], "spectrum")).toEqual([project]);
    expect(filterPanels([project, cap], "interactive")).toEqual([cap]);
    expect(filterPanels([project, pkgA], "blocks-a")).toEqual([pkgA]);
  });

  it("treats blank search as no filter", () => {
    expect(isFilteringPanels("   ")).toBe(false);
    expect(isFilteringPanels("spec")).toBe(true);
  });
});

describe("ownerKindLabel", () => {
  it("labels the four tiers", () => {
    expect(ownerKindLabel("project")).toBe("This Project");
    expect(ownerKindLabel("user")).toBe("My Library");
    expect(ownerKindLabel("package")).toBe("Package");
    expect(ownerKindLabel("core")).toBe("Core");
  });
});

describe("choiceForType / staleChoices", () => {
  it("returns the effective choice for a type, or null when unchosen", () => {
    const choices = [makeChoice()];
    expect(choiceForType(choices, "Spectrum")?.previewer_id).toBe("pkg.spectrum.plot");
    expect(choiceForType(choices, "Image")).toBeNull();
  });

  it("matches exactly — a choice for a type does not claim another type", () => {
    expect(choiceForType([makeChoice({ target_type: "Spectrum" })], "Spectrum2")).toBeNull();
  });

  it("collects choices whose panel is not registered right now", () => {
    const choices = [makeChoice(), makeChoice({ target_type: "Image", available: false })];
    expect(staleChoices(choices)).toEqual([choices[1]]);
  });
});
