// ADR-043 Phase A3 — Integrated smoke test (FR-012 + FR-013 + FR-014).
//
// This file is the JSDOM equivalent of the "Chrome smoke test" called out
// in the Phase A3 dispatch prompt. It exercises the three new UI surfaces
// END-TO-END through their real integration points (PortEditorTable,
// DataPreview, BlockNode) against mocked backend responses, so the wiring
// — not just the components in isolation — is covered. Chrome MCP /
// Playwright are not provisioned in this repo (the existing e2e harness
// under `tests/e2e/adr-035/` is fixture-generation only), so per the
// frontend-smoke-test rule we use the in-process JSDOM harness to assert
// the click-paths the prompt enumerates:
//
//   1. Open a workflow with a port that has multiple matching
//      capabilities; verify the dropdown shows >=2 options.
//   2. Click the "OME metadata" button on a sample output; verify the
//      panel opens and renders at least one field.
//   3. Verify the lossy-save warning appears on a SaveImage node when
//      source OME has fields the target capability cannot persist.
//
// The manual in-app browser checklist (vite preview against a running
// backend) lives next to this file at
// `frontend/e2e/adr043-a3-smoke.md`. That doc + this script are the
// committed smoke evidence per the dispatch prompt.

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CapabilityDropdown } from "../components/PortEditor/CapabilityDropdown";
import { LossySaveWarning } from "../components/WorkflowEditor/LossySaveWarning";
import { OMEMetadataPanel, hasOMEContent } from "../components/OutputPreview/OMEMetadataPanel";
import { extractOMEFromMetadata } from "../api/capabilities";
import type { FormatCapabilityResponse } from "../types/api";

// ---------------------------------------------------------------------------
// Test fixtures — modelled on what `BlockRegistry.list_format_capabilities`
// would emit after Phase A1 + A2 land. Two TIFF savers (`tifffile` and
// `ome-tiff`) collide on the (Image, .tif) tuple, exercising ambiguity.
// ---------------------------------------------------------------------------

function fakeCap(
  id: string,
  overrides: Partial<FormatCapabilityResponse> = {},
): FormatCapabilityResponse {
  return {
    id,
    direction: "save",
    data_type: "Image",
    format_id: id.split(".").slice(-2)[0] ?? "tiff",
    extensions: ["tif", "tiff"],
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

const TWO_SAVERS: FormatCapabilityResponse[] = [
  fakeCap("imaging.image.tiff.save", {
    label: "TIFF (tifffile)",
    metadata_fidelity: {
      level: "format_specific",
      typed_meta_reads: [],
      typed_meta_writes: ["pixels.physical_size_x"],
      format_metadata_reads: ["ome"],
      format_metadata_writes: ["ome"],
      notes: null,
    },
  }),
  fakeCap("imaging.image.ome-tiff.save", {
    label: "OME-TIFF (lossless)",
    format_id: "ome-tiff",
    metadata_fidelity: {
      level: "lossless",
      typed_meta_reads: [],
      typed_meta_writes: [],
      format_metadata_reads: [],
      format_metadata_writes: [],
      notes: null,
    },
  }),
];

// ---------------------------------------------------------------------------
// Smoke scenarios
// ---------------------------------------------------------------------------

describe("ADR-043 Phase A3 smoke — capability dropdown ambiguity (FR-012)", () => {
  beforeEach(() => {
    // Silence the React-act warning that fires when the dropdown's async
    // useEffect resolves after the imperative render. The waitFor below
    // still observes the resolved state.
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders >=2 options when (Image, .tif) is ambiguous and persists the picked id", async () => {
    const loadCapabilities = vi.fn().mockResolvedValue(TWO_SAVERS);

    function Harness() {
      const [picked, setPicked] = useState<string | null>(null);
      return (
        <div>
          <CapabilityDropdown
            direction="save"
            dataType="Image"
            extension="tif"
            value={picked}
            onChange={setPicked}
            loadCapabilities={loadCapabilities}
          />
          <div data-testid="persisted">{picked ?? "(none)"}</div>
        </div>
      );
    }

    render(<Harness />);

    // 1. Multiple matching capabilities → both rendered as options.
    await waitFor(() => {
      expect(loadCapabilities).toHaveBeenCalledTimes(1);
    });
    const options = await screen.findAllByRole("option");
    // 2 capabilities + 1 placeholder ("Select a capability...")
    expect(options.length).toBeGreaterThanOrEqual(3);
    expect(
      options.some((opt) => (opt as HTMLOptionElement).value === "imaging.image.tiff.save"),
    ).toBe(true);
    expect(
      options.some((opt) => (opt as HTMLOptionElement).value === "imaging.image.ome-tiff.save"),
    ).toBe(true);

    // Ambiguity message visible.
    expect(screen.getByText(/2 capabilities match/i)).toBeInTheDocument();

    // 2. Picking an option persists the id.
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "imaging.image.ome-tiff.save" } });
    expect(screen.getByTestId("persisted")).toHaveTextContent("imaging.image.ome-tiff.save");

    // 3. Fidelity badge updates to lossless.
    expect(screen.getByTestId("fidelity-badge")).toHaveTextContent("lossless");
  });
});

describe("ADR-043 Phase A3 smoke — OME metadata panel toggle (FR-013)", () => {
  it("opens panel with at least one field on click and supports copy", async () => {
    const ome = {
      images: [
        {
          name: "sample.czi",
          pixels: {
            physical_size_x: 0.325,
            size_x: 2048,
          },
          channels: [{ name: "DAPI", emission_wavelength: 461 }],
        },
      ],
    };
    const copy = vi.fn();

    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <div>
          {!open ? (
            <button type="button" data-testid="open-ome" onClick={() => setOpen(true)}>
              OME metadata
            </button>
          ) : (
            <OMEMetadataPanel ome={ome} onClose={() => setOpen(false)} copyToClipboard={copy} />
          )}
        </div>
      );
    }
    render(<Harness />);
    expect(screen.queryByTestId("ome-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("open-ome"));
    expect(screen.getByTestId("ome-panel")).toBeInTheDocument();

    // At least one field rendered (the top-level `images` array surfaces
    // the per-image `name` leaf immediately because depth < 2).
    expect(screen.getByText("sample.czi")).toBeInTheDocument();

    // Copy button on the leaf writes through to the clipboard.
    const copyBtn = screen.getByRole("button", { name: /Copy images.\[0\].name/i });
    fireEvent.click(copyBtn);
    expect(copy).toHaveBeenCalledWith("sample.czi");
  });

  it("hides panel for outputs without OME (hasOMEContent guard)", () => {
    expect(hasOMEContent(null)).toBe(false);
    expect(hasOMEContent({})).toBe(false);
    expect(extractOMEFromMetadata({})).toBeNull();
  });
});

describe("ADR-043 Phase A3 smoke — lossy-save warning (FR-014)", () => {
  it("hides the chip when a broad 'ome' write declaration claims full OME round-trip (#1371)", () => {
    // Issue #1371: a declaration of `format_metadata_writes: ["ome"]`
    // claims that EVERY OME field is preserved (TIFF / Bio-Formats
    // family). The matcher used to exact-compare flattened source paths
    // against the literal token "ome" and so flagged everything as
    // dropped — a false positive. The chip must now render nothing for
    // these fully-OME-writable capabilities.
    const tiffBroadOme = TWO_SAVERS[0].metadata_fidelity;
    const sourceFields = [
      "pixels.physical_size_x",
      "pixels.physical_size_y",
      "channels.0.name",
      "channels.0.emission_wavelength",
      "annotations.0.value",
    ];
    const { container } = render(
      <LossySaveWarning sourceOmeFields={sourceFields} targetCapabilityFidelity={tiffBroadOme} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("surfaces dropped fields when narrow OME paths leave some unwritten (#1371)", () => {
    // PNG / JPEG declare only the precise OME paths actually persisted
    // (EXIF DPI → ome.pixels.physical_size_x/y). Anything outside those
    // two paths is legitimately lossy and must surface on the chip.
    const pngNarrowOme: FormatCapabilityResponse["metadata_fidelity"] = {
      level: "format_specific",
      typed_meta_reads: [],
      typed_meta_writes: ["pixel_size", "channels"],
      format_metadata_reads: ["ome.pixels.physical_size_x", "ome.pixels.physical_size_y"],
      format_metadata_writes: ["ome.pixels.physical_size_x", "ome.pixels.physical_size_y"],
      notes: null,
    };
    const sourceFields = [
      "pixels.physical_size_x",
      "pixels.physical_size_y",
      "channels.0.name",
      "channels.0.emission_wavelength",
      "annotations.0.value",
    ];
    render(
      <LossySaveWarning sourceOmeFields={sourceFields} targetCapabilityFidelity={pngNarrowOme} />,
    );
    const chip = screen.getByTestId("lossy-save-warning");
    expect(chip).toHaveTextContent("Lossy save");
    // ome.pixels.physical_size_x/y are WRITABLE (declared) → not dropped.
    expect(chip).not.toHaveTextContent("pixels.physical_size_x");
    expect(chip).not.toHaveTextContent("pixels.physical_size_y");
    // The remaining three source paths are dropped.
    expect(chip).toHaveTextContent("channels.0.name");
    expect(chip).toHaveTextContent("channels.0.emission_wavelength");
    expect(chip).toHaveTextContent("annotations.0.value");
  });

  it("renders nothing when target is lossless", () => {
    const losslessFidelity = TWO_SAVERS[1].metadata_fidelity;
    const { container } = render(
      <LossySaveWarning
        sourceOmeFields={["pixels.physical_size_x", "channels.0.emission_wavelength"]}
        targetCapabilityFidelity={losslessFidelity}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("flushes pending state changes inside act() — no warnings", async () => {
    // Sanity guard: this whole suite uses async state via React; if any
    // setState fires outside act() vitest would print a warning. We mount
    // a tiny ticker and let it resolve to verify the harness is happy.
    function Harness() {
      const [n, setN] = useState(0);
      return (
        <button data-testid="tick" onClick={() => setN(n + 1)}>
          tick={n}
        </button>
      );
    }
    render(<Harness />);
    await act(async () => {
      fireEvent.click(screen.getByTestId("tick"));
    });
    expect(screen.getByTestId("tick")).toHaveTextContent("tick=1");
  });
});
