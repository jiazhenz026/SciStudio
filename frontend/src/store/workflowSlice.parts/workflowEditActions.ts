/**
 * Editing-action factories for workflowSlice. Extracted in #1413 / #1414.
 *
 * Each factory returns a single action function bound to the zustand
 * `set` setter so the main slice can compose them into the slice object
 * without the factory arrow exceeding the 150-LOC lint cap.
 */
import type { StoreApi } from "zustand";

import type {
  BlockPortResponse,
  BlockSchemaResponse,
  BlockSummary,
  WorkflowEdge,
} from "../../types/api";
import type { AppStore, WorkflowSlice } from "../types";
import { markDirty, mergeNodeConfig, pushHistory } from "./workflowHelpers";

type Setter = StoreApi<AppStore>["setState"];
type Direction = "input" | "output";
type VariadicPortParam = { name: string; types: string[] };

function portsFor(schema: Partial<BlockSchemaResponse>, direction: Direction): BlockPortResponse[] {
  return direction === "input" ? (schema.input_ports ?? []) : (schema.output_ports ?? []);
}

function minPortsFor(schema: Partial<BlockSchemaResponse>, direction: Direction): number | null {
  const value = direction === "input" ? schema.min_input_ports : schema.min_output_ports;
  return typeof value === "number" && value > 0 ? value : null;
}

function isVariadic(schema: Partial<BlockSchemaResponse>, direction: Direction): boolean {
  return direction === "input"
    ? schema.variadic_inputs === true
    : schema.variadic_outputs === true;
}

function defaultTypesFor(schema: Partial<BlockSchemaResponse>, direction: Direction): string[] {
  const allowedTypes =
    direction === "input" ? (schema.allowed_input_types ?? []) : (schema.allowed_output_types ?? []);
  return allowedTypes.length > 0 ? [allowedTypes[0]] : ["DataObject"];
}

function minimumVariadicPorts(
  schema: Partial<BlockSchemaResponse>,
  direction: Direction,
): VariadicPortParam[] {
  if (!isVariadic(schema, direction)) return [];
  const minPorts = minPortsFor(schema, direction);
  if (minPorts == null) return [];

  const staticPorts = portsFor(schema, direction);
  if (staticPorts.length >= minPorts) return [];

  const fallbackTypes = defaultTypesFor(schema, direction);
  return Array.from({ length: minPorts }, (_, index) => {
    const staticPort = staticPorts[index];
    const acceptedTypes =
      staticPort?.accepted_types && staticPort.accepted_types.length > 0
        ? staticPort.accepted_types
        : fallbackTypes;
    return {
      name: staticPort?.name || `${direction}_${index + 1}`,
      types: [...acceptedTypes],
    };
  });
}

export function createInitialNodeParams(
  block: BlockSummary,
  schema: BlockSchemaResponse | undefined,
  defaultParams?: Record<string, unknown>,
): Record<string, unknown> {
  const params: Record<string, unknown> = { ...(defaultParams ?? {}) };
  const source = (schema ?? block) as Partial<BlockSchemaResponse>;

  for (const direction of ["input", "output"] as const) {
    const key = direction === "input" ? "input_ports" : "output_ports";
    const current = params[key];
    if (Array.isArray(current) && current.length > 0) continue;
    const seededPorts = minimumVariadicPorts(source, direction);
    if (seededPorts.length > 0) {
      params[key] = seededPorts;
    }
  }

  return params;
}

export function createAddNode(set: Setter): WorkflowSlice["addNode"] {
  return (block: BlockSummary, position, defaultParams) =>
    set((state) => {
      const nodeId = `${block.type_name}-${Date.now()}`;
      const params = createInitialNodeParams(
        block,
        (state as AppStore).blockSchemas[block.type_name],
        defaultParams,
      );

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
