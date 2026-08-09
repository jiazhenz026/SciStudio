// The shared section model, exercised on an item type that is neither a block
// nor a type. ADR-053 FR-047 requires `buildSections<T>` to fit both palette
// surfaces without per-surface special-casing; testing it against a third,
// deliberately foreign shape is how that claim is kept honest.

import { describe, expect, it } from "vitest";

import { buildSections, filterItems, withoutEmptyHints, type SectionSlot } from "../sections";

interface Thing {
  label: string;
  tier: string;
}

const thing = (label: string, tier: string): Thing => ({ label, tier });
const byLabel = (a: Thing, b: Thing): number => a.label.localeCompare(b.label);
const tierOf = (item: Thing): string => item.tier;

const SLOTS: readonly SectionSlot[] = [
  { id: "__pinned__", title: "Pinned", pinned: true },
  { id: "core", title: "Core" },
  { id: "mine", title: "My Library", emptyHint: "Nothing of your own yet." },
  { id: "here", title: "This Project", emptyHint: "Nothing here yet." },
];

describe("filterItems", () => {
  const items = [thing("Alpha", "core"), thing("Beta", "mine")];

  it("matches a case-insensitive substring of the haystack", () => {
    expect(filterItems(items, "ALP", (i) => i.label).map((i) => i.label)).toEqual(["Alpha"]);
  });

  it("returns everything for an empty or whitespace-only search", () => {
    expect(filterItems(items, "", (i) => i.label)).toHaveLength(2);
    expect(filterItems(items, "   ", (i) => i.label)).toHaveLength(2);
  });

  it("does not mutate or alias the input array", () => {
    const result = filterItems(items, "", (i) => i.label);
    expect(result).not.toBe(items);
    expect(result).toEqual(items);
  });

  it("searches whatever the caller puts in the haystack, not a fixed field", () => {
    expect(filterItems(items, "mine", (i) => `${i.label} ${i.tier}`).map((i) => i.label)).toEqual([
      "Beta",
    ]);
  });
});

describe("buildSections", () => {
  it("emits declared slots in order, then remaining groups A→Z", () => {
    const sections = buildSections(
      [
        thing("Zed", "zeta-pkg"),
        thing("Anna", "alpha-pkg"),
        thing("Core thing", "core"),
        thing("Pin", "__pinned__"),
        thing("Mine", "mine"),
        thing("Here", "here"),
      ],
      tierOf,
      SLOTS,
      byLabel,
    );
    expect(sections.map((s) => s.title)).toEqual([
      "Pinned",
      "Core",
      "My Library",
      "This Project",
      "alpha-pkg",
      "zeta-pkg",
    ]);
  });

  it("marks only the declared pinned slot as pinned", () => {
    const sections = buildSections([thing("Pin", "__pinned__")], tierOf, SLOTS, byLabel);
    expect(sections.find((s) => s.id === "__pinned__")!.pinned).toBe(true);
    expect(sections.filter((s) => s.pinned)).toHaveLength(1);
  });

  it("omits an empty slot with no hint and keeps an empty slot that has one", () => {
    const sections = buildSections([], tierOf, SLOTS, byLabel);
    expect(sections.map((s) => s.id)).toEqual(["mine", "here"]);
    expect(sections[0].emptyHint).toBe("Nothing of your own yet.");
    expect(sections[0].items).toEqual([]);
  });

  it("never emits an empty remainder section", () => {
    const sections = buildSections([thing("Only", "core")], tierOf, SLOTS, byLabel);
    expect(sections.filter((s) => s.items.length === 0).map((s) => s.id)).toEqual(["mine", "here"]);
  });

  it("titles a remainder section with its own group key", () => {
    const sections = buildSections([thing("X", "Imaging")], tierOf, [], byLabel);
    expect(sections).toEqual([
      { id: "Imaging", title: "Imaging", items: [thing("X", "Imaging")], pinned: false },
    ]);
  });

  it("sorts within a section with the supplied comparator", () => {
    const sections = buildSections(
      [thing("Zeta", "core"), thing("Alpha", "core")],
      tierOf,
      SLOTS,
      byLabel,
    );
    expect(sections[0].items.map((i) => i.label)).toEqual(["Alpha", "Zeta"]);
  });

  it("keeps insertion order when no comparator is supplied", () => {
    const sections = buildSections([thing("Zeta", "core"), thing("Alpha", "core")], tierOf, SLOTS);
    expect(sections[0].items.map((i) => i.label)).toEqual(["Zeta", "Alpha"]);
  });

  it("routes each item to exactly one section", () => {
    const items = [thing("Pin", "__pinned__"), thing("Mine", "mine"), thing("Pkg", "Imaging")];
    const sections = buildSections(items, tierOf, SLOTS, byLabel);
    const placed = sections.flatMap((s) => s.items);
    expect(placed).toHaveLength(items.length);
    expect(new Set(placed.map((i) => i.label)).size).toBe(items.length);
  });

  it("does not alias the caller's slot list", () => {
    const slots = [...SLOTS];
    buildSections([thing("Mine", "mine")], tierOf, slots, byLabel);
    expect(slots).toEqual(SLOTS);
  });
});

describe("withoutEmptyHints", () => {
  it("strips the teaching copy while preserving order, ids, titles, and pinning", () => {
    const stripped = withoutEmptyHints(SLOTS);
    expect(stripped.map((s) => s.id)).toEqual(SLOTS.map((s) => s.id));
    expect(stripped.map((s) => s.title)).toEqual(SLOTS.map((s) => s.title));
    expect(stripped[0].pinned).toBe(true);
    expect(stripped.every((s) => s.emptyHint === undefined)).toBe(true);
  });

  it("makes every empty slot omit itself", () => {
    expect(buildSections([], tierOf, withoutEmptyHints(SLOTS), byLabel)).toEqual([]);
  });

  it("leaves the caller's slots untouched", () => {
    withoutEmptyHints(SLOTS);
    expect(SLOTS[2].emptyHint).toBe("Nothing of your own yet.");
  });
});
