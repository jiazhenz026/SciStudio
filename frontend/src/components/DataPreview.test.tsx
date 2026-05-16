import { render, waitFor, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { DataPreview } from "./DataPreview";

describe("DataPreview", () => {
  it("requests previews lazily for selected output refs", async () => {
    const onLoadPreview = vi.fn(async () => {});

    render(
      <DataPreview
        blockOutputs={{
          "node-1": {
            output: {
              data_ref: "data-123",
            },
          },
        }}
        onLoadPreview={onLoadPreview}
        previewCache={{}}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="Process Block"
      />,
    );

    await waitFor(() => {
      expect(onLoadPreview).toHaveBeenCalledWith("data-123");
    });
  });

  it("renders image preview with zoom controls and LUT swatches", () => {
    render(
      <DataPreview
        blockOutputs={{
          "node-1": {
            output: { data_ref: "img-ref" },
          },
        }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "img-ref": {
            preview: {
              kind: "image",
              src: "data:image/png;base64,abc",
              shape: [100, 200, 3],
            },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="Image Block"
      />,
    );

    // Zoom controls
    expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();

    // Min/Max display range sliders
    expect(screen.getByRole("slider", { name: /display minimum/i })).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /display maximum/i })).toBeInTheDocument();

    // LUT gradient swatches (at least gray and fire)
    expect(screen.getByRole("button", { name: /LUT gray/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /LUT fire/i })).toBeInTheDocument();

    // Info badge showing shape and zoom
    const badge = screen.getByTestId("image-info-badge");
    expect(badge).toHaveTextContent(/100 × 200 × 3/);
    expect(badge).toHaveTextContent(/100%/);
  });

  it("zoom in button increases scale display", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "img-ref" } } }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "img-ref": {
            preview: { kind: "image", src: "data:image/png;base64,abc" },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="Image Block"
      />,
    );

    // Default zoom is 100% (shown in controls text)
    const zoomTexts = screen.getAllByText("100%");
    expect(zoomTexts.length).toBeGreaterThanOrEqual(1);

    // Click zoom in
    fireEvent.click(screen.getByRole("button", { name: /zoom in/i }));

    // Scale should have increased (125% in controls)
    const updatedTexts = screen.getAllByText("125%");
    expect(updatedTexts.length).toBeGreaterThanOrEqual(1);
  });

  it("renders table preview with compact formatting and row/column count", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "tbl-ref" } } }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "tbl-ref": {
            preview: {
              kind: "table",
              columns: ["A", "B", "C"],
              rows: [
                { A: 1, B: 2.12345, C: 3 },
                { A: 4, B: 5, C: 6.789012 },
              ],
            },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="Table Block"
      />,
    );

    // Row/column count
    expect(screen.getByText(/2 rows × 3 columns/)).toBeInTheDocument();

    // Column headers
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();

    // Integer cells remain integers
    expect(screen.getByText("1")).toBeInTheDocument();

    // Floating-point cells formatted to 4 decimals
    expect(screen.getByText("2.1235")).toBeInTheDocument();
    expect(screen.getByText("6.7890")).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // #898 — pill labels show source filename
  // ---------------------------------------------------------------------

  it("pill label shows source filename when framework.source is set (#898)", () => {
    render(
      <DataPreview
        blockOutputs={{
          "load-1": {
            images: {
              kind: "collection",
              items: [
                {
                  data_ref: "data-abcdef",
                  metadata: {
                    framework: { source: "C:/data/beads.tif" },
                  },
                },
                {
                  data_ref: "data-123456",
                  metadata: {
                    meta: { source_file: "/home/u/sample_002.tif" },
                  },
                },
                {
                  data_ref: "data-xyz789",
                  // No source / source_file / file_path → fall back to slice(0,10).
                  metadata: { framework: { source: "" } },
                },
              ],
            },
          },
        }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{}}
        previewLoading={{}}
        selectedNodeId="load-1"
        selectedNodeLabel="Load Image"
      />,
    );

    expect(screen.getByRole("button", { name: "beads.tif" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "sample_002.tif" })).toBeInTheDocument();
    // Fallback when no metadata source: truncated ref (today's behavior).
    expect(screen.getByRole("button", { name: "data-xyz78" })).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // #899 — single-slider 3D viewer
  // ---------------------------------------------------------------------

  it("renders slice slider when slice_axis_size > 1 (#899)", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "img-ref" } } }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "img-ref": {
            preview: {
              kind: "image",
              src: "data:image/png;base64,abc",
              shape: [643, 1285, 3],
              axes: ["y", "x", "c"],
              slice_axis_name: "c",
              slice_axis_size: 3,
              slice_index: 0,
            },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="plot_cal"
      />,
    );

    const slider = screen.getByTestId("image-slice-slider") as HTMLInputElement;
    expect(slider).toBeInTheDocument();
    expect(slider.max).toBe("2");
    expect(slider.value).toBe("0");
    expect(screen.getByTestId("image-slice-slider-row")).toHaveTextContent(/c \(3\)/);
    expect(screen.getByTestId("image-slice-slider-row")).toHaveTextContent(/1\/3/);
  });

  it("does NOT render slice slider for ndim=2 image (#899)", () => {
    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "img-ref" } } }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "img-ref": {
            preview: {
              kind: "image",
              src: "data:image/png;base64,abc",
              shape: [256, 256],
              axes: ["y", "x"],
              slice_axis_name: null,
              slice_axis_size: null,
              slice_index: null,
            },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="2D Image"
      />,
    );

    expect(screen.queryByTestId("image-slice-slider")).toBeNull();
  });

  it("shows truncation label when 100+ rows", () => {
    const manyRows = Array.from({ length: 100 }, (_, i) => ({ A: i, B: i * 2 }));

    render(
      <DataPreview
        blockOutputs={{ "node-1": { output: { data_ref: "tbl-ref" } } }}
        onLoadPreview={vi.fn(async () => {})}
        previewCache={{
          "tbl-ref": {
            preview: {
              kind: "table",
              columns: ["A", "B"],
              rows: manyRows,
              row_count: 100,
            },
          } as never,
        }}
        previewLoading={{}}
        selectedNodeId="node-1"
        selectedNodeLabel="Table Block"
      />,
    );

    // Should indicate truncation
    expect(screen.getByText(/Showing 100 of 100\+/)).toBeInTheDocument();
  });
});
