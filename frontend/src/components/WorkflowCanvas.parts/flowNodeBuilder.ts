/**
 * `flowNodes` builder helpers extracted from WorkflowCanvas.tsx (#1413 /
 * #1414).
 *
 * Each helper returns the ReactFlow node object for one workflow node. The
 * mapper in WorkflowCanvas dispatches to the right helper by block_type.
 */
import type { Node } from "@xyflow/react";

import { lossyOmeFields } from "../../api/capabilities";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  BlockSummary,
  FormatCapabilityResponse,
  ResolvedSubworkflowPort,
  TypeHierarchyEntry,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import type { BlockNodeData, SubWorkflowNodeData } from "../../types/ui";
import { collectUpstreamOmeFields } from "../WorkflowEditor/LossySaveWarning";

import { NODE_SIZE } from "../nodes/BlockNode.parts/nodeGeometry";

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
  /** Live size during an in-progress NodeResizer drag (overrides config.style). */
  size?: { width: number; height: number };
  params: Record<string, unknown>;
  selectedNodeId: string | null;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
}

export function buildAnnotationNode(opts: AnnotationOpts): Node {
  const { node, position, size, params, selectedNodeId, onUpdateNodeConfig } = opts;
  const style = node.config.style as Record<string, unknown> | undefined;
  // Annotation notes are resizable (NodeResizer); the live drag size wins, then
  // the persisted width/height in config.style, then a comfortable default.
  const width = size?.width ?? (style?.width as number) ?? 240;
  const height = size?.height ?? (style?.height as number) ?? 120;
  return {
    id: node.id,
    type: "_annotation",
    position,
    // ``initialWidth`` / ``initialHeight`` give the MiniMap a bounding box
    // to draw before ReactFlow's ResizeObserver populates ``measured``.
    initialWidth: width,
    initialHeight: height,
    style: { width, height },
    data: {
      text: (params.text as string) ?? "Note",
      onUpdateText: (text: string) => onUpdateNodeConfig(node.id, { text }),
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
  onDelete: () => void;
  onUpdateConfig: (patch: Record<string, unknown>) => void;
  onErrorClick: () => void;
  /**
   * ADR-050 §2.5 / FR-013 — warning-status activation: select node + open
   * BottomPanel Config detail. OPTIONAL so FE-2's existing call sites compile
   * before the integration merge wires `makeOnWarningClick`.
   */
  onWarningClick?: () => void;
}

/**
 * #1988 — what a node's `block_type` string alone can tell us, once the block
 * itself has failed to resolve.
 *
 * `block_type` is an IDENTIFIER, not a category: the real `base_category` is
 * derived on the backend from the class hierarchy (`issubclass(cls, IOBlock)`
 * and friends), which needs a class that can actually be imported. An
 * unresolved block is precisely the case where there is no class to ask, so
 * the name is all that is left.
 *
 * Scope is deliberately IO-only (owner directive). The case this exists for is
 * an agent wiring a package-owned load block instead of the core one — package
 * loaders are folded into the core Load block by design and are not offered
 * separately, so an agent naming one produces a node that cannot resolve here.
 * Owner feedback on #1988: "even when the agent picked the wrong block, a
 * loader should still read as a loader". It stays a guess about APPEARANCE
 * only — `unresolved` is tracked separately and still drives the dashed body
 * and the warning badge, so a prettier colour never hides the defect.
 *
 * Anything that is not recognisably IO returns `unresolved` rather than a
 * broader guess; there is no general name→category heuristic here.
 */
export function inferUnresolvedCategory(blockType: string): {
  category: string;
  iconHint?: string;
} {
  // Match on snake_case word boundaries so `payload_block` never reads as a
  // "load" and `download_block` never reads as a save.
  const words = blockType
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  const has = (...candidates: string[]) => candidates.some((c) => words.includes(c));
  if (has("save", "write", "export", "dump")) {
    return { category: "io", iconHint: "folder-output" };
  }
  if (has("load", "read", "import", "open")) {
    return { category: "io", iconHint: "folder-input" };
  }
  return { category: "unresolved" };
}

/**
 * ADR-050 §2.5 — compute the highest-priority problem signal for a node.
 *
 * Priority: an `error` runtime status is always "error". Otherwise, for a
 * save-direction IO node that has upstream OME fields and a selected (or
 * single) capability whose `metadata_fidelity` would drop any of those fields,
 * the severity is "warning" (the lossy-save signal — verbose detail lives in
 * BottomPanel Config, FR-014). Everything else is "none".
 *
 * #1988 — an unresolved `block_type` is also a "warning". It outranks the
 * lossy-save check because it is unconditional: a node whose block cannot be
 * loaded has no schema, so no other signal on this node can fire. This is the
 * half of #1988 that colour cannot do. Until #1988 nothing reported these nodes
 * at all — `validate_workflow`'s unregistered-type check walked EDGES, and an
 * unresolved node has no ports and therefore no edges. The validator now also
 * reports them per node (Check 4.5); this is the same fact on the canvas, where
 * the user is actually looking when they place the node.
 */
export function computeProblemSeverity(opts: {
  status: string;
  category: string;
  schema?: BlockSchemaResponse;
  config: Record<string, unknown>;
  upstreamOmeFields: string[] | undefined;
  /** #1988 — true when neither a summary nor a schema resolved for this node. */
  unresolved?: boolean;
}): BlockNodeData["problemSeverity"] {
  const { status, category, schema, config, upstreamOmeFields, unresolved } = opts;
  if (status === "error") return "error";
  if (unresolved) return "warning";

  const isSaveIo =
    category === "io" && (schema?.direction === "output" || schema?.direction === "save");
  if (!isSaveIo || !upstreamOmeFields || upstreamOmeFields.length === 0) return "none";

  const capabilities = schema?.format_capabilities ?? [];
  const selectedId = config.capability_id;
  const selectedCap: FormatCapabilityResponse | undefined =
    capabilities.find((cap) => typeof selectedId === "string" && cap.id === selectedId) ??
    (capabilities.length === 1 ? capabilities[0] : undefined);
  if (!selectedCap) return "none";

  const dropped = lossyOmeFields(upstreamOmeFields, selectedCap.metadata_fidelity);
  return dropped.length > 0 ? "warning" : "none";
}

interface BlockOpts {
  node: WorkflowNode;
  position: { x: number; y: number };
  params: Record<string, unknown>;
  summary?: BlockSummary;
  schema?: BlockSchemaResponse;
  status: string;
  /** #1974 — epoch-ms start of the current run; undefined unless running. */
  runStartedAt?: number;
  errorMessage: string | undefined;
  errorSummary: string | undefined;
  callbacks: BlockNodeCallbacks;
  label: string;
  upstreamOmeFields: string[] | undefined;
  selectedNodeId: string | null;
  /** #1799 — true when the plot picker is hovering/selecting this node. */
  highlighted?: boolean;
}

export function buildBlockNode(opts: BlockOpts): Node {
  const {
    node,
    position,
    params,
    summary,
    schema,
    status,
    runStartedAt,
    errorMessage,
    errorSummary,
    callbacks,
    label,
    upstreamOmeFields,
    selectedNodeId,
    highlighted,
  } = opts;
  // #1988 — an EMPTY base_category still counts as resolved: the block was
  // found, the backend simply reports "unknown" for a direct `Block` subclass.
  // Only the absence of BOTH a summary and a schema means the `block_type`
  // resolved to nothing here, and that is the state that must stay visible.
  const resolvedCategory = summary?.base_category || schema?.base_category;
  const unresolved = !summary && !schema;
  const inferred = unresolved ? inferUnresolvedCategory(node.block_type) : undefined;
  const category = resolvedCategory || inferred?.category || "unknown";
  // ADR-050 §2.5 — highest-priority problem signal, surfaced by the node's
  // unified NodeStatusSurface (error from runtime status, warning from the
  // lossy-save check or an unresolved block type). Verbose detail stays in
  // Logs / BottomPanel.
  const problemSeverity = computeProblemSeverity({
    status,
    category,
    schema,
    config: params,
    upstreamOmeFields,
    unresolved,
  });
  return {
    id: node.id,
    type: "block",
    position,
    // ADR-050 §2.1 / FR-001-FR-002 — fixed 104×104 square topology glyph
    // (replaces the old 280×180 card). MUST equal nodeGeometry.NODE_SIZE.
    initialWidth: NODE_SIZE,
    initialHeight: NODE_SIZE,
    data: {
      label,
      blockType: node.block_type,
      category,
      // #1988 — carried so the node can draw the dashed body and so the
      // warning badge can say WHY, instead of the generic Config wording.
      unresolved,
      uiIconHint: inferred?.iconHint,
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
      runStartedAt,
      errorMessage,
      errorSummary,
      problemSeverity,
      selected: selectedNodeId === node.id,
      highlighted: highlighted ?? false,
      onRun: callbacks.onRun,
      onDelete: callbacks.onDelete,
      onUpdateConfig: callbacks.onUpdateConfig,
      onErrorClick: callbacks.onErrorClick,
      onWarningClick: callbacks.onWarningClick,
      upstreamOmeFields,
    },
    selected: selectedNodeId === node.id,
  };
}

/**
 * ADR-044 §3 — convert one `resolved_ports` entry into the `BlockPortResponse`
 * shape `PortHandles` consumes. The port `name` becomes the React Flow handle
 * id (ADR-044 locked contract item 4), and `accepted_types` drive the port
 * colour. The remaining BlockPortResponse fields are inert placeholders;
 * subworkflow ports are never variadic and never user-editable.
 */
function resolvedPortToBlockPort(
  port: ResolvedSubworkflowPort,
  direction: "input" | "output",
): BlockPortResponse {
  return {
    name: port.name,
    direction,
    accepted_types: port.accepted_types ?? [],
    required: false,
    description: "",
    constraint_description: "",
    is_collection: false,
  };
}

export interface SubWorkflowOpts {
  node: WorkflowNode;
  position: { x: number; y: number };
  label: string;
  selectedNodeId: string | null;
  /** Shared type hierarchy (any block schema's copy) for port colours. */
  typeHierarchy?: TypeHierarchyEntry[];
  /** ADR-044 — aggregated run status of the flattened inner blocks. */
  status: string;
  onDelete: () => void;
  /** ADR-044 §10 — broken-ref "locate file…" affordance. */
  onLocateFile: () => void;
}

/**
 * ADR-044 §3 — build the ReactFlow node for a `subworkflow` /
 * `subworkflow_broken` authoring container. Ports are packed from the
 * response-only `node.resolved_ports` surface; `refPath` and `broken` are
 * derived from `resolved_ports` (with `config.ref.path` as the source of
 * truth for the path) so the broken placeholder can show the unresolved ref.
 */
export function buildSubWorkflowNode(opts: SubWorkflowOpts): Node {
  const { node, position, label, selectedNodeId, typeHierarchy, status, onDelete, onLocateFile } =
    opts;

  const resolved = node.resolved_ports;

  const ref = node.config.ref as { path?: string } | undefined;
  // Prefer the persisted config.ref.path; fall back to the response ref_path so
  // a broken placeholder still shows something useful.
  const refPath = ref?.path ?? resolved?.ref_path ?? null;

  // ADR-044 §10 / FR-011 — `subworkflow_broken` is broken by block_type; a
  // `subworkflow_block` node is also treated as broken when its resolved_ports
  // surface flags it (unresolved ref) OR when it has no usable ref at all. A
  // freshly dropped node has no ref, so it MUST surface the "Choose subworkflow
  // file…" affordance (the same shared flow as the broken-ref "Locate file…").
  const broken = node.block_type === "subworkflow_broken" || resolved?.broken === true || !refPath;

  const inputPorts = broken
    ? []
    : (resolved?.inputs ?? []).map((port) => resolvedPortToBlockPort(port, "input"));
  const outputPorts = broken
    ? []
    : (resolved?.outputs ?? []).map((port) => resolvedPortToBlockPort(port, "output"));

  const data: SubWorkflowNodeData = {
    label,
    blockType: node.block_type,
    refPath,
    broken,
    inputPorts,
    outputPorts,
    typeHierarchy,
    status,
    selected: selectedNodeId === node.id,
    onDelete,
    onLocateFile,
  };

  return {
    id: node.id,
    type: "subworkflow",
    position,
    initialWidth: NODE_SIZE,
    initialHeight: NODE_SIZE,
    data,
    selected: selectedNodeId === node.id,
  };
}
