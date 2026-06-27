// ADR-044 FR-011 (US5) — SubworkflowConfigEditor (Config-tab picker) tests.
//
// The editor shows the current `config.ref.path` (top-level, NOT under params)
// and a "Choose subworkflow file…" button that runs the SAME shared import flow
// the canvas node affordance uses, passing the node id + the store's
// setNodeRef / setNodeResolvedPorts / setLastError actions.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { WorkflowNode } from "../../types/api";
import { useAppStore } from "../../store";

// Stub the active-workflow sync the store kicks off on setState so the test
// does not emit a noisy (harmless) fetch-URL error from jsdom.
vi.mock("../../lib/api/ai", () => ({
  postActiveWorkflowContext: vi.fn().mockResolvedValue(undefined),
}));

const chooseMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/chooseSubworkflowFile", () => ({
  chooseSubworkflowFile: chooseMock,
}));

import { SubworkflowConfigEditor } from "./SubworkflowConfigEditor";

function makeNode(overrides: Partial<WorkflowNode> = {}): WorkflowNode {
  return {
    id: "sw1",
    block_type: "subworkflow_block",
    config: { ref: { path: "subworkflows/child.swf.yaml" } },
    ...overrides,
  };
}

beforeEach(() => {
  chooseMock.mockReset();
  chooseMock.mockResolvedValue("subworkflows/child.swf.yaml");
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SubworkflowConfigEditor", () => {
  it("renders the current config.ref.path and a choose button", () => {
    render(<SubworkflowConfigEditor selectedNode={makeNode()} />);

    expect(screen.getByTestId("subworkflow-config-ref-path")).toHaveValue(
      "subworkflows/child.swf.yaml",
    );
    expect(screen.getByTestId("subworkflow-config-choose")).toHaveTextContent(
      "Choose subworkflow file…",
    );
  });

  it("lays the picker out on the shared 2-column config grid (same contract as other blocks)", () => {
    render(<SubworkflowConfigEditor selectedNode={makeNode()} />);

    const root = screen.getByTestId("subworkflow-config-editor");
    // The config contract is a 2-column grid (md:grid-cols-2), matching
    // ConfigPanel / CodeBlockConfigEditor — not a single full-width column.
    expect(root.className).toContain("md:grid-cols-2");
  });

  it("shows an empty path field when no ref is set", () => {
    render(<SubworkflowConfigEditor selectedNode={makeNode({ config: { params: {} } })} />);
    expect(screen.getByTestId("subworkflow-config-ref-path")).toHaveValue("");
  });

  it("runs the shared flow with the node id + store actions when the button is clicked", async () => {
    render(<SubworkflowConfigEditor selectedNode={makeNode()} />);

    fireEvent.click(screen.getByTestId("subworkflow-config-choose"));

    await waitFor(() => expect(chooseMock).toHaveBeenCalledTimes(1));
    const [nodeId, deps] = chooseMock.mock.calls[0];
    expect(nodeId).toBe("sw1");
    const store = useAppStore.getState();
    expect(deps.setNodeRef).toBe(store.setNodeRef);
    expect(deps.setNodeResolvedPorts).toBe(store.setNodeResolvedPorts);
    expect(deps.setLastError).toBe(store.setLastError);
  });
});
