// ADR-043 FR-014 — LossySaveWarning unit tests.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  LossySaveWarning,
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
      lossyOmeFields(
        ["pixels.physical_size_x", "channels.0.name", "annotations.0.value"],
        target,
      ),
    ).toEqual(["annotations.0.value"]);
  });
});

describe("LossySaveWarning", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders nothing when no fields would be dropped", () => {
    const { container } = render(
      <LossySaveWarning
        sourceOmeFields={["x"]}
        targetCapabilityFidelity={fidelity("lossless")}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("lists the dropped fields when the target is pixel_only", () => {
    render(
      <LossySaveWarning
        sourceOmeFields={[
          "pixels.physical_size_x",
          "pixels.physical_size_y",
          "channels.0.name",
        ]}
        targetCapabilityFidelity={fidelity("pixel_only")}
      />,
    );
    const chip = screen.getByTestId("lossy-save-warning");
    expect(chip).toHaveTextContent("Lossy save");
    expect(chip).toHaveTextContent("pixels.physical_size_x");
    expect(chip).toHaveTextContent("channels.0.name");
  });

  it("truncates with +N more and expands on click", () => {
    const fields = [
      "a.b",
      "a.c",
      "a.d",
      "a.e",
      "a.f",
      "a.g",
    ];
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
    expect(flattenOmeFields({ keys: ["a", "b"] })).toEqual([
      "keys.0",
      "keys.1",
    ]);
  });
});
