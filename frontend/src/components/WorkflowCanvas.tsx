import { Background, Controls, ReactFlow, type Edge, useReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";

import { resolveTypeColor } from "../config/typeColorMap";
import type { BlockSchemaResponse, BlockSummary, WorkflowEdge, WorkflowNode } from "../types/api";
import { AnnotationNode } from "./nodes/AnnotationNode";
import { BlockNode } from "./nodes/BlockNode";
import { GroupNode } from "./nodes/GroupNode";
import { TypedEdge } from "./TypedEdge";
import { TypeLegend } from "./TypeLegend";
import { parsePortRef } from "./WorkflowCanvas.parts/flowNodeBuilder";
import { useCanvasHandlers } from "./WorkflowCanvas.parts/useCanvasHandlers";
import { useFlowCallbacks } from "./WorkflowCanvas.parts/useFlowCallbacks";
import { useFlowNodes } from "./WorkflowCanvas.parts/useFlowNodes";
import { WorkflowMiniMap } from "./WorkflowCanvas.parts/WorkflowMiniMap";

const nodeTypes = {
  block: BlockNode,
  _annotation: AnnotationNode,
  _group: GroupNode,
};
const edgeTypes = { typed: TypedEdge };

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
  /** Fires on empty-canvas click. App.tsx folds the bottom panel here. */
  onPaneClick?: () => void;
  /** ADR-043 FR-014 — `blockId -> output payload` for LossySaveWarning chip. */
  blockOutputs?: Record<string, Record<string, unknown>>;
}

interface UseActiveTypesResult {
  activeTypes: Set<string>;
  mergedTypeHierarchy: BlockSchemaResponse["type_hierarchy"] | undefined;
}

function useActiveTypes(
  nodes: WorkflowNode[],
  schemas: Record<string, BlockSchemaResponse>,
): UseActiveTypesResult {
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

  return { activeTypes, mergedTypeHierarchy };
}

function useFlowEdges(
  edges: WorkflowEdge[],
  nodes: WorkflowNode[],
  schemas: Record<string, BlockSchemaResponse>,
): Edge[] {
  return useMemo(() => {
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

  const { activeTypes, mergedTypeHierarchy } = useActiveTypes(nodes, schemas);

  // Track positions locally during drag so nodes follow the cursor smoothly.
  const [dragPositions, setDragPositions] = useState<Record<string, { x: number; y: number }>>({});

  const flowCallbacks = useFlowCallbacks({
    onRunBlock,
    onRestartBlock,
    onDeleteNode,
    onErrorClick,
    onUpdateNodeConfig,
  });

  const flowNodes = useFlowNodes({
    nodes,
    edges,
    blocks,
    schemas,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    selectedNodeId,
    blockOutputs,
    dragPositions,
    onUpdateNodeConfig,
    ...flowCallbacks,
  });

  const flowEdges = useFlowEdges(edges, nodes, schemas);

  const handlers = useCanvasHandlers({
    reactFlow,
    edges,
    onAddNode,
    onConnect,
    onDeleteEdge,
    onDeleteNode,
    onSelectNode,
    onPaneClick,
    onUpdateNodePosition,
    setDragPositions,
  });

  return (
    <div
      className="relative h-full"
      onDragOver={handlers.handleDragOver}
      onDrop={handlers.handleDrop}
    >
      <ReactFlow
        edges={flowEdges}
        edgeTypes={edgeTypes}
        fitView
        nodeTypes={nodeTypes}
        nodes={flowNodes}
        onNodesChange={handlers.handleNodesChange}
        onConnect={handlers.handleConnect}
        onEdgeClick={handlers.handleEdgeClick}
        onEdgesDelete={handlers.handleEdgesDelete}
        onNodeClick={handlers.handleNodeClick}
        onNodeDragStop={handlers.handleNodeDragStop}
        onNodesDelete={handlers.handleNodesDelete}
        onPaneClick={handlers.handlePaneClick}
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        {minimapVisible && <WorkflowMiniMap />}
        <Controls />
        <Background color="#d8d2c4" gap={20} size={1.2} />
      </ReactFlow>
      <TypeLegend activeTypes={activeTypes} typeHierarchy={mergedTypeHierarchy} />
    </div>
  );
}
