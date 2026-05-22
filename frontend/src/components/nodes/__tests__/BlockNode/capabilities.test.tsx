// Split out of BlockNode.test.tsx as part of the #1422 god-file refactor.
// Covers ADR-043 format-capabilities + fix #1307 (filter by core_type) +
// hidden ``direction`` field for IO blocks (ADR-028 Addendum 1 §B fix #2).

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";

import { makeCapability, makeSchema, openNativeDialogMock, renderNode } from "./test-utils";

afterEach(() => {
  cleanup();
  openNativeDialogMock.mockReset();
});

describe("BlockNode - ADR-043 format capabilities", () => {
  it("renders backend capability choices and persists capability_id", () => {
    const onUpdateConfig = vi.fn();
    renderNode({
      category: "io",
      onUpdateConfig,
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        format_capabilities: [
          makeCapability({ id: "imaging.image.tiff.load", label: "TIFF" }),
          makeCapability({
            id: "imaging.image.png.load",
            extensions: [".png"],
            format_id: "png",
            label: "PNG",
          }),
        ],
      }),
    });

    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "imaging.image.png.load" } });

    expect(onUpdateConfig).toHaveBeenCalledWith({
      capability_id: "imaging.image.png.load",
    });
  });

  it("surfaces backend-derived metadata loss warnings", () => {
    renderNode({
      category: "io",
      config: { capability_id: "imaging.image.png.save" },
      schema: makeSchema({
        base_category: "io",
        direction: "output",
        format_capabilities: [
          makeCapability({
            id: "imaging.image.png.save",
            direction: "save",
            extensions: [".png"],
            format_id: "png",
            label: "PNG",
            metadata_fidelity: {
              level: "pixel_only",
              typed_meta_reads: [],
              typed_meta_writes: [],
              format_metadata_reads: [],
              format_metadata_writes: [],
              notes: null,
            },
          }),
        ],
      }),
    });

    expect(screen.getByText(/typed metadata may not be written/i)).toBeInTheDocument();
  });
});

describe("BlockNode - Fix #1307 format dropdown filters by core_type", () => {
  const mixedCapabilities = [
    makeCapability({
      id: "core.dataframe.csv.save",
      direction: "save",
      data_type: "DataFrame",
      format_id: "csv",
      extensions: [".csv"],
      label: "CSV (DataFrame)",
    }),
    makeCapability({
      id: "core.dataframe.parquet.save",
      direction: "save",
      data_type: "DataFrame",
      format_id: "parquet",
      extensions: [".parquet"],
      label: "Parquet (DataFrame)",
    }),
    makeCapability({
      id: "core.series.csv.save",
      direction: "save",
      data_type: "Series",
      format_id: "csv",
      extensions: [".csv"],
      label: "CSV (Series)",
    }),
    makeCapability({
      id: "core.array.npy.save",
      direction: "save",
      data_type: "Array",
      format_id: "npy",
      extensions: [".npy"],
      label: "NumPy NPY",
    }),
  ];

  it("filters the dropdown to DataFrame capabilities when core_type=DataFrame", () => {
    renderNode({
      category: "io",
      config: { core_type: "DataFrame" },
      schema: makeSchema({
        base_category: "io",
        direction: "output",
        format_capabilities: mixedCapabilities,
      }),
    });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(select.options)
      .map((o) => o.value)
      .filter((v) => v);
    expect(optionValues).toEqual(["core.dataframe.csv.save", "core.dataframe.parquet.save"]);
  });

  it("filters the dropdown to Series capabilities when core_type=Series", () => {
    renderNode({
      category: "io",
      config: { core_type: "Series" },
      schema: makeSchema({
        base_category: "io",
        direction: "output",
        format_capabilities: mixedCapabilities,
      }),
    });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(select.options)
      .map((o) => o.value)
      .filter((v) => v);
    expect(optionValues).toEqual(["core.series.csv.save"]);
  });

  it("shows all capabilities when no core_type is set (no-op for non-IO blocks)", () => {
    renderNode({
      category: "io",
      config: {},
      schema: makeSchema({
        base_category: "io",
        direction: "output",
        format_capabilities: mixedCapabilities,
      }),
    });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(select.options)
      .map((o) => o.value)
      .filter((v) => v);
    expect(optionValues).toEqual([
      "core.dataframe.csv.save",
      "core.dataframe.parquet.save",
      "core.series.csv.save",
      "core.array.npy.save",
    ]);
  });
});

describe("BlockNode — hidden direction field (ADR-028 Addendum 1 §B fix #2)", () => {
  it("hides the direction config field for IO blocks", () => {
    renderNode({
      category: "io",
      schema: makeSchema({
        base_category: "io",
        direction: "input",
        config_schema: {
          type: "object",
          properties: {
            direction: {
              type: "string",
              enum: ["input", "output"],
              ui_priority: 0,
            },
            path: { type: "string", title: "Path", ui_priority: 1 },
          },
        },
      }),
    });
    // The direction <select> must NOT be rendered.
    expect(screen.queryByRole("combobox")).toBeNull();
    // The path field must still be rendered.
    expect(screen.getByText("Path")).toBeInTheDocument();
  });

  it("does NOT hide the direction field on non-IO blocks", () => {
    // A hypothetical process block that happens to have a 'direction' config
    // field. The hide-direction filter must scope to category=io, not match
    // the field name globally.
    renderNode({
      category: "process",
      schema: makeSchema({
        base_category: "process",
        config_schema: {
          type: "object",
          properties: {
            direction: {
              type: "string",
              enum: ["forward", "reverse"],
              title: "Direction",
              ui_priority: 0,
            },
          },
        },
      }),
    });
    expect(screen.getByText("Direction")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });
});
