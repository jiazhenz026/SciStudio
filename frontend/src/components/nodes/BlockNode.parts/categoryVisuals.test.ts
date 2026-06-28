// #1839 — per-block ui_color / ui_icon overrides on the canvas node visual,
// with safe fallback to the base-category default.

import { describe, expect, it } from "vitest";
import { FolderDown, FunctionSquare, Microscope, Split } from "lucide-react";

import { categoryVisuals, getCategoryVisual, resolveIconByName } from "./categoryVisuals";

describe("resolveIconByName (#1839)", () => {
  it("resolves a curated Lucide name", () => {
    expect(resolveIconByName("Microscope")).toBe(Microscope);
  });

  it("resolves case-insensitively", () => {
    expect(resolveIconByName("microscope")).toBe(Microscope);
  });

  it("returns undefined for an unknown name", () => {
    expect(resolveIconByName("NotARealLucideIcon")).toBeUndefined();
  });

  it("returns undefined for empty / nullish input", () => {
    expect(resolveIconByName("")).toBeUndefined();
    expect(resolveIconByName(null)).toBeUndefined();
    expect(resolveIconByName(undefined)).toBeUndefined();
  });
});

describe("resolveIconByName — full lucide set + kebab + rotation suffix (#1847)", () => {
  it("resolves ANY lucide name, not just the old curated subset", () => {
    // FolderDown was never in the curated set; it must resolve now.
    expect(resolveIconByName("FolderDown")).toBe(FolderDown);
  });

  it("resolves kebab-case names", () => {
    expect(resolveIconByName("folder-down")).toBe(FolderDown);
    expect(resolveIconByName("arrow-left-right")).toBeDefined();
  });

  it("strips a trailing :<deg> rotation suffix before lookup", () => {
    expect(resolveIconByName("split:90")).toBe(Split);
    expect(resolveIconByName("folder-down:270")).toBe(FolderDown);
  });
});

describe("getCategoryVisual — icon rotation (#1847)", () => {
  it("returns the raw icon (reference-equal) when no rotation is requested", () => {
    expect(getCategoryVisual("process", null, "Split").Icon).toBe(Split);
  });

  it("wraps the icon (not reference-equal) when a rotation is requested", () => {
    const v = getCategoryVisual("process", null, "split:90");
    expect(v.Icon).not.toBe(Split);
    expect(v.Icon).toBeDefined();
  });

  it("falls back to the category icon for an unknown name even with a suffix", () => {
    expect(getCategoryVisual("process", null, "totally-unknown:90").Icon).toBe(FunctionSquare);
  });
});

describe("getCategoryVisual with no overrides (#1698 behaviour preserved)", () => {
  it("returns the category default unchanged", () => {
    expect(getCategoryVisual("process")).toEqual(categoryVisuals.process);
  });

  it("falls back to custom for an unknown category", () => {
    expect(getCategoryVisual("nope")).toEqual(categoryVisuals.custom);
  });
});

describe("getCategoryVisual with overrides (#1839)", () => {
  it("applies a block-declared icon over the category icon", () => {
    const v = getCategoryVisual("process", null, "Microscope");
    expect(v.Icon).toBe(Microscope);
    // Colours untouched when only the icon is overridden.
    expect(v.bg).toBe(categoryVisuals.process.bg);
  });

  it("keeps the category icon when the declared icon name is unknown", () => {
    const v = getCategoryVisual("process", null, "TotallyUnknownIcon");
    expect(v.Icon).toBe(FunctionSquare);
  });

  it("applies a block-declared color and derives deeper fg/border", () => {
    const v = getCategoryVisual("process", "#ff5733");
    expect(v.bg).toBe("#ff5733");
    // fg / border are darker shades derived from the fill, not the category's.
    expect(v.fg).not.toBe(categoryVisuals.process.fg);
    expect(v.fg).toMatch(/^#[0-9a-f]{6}$/);
    expect(v.border).toMatch(/^#[0-9a-f]{6}$/);
    // Icon unchanged when only the color is overridden.
    expect(v.Icon).toBe(FunctionSquare);
  });

  it("expands a 3-digit hex and derives shades", () => {
    const v = getCategoryVisual("process", "#f53");
    expect(v.bg).toBe("#f53");
    expect(v.fg).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("ignores an invalid hex and keeps the category colours", () => {
    const v = getCategoryVisual("process", "not-a-color");
    expect(v.bg).toBe(categoryVisuals.process.bg);
    expect(v.fg).toBe(categoryVisuals.process.fg);
    expect(v.border).toBe(categoryVisuals.process.border);
  });

  it("combines a color and an icon override together", () => {
    const v = getCategoryVisual("io", "#123456", "Microscope");
    expect(v.bg).toBe("#123456");
    expect(v.Icon).toBe(Microscope);
  });
});
