/**
 * Event handlers bundle for WorkflowCanvas. Extracted in #1413.
 */
import type { Connection, Edge, Node, NodeChange, useReactFlow } from "@xyflow/react";
import { useCallback } from "react";

import { NODE_SIZE } from "../nodes/BlockNode.parts/nodeGeometry";
import {
  NOTHING_TO_EXPLORE_REASON,
  hasExploreableOutputs,
  packagedBlockNameFor,
} from "../../explore/packagedBlock";
import type { BlockSummary, WorkflowEdge, WorkflowNode } from "../../types/api";
import type { CanvasContextMenuState } from "./NodeContextMenu";

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
  /**
   * ADR-054 FR-002 - `nodeId -> output payload` for the context menu's
   * disabled test. The same map the canvas already receives for the
   * lossy-save chip; a node absent from it has produced nothing to explore.
   */
  blockOutputs?: Record<string, Record<string, unknown>>;
  /**
   * ADR-054 FR-004 - the block catalogue, so the double-click can tell a
   * packaged block's node from an ordinary one. OPTIONAL so existing call
   * sites compile; absent means no node is treated as packaged.
   */
  blocks?: BlockSummary[];
  /**
   * ADR-054 FR-003 - open the node context menu. The menu itself is state on
   * `WorkflowCanvas`; this handler is what computes what it may offer.
   */
  onOpenNodeContextMenu?: (menu: CanvasContextMenuState) => void;
  /**
   * ADR-054 FR-004 - double-click on a packaged block's node opens its
   * notebook in an Explore tab bound to the node's most recent run.
   */
  onOpenPackagedNotebook?: (blockName: string, nodeId: string) => void;
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
    blockOutputs,
    blocks,
    onOpenNodeContextMenu,
    onOpenPackagedNotebook,
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
      // #2151 — a React Flow node position is the node's TOP-LEFT corner, so
      // a raw drop lands the block down-right of the cursor. Re-anchor on the
      // fixed square body's centre (ADR-050 §2.1): the block the user was
      // dragging lands centred under the mouse. The label below the square is
      // absolutely positioned and adds nothing to the node's flow footprint,
      // so NODE_SIZE is the whole offset.
      onAddNode(
        parsed,
        { x: position.x - NODE_SIZE / 2, y: position.y - NODE_SIZE / 2 },
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
      // ADR-054 FR-004 - a packaged block's node is the second kind of node
      // this handler recognises, beside the subworkflow node it already did.
      // Checked first because a packaged block is an ordinary block type and
      // would otherwise fall straight through the subworkflow guard below.
      const summary = blocks?.find((candidate) => candidate.type_name === authored.block_type);
      const packagedName = packagedBlockNameFor(authored, summary);
      if (packagedName) {
        onOpenPackagedNotebook?.(packagedName, node.id);
        return;
      }
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
    [
      nodes,
      runScopePrefix,
      onOpenSubworkflow,
      onLocateSubworkflow,
      blocks,
      onOpenPackagedNotebook,
    ],
  );

  /**
   * ADR-054 FR-003 - the canvas's first context menu.
   *
   * The browser menu is suppressed on a node and offered on nothing else, so
   * right-clicking the pane still behaves as it did. FR-002's disabled case is
   * decided here rather than in the menu: the menu draws what it is told, and
   * "this block has produced no outputs" is a fact about the run, which is
   * what this hook has in hand.
   */
  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (!onOpenNodeContextMenu) return;
      event.preventDefault();
      const canExplore = hasExploreableOutputs(node.id, blockOutputs);
      // The rendered label, which is what the person right-clicked; the
      // authored node carries only its id and its block type.
      const label = (node.data as { label?: string } | undefined)?.label;
      onOpenNodeContextMenu({
        x: event.clientX,
        y: event.clientY,
        nodeId: node.id,
        nodeLabel: label || node.id,
        canExplore,
        disabledReason: canExplore ? null : NOTHING_TO_EXPLORE_REASON,
      });
    },
    [blockOutputs, onOpenNodeContextMenu],
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
    handleNodeContextMenu,
    handleNodeDoubleClick,
    handleNodesDelete,
    handlePaneClick,
  };
}
