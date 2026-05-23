/**
 * Editing-action factories for workflowSlice. Extracted in #1413 / #1414.
 *
 * Each factory returns a single action function bound to the zustand
 * `set` setter so the main slice can compose them into the slice object
 * without the factory arrow exceeding the 150-LOC lint cap.
 */
import type { StoreApi } from "zustand";

import type { BlockSummary, WorkflowEdge } from "../../types/api";
import type { AppStore, WorkflowSlice } from "../types";
import { markDirty, mergeNodeConfig, pushHistory } from "./workflowHelpers";

type Setter = StoreApi<AppStore>["setState"];

export function createAddNode(set: Setter): WorkflowSlice["addNode"] {
  return (block: BlockSummary, position, defaultParams) =>
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
    });
}

export function createAddAnnotationNode(set: Setter): WorkflowSlice["addAnnotationNode"] {
  return (position) =>
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
    }));
}

export function createAddGroupNode(set: Setter): WorkflowSlice["addGroupNode"] {
  return (position) =>
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
    }));
}

export function createUpdateNodeConfig(set: Setter): WorkflowSlice["updateNodeConfig"] {
  return (nodeId, config) =>
    set((state) => ({
      ...pushHistory(state),
      ...markDirty(state),
      workflowNodes: state.workflowNodes.map((node) =>
        node.id === nodeId ? mergeNodeConfig(node, config) : node,
      ),
    }));
}

export function createUpdateNodeLayout(set: Setter): WorkflowSlice["updateNodeLayout"] {
  return (nodeId, position) =>
    set((state) => ({
      ...markDirty(state),
      workflowNodes: state.workflowNodes.map((node) =>
        node.id === nodeId ? { ...node, layout: position } : node,
      ),
    }));
}

export function createConnectNodes(set: Setter): WorkflowSlice["connectNodes"] {
  return (edge: WorkflowEdge) =>
    set((state) => ({
      ...pushHistory(state),
      ...markDirty(state),
      workflowEdges: [...state.workflowEdges, edge],
    }));
}

export function createRemoveNode(set: Setter): WorkflowSlice["removeNode"] {
  return (nodeId) =>
    set((state) => ({
      ...pushHistory(state),
      ...markDirty(state),
      workflowNodes: state.workflowNodes.filter((node) => node.id !== nodeId),
      workflowEdges: state.workflowEdges.filter(
        (edge) => !edge.source.startsWith(`${nodeId}:`) && !edge.target.startsWith(`${nodeId}:`),
      ),
    }));
}

export function createRemoveEdge(set: Setter): WorkflowSlice["removeEdge"] {
  return (edgeToRemove) =>
    set((state) => ({
      ...pushHistory(state),
      ...markDirty(state),
      workflowEdges: state.workflowEdges.filter(
        (edge) => edge.source !== edgeToRemove.source || edge.target !== edgeToRemove.target,
      ),
    }));
}

export function createSetWorkflowDescription(set: Setter): WorkflowSlice["setWorkflowDescription"] {
  return (description) =>
    set((state) => ({ workflowDescription: description, ...markDirty(state) }));
}
