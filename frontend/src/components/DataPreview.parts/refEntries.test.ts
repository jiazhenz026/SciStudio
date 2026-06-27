import { describe, expect, it } from "vitest";

import { extractRefEntries } from "./refEntries";

describe("extractRefEntries", () => {
  it("returns empty for non-object payload", () => {
    expect(extractRefEntries(null)).toEqual([]);
    expect(extractRefEntries(undefined)).toEqual([]);
    expect(extractRefEntries("not-an-object")).toEqual([]);
  });

  it("extracts a single entry from a top-level data_ref", () => {
    expect(extractRefEntries({ data_ref: "data-abc" })).toEqual([
      {
        id: "data-abc",
        ref: "data-abc",
        displayName: "data-abc",
        outputPort: undefined,
        target: { kind: "data_ref", ref: "data-abc" },
      },
    ]);
  });

  it("falls back to truncated ref when no metadata source available", () => {
    expect(extractRefEntries({ data_ref: "data-abcdefghij-tail" })).toEqual([
      expect.objectContaining({ ref: "data-abcdefghij-tail", displayName: "data-abcde" }),
    ]);
  });

  it("prefers metadata.framework.source over fallback", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { framework: { source: "/tmp/beads.tif" } },
    });
    expect(result).toEqual([
      expect.objectContaining({ ref: "data-xyz", displayName: "beads.tif" }),
    ]);
  });

  it("prefers user.display_name over framework.source (#1810 — disambiguates xlsx sheets)", () => {
    // Two sheets of one workbook share framework.source; the per-item
    // user.display_name is what keeps them distinct.
    const result = extractRefEntries({
      data_ref: "data-sheet2",
      metadata: {
        framework: { source: "/data/exp.xlsx" },
        user: { sheet_name: "beta", display_name: "exp.xlsx — beta" },
      },
    });
    expect(result).toEqual([
      expect.objectContaining({ ref: "data-sheet2", displayName: "exp.xlsx — beta" }),
    ]);
  });

  it("falls back to metadata.meta.source_file when framework absent", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { meta: { source_file: "/data/input.csv" } },
    });
    expect(result).toEqual([
      expect.objectContaining({ ref: "data-xyz", displayName: "input.csv" }),
    ]);
  });

  it("prefers source_file over package provenance framework source", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: {
        framework: { source: "scistudio-blocks-spectroscopy" },
        meta: { source_file: "/data/Urd_01.txt" },
      },
    });
    expect(result).toEqual([
      expect.objectContaining({ ref: "data-xyz", displayName: "Urd_01.txt" }),
    ]);
  });

  it("falls back to metadata.meta.file_path when source_file absent", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { meta: { file_path: "C:\\data\\sample.tif" } },
    });
    expect(result).toEqual([
      expect.objectContaining({ ref: "data-xyz", displayName: "sample.tif" }),
    ]);
  });

  it("handles collection kind as one collection-first preview entry", () => {
    const result = extractRefEntries({
      images: {
        kind: "collection",
        item_type: "DataFrame",
        items: [{ data_ref: "data-1", type_name: "DataFrame" }, { data_ref: "data-2" }],
      },
    });
    expect(result).toEqual([
      expect.objectContaining({
        id: "collection:images",
        ref: "collection:images",
        displayName: "images (2)",
        outputPort: "images",
        target: expect.objectContaining({
          kind: "collection_ref",
          ref: "collection:images",
          recorded_type: "DataFrame",
          collection_item_type: "DataFrame",
        }),
        initialQuery: expect.objectContaining({
          _collection_count: 2,
          _collection_item_type: "DataFrame",
          _collection_items: [
            { data_ref: "data-1", type_name: "DataFrame" },
            { data_ref: "data-2" },
          ],
        }),
      }),
    ]);
  });

  it("recurses into nested output dictionaries", () => {
    const result = extractRefEntries({
      output_a: { data_ref: "ref-a" },
      output_b: { data_ref: "ref-b" },
    });
    expect(result.map((e) => e.ref).sort()).toEqual(["ref-a", "ref-b"]);
  });
});
