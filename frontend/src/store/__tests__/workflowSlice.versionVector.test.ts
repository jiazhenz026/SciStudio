import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../index";
import type { VersionedWorkflowResponse } from "../../lib/api";

function workflow(stateVersion: number): VersionedWorkflowResponse {
  return {
    id: "demo",
    version: "1.0.0",
    state_version: stateVersion,
    workflow_version: "1.0.0",
    description: "",
    nodes: [],
    edges: [],
    metadata: {},
  };
}

function resetStore(): void {
  useAppStore.setState({
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
  });
}

describe("workflowSlice ADR-045 version state", () => {
  beforeEach(() => {
    resetStore();
  });

  it("loads state_version without repurposing workflow schema version", () => {
    useAppStore.getState().setWorkflow(workflow(10));

    const state = useAppStore.getState();
    expect(state.workflowVersion).toBe("1.0.0");
    expect(state.workflowBaseVersion).toBe(10);
    expect(state.workflowPendingVersion).toBe(10);
    expect(state.workflowPendingSourceId).toBeNull();
  });

  it("increments pendingVersion for local edits and records save source_id", () => {
    useAppStore.getState().setWorkflow(workflow(10));

    useAppStore.getState().setWorkflowDescription("local edit");
    useAppStore.getState().beginWorkflowSave("demo", "workflow-source-1");

    const state = useAppStore.getState();
    expect(state.workflowDirty).toBe(true);
    expect(state.workflowBaseVersion).toBe(10);
    expect(state.workflowPendingVersion).toBeGreaterThan(10);
    expect(state.workflowPendingSourceId).toBe("workflow-source-1");
  });

  it("confirming an autosave echo preserves newer local edits", () => {
    useAppStore.getState().setWorkflow(workflow(10));
    useAppStore.setState({
      workflowDirty: true,
      workflowBaseVersion: 10,
      workflowPendingVersion: 12,
      workflowPendingSourceId: "workflow-source-1",
      workflowDescription: "newer local edit",
    });

    useAppStore.getState().confirmWorkflowVersion(11, "workflow-source-1");

    const state = useAppStore.getState();
    expect(state.workflowBaseVersion).toBe(11);
    expect(state.workflowPendingVersion).toBe(12);
    expect(state.workflowDirty).toBe(true);
    expect(state.workflowDescription).toBe("newer local edit");
    expect(state.workflowPendingSourceId).toBeNull();
  });
});
