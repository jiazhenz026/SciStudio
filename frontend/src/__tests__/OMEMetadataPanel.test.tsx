// ADR-043 FR-013 — OMEMetadataPanel unit tests.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  OMEMetadataPanel,
  hasOMEContent,
} from "../components/OutputPreview/OMEMetadataPanel";
import {
  extractOMEFromMetadata,
  getOMEMetadata,
} from "../api/capabilities";

describe("OMEMetadataPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders a placeholder when ome is null", () => {
    render(<OMEMetadataPanel ome={null} />);
    expect(screen.getByTestId("ome-panel-empty")).toBeInTheDocument();
    expect(screen.getByText(/No OME metadata/i)).toBeInTheDocument();
  });

  it("renders an image > pixels > physical_size_x tree (FR-013)", () => {
    const ome = {
      images: [
        {
          name: "img-0",
          pixels: {
            physical_size_x: 0.325,
            physical_size_y: 0.4,
            size_x: 2048,
            size_y: 1024,
          },
          channels: [
            { name: "DAPI", color: "#0000ff", emission_wavelength: 461 },
          ],
        },
      ],
    };
    render(<OMEMetadataPanel ome={ome} />);
    expect(screen.getByTestId("ome-panel")).toBeInTheDocument();
    // The top-level "images" key renders as a toggle button (open by default
    // for depth < 2). The first array element ("0") is at depth 1 so it is
    // open as well, surfacing the per-image scalar "name" leaf immediately.
    expect(screen.getAllByText(/images/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("img-0")).toBeInTheDocument();

    // Nested groups ("pixels", "channels") are collapsed by default at
    // depth 2 to keep the panel scannable. Expanding them surfaces the
    // spec-named leaves per FR-013.
    fireEvent.click(screen.getByRole("button", { name: /pixels/i }));
    expect(screen.getByText("0.325")).toBeInTheDocument();
    expect(screen.getByText("2048")).toBeInTheDocument();
  });

  it("copy button writes the leaf value to the injected clipboard", () => {
    const ome = {
      pixels: { physical_size_x: 0.325 },
    };
    const copy = vi.fn().mockResolvedValue(undefined);
    render(<OMEMetadataPanel ome={ome} copyToClipboard={copy} />);

    const copyButton = screen.getByRole("button", { name: /Copy pixels.physical_size_x/i });
    fireEvent.click(copyButton);
    expect(copy).toHaveBeenCalledWith("0.325");
  });

  it("renders the close affordance when onClose is provided", () => {
    const onClose = vi.fn();
    render(<OMEMetadataPanel ome={{ x: 1 }} onClose={onClose} />);
    const closeBtn = screen.getByRole("button", { name: /Close OME metadata/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it("treats an empty object as no-content", () => {
    render(<OMEMetadataPanel ome={{}} />);
    expect(screen.getByTestId("ome-panel-empty")).toBeInTheDocument();
  });
});

describe("hasOMEContent", () => {
  it("returns false for null / undefined / empty", () => {
    expect(hasOMEContent(null)).toBe(false);
    expect(hasOMEContent(undefined)).toBe(false);
    expect(hasOMEContent({})).toBe(false);
  });

  it("returns true when the tree has any key", () => {
    expect(hasOMEContent({ images: [] })).toBe(true);
  });
});

describe("extractOMEFromMetadata", () => {
  it("prefers metadata.meta.ome (canonical typed-meta path)", () => {
    const ome = { images: [{ name: "x" }] };
    const got = extractOMEFromMetadata({ meta: { ome } });
    expect(got).toBe(ome);
  });

  it("falls back to metadata.ome (flat alias)", () => {
    const ome = { images: [] };
    const got = extractOMEFromMetadata({ ome });
    expect(got).toBe(ome);
  });

  it("falls back to metadata.framework.ome (defensive)", () => {
    const ome = { x: 1 };
    const got = extractOMEFromMetadata({ framework: { ome } });
    expect(got).toBe(ome);
  });

  it("returns null when no path matches", () => {
    expect(extractOMEFromMetadata({})).toBeNull();
    expect(extractOMEFromMetadata(null)).toBeNull();
    expect(extractOMEFromMetadata(undefined)).toBeNull();
  });

  it("ignores non-object ome values", () => {
    expect(extractOMEFromMetadata({ ome: "not-a-tree" })).toBeNull();
    expect(extractOMEFromMetadata({ ome: 42 })).toBeNull();
  });
});

describe("getOMEMetadata (integration)", () => {
  it("delegates to api.getDataMetadata and extracts ome", async () => {
    // Import lazily so vi.mock plays nice with the relative path.
    const apiMod = await import("../lib/api");
    const ome = { images: [{ name: "loaded" }] };
    const spy = vi
      .spyOn(apiMod.api, "getDataMetadata")
      .mockResolvedValue({ ref: "obj-1", type_name: "Image", metadata: { meta: { ome } } });

    const got = await getOMEMetadata("obj-1");
    expect(spy).toHaveBeenCalledWith("obj-1");
    expect(got).toBe(ome);
  });
});
