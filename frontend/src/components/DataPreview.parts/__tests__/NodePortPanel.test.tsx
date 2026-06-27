// NodePortPanel — branch parity with the former inline DataPreview port-panel
// logic: subworkflow provenance panel vs #1326 generic panel vs nothing.
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { BlockPortResponse, ResolvedSubworkflowPort } from "../../../types/api";
import { NodePortPanel } from "../NodePortPanel";

afterEach(() => cleanup());

function genericPort(name: string): BlockPortResponse {
  return {
    name,
    direction: "input",
    accepted_types: ["DataObject"],
    required: false,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

function exposed(name: string): ResolvedSubworkflowPort {
  return { name, accepted_types: ["Spectrum"], block_label: "Baseline Correction", port: "spectra" };
}

describe("NodePortPanel", () => {
  it("renders nothing when neither subworkflow nor generic ports exist", () => {
    const { container } = render(<NodePortPanel inputPorts={[]} outputPorts={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the subworkflow provenance panel when exposed ports are present", () => {
    render(
      <NodePortPanel
        subworkflowPorts={{ inputs: [exposed("d_bl.spectra")], outputs: [] }}
        inputPorts={[]}
        outputPorts={[]}
      />,
    );
    expect(screen.getByTestId("subworkflow-port-panel")).toBeTruthy();
    expect(screen.queryByTestId("port-info-panel")).toBeNull();
  });

  it("renders the generic #1326 panel when only schema ports are present", () => {
    render(<NodePortPanel inputPorts={[genericPort("image")]} outputPorts={[]} />);
    expect(screen.getByTestId("port-info-panel")).toBeTruthy();
    expect(screen.queryByTestId("subworkflow-port-panel")).toBeNull();
  });

  it("prefers the subworkflow panel when both are present (parity with old branch order)", () => {
    render(
      <NodePortPanel
        subworkflowPorts={{ inputs: [exposed("d_bl.spectra")], outputs: [] }}
        inputPorts={[genericPort("image")]}
        outputPorts={[]}
      />,
    );
    expect(screen.getByTestId("subworkflow-port-panel")).toBeTruthy();
    expect(screen.queryByTestId("port-info-panel")).toBeNull();
  });
});
