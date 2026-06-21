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
  ResolvedSubworkflowPorts,
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
  return direction === "input" ? schema.variadic_inputs === true : schema.variadic_outputs === true;
}

function defaultTypesFor(schema: Partial<BlockSchemaResponse>, direction: Direction): string[] {
  const allowedTypes =
    direction === "input"
      ? (schema.allowed_input_types ?? [])
      : (schema.allowed_output_types ?? []);
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
          config: { params: { text: "Note" }, style: { width: 240, height: 120 } },
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

/**
 * ADR-044 FR-011 / US5 + US6 — repoint a subworkflow node's referenced file.
 *
 * Unlike `createUpdateNodeConfig` (which deep-merges into `config.params`), the
 * subworkflow reference lives at the TOP level of the node config
 * (`config.ref.path`) — the on-disk schema declares a nested `ref.path` object,
 * the Python `SubWorkflowBlock` reads `config.get("ref")`, and the canvas
 * builder reads `node.config.ref`. Writing through the params merge would land
 * the ref at `config.params.ref` where nothing reads it, so this action sets
 * `config.ref` directly. Pushes history + marks dirty so the autosave persists.
 */
export function createSetNodeRef(set: Setter): WorkflowSlice["setNodeRef"] {
  return (nodeId, refPath) =>
    set((state) => ({
      ...pushHistory(state),
      ...markDirty(state),
      workflowNodes: state.workflowNodes.map((node) =>
        node.id === nodeId ? { ...node, config: { ...node.config, ref: { path: refPath } } } : node,
      ),
    }));
}

/**
 * ADR-044 FR-004 / US5 — set the response-only `resolved_ports` surface on a
 * subworkflow node so its handles refresh immediately. `resolved_ports` is
 * never persisted (the backend recomputes it per load), so this does NOT mark
 * the workflow dirty and does NOT push an undo entry.
 */
export function createSetNodeResolvedPorts(set: Setter): WorkflowSlice["setNodeResolvedPorts"] {
  return (nodeId, resolvedPorts: ResolvedSubworkflowPorts) =>
    set((state) => ({
      workflowNodes: state.workflowNodes.map((node) =>
        node.id === nodeId ? { ...node, resolved_ports: resolvedPorts } : node,
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

/**
 * Persist a resizable node's width/height into `config.style` (live hotfix
 * batch — annotation notes are now resizable). Scoped to `_annotation` nodes so
 * a stray dimensions change on a regular block can never write a body size.
 * markDirty without pushHistory: a resize is a single committed change, not an
 * undo step per frame.
 */
export function createUpdateNodeSize(set: Setter): WorkflowSlice["updateNodeSize"] {
  return (nodeId, size) =>
    set((state) => {
      const target = state.workflowNodes.find((node) => node.id === nodeId);
      if (!target || target.block_type !== "_annotation") return {};
      return {
        ...markDirty(state),
        workflowNodes: state.workflowNodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                config: {
                  ...node.config,
                  style: {
                    ...((node.config.style as Record<string, unknown> | undefined) ?? {}),
                    width: size.width,
                    height: size.height,
                  },
                },
              }
            : node,
        ),
      };
    });
}

/**
 * ADR-050 §3.2 / FR-022 / FR-024 — batch layout update for the tidy action.
 *
 * Applies many node positions in a SINGLE store mutation so tidy moves the
 * whole (or focused) graph as one history entry rather than one-per-node.
 * Writes ONLY `node.layout`: ids, block types, config, ports, edges, and
 * runtime state are left untouched. Nodes absent from `positions` keep their
 * current layout, so a focus-scoped tidy never disturbs hidden nodes
 * (ADR-050 §3.2). A no-op call (no matching nodes) does not push history or
 * mark the workflow dirty.
 */
export function createUpdateNodeLayoutBatch(set: Setter): WorkflowSlice["updateNodeLayoutBatch"] {
  return (positions) =>
    set((state) => {
      const hasChange = state.workflowNodes.some((node) => node.id in positions);
      if (!hasChange) return {};
      return {
        ...pushHistory(state),
        ...markDirty(state),
        workflowNodes: state.workflowNodes.map((node) =>
          node.id in positions ? { ...node, layout: positions[node.id] } : node,
        ),
      };
    });
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
