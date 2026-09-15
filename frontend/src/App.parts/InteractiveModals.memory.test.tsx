/**
 * #2412 — interaction memory is stored only under `config.params`, and blocks
 * inside an expanded subworkflow are never remembered.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../store";
import { interactivePromptKey } from "../store/executionSlice.parts/interactivePrompts";
import type { InteractivePrompt } from "../store/types";
import type { WorkflowNode } from "../types/api";
import { resetAppStore } from "../testUtils";
import { InteractiveModals } from "./InteractiveModals";

vi.mock("../hooks/useWebSocket", () => ({ sendWebSocketMessage: vi.fn() }));
vi.mock("./InteractiveModals.parts/DynamicPanel", () => ({
  DynamicPanel: (props: { onConfirm: (data: Record<string, unknown>) => void }) => (
    <button type="button" onClick={() => props.onConfirm({ routes: ["choice"] })}>
      confirm
    </button>
  ),
}));

import { sendWebSocketMessage } from "../hooks/useWebSocket";

function seedPrompt(blockId: string) {
  const prompt: InteractivePrompt = {
    blockId,
    blockType: "pkg.router",
    workflowId: "main",
    panelManifest: {
      panel_id: "pkg.router",
      module_url: "/api/blocks/panels/pkg/x.js",
      api_version: "1.0",
    },
    panelPayload: {},
    inputSignature: { in: ["a.tif", "b.tif"] },
    data: {},
  };
  useAppStore.setState({
    interactivePrompts: { [interactivePromptKey(prompt.workflowId, blockId)]: prompt },
  });
}

function setCanvas(nodes: WorkflowNode[]) {
  useAppStore.setState({ workflowId: "main", workflowNodes: nodes, workflowDirty: false });
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ interactivePrompts: {} });
  vi.mocked(sendWebSocketMessage).mockClear();
});

afterEach(() => cleanup());

describe("<InteractiveModals> interaction memory (#2412)", () => {
  it("saves the decision under params and removes a legacy top-level record", () => {
    setCanvas([
      {
        id: "pick",
        block_type: "pkg.router",
        config: { interactive_memory: { enabled: true, decision: null, signature: null } },
      } as WorkflowNode,
    ]);
    seedPrompt("pick");
    render(<InteractiveModals />);
    fireEvent.click(screen.getByText("confirm"));

    const node = useAppStore.getState().workflowNodes.find((n) => n.id === "pick")!;
    expect(node.config).toEqual({
      params: {
        interactive_memory: {
          enabled: true,
          decision: { routes: ["choice"] },
          signature: { in: ["a.tif", "b.tif"] },
        },
      },
    });
  });

  it("does not remember a flattened subworkflow block on the parent canvas", () => {
    setCanvas([
      {
        id: "sw1",
        block_type: "subworkflow_block",
        config: { params: { ref: { path: "workflows/sub.yaml" } } },
      } as WorkflowNode,
    ]);
    seedPrompt("sw1__pick");
    render(<InteractiveModals />);
    fireEvent.click(screen.getByText("confirm"));

    expect(sendWebSocketMessage).toHaveBeenCalled();
    expect(useAppStore.getState().workflowDirty).toBe(false);
    expect(useAppStore.getState().interactivePrompts).toEqual({});
  });
});
