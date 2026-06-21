// ADR-044 §3 — regression guard for the SubWorkflowNode routing contract.
//
// The backend's persisted/API block type for the authoring container is
// `subworkflow_block` (registry `type_name`), NOT the bare `subworkflow`.
// If the routing set drifts back to `subworkflow`, real SubWorkflowBlock nodes
// fall through to the generic BlockNode (no dynamic ports, no double-click, no
// broken UI). This test fails on that regression.

import { describe, expect, it } from "vitest";

import { SUBWORKFLOW_BLOCK_TYPES } from "../useFlowNodes";
import { buildSubWorkflowNode } from "../flowNodeBuilder";
import type { WorkflowNode } from "../../../types/api";
import type { SubWorkflowNodeData } from "../../../types/ui";

describe("ADR-044 subworkflow routing", () => {
  it("routes the real backend block type `subworkflow_block` to SubWorkflowNode", () => {
    expect(SUBWORKFLOW_BLOCK_TYPES.has("subworkflow_block")).toBe(true);
    expect(SUBWORKFLOW_BLOCK_TYPES.has("subworkflow_broken")).toBe(true);
    // The bare "subworkflow" is the ReactFlow node-type key, NOT a backend
    // block type, and must not be used for routing.
    expect(SUBWORKFLOW_BLOCK_TYPES.has("subworkflow")).toBe(false);
  });

  it("builds a SubWorkflowNode (type=subworkflow) from a subworkflow_block node with resolved ports", () => {
    const node = {
      id: "sw1",
      block_type: "subworkflow_block",
      config: { ref: { path: "subworkflows/child.yaml" } },
      resolved_ports: {
        inputs: [{ name: "raw_in", accepted_types: ["DataObject"] }],
        outputs: [{ name: "report", accepted_types: ["DataObject"] }],
        broken: false,
        ref_path: "subworkflows/child.yaml",
      },
    } as unknown as WorkflowNode;

    const built = buildSubWorkflowNode({
      node,
      position: { x: 0, y: 0 },
      label: "child",
      selectedNodeId: null,
      typeHierarchy: [],
      onDelete: () => {},
      onLocateFile: () => {},
    } as Parameters<typeof buildSubWorkflowNode>[0]);

    const data = built.data as SubWorkflowNodeData;
    expect(built.type).toBe("subworkflow");
    expect(data.blockType).toBe("subworkflow_block");
    expect(data.broken).toBe(false);
    expect(data.inputPorts.map((p) => p.name)).toEqual(["raw_in"]);
    expect(data.outputPorts.map((p) => p.name)).toEqual(["report"]);
  });

  // ADR-044 FR-011 / US5 — a freshly dropped subworkflow_block has NO ref, so it
  // must be treated as broken (refPath=null) and surface the "Choose subworkflow
  // file…" affordance. Without this it would render an empty pink node with no
  // way to attach a reference.
  it("treats a subworkflow_block with NO ref as broken so it offers the choose affordance", () => {
    const node = {
      id: "sw_new",
      block_type: "subworkflow_block",
      config: { params: {} },
    } as unknown as WorkflowNode;

    const built = buildSubWorkflowNode({
      node,
      position: { x: 0, y: 0 },
      label: "sw_new",
      selectedNodeId: null,
      typeHierarchy: [],
      onDelete: () => {},
      onLocateFile: () => {},
    } as Parameters<typeof buildSubWorkflowNode>[0]);

    const data = built.data as SubWorkflowNodeData;
    expect(data.broken).toBe(true);
    expect(data.refPath).toBeNull();
    expect(data.inputPorts).toEqual([]);
    expect(data.outputPorts).toEqual([]);
  });
});
