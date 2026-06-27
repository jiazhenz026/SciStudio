// ADR-044 — SubworkflowPortPanel: exposed-port → owning-block provenance.
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { ResolvedSubworkflowPort } from "../../../types/api";
import { SubworkflowPortPanel } from "../SubworkflowPortPanel";

afterEach(() => cleanup());

function port(overrides: Partial<ResolvedSubworkflowPort>): ResolvedSubworkflowPort {
  return { name: "d_bl.spectra", accepted_types: ["Spectrum"], ...overrides };
}

describe("SubworkflowPortPanel", () => {
  it("renders nothing when there are no exposed ports", () => {
    const { container } = render(<SubworkflowPortPanel inputs={[]} outputs={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("lists each port with its owning inner block label and port", () => {
    render(
      <SubworkflowPortPanel
        inputs={[
          port({
            name: "d_bl.spectra",
            block_label: "Baseline Correction",
            block_id: "d_bl",
            port: "spectra",
          }),
        ]}
        outputs={[
          port({
            name: "d_cen.features",
            accepted_types: ["DataFrame"],
            block_label: "Calculate Centroid",
            block_id: "d_cen",
            port: "features",
          }),
        ]}
      />,
    );
    // The exposed (handle) name is shown verbatim…
    expect(screen.getByText("d_bl.spectra")).toBeTruthy();
    expect(screen.getByText("d_cen.features")).toBeTruthy();
    // …alongside its owning block label + inner port + type.
    expect(screen.getByText(/Baseline Correction · spectra/)).toBeTruthy();
    expect(screen.getByText(/Calculate Centroid · features/)).toBeTruthy();
    expect(screen.getByText(/Spectrum/)).toBeTruthy();
    expect(screen.getByText(/DataFrame/)).toBeTruthy();
  });

  it("falls back to the block id when no display label is present", () => {
    render(
      <SubworkflowPortPanel
        inputs={[port({ name: "x.in", block_id: "x", port: "in", block_label: "" })]}
        outputs={[]}
      />,
    );
    expect(screen.getByText(/x · in/)).toBeTruthy();
  });

  it("renders only the section that has ports", () => {
    render(
      <SubworkflowPortPanel
        inputs={[port({ name: "a.in", block_label: "A", port: "in" })]}
        outputs={[]}
      />,
    );
    expect(screen.getByText("Input Ports")).toBeTruthy();
    expect(screen.queryByText("Output Ports")).toBeNull();
  });
});
