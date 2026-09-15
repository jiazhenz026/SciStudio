/**
 * #2394 — a workflow tab is keyed by its file's run identity.
 *
 * An expanded subworkflow tab carries the path identity the backend gives the
 * file (`@subworkflows@imported.yaml`), not the `id:` declared inside it, so it
 * can declare `main` without being mistaken for `workflows/main.yaml`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockBackend } from "../../__tests__/contract/mockBackend";
import { handleWorkflowChanged } from "../../hooks/useWebSocket.parts/handleWorkflowChanged";
import type { WorkflowEventMessage, WorkflowResponse } from "../../types/api";
import { useAppStore } from "../index";

const SUB = "@subworkflows@imported.yaml";

function workflow(id: string): WorkflowResponse {
  return { id, version: "1.0.0", description: "", metadata: {}, nodes: [], edges: [] };
}

function event(overrides: Partial<WorkflowEventMessage>): WorkflowEventMessage {
  return {
    type: "block_done",
    block_id: "load",
    workflow_id: "main",
    data: {},
    timestamp: "2026-09-15T00:00:00Z",
    ...overrides,
  };
}

function expandImportedSubworkflow() {
  const store = useAppStore.getState();
  store.openTab(workflow("main"), "main");
  store.consumeEvent(event({ type: "block_running", block_id: "sub__load" }));
  useAppStore.getState().openTab(workflow(SUB), "imported", "sub__", "subworkflows/imported.yaml");
}

// No route is declared: any request the handlers make fails the test.
let backend: ReturnType<typeof mockBackend>;

afterEach(() => backend.restore());

beforeEach(() => {
  backend = mockBackend({});
  useAppStore.getState().resetExecution();
  useAppStore.setState({ currentProject: null, tabs: [], activeTabId: null });
  useAppStore.getState().setWorkflow(null);
});

describe("expanded subworkflow tabs use the file identity (#2394)", () => {
  it("keys the tab by the path identity and labels it by file name", () => {
    expandImportedSubworkflow();
    const state = useAppStore.getState();
    expect(state.tabs.map((tab) => (tab.kind === "workflow" ? tab.workflowId : null))).toEqual([
      "main",
      SUB,
    ]);
    expect(state.workflowId).toBe(SUB);
    expect(state.workflowName).toBe("imported");
  });

  it("a change to workflows/main.yaml never refreshes the subworkflow tab", async () => {
    expandImportedSubworkflow();
    const setWorkflow = vi.fn();
    const appendLog = vi.fn();
    handleWorkflowChanged(
      event({
        type: "workflow.changed",
        block_id: null,
        workflow_id: "main",
        data: { entity_id: "main", kind: "modified", version: 99, source: "agent" },
      }),
      { appendLog, setWorkflow },
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(setWorkflow).not.toHaveBeenCalled();
    expect(appendLog).not.toHaveBeenCalled();
    expect(useAppStore.getState().workflowConflict).toBeFalsy();
  });

  it("running the expanded tab switches it from the parent run to its own run", () => {
    expandImportedSubworkflow();
    useAppStore.getState().consumeEvent(event({ type: "block_running", workflow_id: SUB }));
    // Still projecting the parent's run: the unprefixed standalone node is not shown.
    expect(useAppStore.getState().blockStates.load).toBeUndefined();
    expect(useAppStore.getState().blockStates["sub__load"]).toBe("running");

    useAppStore.getState().showActiveTabOwnRun();

    const state = useAppStore.getState();
    const active = state.tabs.find((tab) => tab.id === state.activeTabId);
    expect(active?.kind === "workflow" && active.runPrefix).toBeFalsy();
    expect(active?.kind === "workflow" && active.runWorkflowId).toBeFalsy();
    expect(state.blockStates.load).toBe("running");
    expect(state.blockStates["sub__load"]).toBeUndefined();
  });

  it("showing its own run is a no-op for a tab that is not an expansion", () => {
    useAppStore.getState().openTab(workflow("main"), "main");
    const before = useAppStore.getState().tabs;
    useAppStore.getState().showActiveTabOwnRun();
    expect(useAppStore.getState().tabs).toBe(before);
  });
});
