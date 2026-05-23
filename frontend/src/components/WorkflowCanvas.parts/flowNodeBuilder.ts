/**
 * `flowNodes` builder helpers extracted from WorkflowCanvas.tsx (#1413 /
 * #1414).
 *
 * Each helper returns the ReactFlow node object for one workflow node. The
 * mapper in WorkflowCanvas dispatches to the right helper by block_type.
 */
import type { Node } from "@xyflow/react";

import type {
  BlockPortResponse,
  BlockSchemaResponse,
  BlockSummary,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import { collectUpstreamOmeFields } from "../WorkflowEditor/LossySaveWarning";

/**
 * For variadic blocks, merge config-driven ports with schema-level ports.
 * Schema-level ports are empty ([]) for variadic blocks like DataRouter /
 * PairEditor. The actual ports are stored in config.input_ports /
 * config.output_ports as arrays of {name: string, types: string[]}.
 */
export function resolveVariadicPorts(
  schemaPorts: BlockPortResponse[],
  config: Record<string, unknown>,
  direction: "input" | "output",
  schema?: BlockSchemaResponse,
): BlockPortResponse[] {
  const isVariadic =
    direction === "input" ? schema?.variadic_inputs === true : schema?.variadic_outputs === true;
  if (!isVariadic) return schemaPorts;

  const configKey = direction === "input" ? "input_ports" : "output_ports";
  const configPorts = config[configKey];
  if (!Array.isArray(configPorts) || configPorts.length === 0) return schemaPorts;

  return (configPorts as Array<{ name: string; types?: string[] }>).map((cp) => ({
    name: cp.name,
    direction,
    accepted_types: cp.types ?? [],
    required: false,
    description: "",
    constraint_description: "",
    is_collection: false,
  }));
}

export function parsePortRef(ref: string): { nodeId: string; portName: string } {
  const [nodeId, portName] = ref.split(":");
  return { nodeId, portName };
}

export function defaultLayout(index: number): { x: number; y: number } {
  return { x: 120 + index * 80, y: 120 + index * 40 };
}

export function paramsOf(node: WorkflowNode): Record<string, unknown> {
  return ((node.config.params as Record<string, unknown> | undefined) ?? {}) as Record<
    string,
    unknown
  >;
}

interface AnnotationOpts {
  node: WorkflowNode;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  selectedNodeId: string | null;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildAnnotationNode(opts: AnnotationOpts): Node<any> {
  const { node, position, params, selectedNodeId, onUpdateNodeConfig } = opts;
  return {
    id: node.id,
    type: "_annotation",
    position,
    // ``initialWidth`` / ``initialHeight`` give the MiniMap a bounding box
    // to draw before ReactFlow's ResizeObserver populates ``measured``.
    initialWidth: 200,
    initialHeight: 80,
    data: {
      text: (params.text as string) ?? "Note",
      onUpdateText: (text: string) => onUpdateNodeConfig(node.id, { text }),
    },
    selected: selectedNodeId === node.id,
  };
}

interface GroupOpts {
  node: WorkflowNode;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  selectedNodeId: string | null;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildGroupNode(opts: GroupOpts): Node<any> {
  const { node, position, params, selectedNodeId, onUpdateNodeConfig } = opts;
  const groupW =
    ((node.config.style as Record<string, unknown> | undefined)?.width as number) ?? 400;
  const groupH =
    ((node.config.style as Record<string, unknown> | undefined)?.height as number) ?? 250;
  return {
    id: node.id,
    type: "_group",
    position,
    initialWidth: groupW,
    initialHeight: groupH,
    style: { width: groupW, height: groupH },
    data: {
      title: (params.title as string) ?? "Group",
      note: (params.note as string) ?? "",
      color: (params.color as string) ?? "gray",
      onUpdateTitle: (title: string) => onUpdateNodeConfig(node.id, { title }),
      onUpdateNote: (note: string) => onUpdateNodeConfig(node.id, { note }),
    },
    selected: selectedNodeId === node.id,
  };
}

interface UpstreamOmeOpts {
  nodeId: string;
  edges: WorkflowEdge[];
  blockOutputs?: Record<string, Record<string, unknown>>;
}

export function computeUpstreamOmeFields(opts: UpstreamOmeOpts): string[] | undefined {
  const { nodeId, edges, blockOutputs } = opts;
  if (!blockOutputs) return undefined;
  const sourceIds = edges
    .filter((edge) => edge.target.split(":")[0] === nodeId)
    .map((edge) => edge.source.split(":")[0]);
  if (sourceIds.length === 0) return undefined;
  const collected = new Set<string>();
  for (const sourceId of sourceIds) {
    const outputs = blockOutputs[sourceId];
    if (!outputs) continue;
    for (const field of collectUpstreamOmeFields(outputs)) {
      collected.add(field);
    }
  }
  return collected.size > 0 ? Array.from(collected) : undefined;
}

export interface BlockNodeCallbacks {
  onRun: () => void;
  onRestart: () => void;
  onDelete: () => void;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  onErrorClick: () => void;
}

interface BlockOpts {
  node: WorkflowNode;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  summary?: BlockSummary;
  schema?: BlockSchemaResponse;
  status: string;
  errorMessage: string | undefined;
  errorSummary: string | undefined;
  callbacks: BlockNodeCallbacks;
  label: string;
  upstreamOmeFields: string[] | undefined;
  selectedNodeId: string | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildBlockNode(opts: BlockOpts): Node<any> {
  const {
    node,
    position,
    params,
    summary,
    schema,
    status,
    errorMessage,
    errorSummary,
    callbacks,
    label,
    upstreamOmeFields,
    selectedNodeId,
  } = opts;
  return {
    id: node.id,
    type: "block",
    position,
    // Block nodes are fixed-width 280px (ARCHITECTURE §9.5).
    initialWidth: 280,
    initialHeight: 180,
    data: {
      label,
      blockType: node.block_type,
      category: summary?.base_category ?? schema?.base_category ?? "custom",
      summary,
      schema,
      config: params,
      inputPorts: resolveVariadicPorts(
        schema?.input_ports ?? summary?.input_ports ?? [],
        params,
        "input",
        schema,
      ),
      outputPorts: resolveVariadicPorts(
        schema?.output_ports ?? summary?.output_ports ?? [],
        params,
        "output",
        schema,
      ),
      status,
      errorMessage,
      errorSummary,
      selected: selectedNodeId === node.id,
      onRun: callbacks.onRun,
      onRestart: callbacks.onRestart,
      onDelete: callbacks.onDelete,
      onUpdateConfig: callbacks.onUpdateConfig,
      onErrorClick: callbacks.onErrorClick,
      upstreamOmeFields,
    },
    selected: selectedNodeId === node.id,
  };
}
