/**
 * #2412 — the Config tab reads interaction memory from `config.params` first and
 * hides "remember" for blocks shown in an expanded subworkflow tab.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import { ConfigPanel } from "./ConfigPanel";

const interactiveMemorySchema = {
  name: "Data Router",
  type_name: "data_router",
  base_category: "process",
  subcategory: "routing",
  description: "",
  version: "1",
  input_ports: [],
  output_ports: [],
  execution_mode: "interactive",
  config_schema: { properties: {} },
  type_hierarchy: [],
};

describe("ConfigPanel interaction memory (#2412)", () => {
  afterEach(() => {
    cleanup();
    resetAppStore();
  });

  it("shows the saved params record over a legacy top-level one (#2412)", () => {
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "dr-1",
          block_type: "data_router",
          config: {
            interactive_memory: { enabled: false },
            params: {
              interactive_memory: { enabled: true, decision: { a: 1 }, signature: {} },
            },
          },
        }}
        schema={interactiveMemorySchema}
      />,
    );
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("button", { name: /Choose again/ })).toBeInTheDocument();
  });

  it("replaces the remember toggle with an explanation in an expanded subworkflow tab (#2412)", () => {
    useAppStore.setState({
      tabs: [
        {
          id: "tab-sub",
          kind: "workflow",
          label: "sub",
          workflowId: "sub",
          runPrefix: "sw1__",
          runWorkflowId: "main",
        },
      ] as never,
      activeTabId: "tab-sub",
    });
    render(
      <ConfigPanel
        onUpdateConfig={vi.fn()}
        selectedNode={{
          id: "pick",
          block_type: "data_router",
          config: { params: { interactive_memory: { enabled: true } } },
        }}
        schema={interactiveMemorySchema}
      />,
    );
    expect(screen.queryByText(/Remember my choice and skip this dialog/)).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByTestId("interactive-memory-unavailable")).toHaveTextContent(
      /isn't available for blocks inside a subworkflow/,
    );
  });
});
