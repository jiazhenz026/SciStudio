import type { StateCreator } from "zustand";

import { setWorkflowWriteStartedListener } from "../lib/api";
import type { VersionedWorkflowResponse } from "../lib/api";
import type { BlockSummary, WorkflowEdge, WorkflowNode } from "../types/api";
import type { AppStore, WorkflowHistoryEntry, WorkflowSlice } from "./types";

function snapshot(state: AppStore): WorkflowHistoryEntry {
  return {
    nodes: state.workflowNodes.map((node) => ({
      ...node,
      config: { ...node.config },
      layout: node.layout ? { ...node.layout } : null,
    })),
    edges: state.workflowEdges.map((edge) => ({ ...edge })),
    description: state.workflowDescription,
  };
}

function pushHistory(state: AppStore): Pick<AppStore, "workflowHistory" | "workflowFuture"> {
  return {
    workflowHistory: [...state.workflowHistory, snapshot(state)].slice(-40),
    workflowFuture: [],
  };
}

function stateVersionOf(workflow: VersionedWorkflowResponse | null | undefined): number | null {
  return typeof workflow?.state_version === "number" ? workflow.state_version : null;
}

function nextPendingVersion(
  base: number | null,
  pending: number | null,
  saveInFlight: boolean,
): number | null {
  if (base === null) return pending;
  if (saveInFlight) return Math.max(base + 2, pending ?? base + 2);
  return base + 1;
}

function markDirty(
  state: AppStore,
): Pick<AppStore, "workflowDirty" | "workflowPendingVersion" | "workflowConflict"> {
  return {
    workflowDirty: true,
    workflowPendingVersion: nextPendingVersion(
      state.workflowBaseVersion,
      state.workflowPendingVersion,
      state.workflowPendingSourceId !== null,
    ),
    workflowConflict: null,
  };
}

function mergeNodeConfig(node: WorkflowNode, config: Record<string, unknown>): WorkflowNode {
  return {
    ...node,
    config: {
      ...node.config,
      params: {
        ...((node.config.params as Record<string, unknown> | undefined) ?? {}),
        ...config,
      },
    },
  };
}

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
          workflowNodes: workflow?.nodes ?? [],
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
    addNode: (block, position, defaultParams) =>
      set((state) => {
        const nodeId = `${block.type_name}-${Date.now()}`;
        const params: Record<string, unknown> = { ...(defaultParams ?? {}) };

        // Auto-fill output_dir for AppBlock-category blocks with the
        // project exchange directory so users see the default path.
        const projectPath = (state as AppStore).currentProject?.path;
        if (projectPath && block.base_category === "app" && !params.output_dir) {
          params.output_dir = `${projectPath}/data/exchange/${nodeId}/outputs`;
        }

        return {
          ...pushHistory(state),
          ...markDirty(state),
          workflowId: state.workflowId ?? "main",
          workflowNodes: [
            ...state.workflowNodes,
            {
              id: nodeId,
              block_type: block.type_name,
              config: { params },
              layout: position,
            },
          ],
        };
      }),
    addAnnotationNode: (position) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowId: state.workflowId ?? "main",
        workflowNodes: [
          ...state.workflowNodes,
          {
            id: `note-${Date.now()}`,
            block_type: "_annotation",
            config: { params: { text: "Note" } },
            layout: position,
          },
        ],
      })),
    addGroupNode: (position) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowId: state.workflowId ?? "main",
        workflowNodes: [
          ...state.workflowNodes,
          {
            id: `group-${Date.now()}`,
            block_type: "_group",
            config: {
              params: { title: "Group", note: "", color: "gray" },
              style: { width: 400, height: 250 },
            },
            layout: position,
          },
        ],
      })),
    updateNodeConfig: (nodeId, config) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowNodes: state.workflowNodes.map((node) =>
          node.id === nodeId ? mergeNodeConfig(node, config) : node,
        ),
      })),
    updateNodeLayout: (nodeId, position) =>
      set((state) => ({
        ...markDirty(state),
        workflowNodes: state.workflowNodes.map((node) =>
          node.id === nodeId ? { ...node, layout: position } : node,
        ),
      })),
    connectNodes: (edge) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowEdges: [...state.workflowEdges, edge],
      })),
    removeNode: (nodeId) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowNodes: state.workflowNodes.filter((node) => node.id !== nodeId),
        workflowEdges: state.workflowEdges.filter(
          (edge) => !edge.source.startsWith(`${nodeId}:`) && !edge.target.startsWith(`${nodeId}:`),
        ),
      })),
    removeEdge: (edgeToRemove) =>
      set((state) => ({
        ...pushHistory(state),
        ...markDirty(state),
        workflowEdges: state.workflowEdges.filter(
          (edge) => edge.source !== edgeToRemove.source || edge.target !== edgeToRemove.target,
        ),
      })),
    setWorkflowDescription: (description) =>
      set((state) => ({ workflowDescription: description, ...markDirty(state) })),
    markWorkflowSaved: () =>
      set((state) => {
        if (
          state.workflowBaseVersion !== null &&
          state.workflowPendingVersion !== null &&
          state.workflowPendingVersion > state.workflowBaseVersion + 1
        ) {
          return {};
        }
        return { workflowDirty: false };
      }),
    beginWorkflowSave: (workflowId, sourceId) =>
      set((state) => {
        if (state.workflowId !== workflowId) return {};
        return {
          workflowPendingVersion:
            state.workflowBaseVersion === null
              ? state.workflowPendingVersion
              : Math.max(
                  state.workflowBaseVersion + 1,
                  state.workflowPendingVersion ?? state.workflowBaseVersion,
                ),
          workflowPendingSourceId: sourceId,
        };
      }),
    confirmWorkflowVersion: (version, sourceId = null) =>
      set((state) => {
        const hasNewerLocalEdits =
          state.workflowPendingVersion !== null && state.workflowPendingVersion > version;
        return {
          workflowBaseVersion: version,
          workflowPendingVersion: hasNewerLocalEdits ? state.workflowPendingVersion : version,
          workflowPendingSourceId:
            state.workflowPendingSourceId === sourceId ? null : state.workflowPendingSourceId,
          workflowDirty: hasNewerLocalEdits ? state.workflowDirty : false,
          workflowConflict: null,
        };
      }),
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
