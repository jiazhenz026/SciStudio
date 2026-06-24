// MergeCollection connect-time validation: both inputs must carry the same
// Collection item type. Each edge alone is type-valid (inputs accept
// DataObject), so the cross-input check lives in handleCanvasConnect and
// rejects with a banner ("can't connect + top banner" pattern).
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCanvasHandlers, type CanvasHandlersDeps } from "./useCanvasHandlers";
import type { BlockSchemaResponse, WorkflowEdge, WorkflowNode } from "../types/api";

const apiMocks = vi.hoisted(() => ({
  validateConnection: vi.fn().mockResolvedValue({ compatible: true, reason: "" }),
}));
vi.mock("../lib/api", () => ({ api: apiMocks }));

const loadDataSchema = {
  input_ports: [],
  output_ports: [{ name: "data", direction: "output", accepted_types: ["DataObject"] }],
  variadic_inputs: false,
  variadic_outputs: false,
  dynamic_ports: {
    source_config_key: "core_type",
    output_port_mapping: { data: { Array: ["Array"], DataFrame: ["DataFrame"] } },
  },
} as unknown as BlockSchemaResponse;

const mergeSchema = {
  input_ports: [
    { name: "input_a", direction: "input", accepted_types: ["DataObject"] },
    { name: "input_b", direction: "input", accepted_types: ["DataObject"] },
  ],
  output_ports: [{ name: "output", direction: "output", accepted_types: ["DataObject"] }],
  variadic_inputs: false,
  variadic_outputs: false,
  dynamic_ports: null,
} as unknown as BlockSchemaResponse;

function loadNode(id: string, coreType: string): WorkflowNode {
  return {
    id,
    block_type: "load_data",
    config: { params: { core_type: coreType } },
  } as WorkflowNode;
}

function renderHandlers(nodes: WorkflowNode[], edges: WorkflowEdge[]) {
  const connectNodes = vi.fn();
  const setLastError = vi.fn();
  const deps = {
    currentProject: { id: "p" },
    workflowId: "main",
    workflowNodes: nodes,
    workflowEdges: edges,
    activeFileTab: null,
    addNode: vi.fn(),
    connectNodes,
    openFileTab: vi.fn(),
    saveFileTab: vi.fn(),
    saveWorkflow: vi.fn(),
    setLastError,
    schemas: { load_data: loadDataSchema, mergecollection_block: mergeSchema },
  } as unknown as CanvasHandlersDeps;
  const { result } = renderHook(() => useCanvasHandlers(deps));
  return { result, connectNodes, setLastError };
}

describe("useCanvasHandlers — MergeCollection input type validation", () => {
  afterEach(() => vi.clearAllMocks());

  it("rejects a second input of a different Collection type", async () => {
    const nodes = [
      loadNode("load1", "Array"),
      loadNode("load2", "DataFrame"),
      { id: "merge", block_type: "mergecollection_block", config: { params: {} } } as WorkflowNode,
    ];
    const edges: WorkflowEdge[] = [{ source: "load1:data", target: "merge:input_a" }];
    const { result, connectNodes, setLastError } = renderHandlers(nodes, edges);

    await result.current.handleCanvasConnect({ source: "load2:data", target: "merge:input_b" });

    expect(setLastError).toHaveBeenCalledWith(
      "MergeCollection inputs must be the same Collection type: Array vs DataFrame.",
    );
    expect(connectNodes).not.toHaveBeenCalled();
    expect(apiMocks.validateConnection).not.toHaveBeenCalled();
  });

  it("allows a second input of the same Collection type", async () => {
    const nodes = [
      loadNode("load1", "Array"),
      loadNode("load2", "Array"),
      { id: "merge", block_type: "mergecollection_block", config: { params: {} } } as WorkflowNode,
    ];
    const edges: WorkflowEdge[] = [{ source: "load1:data", target: "merge:input_a" }];
    const { result, connectNodes } = renderHandlers(nodes, edges);

    await result.current.handleCanvasConnect({ source: "load2:data", target: "merge:input_b" });

    expect(connectNodes).toHaveBeenCalled();
  });
});

describe("useCanvasHandlers — View source routing (#1758)", () => {
  afterEach(() => vi.clearAllMocks());

  function renderView(overrides: Partial<CanvasHandlersDeps>) {
    const openFileTab = vi.fn();
    const openBlockSourceTab = vi.fn();
    const saveWorkflow = vi.fn().mockResolvedValue(undefined);
    const deps = {
      currentProject: { id: "p" },
      workflowId: "main",
      workflowNodes: [],
      workflowEdges: [],
      activeFileTab: null,
      addNode: vi.fn(),
      connectNodes: vi.fn(),
      openFileTab,
      selectedNodeId: null,
      openBlockSourceTab,
      saveFileTab: vi.fn(),
      saveWorkflow,
      setLastError: vi.fn(),
      schemas: {},
      ...overrides,
    } as unknown as CanvasHandlersDeps;
    const { result } = renderHook(() => useCanvasHandlers(deps));
    return { result, openFileTab, openBlockSourceTab, saveWorkflow };
  }

  it("opens the selected block's source instead of the workflow YAML", async () => {
    const node = { id: "n1", block_type: "load_data" } as unknown as WorkflowNode;
    const { result, openFileTab, openBlockSourceTab } = renderView({
      workflowNodes: [node],
      selectedNodeId: "n1",
    });

    await act(async () => {
      await result.current.handleViewSource();
    });

    expect(openBlockSourceTab).toHaveBeenCalledWith("load_data");
    expect(openFileTab).not.toHaveBeenCalled();
  });

  it("falls back to the workflow YAML when no block is selected", async () => {
    const { result, openFileTab, openBlockSourceTab, saveWorkflow } = renderView({
      selectedNodeId: null,
    });

    await act(async () => {
      await result.current.handleViewSource();
    });

    expect(saveWorkflow).toHaveBeenCalled();
    expect(openFileTab).toHaveBeenCalledWith("workflows/main.yaml", { readOnly: true });
    expect(openBlockSourceTab).not.toHaveBeenCalled();
  });
});
