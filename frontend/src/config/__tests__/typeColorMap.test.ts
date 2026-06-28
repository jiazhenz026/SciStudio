import { describe, it, expect } from "vitest";

import {
  hashTypeName,
  isAnyType,
  primaryTypeName,
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

  it("returns the backend-supplied ui_ring_color when present", () => {
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
    ).toBe("#123456");
  });

  it("returns undefined for base types not in the manual maps", () => {
    expect(resolveRingColor(["Array"])).toBeUndefined();
  });
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
