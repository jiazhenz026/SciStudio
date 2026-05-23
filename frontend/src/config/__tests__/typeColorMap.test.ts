import { describe, it, expect } from "vitest";

import {
  hashTypeName,
  isAnyType,
  primaryTypeName,
  resolveRingColor,
  resolveTypeColor,
  subtypeRingColorMap,
  typeColorMap,
} from "../typeColorMap";

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
