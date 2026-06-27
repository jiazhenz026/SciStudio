/**
 * Event handlers bundle for WorkflowCanvas. Extracted in #1413.
 */
import type { Connection, Edge, Node, NodeChange, useReactFlow } from "@xyflow/react";
import { useCallback } from "react";

import type { BlockSummary, WorkflowEdge, WorkflowNode } from "../../types/api";

export interface CanvasHandlersOpts {
  reactFlow: ReturnType<typeof useReactFlow>;
  edges: WorkflowEdge[];
  /**
   * ADR-044 — authored workflow nodes, used by `handleNodeDoubleClick` to read
   * a subworkflow node's `config.ref.path` and block type. OPTIONAL so existing
   * call sites compile.
   */
  nodes?: WorkflowNode[];
  /**
   * ADR-044 — this canvas's run-scope prefix (`""` for a top-level workflow,
   * `"<sw>__"` when it is the expanded child of a subworkflow). Used to COMPOSE
   * the child prefix passed to `onOpenSubworkflow` so nested expansion maps to
   * the right flattened run ids.
   */
  runScopePrefix?: string;
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
  /** Persist a resizable node's size when a NodeResizer drag ends. */
  onResizeNode?: (nodeId: string, size: { width: number; height: number }) => void;
  setDragPositions: React.Dispatch<React.SetStateAction<Record<string, { x: number; y: number }>>>;
  setDragSizes: React.Dispatch<
    React.SetStateAction<Record<string, { width: number; height: number }>>
  >;
  /**
   * ADR-044 §3 — open a (healthy) subworkflow node's referenced file in a
   * canvas tab on double-click. OPTIONAL.
   */
  onOpenSubworkflow?: (refPath: string, runPrefix?: string) => void;
  /**
   * ADR-044 §10 — surface the broken-ref "locate file…" affordance on
   * double-click of a `subworkflow_broken` / unresolved node. OPTIONAL.
   */
  onLocateSubworkflow?: (nodeId: string) => void;
}

export function useCanvasHandlers(opts: CanvasHandlersOpts) {
  const {
    reactFlow,
    edges,
    nodes,
    runScopePrefix = "",
    onAddNode,
    onConnect,
    onDeleteEdge,
    onDeleteNode,
    onSelectNode,
    onPaneClick,
    onUpdateNodePosition,
    onResizeNode,
    setDragPositions,
    setDragSizes,
    onOpenSubworkflow,
    onLocateSubworkflow,
  } = opts;

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const positionUpdates: Record<string, { x: number; y: number }> = {};
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          positionUpdates[change.id] = change.position;
        }
        // NodeResizer emits dimensions changes with `resizing: true` during the
        // drag and a final `resizing: false` on release. ReactFlow is controlled
        // here, so the live size must be fed back through dragSizes or the body
        // stays locked at the persisted size until release. A top/left-anchored
        // resize ALSO moves the origin (position changes that land in
        // dragPositions). On release we persist the committed size + final
        // position, then clear both overrides.
        if (change.type === "dimensions" && change.dimensions) {
          if (change.resizing) {
            const { width, height } = change.dimensions;
            setDragSizes((prev) => ({ ...prev, [change.id]: { width, height } }));
          } else if (change.resizing === false) {
            if (onResizeNode) {
              onResizeNode(change.id, {
                width: change.dimensions.width,
                height: change.dimensions.height,
              });
            }
            const node = reactFlow.getNode(change.id);
            if (node) {
              onUpdateNodePosition(change.id, node.position);
            }
            setDragPositions((prev) => {
              if (!(change.id in prev)) return prev;
              const next = { ...prev };
              delete next[change.id];
              return next;
            });
            setDragSizes((prev) => {
              if (!(change.id in prev)) return prev;
              const next = { ...prev };
              delete next[change.id];
              return next;
            });
          }
        }
      }
      if (Object.keys(positionUpdates).length > 0) {
        setDragPositions((prev) => ({ ...prev, ...positionUpdates }));
      }
    },
    [onResizeNode, onUpdateNodePosition, reactFlow, setDragPositions, setDragSizes],
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

  // ADR-044 §3 / §10 — double-clicking a subworkflow container opens its
  // referenced file (`config.ref.path`) in a canvas tab; a broken /
  // unresolved-ref node surfaces the "locate file…" affordance instead. All
  // other node types ignore double-click (no behaviour change for them).
  const handleNodeDoubleClick = useCallback(
    (_: unknown, node: Node) => {
      const authored = nodes?.find((candidate) => candidate.id === node.id);
      if (!authored) return;
      if (
        authored.block_type !== "subworkflow_block" &&
        authored.block_type !== "subworkflow_broken"
      ) {
        return;
      }
      const ref = authored.config.ref as { path?: string } | undefined;
      const refPath = ref?.path ?? authored.resolved_ports?.ref_path ?? null;
      const broken =
        authored.block_type === "subworkflow_broken" ||
        authored.resolved_ports?.broken === true ||
        !refPath;
      if (broken) {
        onLocateSubworkflow?.(node.id);
        return;
      }
      // Compose the child's run-scope prefix from this canvas's prefix + the
      // node id so a nested expansion (child-of-child) still maps to the right
      // flattened run ids `<parentPrefix><nodeId>__<innerId>`.
      onOpenSubworkflow?.(refPath, `${runScopePrefix}${node.id}__`);
    },
    [nodes, runScopePrefix, onOpenSubworkflow, onLocateSubworkflow],
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
    handleNodeDoubleClick,
    handleNodesDelete,
    handlePaneClick,
  };
}
