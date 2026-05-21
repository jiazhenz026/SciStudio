// ADR-043 — capabilities API client unit tests (FR-012).
//
// These tests focus on the pure helpers in `frontend/src/api/capabilities.ts`
// (`aggregateCapabilities`, `ancestorTypeNames`, `normalizeExtension`).
// They were added in response to the Codex auto-review on PR #1299
// flagging two filter bugs:
//   P1: aggregateCapabilities compared user-entered extensions ("tif")
//       against backend extensions (".tif") without normalising both sides.
//   P2: aggregateCapabilities required exact data_type equality, missing
//       capabilities declared on a supertype (e.g. `DataObject`).
//
// Both bugs are fixed by `normalizeBackendExtension` + `ancestorTypeNames`
// in the client; the tests below pin the fixes so the next refactor can
// not silently regress them.

import { describe, expect, it } from "vitest";

import {
  aggregateCapabilities,
  ancestorTypeNames,
  normalizeExtension,
} from "../api/capabilities";
import type { BlockListResponse, FormatCapabilityResponse, TypeHierarchyEntry } from "../types/api";

function fakeCap(
  id: string,
  overrides: Partial<FormatCapabilityResponse> = {},
): FormatCapabilityResponse {
  return {
    id,
    direction: "save",
    data_type: "Image",
    format_id: "tiff",
    extensions: [".tif", ".tiff"],
    label: id,
    block_type: "SaveImage",
    handler: "tifffile",
    is_default: false,
    priority: 0,
    roundtrip_group: null,
    metadata_fidelity: {
      level: "pixel_only",
      typed_meta_reads: [],
      typed_meta_writes: [],
      format_metadata_reads: [],
      format_metadata_writes: [],
      notes: null,
    },
    is_synthesized: false,
    migration_scaffold: false,
    ...overrides,
  };
}

function pkg(blockType: string, caps: FormatCapabilityResponse[]): BlockListResponse {
  return {
    blocks: [
      {
        name: blockType,
        type_name: blockType,
        base_category: "io",
        subcategory: "",
        description: "",
        version: "0.1.0",
        input_ports: [],
        output_ports: [],
        direction: "output",
        source: "package",
        package_name: "scistudio-blocks-imaging",
        variadic_inputs: false,
        variadic_outputs: false,
        format_capabilities: caps,
      },
    ],
  };
}

describe("normalizeExtension", () => {
  it("lowercases and strips leading dots", () => {
    expect(normalizeExtension(".TIF")).toBe("tif");
    expect(normalizeExtension("..TIFF")).toBe("tiff");
    expect(normalizeExtension("tif")).toBe("tif");
    expect(normalizeExtension("")).toBe("");
    expect(normalizeExtension(null)).toBe("");
    expect(normalizeExtension(undefined)).toBe("");
  });
});

describe("ancestorTypeNames", () => {
  const hier: TypeHierarchyEntry[] = [
    { name: "Image", base_type: "Tensor", description: "" },
    { name: "Tensor", base_type: "DataObject", description: "" },
    { name: "DataFrame", base_type: "DataObject", description: "" },
    { name: "DataObject", base_type: "", description: "" },
  ];

  it("includes the type itself, the universal DataObject base, and every supertype", () => {
    const got = ancestorTypeNames("Image", hier);
    expect(Array.from(got).sort()).toEqual(
      ["DataObject", "Image", "Tensor"].sort(),
    );
  });

  it("falls back to {typeName, DataObject} when no hierarchy is supplied", () => {
    const got = ancestorTypeNames("Image");
    expect(Array.from(got).sort()).toEqual(["DataObject", "Image"]);
  });

  it("returns just DataObject for an empty type name", () => {
    expect(Array.from(ancestorTypeNames(""))).toEqual(["DataObject"]);
  });
});

describe("aggregateCapabilities (Codex P1 — dot-prefixed backend extensions)", () => {
  it("matches dot-stripped user input against dot-prefixed backend extensions", () => {
    // Backend emits ".tif" / ".tiff"; user types "tif" in the port editor.
    const blocks = pkg("SaveImage", [fakeCap("imaging.image.tiff.save")]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
      extension: "tif",
    });
    expect(matches.map((c) => c.id)).toEqual(["imaging.image.tiff.save"]);
  });

  it("matches user-typed dot-prefixed extensions too (.tif → tif)", () => {
    const blocks = pkg("SaveImage", [fakeCap("imaging.image.tiff.save")]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
      extension: ".TIFF",
    });
    expect(matches.map((c) => c.id)).toEqual(["imaging.image.tiff.save"]);
  });

  it("excludes extension mismatches", () => {
    const blocks = pkg("SaveImage", [fakeCap("imaging.image.tiff.save")]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
      extension: "png",
    });
    expect(matches).toEqual([]);
  });
});

describe("aggregateCapabilities (Codex P2 — subtype compatibility)", () => {
  const hier: TypeHierarchyEntry[] = [
    { name: "Image", base_type: "Tensor", description: "" },
    { name: "Tensor", base_type: "DataObject", description: "" },
    { name: "DataObject", base_type: "", description: "" },
  ];

  it("matches a capability declared on a supertype when hierarchy is provided", () => {
    const blocks = pkg("SaveData", [
      fakeCap("core.dataobject.zarr.save", {
        data_type: "DataObject",
        extensions: [".zarr"],
      }),
    ]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
      extension: "zarr",
      typeHierarchy: hier,
    });
    expect(matches.map((c) => c.id)).toEqual(["core.dataobject.zarr.save"]);
  });

  it("matches DataObject-declared caps even without typeHierarchy (universal-base fallback)", () => {
    const blocks = pkg("SaveData", [
      fakeCap("core.dataobject.zarr.save", {
        data_type: "DataObject",
        extensions: [".zarr"],
      }),
    ]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
      extension: "zarr",
    });
    expect(matches.map((c) => c.id)).toEqual(["core.dataobject.zarr.save"]);
  });

  it("still rejects unrelated types (DataFrame request, Image-only cap)", () => {
    const blocks = pkg("SaveImage", [fakeCap("imaging.image.tiff.save")]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "DataFrame",
      extension: "tif",
      typeHierarchy: hier,
    });
    expect(matches).toEqual([]);
  });
});

describe("aggregateCapabilities (sort + dedup)", () => {
  it("sorts by (priority DESC, id ASC)", () => {
    const blocks = pkg("SaveImage", [
      fakeCap("a.lower", { priority: 0 }),
      fakeCap("z.lower", { priority: 0 }),
      fakeCap("middle", { priority: 10 }),
    ]);
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
    });
    expect(matches.map((c) => c.id)).toEqual(["middle", "a.lower", "z.lower"]);
  });

  it("deduplicates capabilities that appear in multiple blocks", () => {
    const shared = fakeCap("imaging.image.tiff.save");
    const blocks: BlockListResponse = {
      blocks: [
        { ...pkg("SaveImage", [shared]).blocks[0] },
        { ...pkg("AlternateSaveBlock", [shared]).blocks[0], type_name: "OtherSave" },
      ],
    };
    const matches = aggregateCapabilities(blocks, {
      direction: "save",
      dataType: "Image",
    });
    expect(matches).toHaveLength(1);
  });
});
