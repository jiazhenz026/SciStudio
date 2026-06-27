import type { StateCreator } from "zustand";

import { setWorkflowWriteStartedListener } from "../lib/api";
import type { VersionedWorkflowResponse } from "../lib/api";
import type { AppStore, WorkflowSlice } from "./types";
import {
  createAddAnnotationNode,
  createAddNode,
  createConnectNodes,
  createRemoveEdge,
  createRemoveNode,
  createSetNodeRef,
  createSetNodeResolvedPorts,
  createSetWorkflowDescription,
  createUpdateNodeConfig,
  createUpdateNodeLayout,
  createUpdateNodeLayoutBatch,
  createUpdateNodeSize,
} from "./workflowSlice.parts/workflowEditActions";
import {
  markDirty,
  normalizeLoadedNodes,
  snapshot,
  stateVersionOf,
} from "./workflowSlice.parts/workflowHelpers";
import {
  createBeginWorkflowSave,
  createConfirmWorkflowVersion,
  createMarkWorkflowSaved,
} from "./workflowSlice.parts/workflowVersionActions";

export const createWorkflowSlice: StateCreator<AppStore, [], [], WorkflowSlice> = (set, get) => {
  setWorkflowWriteStartedListener((workflowId, sourceId) => {
    get().beginWorkflowSave(workflowId, sourceId);
  });

  return {
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
    setWorkflow: (workflow) =>
      set(() => {
        const baseVersion = stateVersionOf(workflow as VersionedWorkflowResponse | null);
        return {
          workflowId: workflow?.id ?? null,
          // #796: WorkflowModel.id has an empty-string default in the backend
          // schema. A workflow YAML that omits the `id:` field round-trips through
          // the API as ``id: ""`` and would render a blank top-left title here.
          // Fall back to "Untitled" so the user always sees a label.
          workflowName: workflow?.id || "Untitled",
          workflowDescription: workflow?.description ?? "",
          workflowVersion: workflow?.version ?? "1.0.0",
          workflowMetadata: workflow?.metadata ?? {},
          // #11: wrap flat (agent/hand-authored) node configs into the canonical
          // { params } shape so the config panel shows the real stored values.
          workflowNodes: normalizeLoadedNodes(workflow?.nodes ?? []),
          workflowEdges: workflow?.edges ?? [],
          workflowDirty: false,
          workflowBaseVersion: baseVersion,
          workflowPendingVersion: baseVersion,
          workflowPendingSourceId: null,
          workflowConflict: null,
          workflowHistory: [],
          workflowFuture: [],
        };
      }),
    setWorkflowName: (name) => set({ workflowName: name }),
    addNode: createAddNode(set),
    addAnnotationNode: createAddAnnotationNode(set),
    updateNodeConfig: createUpdateNodeConfig(set),
    setNodeRef: createSetNodeRef(set),
    setNodeResolvedPorts: createSetNodeResolvedPorts(set),
    updateNodeLayout: createUpdateNodeLayout(set),
    updateNodeSize: createUpdateNodeSize(set),
    updateNodeLayoutBatch: createUpdateNodeLayoutBatch(set),
    connectNodes: createConnectNodes(set),
    removeNode: createRemoveNode(set),
    removeEdge: createRemoveEdge(set),
    setWorkflowDescription: createSetWorkflowDescription(set),
    markWorkflowSaved: createMarkWorkflowSaved(set),
    beginWorkflowSave: createBeginWorkflowSave(set),
    confirmWorkflowVersion: createConfirmWorkflowVersion(set),
    markWorkflowRemoteConflict: (conflict) =>
      set({ workflowConflict: conflict, workflowDirty: true }),
    clearWorkflowConflict: () => set({ workflowConflict: null }),
    undoWorkflow: () => {
      const state = get();
      const last = state.workflowHistory[state.workflowHistory.length - 1];
      if (!last) {
        return;
      }
      set({
        workflowNodes: last.nodes,
        workflowEdges: last.edges,
        workflowDescription: last.description,
        ...markDirty(state),
        workflowHistory: state.workflowHistory.slice(0, -1),
        workflowFuture: [...state.workflowFuture, snapshot(state)].slice(-40),
      });
    },
    redoWorkflow: () => {
      const state = get();
      const next = state.workflowFuture[state.workflowFuture.length - 1];
      if (!next) {
        return;
      }
      set({
        workflowNodes: next.nodes,
        workflowEdges: next.edges,
        workflowDescription: next.description,
        ...markDirty(state),
        workflowHistory: [...state.workflowHistory, snapshot(state)].slice(-40),
        workflowFuture: state.workflowFuture.slice(0, -1),
      });
    },
  };
};
