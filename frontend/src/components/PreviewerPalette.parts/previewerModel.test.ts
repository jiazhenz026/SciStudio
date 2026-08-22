// Unit tests for the pure Previewers tab model (#2113) — tier grouping,
// ordering, search, and the choice lookups. Mirrors
// `TypePalette.parts/__tests__/typeModel.test.ts`: the model carries every
// rule so the component carries none.

import { describe, expect, it } from "vitest";

import type { PreviewerChoice, PreviewerSpecSummary } from "../../types/api";
import {
  buildPreviewerSections,
  choiceForType,
  CORE_SECTION_ID,
  filterPreviewers,
  isFilteringPreviewers,
  MY_LIBRARY_EMPTY_HINT,
  ownerKindLabel,
  PACKAGES_SECTION_ID,
  PROJECT_SECTION_ID,
  previewerSectionIdFor,
  staleChoices,
  THIS_PROJECT_EMPTY_HINT,
  USER_LIBRARY_SECTION_ID,
} from "./previewerModel";

function makePreviewer(overrides: Partial<PreviewerSpecSummary> = {}): PreviewerSpecSummary {
  return {
    previewer_id: "test.previewer",
    owner_kind: "core",
    owner_name: "scistudio",
    target_type: "DataObject",
    supports_collection: false,
    priority: 0,
    capabilities: [],
    backend_provider: null,
    frontend_manifest: null,
    api_version: "1",
    ...overrides,
  };
}

function makeChoice(overrides: Partial<PreviewerChoice> = {}): PreviewerChoice {
  return {
    target_type: "Spectrum",
    previewer_id: "pkg.spectrum.plot",
    scope: "user",
    available: true,
    ...overrides,
  };
}

const project = makePreviewer({
  previewer_id: "project.my.view",
  owner_kind: "project",
  owner_name: "demo",
  target_type: "Spectrum",
});
const user = makePreviewer({
  previewer_id: "user.my.view",
  owner_kind: "user",
  owner_name: "library",
  target_type: "Spectrum",
});
const pkgB = makePreviewer({
  previewer_id: "pkgb.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-b",
});
const pkgA = makePreviewer({
  previewer_id: "pkga.view",
  owner_kind: "package",
  owner_name: "scistudio-blocks-a",
});
const unnamed = makePreviewer({
  previewer_id: "orphan.view",
  owner_kind: "package",
  owner_name: "",
});
const core = makePreviewer({ previewer_id: "core.table" });

describe("previewerSectionIdFor", () => {
  it("groups by tier, and by package name inside the package tier", () => {
    expect(previewerSectionIdFor(project)).toBe(PROJECT_SECTION_ID);
    expect(previewerSectionIdFor(user)).toBe(USER_LIBRARY_SECTION_ID);
    expect(previewerSectionIdFor(core)).toBe(CORE_SECTION_ID);
    expect(previewerSectionIdFor(pkgA)).toBe("scistudio-blocks-a");
  });

  it("collects a package-tier previewer with no owner name rather than dropping it", () => {
    expect(previewerSectionIdFor(unnamed)).toBe(PACKAGES_SECTION_ID);
  });
});

describe("buildPreviewerSections", () => {
  it("orders This Project, My Library, Core, then packages A→Z", () => {
    const sections = buildPreviewerSections([pkgB, core, user, pkgA, project], "");
    expect(sections.map((s) => s.title)).toEqual([
      "This Project",
      "My Library",
      "Core",
      "scistudio-blocks-a",
      "scistudio-blocks-b",
    ]);
  });

  it("keeps both drop-in tier sections with their teaching copy when empty", () => {
    const sections = buildPreviewerSections([core], "");
    const byId = new Map(sections.map((s) => [s.id, s]));
    expect(byId.get(PROJECT_SECTION_ID)?.emptyHint).toBe(THIS_PROJECT_EMPTY_HINT);
    expect(byId.get(USER_LIBRARY_SECTION_ID)?.emptyHint).toBe(MY_LIBRARY_EMPTY_HINT);
  });

  it("omits core when no core previewer is registered", () => {
    const sections = buildPreviewerSections([user], "");
    expect(sections.map((s) => s.id)).not.toContain(CORE_SECTION_ID);
  });

  it("sorts cards inside a section by previewer id", () => {
    const a = makePreviewer({ previewer_id: "core.alpha" });
    const z = makePreviewer({ previewer_id: "core.zulu" });
    const sections = buildPreviewerSections([z, a], "");
    const coreSection = sections.find((s) => s.id === CORE_SECTION_ID);
    expect(coreSection?.items.map((item) => item.previewer_id)).toEqual([
      "core.alpha",
      "core.zulu",
    ]);
  });

  it("drops the teaching empty hints while a search is active", () => {
    const sections = buildPreviewerSections([core], "zzz-no-match");
    expect(sections.every((s) => s.emptyHint === undefined)).toBe(true);
    expect(sections).toHaveLength(0);
  });
});

describe("filterPreviewers / isFilteringPreviewers", () => {
  it("matches on id, target type, owner, and capabilities", () => {
    const cap = makePreviewer({ previewer_id: "core.plot", capabilities: ["interactive"] });
    expect(filterPreviewers([project, cap], "spectrum")).toEqual([project]);
    expect(filterPreviewers([project, cap], "interactive")).toEqual([cap]);
    expect(filterPreviewers([project, pkgA], "blocks-a")).toEqual([pkgA]);
  });

  it("treats blank search as no filter", () => {
    expect(isFilteringPreviewers("   ")).toBe(false);
    expect(isFilteringPreviewers("spec")).toBe(true);
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

  it("collects choices whose previewer is not registered right now", () => {
    const choices = [makeChoice(), makeChoice({ target_type: "Image", available: false })];
    expect(staleChoices(choices)).toEqual([choices[1]]);
  });
});
