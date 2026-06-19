/**
 * Event handlers bundle for WorkflowCanvas. Extracted in #1413.
 */
import type { Connection, Edge, Node, NodeChange, useReactFlow } from "@xyflow/react";
import { useCallback } from "react";

import type { BlockSummary, WorkflowEdge } from "../../types/api";

export interface CanvasHandlersOpts {
  reactFlow: ReturnType<typeof useReactFlow>;
  edges: WorkflowEdge[];
  onAddNode: (
    block: BlockSummary,
    position: { x: number; y: number },
    defaultParams?: Record<string, unknown>,
  ) => void;
  onConnect: (connection: WorkflowEdge) => Promise<void>;
  onDeleteEdge: (edge: WorkflowEdge) => void;
  onDeleteNode: (nodeId: string) => void;
  onSelectNode: (nodeId: string | null) => void;
  onPaneClick?: () => void;
  onUpdateNodePosition: (nodeId: string, position: { x: number; y: number }) => void;
  setDragPositions: React.Dispatch<React.SetStateAction<Record<string, { x: number; y: number }>>>;
}

export function useCanvasHandlers(opts: CanvasHandlersOpts) {
  const {
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
  } = opts;

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const positionUpdates: Record<string, { x: number; y: number }> = {};
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          positionUpdates[change.id] = change.position;
        }
      }
      if (Object.keys(positionUpdates).length > 0) {
        setDragPositions((prev) => ({ ...prev, ...positionUpdates }));
      }
    },
    [setDragPositions],
  );

  const handleConnect = useCallback(
    async (connection: Connection) => {
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
    },
    [onConnect],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const payload = event.dataTransfer.getData("application/scistudio-block");
      if (!payload) return;
      const parsed = JSON.parse(payload) as BlockSummary & { _default_direction?: string };
      const position = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      onAddNode(
        parsed,
        position,
        parsed._default_direction ? { direction: parsed._default_direction } : undefined,
      );
    },
    [onAddNode, reactFlow],
  );

  const handleEdgeClick = useCallback(
    (_: unknown, edge: Edge) => {
      const match = edges.find(
        (candidate) => `${candidate.source}->${candidate.target}` === edge.id,
      );
      if (match) onDeleteEdge(match);
    },
    [edges, onDeleteEdge],
  );

  const handleEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      deleted.forEach((edge) => {
        const match = edges.find(
          (candidate) => `${candidate.source}->${candidate.target}` === edge.id,
        );
        if (match) onDeleteEdge(match);
      });
    },
    [edges, onDeleteEdge],
  );

  const handleNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      onUpdateNodePosition(node.id, node.position);
      setDragPositions((prev) => {
        const next = { ...prev };
        delete next[node.id];
        return next;
      });
    },
    [onUpdateNodePosition, setDragPositions],
  );

  const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const handleNodeClick = useCallback(
    (_: unknown, node: Node) => onSelectNode(node.id),
    [onSelectNode],
  );

  const handleNodesDelete = useCallback(
    (deleted: Node[]) => deleted.forEach((node) => onDeleteNode(node.id)),
    [onDeleteNode],
  );

  const handlePaneClick = useCallback(() => {
    onSelectNode(null);
    onPaneClick?.();
  }, [onSelectNode, onPaneClick]);

  return {
    handleNodesChange,
    handleConnect,
    handleDrop,
    handleEdgeClick,
    handleEdgesDelete,
    handleNodeDragStop,
    handleDragOver,
    handleNodeClick,
    handleNodesDelete,
    handlePaneClick,
  };
}
