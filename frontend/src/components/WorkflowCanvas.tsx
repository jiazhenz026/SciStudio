import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useMemo, useState } from "react";

import { resolveTypeColor } from "../config/typeColorMap";
import type {
  BlockPortResponse,
  BlockSchemaResponse,
  BlockSummary,
  WorkflowEdge,
  WorkflowNode,
} from "../types/api";
import type { BlockNodeData } from "../types/ui";
import { collectUpstreamOmeFields } from "./WorkflowEditor/LossySaveWarning";
import { AnnotationNode } from "./nodes/AnnotationNode";
import { BlockNode } from "./nodes/BlockNode";
import { GroupNode } from "./nodes/GroupNode";
import { TypedEdge } from "./TypedEdge";
import { TypeLegend } from "./TypeLegend";

const nodeTypes = {
  block: BlockNode,
  _annotation: AnnotationNode,
  _group: GroupNode,
};
const edgeTypes = { typed: TypedEdge };

/**
 * For variadic blocks, merge config-driven ports with schema-level ports.
 * Schema-level ports are empty ([]) for variadic blocks like DataRouter/PairEditor.
 * The actual ports are stored in config.input_ports / config.output_ports as
 * arrays of {name: string, types: string[]}.
 */
function resolveVariadicPorts(
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

  // Convert config port dicts to BlockPortResponse shape.
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

function parsePortRef(ref: string): { nodeId: string; portName: string } {
  const [nodeId, portName] = ref.split(":");
  return { nodeId, portName };
}

interface WorkflowCanvasProps {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  blocks: BlockSummary[];
  schemas: Record<string, BlockSchemaResponse>;
  blockStates: Record<string, string>;
  blockErrors: Record<string, string>;
  blockErrorSummaries: Record<string, string>;
  selectedNodeId: string | null;
  minimapVisible: boolean;
  onSelectNode: (nodeId: string | null) => void;
  onAddNode: (
    block: BlockSummary,
    position: { x: number; y: number },
    defaultParams?: Record<string, unknown>,
  ) => void;
  onUpdateNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
  onUpdateNodeConfig: (nodeId: string, config: Record<string, unknown>) => void;
  onConnect: (connection: WorkflowEdge) => Promise<void>;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edge: WorkflowEdge) => void;
  onRunBlock: (blockId: string) => void;
  onRestartBlock: (blockId: string) => void;
  onErrorClick: (blockId: string) => void;
  /**
   * Fires when the user clicks empty canvas pane (not a node or edge).
   * App.tsx wires this to ``bottomPanelRef.collapse()`` when the bottom
   * panel is not pinned, so a stray click on empty canvas folds the
   * panel down to its tab strip.
   */
  onPaneClick?: () => void;
  /**
   * ADR-043 FR-014 — optional map of `blockId -> output payload` used by the
   * SaveImage `LossySaveWarning` chip. The payload shape matches the
   * `blockOutputs` slice in `useAppStore`; the canvas walks upstream edges
   * to find the OME field list on the source block's outputs and forwards
   * it via `BlockNodeData.upstreamOmeFields`. When omitted, no warning is
   * computed (forward-compatible with callers that don't yet wire it).
   */
  blockOutputs?: Record<string, Record<string, unknown>>;
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  const reactFlow = useReactFlow();
  const {
    blocks,
    schemas,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    edges,
    minimapVisible,
    nodes,
    onAddNode,
    onConnect,
    onDeleteEdge,
    onDeleteNode,
    onErrorClick,
    onPaneClick,
    onRestartBlock,
    onRunBlock,
    onSelectNode,
    onUpdateNodeConfig,
    onUpdateNodePosition,
    selectedNodeId,
    blockOutputs,
  } = props;

  // Collect the set of type names and merged type hierarchy present across
  // all ports in the workflow for the TypeLegend component.
  const activeTypes = useMemo<Set<string>>(() => {
    const types = new Set<string>();
    for (const node of nodes) {
      const schema = schemas[node.block_type];
      if (!schema) continue;
      for (const port of [...(schema.input_ports ?? []), ...(schema.output_ports ?? [])]) {
        if (port.accepted_types.length === 0) {
          types.add("Any");
        } else {
          for (const t of port.accepted_types) {
            types.add(t);
          }
        }
      }
    }
    return types;
  }, [nodes, schemas]);

  const mergedTypeHierarchy = useMemo(() => {
    for (const schema of Object.values(schemas)) {
      if (schema?.type_hierarchy?.length) return schema.type_hierarchy;
    }
    return undefined;
  }, [schemas]);

  // Track positions locally during drag so nodes follow the cursor smoothly.
  // ReactFlow is in controlled mode (nodes prop), so without this the node
  // would only jump to its final position on drag-stop.
  const [dragPositions, setDragPositions] = useState<Record<string, { x: number; y: number }>>({});

  const makeOnRun = useCallback((nodeId: string) => () => onRunBlock(nodeId), [onRunBlock]);
  const makeOnRestart = useCallback(
    (nodeId: string) => () => onRestartBlock(nodeId),
    [onRestartBlock],
  );
  const makeOnDelete = useCallback((nodeId: string) => () => onDeleteNode(nodeId), [onDeleteNode]);
  const makeOnErrorClick = useCallback(
    (nodeId: string) => () => onErrorClick(nodeId),
    [onErrorClick],
  );
  const makeOnUpdateConfig = useCallback(
    (nodeId: string) => (patch: Record<string, unknown>) => onUpdateNodeConfig(nodeId, patch),
    [onUpdateNodeConfig],
  );

  /** Derive canvas display label for a node. For io_block nodes the label
   *  reflects the configured direction (Load Block / Save Block). */
  const resolveLabel = useCallback(
    (node: WorkflowNode, summary?: BlockSummary, schema?: BlockSchemaResponse) => {
      if (node.block_type === "io_block") {
        const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
        const direction = params.direction as string | undefined;
        if (direction === "output") return "Save Block";
        return "Load Block";
      }
      return summary?.name ?? schema?.name ?? node.block_type;
    },
    [],
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const flowNodes = useMemo<Array<Node<any>>>(() => {
    return nodes.map((node, index) => {
      const storePos = node.layout ?? { x: 120 + index * 80, y: 120 + index * 40 };
      const position = dragPositions[node.id] ?? storePos;
      const params = ((node.config.params as Record<string, unknown> | undefined) ?? {}) as Record<
        string,
        unknown
      >;

      // Annotation node
      if (node.block_type === "_annotation") {
        return {
          id: node.id,
          type: "_annotation",
          position,
          // ``initialWidth`` / ``initialHeight`` give the MiniMap a
          // bounding box to draw before ReactFlow's ResizeObserver
          // populates ``measured``. Our ``onNodesChange`` only forwards
          // position changes (dimension changes are intentionally not
          // round-tripped through the zustand store), so without these
          // the minimap permanently sees ``measured === undefined`` and
          // skips the node — see @xyflow/system ``nodeHasDimensions``.
          initialWidth: 200,
          initialHeight: 80,
          data: {
            text: (params.text as string) ?? "Note",
            onUpdateText: (text: string) => onUpdateNodeConfig(node.id, { text }),
          },
          selected: selectedNodeId === node.id,
        };
      }

      // Group frame node
      if (node.block_type === "_group") {
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

      // Regular block node
      const summary = blocks.find((block) => block.type_name === node.block_type);
      const schema = schemas[node.block_type];

      // ADR-043 FR-014 — derive upstream OME fields by walking incoming
      // edges and inspecting the source block's cached outputs for an OME
      // payload (typed Image.Meta.ome). Cheap when blockOutputs is
      // undefined or the node has no upstream IO; the LossySaveWarning
      // chip self-suppresses when the resulting list is empty.
      // Fix #1313 bug 1: collection-shaped payloads
      // (``{ kind: "collection", items: [...] }``) carry metadata under
      // ``items[*].metadata``; recursion lives in
      // ``collectUpstreamOmeFields``.
      const upstreamOmeFields = (() => {
        if (!blockOutputs) return undefined;
        const sourceIds = edges
          .filter((edge) => edge.target.split(":")[0] === node.id)
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
      })();

      return {
        id: node.id,
        type: "block",
        position,
        // Block nodes are fixed-width 280px (ARCHITECTURE §9.5). Height
        // varies with inline params + ports; 180px is a reasonable
        // average and is only used by the MiniMap until the real node
        // mounts and ReactFlow measures it. See annotation comment
        // above for why we need this.
        initialWidth: 280,
        initialHeight: 180,
        data: {
          label: resolveLabel(node, summary, schema),
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
          status: blockStates[node.id] ?? "idle",
          errorMessage: blockErrors[node.id],
          errorSummary: blockErrorSummaries[node.id],
          selected: selectedNodeId === node.id,
          onRun: makeOnRun(node.id),
          onRestart: makeOnRestart(node.id),
          onDelete: makeOnDelete(node.id),
          onUpdateConfig: makeOnUpdateConfig(node.id),
          onErrorClick: makeOnErrorClick(node.id),
          upstreamOmeFields,
        },
        selected: selectedNodeId === node.id,
      };
    });
  }, [
    blocks,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    blockOutputs,
    dragPositions,
    edges,
    makeOnDelete,
    makeOnErrorClick,
    makeOnRestart,
    makeOnRun,
    makeOnUpdateConfig,
    nodes,
    onUpdateNodeConfig,
    resolveLabel,
    schemas,
    selectedNodeId,
  ]);

  const flowEdges = useMemo<Array<Edge>>(() => {
    return edges.map((edge) => {
      const source = parsePortRef(edge.source);
      const target = parsePortRef(edge.target);
      const sourceNode = nodes.find((node) => node.id === source.nodeId);
      const sourceSchema = sourceNode ? schemas[sourceNode.block_type] : undefined;
      const sourcePort = sourceSchema?.output_ports.find((port) => port.name === source.portName);
      return {
        id: `${edge.source}->${edge.target}`,
        source: source.nodeId,
        sourceHandle: source.portName,
        target: target.nodeId,
        targetHandle: target.portName,
        type: "typed",
        data: {
          color: resolveTypeColor(sourcePort?.accepted_types ?? [], sourceSchema?.type_hierarchy),
          dashed: false,
        },
      };
    });
  }, [edges, nodes, schemas]);

  return (
    <div
      className="relative h-full"
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(event) => {
        event.preventDefault();
        const payload = event.dataTransfer.getData("application/scistudio-block");
        if (!payload) {
          return;
        }
        const parsed = JSON.parse(payload) as BlockSummary & { _default_direction?: string };
        const position = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
        onAddNode(
          parsed,
          position,
          parsed._default_direction ? { direction: parsed._default_direction } : undefined,
        );
      }}
    >
      <ReactFlow
        edges={flowEdges}
        edgeTypes={edgeTypes}
        fitView
        nodeTypes={nodeTypes}
        nodes={flowNodes}
        onNodesChange={(changes: NodeChange<Node<BlockNodeData>>[]) => {
          // Apply position changes locally during drag so nodes follow the
          // cursor in real time. Other change types (select, remove, etc.)
          // are handled by dedicated callbacks below.
          const positionUpdates: Record<string, { x: number; y: number }> = {};
          for (const change of changes) {
            if (change.type === "position" && change.position) {
              positionUpdates[change.id] = change.position;
            }
          }
          if (Object.keys(positionUpdates).length > 0) {
            setDragPositions((prev) => ({ ...prev, ...positionUpdates }));
          }
        }}
        onConnect={async (connection: Connection) => {
          if (
            !connection.source ||
            !connection.target ||
            !connection.sourceHandle ||
            !connection.targetHandle
          ) {
            return;
          }
          await onConnect({
            source: `${connection.source}:${connection.sourceHandle}`,
            target: `${connection.target}:${connection.targetHandle}`,
          });
        }}
        onEdgeClick={(_, edge) => {
          const match = edges.find(
            (candidate) => `${candidate.source}->${candidate.target}` === edge.id,
          );
          if (match) {
            onDeleteEdge(match);
          }
        }}
        onEdgesDelete={(deleted) => {
          deleted.forEach((edge) => {
            const match = edges.find(
              (candidate) => `${candidate.source}->${candidate.target}` === edge.id,
            );
            if (match) {
              onDeleteEdge(match);
            }
          });
        }}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        onNodeDragStop={(_, node) => {
          // Persist the final position to the store and clear the local
          // drag override so subsequent renders use the store value.
          onUpdateNodePosition(node.id, node.position);
          setDragPositions((prev) => {
            const next = { ...prev };
            delete next[node.id];
            return next;
          });
        }}
        onNodesDelete={(deleted) => deleted.forEach((node) => onDeleteNode(node.id))}
        onPaneClick={() => {
          onSelectNode(null);
          onPaneClick?.();
        }}
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        {minimapVisible && (
          <MiniMap
            pannable
            zoomable
            maskColor="rgba(245, 241, 232, 0.7)"
            style={{ backgroundColor: "#faf8f4" }}
            nodeColor={(node) => {
              if (node.type === "_annotation" || node.type === "_group") {
                return "#d6d3d1";
              }
              const data = node.data as BlockNodeData | undefined;
              const color = resolveTypeColor(data?.outputPorts?.[0]?.accepted_types ?? []);
              // Fallback DataObject gray (#e5e7eb) is nearly invisible on
              // the light minimap background — use a darker substitute.
              return color === "#e5e7eb" ? "#9ca3af" : color;
            }}
          />
        )}
        <Controls />
        <Background color="#d8d2c4" gap={20} size={1.2} />
      </ReactFlow>
      <TypeLegend activeTypes={activeTypes} typeHierarchy={mergedTypeHierarchy} />
    </div>
  );
}
