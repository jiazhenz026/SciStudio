// ADR-044 §3 — SubWorkflowNode rendering tests.
//
// Covers the dispatch acceptance set:
//   - renders one input + one output handle per derived exposed port,
//   - React Flow handle ids EQUAL the exposed port names (locked contract
//     item 4 — colon-ref edge logic depends on this),
//   - renders the broken-reference placeholder (red, with the unresolved
//     ref_path) and a "locate file…" affordance, with NO port handles.

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";

import { SubWorkflowNode } from "../SubWorkflowNode";
import type { BlockPortResponse } from "../../../types/api";
import type { SubWorkflowNodeData } from "../../../types/ui";

afterEach(() => cleanup());

function makePort(name: string, direction: "input" | "output"): BlockPortResponse {
  return {
    name,
    direction,
    accepted_types: ["DataObject"],
    required: false,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

function renderSubWorkflowNode(dataOverrides: Partial<SubWorkflowNodeData> = {}, selected = false) {
  const baseData: SubWorkflowNodeData = {
    label: "my_subflow",
    blockType: "subworkflow_block",
    refPath: "subworkflows/my_subflow.swf.yaml",
    broken: false,
    inputPorts: [],
    outputPorts: [],
  };
  const props = {
    id: "sw1",
    type: "subworkflow",
    data: { ...baseData, ...dataOverrides },
    selected,
    isConnectable: false,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
  } as Parameters<typeof SubWorkflowNode>[0];

  return render(
    <ReactFlowProvider>
      <SubWorkflowNode {...props} />
    </ReactFlowProvider>,
  );
}

describe("SubWorkflowNode — healthy reference", () => {
  it("renders input + output handles derived from resolved exposed ports", () => {
    const { container } = renderSubWorkflowNode({
      inputPorts: [makePort("raw_in", "input")],
      outputPorts: [makePort("report", "output")],
    });

    // React Flow renders each Handle as a div with a `data-handleid` attribute.
    const handles = container.querySelectorAll<HTMLElement>("[data-handleid]");
    const handleIds = Array.from(handles).map((el) => el.getAttribute("data-handleid"));
    expect(handleIds).toContain("raw_in");
    expect(handleIds).toContain("report");
  });

  it("uses the exposed port name as the React Flow handle id (colon-ref contract)", () => {
    const { container } = renderSubWorkflowNode({
      inputPorts: [makePort("alpha", "input"), makePort("beta", "input")],
      outputPorts: [makePort("gamma", "output")],
    });

    for (const name of ["alpha", "beta", "gamma"]) {
      expect(container.querySelector(`[data-handleid="${name}"]`)).not.toBeNull();
    }
  });

  it("renders the subworkflow label and a category icon, not the broken banner", () => {
    const { container } = renderSubWorkflowNode({ label: "qc_pipeline" });
    expect(screen.getByTestId("subworkflow-node-label")).toHaveTextContent("qc_pipeline");
    expect(screen.queryByTestId("subworkflow-node-broken")).toBeNull();
    const body = container.querySelector('[data-testid="subworkflow-node-body"]');
    expect(body?.getAttribute("data-broken")).toBe("false");
    expect(body?.querySelector("svg")).not.toBeNull();
  });
});

describe("SubWorkflowNode — broken reference", () => {
  it("renders the broken placeholder with the unresolved ref_path and no handles", () => {
    const { container } = renderSubWorkflowNode({
      blockType: "subworkflow_broken",
      broken: true,
      refPath: "subworkflows/missing.swf.yaml",
      inputPorts: [],
      outputPorts: [],
    });

    expect(screen.getByTestId("subworkflow-node-broken")).toBeInTheDocument();
    expect(screen.getByTestId("subworkflow-node-broken-path")).toHaveTextContent(
      "subworkflows/missing.swf.yaml",
    );
    // Broken nodes expose zero ports per the locked contract.
    expect(container.querySelectorAll("[data-handleid]").length).toBe(0);

    const body = container.querySelector('[data-testid="subworkflow-node-body"]');
    expect(body?.getAttribute("data-broken")).toBe("true");
  });

  it("fires the locate-file affordance when the broken button is clicked", () => {
    const onLocateFile = vi.fn();
    renderSubWorkflowNode({
      blockType: "subworkflow_broken",
      broken: true,
      refPath: "subworkflows/missing.swf.yaml",
      onLocateFile,
    });

    fireEvent.click(screen.getByTestId("subworkflow-node-locate"));
    expect(onLocateFile).toHaveBeenCalledTimes(1);
  });

  it("labels the affordance 'Locate file…' when a (broken) ref path is present", () => {
    renderSubWorkflowNode({
      blockType: "subworkflow_broken",
      broken: true,
      refPath: "subworkflows/missing.swf.yaml",
      onLocateFile: vi.fn(),
    });
    expect(screen.getByTestId("subworkflow-node-locate")).toHaveTextContent("Locate file…");
  });
});

// ADR-044 FR-011 / US5 — a node with NO ref (freshly dropped) is broken with a
// null refPath; it must offer the "Choose subworkflow file…" affordance.
describe("SubWorkflowNode — no reference (fresh node)", () => {
  it("shows the 'Choose subworkflow file…' affordance and no ports when there is no ref", () => {
    const onLocateFile = vi.fn();
    const { container } = renderSubWorkflowNode({
      blockType: "subworkflow_block",
      broken: true,
      refPath: null,
      inputPorts: [],
      outputPorts: [],
      onLocateFile,
    });

    expect(screen.getByTestId("subworkflow-node-broken")).toHaveTextContent("No subworkflow file");
    const button = screen.getByTestId("subworkflow-node-locate");
    expect(button).toHaveTextContent("Choose subworkflow file…");
    expect(container.querySelectorAll("[data-handleid]").length).toBe(0);

    fireEvent.click(button);
    expect(onLocateFile).toHaveBeenCalledTimes(1);
  });
});
