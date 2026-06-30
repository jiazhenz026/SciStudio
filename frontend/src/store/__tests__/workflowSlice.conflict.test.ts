import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../index";
import type { VersionedWorkflowResponse } from "../../lib/api";
import type { VersionConflictState } from "../types";

function workflow(stateVersion: number, description = ""): VersionedWorkflowResponse {
  return {
    id: "demo",
    version: "1.0.0",
    state_version: stateVersion,
    workflow_version: "1.0.0",
    description,
    nodes: [],
    edges: [],
    metadata: {},
  };
}

function conflictAt(
  remoteVersion: number,
  remote: VersionedWorkflowResponse | null,
): VersionConflictState {
  return {
    entityClass: "workflow",
    entityId: "demo",
    kind: "modified",
    source: "agent",
    sourceId: null,
    baseVersion: 5,
    pendingVersion: 5,
    remoteVersion,
    detectedAt: "2026-06-30T00:00:00Z",
    message: "remote change",
    remoteWorkflow: remote,
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

describe("workflowSlice #1891 conflict resolution", () => {
  beforeEach(() => {
    resetStore();
  });

  it("keepLocal drops the conflict but preserves the dirty local edits", () => {
    useAppStore.getState().setWorkflow(workflow(5));
    useAppStore.getState().setWorkflowDescription("local edit");
    useAppStore.getState().markWorkflowRemoteConflict(conflictAt(6, workflow(6, "agent edit")));

    expect(useAppStore.getState().workflowConflict).not.toBeNull();

    useAppStore.getState().resolveWorkflowConflict("keepLocal");

    const state = useAppStore.getState();
    expect(state.workflowConflict).toBeNull();
    // Local edits survive so the now-unfrozen autosave persists them.
    expect(state.workflowDirty).toBe(true);
    expect(state.workflowDescription).toBe("local edit");
    expect(state.workflowBaseVersion).toBe(5);
  });

  it("loadRemote adopts the remote workflow as the new clean base", () => {
    useAppStore.getState().setWorkflow(workflow(5));
    useAppStore.getState().setWorkflowDescription("local edit");
    useAppStore.getState().markWorkflowRemoteConflict(conflictAt(6, workflow(6, "agent edit")));

    useAppStore.getState().resolveWorkflowConflict("loadRemote");

    const state = useAppStore.getState();
    expect(state.workflowConflict).toBeNull();
    expect(state.workflowDirty).toBe(false);
    expect(state.workflowDescription).toBe("agent edit");
    expect(state.workflowBaseVersion).toBe(6);
    expect(state.workflowPendingVersion).toBe(6);
  });

  it("loadRemote with no remote payload clears the canvas", () => {
    useAppStore.getState().setWorkflow(workflow(5));
    useAppStore.getState().setWorkflowDescription("local edit");
    useAppStore.getState().markWorkflowRemoteConflict(conflictAt(6, null));

    useAppStore.getState().resolveWorkflowConflict("loadRemote");

    const state = useAppStore.getState();
    expect(state.workflowConflict).toBeNull();
    expect(state.workflowId).toBeNull();
    expect(state.workflowDirty).toBe(false);
  });

  it("is a no-op when there is no active conflict", () => {
    useAppStore.getState().setWorkflow(workflow(5));
    useAppStore.getState().resolveWorkflowConflict("keepLocal");

    expect(useAppStore.getState().workflowConflict).toBeNull();
    expect(useAppStore.getState().workflowBaseVersion).toBe(5);
  });
});
