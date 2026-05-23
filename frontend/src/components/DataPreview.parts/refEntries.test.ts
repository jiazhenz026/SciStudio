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
      { ref: "data-abc", displayName: "data-abc" },
    ]);
  });

  it("falls back to truncated ref when no metadata source available", () => {
    expect(extractRefEntries({ data_ref: "data-abcdefghij-tail" })).toEqual([
      { ref: "data-abcdefghij-tail", displayName: "data-abcde" },
    ]);
  });

  it("prefers metadata.framework.source over fallback", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { framework: { source: "/tmp/beads.tif" } },
    });
    expect(result).toEqual([{ ref: "data-xyz", displayName: "beads.tif" }]);
  });

  it("falls back to metadata.meta.source_file when framework absent", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { meta: { source_file: "/data/input.csv" } },
    });
    expect(result).toEqual([{ ref: "data-xyz", displayName: "input.csv" }]);
  });

  it("falls back to metadata.meta.file_path when source_file absent", () => {
    const result = extractRefEntries({
      data_ref: "data-xyz",
      metadata: { meta: { file_path: "C:\\data\\sample.tif" } },
    });
    expect(result).toEqual([{ ref: "data-xyz", displayName: "sample.tif" }]);
  });

  it("handles collection kind by flattening its items", () => {
    const result = extractRefEntries({
      kind: "collection",
      items: [{ data_ref: "data-1" }, { data_ref: "data-2" }],
    });
    expect(result).toEqual([
      { ref: "data-1", displayName: "data-1" },
      { ref: "data-2", displayName: "data-2" },
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
