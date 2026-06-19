import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BlockSchemaResponse, BlockSummary } from "../../types/api";
import { useAppStore } from "../index";

vi.mock("../../lib/api/ai", () => ({
  postActiveWorkflowContext: vi.fn().mockResolvedValue(undefined),
}));

function blockSummary(overrides: Partial<BlockSummary> = {}): BlockSummary {
  return {
    name: "Variadic Block",
    type_name: "variadic_block",
    base_category: "process",
    subcategory: "routing",
    description: "",
    version: "0.1.0",
    input_ports: [],
    output_ports: [],
    variadic_inputs: true,
    variadic_outputs: true,
    ...overrides,
  };
}

function blockSchema(overrides: Partial<BlockSchemaResponse> = {}): BlockSchemaResponse {
  const summary = blockSummary(overrides);
  return {
    ...summary,
    config_schema: {},
    type_hierarchy: [],
    dynamic_ports: null,
    allowed_input_types: [],
    allowed_output_types: [],
    min_input_ports: null,
    max_input_ports: null,
    min_output_ports: null,
    max_output_ports: null,
    ...overrides,
  };
}

function resetWorkflowStore(): void {
  useAppStore.setState({
    currentProject: null,
    workflowId: null,
    workflowName: "Untitled",
    workflowDescription: "",
    workflowVersion: "1.0.0",
    workflowMetadata: {},
    workflowNodes: [],
    workflowEdges: [],
    workflowDirty: false,
    workflowBaseVersion: null,
    workflowPendingVersion: null,
    workflowPendingSourceId: null,
    workflowConflict: null,
    workflowHistory: [],
    workflowFuture: [],
    blockSchemas: {},
  });
}

describe("workflowSlice variadic port initialization", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetWorkflowStore();
    vi.spyOn(Date, "now").mockReturnValue(1781818299312);
  });

  it("seeds minimum variadic ports before the first autosave can validate the node", () => {
    const block = blockSummary({ type_name: "datarouter_block", name: "Data Router" });
    useAppStore.setState({
      blockSchemas: {
        datarouter_block: blockSchema({
          ...block,
          min_input_ports: 1,
          min_output_ports: 1,
        }),
      },
    });

    useAppStore.getState().addNode(block, { x: 160, y: 160 }, { direction: "process" });

    const node = useAppStore.getState().workflowNodes[0];
    expect(node.id).toBe("datarouter_block-1781818299312");
    expect(node.config.params).toMatchObject({
      direction: "process",
      input_ports: [{ name: "input_1", types: ["DataObject"] }],
      output_ports: [{ name: "output_1", types: ["DataObject"] }],
    });
  });

  it("does not override variadic blocks whose static scaffold already satisfies the minimum", () => {
    const block = blockSummary({ type_name: "code_block", name: "Code Block" });
    useAppStore.setState({
      blockSchemas: {
        code_block: blockSchema({
          ...block,
          input_ports: [
            {
              name: "data",
              direction: "input",
              accepted_types: ["DataObject"],
              required: false,
              description: "",
              constraint_description: "",
              is_collection: false,
            },
          ],
          output_ports: [
            {
              name: "result",
              direction: "output",
              accepted_types: ["DataObject"],
              required: true,
              description: "",
              constraint_description: "",
              is_collection: false,
            },
          ],
          min_input_ports: 1,
          min_output_ports: 1,
        }),
      },
    });

    useAppStore.getState().addNode(block, { x: 160, y: 160 });

    const params = useAppStore.getState().workflowNodes[0].config.params as Record<string, unknown>;
    expect(params.input_ports).toBeUndefined();
    expect(params.output_ports).toBeUndefined();
  });
});
