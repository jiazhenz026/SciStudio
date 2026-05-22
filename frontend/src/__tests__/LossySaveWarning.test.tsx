// ADR-043 FR-014 — LossySaveWarning unit tests.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  LossySaveWarning,
  collectUpstreamOmeFields,
  flattenOmeFields,
} from "../components/WorkflowEditor/LossySaveWarning";
import { lossyOmeFields } from "../api/capabilities";
import type { MetadataFidelityResponse } from "../types/api";

function fidelity(
  level: MetadataFidelityResponse["level"],
  overrides: Partial<MetadataFidelityResponse> = {},
): MetadataFidelityResponse {
  return {
    level,
    typed_meta_reads: [],
    typed_meta_writes: [],
    format_metadata_reads: [],
    format_metadata_writes: [],
    notes: null,
    ...overrides,
  };
}

describe("lossyOmeFields", () => {
  it("returns [] for a lossless capability", () => {
    expect(
      lossyOmeFields(["pixels.physical_size_x", "channels.0.name"], fidelity("lossless")),
    ).toEqual([]);
  });

  it("returns every field for a pixel_only capability", () => {
    expect(
      lossyOmeFields(["pixels.physical_size_x", "channels.0.name"], fidelity("pixel_only")),
    ).toEqual(["pixels.physical_size_x", "channels.0.name"]);
  });

  it("considers fields writable when listed in EITHER write set", () => {
    const target = fidelity("format_specific", {
      format_metadata_writes: ["pixels.physical_size_x"],
      typed_meta_writes: ["channels.0.name"],
    });
    expect(
      lossyOmeFields(["pixels.physical_size_x", "channels.0.name", "annotations.0.value"], target),
    ).toEqual(["annotations.0.value"]);
  });

  // Issue #1371: broad declaration ``"ome"`` is a prefix covering every
  // OME field path; hierarchical declarations like
  // ``"ome.pixels.physical_size_x"`` strip the ``ome.`` prefix before
  // comparing against source paths (which arrive bare per
  // ``flattenOmeFields``).
  it("treats the broad token 'ome' as covering every OME source path (#1371)", () => {
    const target = fidelity("format_specific", {
      format_metadata_writes: ["ome"],
    });
    expect(
      lossyOmeFields(
        ["pixels.physical_size_x", "pixels.physical_size_y", "channels.0.emission_wavelength"],
        target,
      ),
    ).toEqual([]);
  });

  it("treats a hierarchical 'ome.pixels.physical_size_x' as covering the bare 'pixels.physical_size_x' (#1371)", () => {
    const target = fidelity("format_specific", {
      format_metadata_writes: ["ome.pixels.physical_size_x", "ome.pixels.physical_size_y"],
    });
    expect(
      lossyOmeFields(
        ["pixels.physical_size_x", "pixels.physical_size_y", "channels.0.emission_wavelength"],
        target,
      ),
    ).toEqual(["channels.0.emission_wavelength"]);
  });

  it("does not exact-match 'pixels.physical_size_x' source field against bare 'ome' declaration alone (#1371 false-positive guard)", () => {
    // Pre-#1371 logic exact-matched the source path against the
    // declaration set, so "pixels.physical_size_x" vs declaration ["ome"]
    // marked every source field as lossy. The fix treats "ome" as a
    // prefix covering everything; this case verifies that exact-match
    // semantics no longer leak through.
    const target = fidelity("format_specific", {
      format_metadata_writes: ["ome"],
      typed_meta_writes: [],
    });
    expect(lossyOmeFields(["pixels.physical_size_x"], target)).toEqual([]);
  });

  it("still flags fields when neither broad 'ome' nor matching hierarchical declaration covers them (#1371 false-negative guard)", () => {
    const target = fidelity("format_specific", {
      // PNG/JPEG narrow declaration.
      format_metadata_writes: ["ome.pixels.physical_size_x", "ome.pixels.physical_size_y"],
    });
    expect(
      lossyOmeFields(
        ["pixels.physical_size_x", "channels.0.emission_wavelength", "annotations.0.value"],
        target,
      ),
    ).toEqual(["channels.0.emission_wavelength", "annotations.0.value"]);
  });

  it("returns every source field for a pixel_only capability even when declarations are empty (#1371 zarr regression)", () => {
    // Zarr capability narrowed to pixel_only; the early return at the
    // top of the function MUST NOT cover this case because the level is
    // not lossless and declarations are empty — every source field is
    // legitimately lossy.
    expect(
      lossyOmeFields(["pixels.physical_size_x", "channels.0.name"], fidelity("pixel_only")),
    ).toEqual(["pixels.physical_size_x", "channels.0.name"]);
  });

  // Codex P1 (PR #1388 / #1371): runtime source paths produced by
  // ``collectUpstreamOmeFields`` carry the `images.<index>.` prefix
  // (the OME tree walk starts from { images: [...] }), while capability
  // declarations use the post-images structural path. The matcher
  // normalises the prefix away before comparing.
  it("normalises 'images.<index>.' prefix on source paths before matching narrow declarations (Codex P1 #1388)", () => {
    const target = fidelity("format_specific", {
      // PNG / JPEG narrow declaration (the post-#1371 form).
      format_metadata_writes: ["ome.pixels.physical_size_x", "ome.pixels.physical_size_y"],
    });
    // Real runtime source paths from collectUpstreamOmeFields walking
    // `{ images: [{ pixels: { physical_size_x: 0.5, physical_size_y: 0.5 } }] }`.
    expect(
      lossyOmeFields(
        [
          "images.0.pixels.physical_size_x",
          "images.0.pixels.physical_size_y",
          "images.0.channels.0.emission_wavelength",
          "images.0.annotations.0.value",
        ],
        target,
      ),
    ).toEqual([
      // Two physical_size paths are writable → not flagged.
      "images.0.channels.0.emission_wavelength",
      "images.0.annotations.0.value",
    ]);
  });

  it("also normalises 'images.<index>.' against a broad 'ome' declaration (Codex P1 #1388)", () => {
    // Defensive — broad declarations already early-return, but pin the
    // semantics so a future refactor that drops the early-return still
    // matches against normalised source paths.
    const target = fidelity("format_specific", {
      format_metadata_writes: ["ome"],
    });
    expect(
      lossyOmeFields(["images.0.pixels.physical_size_x", "images.1.channels.0.name"], target),
    ).toEqual([]);
  });

  it("does not double-strip a path with an inner 'images.<index>.' segment (Codex P1 #1388 defensive)", () => {
    // The regex anchors at the start, so `pixels.images.0.x` (an
    // unlikely-but-possible legitimately-nested path) stays intact and
    // matches the declaration verbatim.
    const target = fidelity("format_specific", {
      format_metadata_writes: ["pixels.images.0.x"],
    });
    expect(lossyOmeFields(["pixels.images.0.x"], target)).toEqual([]);
  });

  it("matches multi-digit and large indexes 'images.42.pixels.x' (Codex P1 #1388)", () => {
    const target = fidelity("format_specific", {
      format_metadata_writes: ["ome.pixels.physical_size_x"],
    });
    expect(lossyOmeFields(["images.42.pixels.physical_size_x"], target)).toEqual([]);
  });
});

describe("LossySaveWarning", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders nothing when no fields would be dropped", () => {
    const { container } = render(
      <LossySaveWarning sourceOmeFields={["x"]} targetCapabilityFidelity={fidelity("lossless")} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("lists the dropped fields when the target is pixel_only", () => {
    render(
      <LossySaveWarning
        sourceOmeFields={["pixels.physical_size_x", "pixels.physical_size_y", "channels.0.name"]}
        targetCapabilityFidelity={fidelity("pixel_only")}
      />,
    );
    const chip = screen.getByTestId("lossy-save-warning");
    expect(chip).toHaveTextContent("Lossy save");
    expect(chip).toHaveTextContent("pixels.physical_size_x");
    expect(chip).toHaveTextContent("channels.0.name");
  });

  it("truncates with +N more and expands on click", () => {
    const fields = ["a.b", "a.c", "a.d", "a.e", "a.f", "a.g"];
    render(
      <LossySaveWarning
        sourceOmeFields={fields}
        targetCapabilityFidelity={fidelity("pixel_only")}
        inlineLimit={3}
      />,
    );
    expect(screen.getByText("+3 more")).toBeInTheDocument();
    expect(screen.queryByText("a.g")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("+3 more"));
    expect(screen.getByText("a.g")).toBeInTheDocument();
    expect(screen.getByText("collapse")).toBeInTheDocument();
  });
});

describe("flattenOmeFields", () => {
  it("returns [] for null/undefined/empty", () => {
    expect(flattenOmeFields(null)).toEqual([]);
    expect(flattenOmeFields(undefined)).toEqual([]);
    expect(flattenOmeFields({})).toEqual([]);
  });

  it("flattens scalars to dotted paths", () => {
    expect(flattenOmeFields({ x: 1, y: "two" })).toEqual(["x", "y"]);
  });

  it("recurses into nested objects", () => {
    expect(
      flattenOmeFields({
        pixels: { physical_size_x: 0.5, physical_size_y: 0.5 },
      }),
    ).toEqual(["pixels.physical_size_x", "pixels.physical_size_y"]);
  });

  it("indexes arrays of records numerically (channels[0].name -> channels.0.name)", () => {
    expect(
      flattenOmeFields({
        channels: [
          { name: "DAPI", emission_wavelength: 461 },
          { name: "FITC", emission_wavelength: 519 },
        ],
      }),
    ).toEqual([
      "channels.0.name",
      "channels.0.emission_wavelength",
      "channels.1.name",
      "channels.1.emission_wavelength",
    ]);
  });

  it("indexes arrays of scalars by position", () => {
    expect(flattenOmeFields({ keys: ["a", "b"] })).toEqual(["keys.0", "keys.1"]);
  });

  // Fix #1313 bug 2: null/undefined values are NOT recorded as present.
  it("skips null/undefined scalar fields (treat as missing, not as dropped)", () => {
    expect(
      flattenOmeFields({
        physical_size_x: 0.5,
        physical_size_y: null,
        physical_size_z: undefined,
      }),
    ).toEqual(["physical_size_x"]);
  });

  it("skips null/undefined values inside nested objects", () => {
    expect(
      flattenOmeFields({
        pixels: {
          physical_size_x: 0.5,
          physical_size_y: null,
        },
      }),
    ).toEqual(["pixels.physical_size_x"]);
  });

  it("skips null/undefined elements inside arrays", () => {
    expect(
      flattenOmeFields({
        channels: [{ name: "DAPI" }, null, { name: "FITC" }],
      }),
    ).toEqual(["channels.0.name", "channels.2.name"]);
  });

  it("returns [] when every leaf is null (regression: model_dump(mode='json') with all-None Meta)", () => {
    expect(
      flattenOmeFields({
        physical_size_x: null,
        physical_size_y: null,
        pixels: { physical_size_x: null },
      }),
    ).toEqual([]);
  });
});

// Fix #1313 bug 1: walk Collection-shaped payloads (LoadImage etc.).
describe("collectUpstreamOmeFields", () => {
  it("returns [] for null/undefined/empty", () => {
    expect(collectUpstreamOmeFields(null)).toEqual([]);
    expect(collectUpstreamOmeFields(undefined)).toEqual([]);
    expect(collectUpstreamOmeFields({})).toEqual([]);
  });

  it("extracts OME from top-level value.metadata.ome", () => {
    const outputs = {
      out_port: {
        metadata: {
          ome: { images: [{ pixels: { physical_size_x: 0.5 } }] },
        },
      },
    };
    expect(collectUpstreamOmeFields(outputs).sort()).toEqual(["images.0.pixels.physical_size_x"]);
  });

  it("recurses into kind=collection items[] (regression: LoadImage payload shape)", () => {
    const outputs = {
      images: {
        kind: "collection",
        items: [
          {
            metadata: {
              ome: { images: [{ pixels: { physical_size_x: 0.5 } }] },
            },
          },
          {
            metadata: {
              ome: { images: [{ pixels: { size_x: 320 } }] },
            },
          },
        ],
      },
    };
    expect(collectUpstreamOmeFields(outputs).sort()).toEqual([
      "images.0.pixels.physical_size_x",
      "images.0.pixels.size_x",
    ]);
  });

  it("deduplicates fields when multiple items share the same OME paths", () => {
    const outputs = {
      images: {
        kind: "collection",
        items: [
          { metadata: { ome: { images: [{ pixels: { size_x: 320 } }] } } },
          { metadata: { ome: { images: [{ pixels: { size_x: 640 } }] } } },
        ],
      },
    };
    // Both items expose the same path "images.0.pixels.size_x" — single entry.
    expect(collectUpstreamOmeFields(outputs)).toEqual(["images.0.pixels.size_x"]);
  });

  it("recurses through nested wrappers like { output: { metadata: ... } }", () => {
    const outputs = {
      wrapper: {
        output: {
          metadata: {
            ome: { images: [{ pixels: { size_x: 320 } }] },
          },
        },
      },
    };
    expect(collectUpstreamOmeFields(outputs)).toEqual(["images.0.pixels.size_x"]);
  });

  it("returns [] when no metadata.ome is reachable anywhere", () => {
    const outputs = {
      images: {
        kind: "collection",
        items: [{ metadata: { source_file: "/path" } }, { metadata: null }],
      },
      other: { value: 42 },
    };
    expect(collectUpstreamOmeFields(outputs)).toEqual([]);
  });
});
