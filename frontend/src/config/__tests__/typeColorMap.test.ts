import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import {
  buildDeclaredTypeColors,
  hashTypeName,
  isAnyType,
  normalizeDeclaredColor,
  primaryTypeName,
  resetDeclaredColorWarnings,
  resolveCoreBaseType,
  resolveRingColor,
  resolveTypeColor,
  subtypeRingColorMap,
  typeColorMap,
} from "../typeColorMap";
import type { TypeHierarchyEntry } from "../../types/api";

// Regression test for #1487: DataObject was rendered with #e5e7eb
// (gray-200) which is unreadable on the white canvas. The fallback used
// by resolveTypeColor() also returns this entry, so a too-light color
// silently degrades every port that does not resolve to a more
// specific type. Lock the new dark fallback in.
describe("typeColorMap.DataObject", () => {
  it("is no longer the unreadable #e5e7eb", () => {
    expect(typeColorMap.DataObject.toLowerCase()).not.toBe("#e5e7eb");
  });

  it("is dark enough to render on white (luminance < 0.5)", () => {
    const hex = typeColorMap.DataObject;
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    // Rec. 709 relative luminance — a value < 0.5 reads as a darker
    // mid-gray or below on a white background.
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    expect(luminance).toBeLessThan(0.5);
  });
});

describe("resolveTypeColor", () => {
  it("returns the typeColorMap entry for a known base type", () => {
    expect(resolveTypeColor(["Array"])).toBe(typeColorMap.Array);
  });

  it("falls back to the base type via typeHierarchy", () => {
    expect(
      resolveTypeColor(["MyMask"], [{ name: "MyMask", base_type: "Mask", description: "" }]),
    ).toBe(typeColorMap.Mask);
  });

  it("returns the (now dark) DataObject fallback when typeNames is empty", () => {
    expect(resolveTypeColor([])).toBe(typeColorMap.DataObject);
  });

  it("uses the hash palette for unknown types", () => {
    // Deterministic: the same name resolves to the same color across calls.
    expect(resolveTypeColor(["SomePluginType"])).toBe(resolveTypeColor(["SomePluginType"]));
  });
});

describe("resolveRingColor", () => {
  it("returns the explicit ring color for a known subtype", () => {
    expect(resolveRingColor(["Image"])).toBe(subtypeRingColorMap.Image);
  });

  it("ignores type_hierarchy.ui_ring_color — it is not a colour transport (FR-066)", () => {
    // The field was declared and never populated (spec §2.8); ADR-053 leaves
    // it dead rather than reviving it, so declared ring colour travels only on
    // the types listing. A payload that somehow carried one must not become a
    // second supply point.
    expect(
      resolveRingColor(
        ["MyType"],
        [
          {
            name: "MyType",
            base_type: "DataObject",
            description: "",
            ui_ring_color: "#123456",
          },
        ],
      ),
    ).not.toBe("#123456");
  });

  it("returns undefined for base types not in the manual maps", () => {
    expect(resolveRingColor(["Array"])).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// ADR-053 §7.1 — declared type colour (FR-050 – FR-052, FR-066, FR-067)
// ---------------------------------------------------------------------------

describe("normalizeDeclaredColor + buildDeclaredTypeColors (FR-050, FR-052)", () => {
  beforeEach(() => {
    resetDeclaredColorWarnings();
  });

  it("accepts every CSS hex form the backend can emit and lowercases it", () => {
    expect(normalizeDeclaredColor("#4F8EF7", "T.ui_color")).toBe("#4f8ef7");
    expect(normalizeDeclaredColor("#4f8ef780", "T.ui_color")).toBe("#4f8ef780");
  });

  it("expands short hex to long so no consumer has to parse two shapes", () => {
    expect(normalizeDeclaredColor("#abc", "T.ui_color")).toBe("#aabbcc");
    expect(normalizeDeclaredColor("#abcd", "T.ui_color")).toBe("#aabbccdd");
  });

  it("treats null/undefined as 'declared nothing', without warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(normalizeDeclaredColor(null, "T.ui_color")).toBeUndefined();
    expect(normalizeDeclaredColor(undefined, "T.ui_color")).toBeUndefined();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("warns once and drops an unusable value (FR-052)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(normalizeDeclaredColor("not-a-colour", "Bad.ui_color")).toBeUndefined();
    expect(normalizeDeclaredColor("not-a-colour", "Bad.ui_color")).toBeUndefined();
    // Ports re-resolve colour on every render; one typo must not flood the
    // console.
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("omits types that declared nothing usable from the lookup", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const declared = buildDeclaredTypeColors([
      { name: "Plain", ui_color: null, ui_ring_color: null },
      { name: "Broken", ui_color: "#zzz", ui_ring_color: null },
      { name: "Declared", ui_color: "#4f8ef7", ui_ring_color: null },
    ]);
    expect(declared.has("Plain")).toBe(false);
    expect(declared.has("Broken")).toBe(false);
    expect(declared.get("Declared")).toEqual({ fill: "#4f8ef7" });
    warn.mockRestore();
  });
});

describe("colour precedence (FR-051)", () => {
  beforeEach(() => {
    resetDeclaredColorWarnings();
  });

  const HIERARCHY: TypeHierarchyEntry[] = [
    { name: "Array", base_type: "DataObject", description: "" },
    { name: "MyMask", base_type: "Mask", description: "" },
  ];

  it("a declared colour beats the typeColorMap entry", () => {
    const declared = buildDeclaredTypeColors([{ name: "Array", ui_color: "#4f8ef7" }]);
    expect(resolveTypeColor(["Array"], HIERARCHY, declared)).toBe("#4f8ef7");
    expect(resolveTypeColor(["Array"], HIERARCHY, declared)).not.toBe(typeColorMap.Array);
  });

  it("a declared colour beats the hash fallback", () => {
    const declared = buildDeclaredTypeColors([{ name: "Plugin", ui_color: "#123456" }]);
    expect(resolveTypeColor(["Plugin"], HIERARCHY, declared)).toBe("#123456");
    expect(resolveTypeColor(["Plugin"], HIERARCHY, declared)).not.toBe(
      resolveTypeColor(["Plugin"], HIERARCHY),
    );
  });

  it("typeColorMap still beats the hash fallback", () => {
    const declared = buildDeclaredTypeColors([{ name: "Other", ui_color: "#123456" }]);
    expect(resolveTypeColor(["Array"], HIERARCHY, declared)).toBe(typeColorMap.Array);
  });

  it("an undeclared type is byte-identical to today, declared map or not", () => {
    // The snapshot is the pre-ADR-053 answer for a core base, a subtype
    // resolved through the hierarchy, an unknown plugin type, and the empty
    // port. FR-051: a declared colour wins; everything else is untouched.
    const declared = buildDeclaredTypeColors([{ name: "Elsewhere", ui_color: "#4f8ef7" }]);
    for (const names of [["Array"], ["Image"], ["MyMask"], ["SomePluginType"], []]) {
      expect(resolveTypeColor(names, HIERARCHY, declared)).toBe(resolveTypeColor(names, HIERARCHY));
      expect(resolveTypeColor(names, HIERARCHY, new Map())).toBe(
        resolveTypeColor(names, HIERARCHY),
      );
      expect(resolveRingColor(names, HIERARCHY, declared)).toBe(resolveRingColor(names, HIERARCHY));
    }
  });

  it("resolves identically with the declared map absent — the FR-067 window", () => {
    // `undefined` (listing in flight) and an arrived-but-empty map must give
    // the same answer as each other and as the pre-ADR-053 resolution, which
    // is what makes the loading window invisible.
    expect(resolveTypeColor(["Image"], HIERARCHY, undefined)).toBe(
      resolveTypeColor(["Image"], HIERARCHY, new Map()),
    );
  });

  it("an unusable declaration falls through to the next level (FR-052)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const declared = buildDeclaredTypeColors([{ name: "Array", ui_color: "rgb(1,2,3)" }]);
    expect(resolveTypeColor(["Array"], HIERARCHY, declared)).toBe(typeColorMap.Array);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("declared ring colour (FR-041, FR-051)", () => {
  beforeEach(() => {
    resetDeclaredColorWarnings();
  });

  it("uses the declared ring ahead of the manual subtype map", () => {
    const declared = buildDeclaredTypeColors([{ name: "Image", ui_ring_color: "#0a0b0c" }]);
    expect(resolveRingColor(["Image"], undefined, declared)).toBe("#0a0b0c");
  });

  it("derives a ring from the declared fill when only a fill was declared", () => {
    // A declaring type still gets the solid-plus-ring treatment (FR-041), and
    // gets it from its own colour rather than from a hash entry it no longer
    // uses.
    const declared = buildDeclaredTypeColors([{ name: "Plugin", ui_color: "#4f8ef7" }]);
    const ring = resolveRingColor(["Plugin"], undefined, declared);
    expect(ring).toBe("#3763ad");
    expect(ring).not.toBe(resolveRingColor(["Plugin"]));
  });

  it("drops the alpha channel when darkening an 8-digit declared fill", () => {
    const declared = buildDeclaredTypeColors([{ name: "Plugin", ui_color: "#4f8ef780" }]);
    expect(resolveRingColor(["Plugin"], undefined, declared)).toBe("#3763ad");
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("primaryTypeName + isAnyType", () => {
  it("returns 'Any' and reports isAnyType for empty typeNames", () => {
    expect(primaryTypeName([])).toBe("Any");
    expect(isAnyType([])).toBe(true);
  });

  it("returns the first name for a populated list", () => {
    expect(primaryTypeName(["Image", "Array"])).toBe("Image");
    expect(isAnyType(["Image"])).toBe(false);
  });
});

describe("hashTypeName", () => {
  it("returns the same hash for the same input (deterministic)", () => {
    expect(hashTypeName("Foo")).toBe(hashTypeName("Foo"));
  });

  it("is non-negative", () => {
    expect(hashTypeName("Foo")).toBeGreaterThanOrEqual(0);
  });
});

// #1840: annotate a specialized type with its fundamental core base — the
// highest ancestor above the universal DataObject root.
describe("resolveCoreBaseType", () => {
  const HIERARCHY: TypeHierarchyEntry[] = [
    { name: "DataObject", base_type: "", description: "" },
    { name: "Array", base_type: "DataObject", description: "" },
    { name: "Image", base_type: "Array", description: "" },
    { name: "SRSImage", base_type: "Image", description: "" },
    { name: "DataFrame", base_type: "DataObject", description: "" },
    { name: "SpectralDataset", base_type: "DataFrame", description: "" },
  ];

  it("walks a multi-level chain to the core base (SRSImage → Array)", () => {
    expect(resolveCoreBaseType("SRSImage", HIERARCHY)).toBe("Array");
  });

  it("resolves a one-level chain (SpectralDataset → DataFrame)", () => {
    expect(resolveCoreBaseType("SpectralDataset", HIERARCHY)).toBe("DataFrame");
  });

  it("resolves an intermediate type to its core base (Image → Array)", () => {
    expect(resolveCoreBaseType("Image", HIERARCHY)).toBe("Array");
  });

  it("returns null when the type already IS a core base (no Array (Array))", () => {
    expect(resolveCoreBaseType("Array", HIERARCHY)).toBeNull();
    expect(resolveCoreBaseType("DataFrame", HIERARCHY)).toBeNull();
  });

  it("returns null for DataObject itself", () => {
    expect(resolveCoreBaseType("DataObject", HIERARCHY)).toBeNull();
  });

  it("returns null for an unknown type or missing hierarchy", () => {
    expect(resolveCoreBaseType("Mystery", HIERARCHY)).toBeNull();
    expect(resolveCoreBaseType("SRSImage", undefined)).toBeNull();
  });

  it("returns null and does not hang on a cycle", () => {
    const cyclic: TypeHierarchyEntry[] = [
      { name: "A", base_type: "B", description: "" },
      { name: "B", base_type: "A", description: "" },
    ];
    expect(resolveCoreBaseType("A", cyclic)).toBeNull();
  });
});
