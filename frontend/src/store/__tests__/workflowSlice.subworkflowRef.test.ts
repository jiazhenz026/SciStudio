// ADR-044 FR-011 (US5) + FR-004 — store actions for repointing a subworkflow
// node's reference and refreshing its resolved-port surface.
//
//   - setNodeRef writes config.ref.path at the TOP level (NOT config.params,
//     where updateNodeConfig merges) and marks the workflow dirty.
//   - setNodeResolvedPorts sets the response-only resolved_ports surface in
//     place and does NOT mark dirty (it is never persisted).

import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ResolvedSubworkflowPorts, WorkflowNode } from "../../types/api";
import { useAppStore } from "../index";

vi.mock("../../lib/api/ai", () => ({
  postActiveWorkflowContext: vi.fn().mockResolvedValue(undefined),
}));

function subworkflowNode(): WorkflowNode {
  return {
    id: "sw1",
    block_type: "subworkflow_block",
    config: { params: {} },
  };
}

function resetWithNode(node: WorkflowNode): void {
  useAppStore.setState({
    workflowNodes: [node],
    workflowEdges: [],
    workflowDirty: false,
    workflowBaseVersion: null,
    workflowPendingVersion: null,
    workflowPendingSourceId: null,
    workflowConflict: null,
    workflowHistory: [],
    workflowFuture: [],
  });
}

const ports: ResolvedSubworkflowPorts = {
  inputs: [{ name: "raw_in", accepted_types: ["DataObject"] }],
  outputs: [{ name: "report", accepted_types: ["DataObject"] }],
  broken: false,
  ref_path: "subworkflows/child.swf.yaml",
};

describe("setNodeRef", () => {
  beforeEach(() => resetWithNode(subworkflowNode()));

  it("writes config.ref.path at the top level (not under params) and marks dirty", () => {
    useAppStore.getState().setNodeRef("sw1", "subworkflows/child.swf.yaml");

    const node = useAppStore.getState().workflowNodes[0];
    expect(node.config.ref).toEqual({ path: "subworkflows/child.swf.yaml" });
    // The params merge path must NOT have been used.
    expect((node.config.params as Record<string, unknown>).ref).toBeUndefined();
    expect(useAppStore.getState().workflowDirty).toBe(true);
  });

  it("does nothing to other nodes", () => {
    useAppStore.setState({
      workflowNodes: [subworkflowNode(), { ...subworkflowNode(), id: "sw2" }],
    });
    useAppStore.getState().setNodeRef("sw2", "subworkflows/other.swf.yaml");

    const [first, second] = useAppStore.getState().workflowNodes;
    expect(first.config.ref).toBeUndefined();
    expect(second.config.ref).toEqual({ path: "subworkflows/other.swf.yaml" });
  });
});

describe("setNodeResolvedPorts", () => {
  beforeEach(() => resetWithNode(subworkflowNode()));

  it("sets resolved_ports in place without marking the workflow dirty", () => {
    useAppStore.getState().setNodeResolvedPorts("sw1", ports);

    const node = useAppStore.getState().workflowNodes[0];
    expect(node.resolved_ports).toEqual(ports);
    expect(useAppStore.getState().workflowDirty).toBe(false);
  });
});
