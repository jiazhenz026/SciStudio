import { Background, Controls, ReactFlow, type Edge, useReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";

import { resolveTypeColor } from "../config/typeColorMap";
import { useAppStore } from "../store";
import type { BlockSchemaResponse, BlockSummary, WorkflowEdge, WorkflowNode } from "../types/api";
import { computeEffectivePorts } from "../utils/computeEffectivePorts";
import { arePortTypesCompatible } from "../utils/portCompat";
import { AnnotationNode } from "./nodes/AnnotationNode";
import { BlockNode } from "./nodes/BlockNode";
import { SubWorkflowNode } from "./nodes/SubWorkflowNode";
import { TypedEdge } from "./TypedEdge";
import { applyFocusToEdges, applyFocusToNodes } from "./WorkflowCanvas.parts/applyFocus";
import { computeAutoLayout } from "./WorkflowCanvas.parts/autoLayout";
import { CanvasReadabilityControls } from "./WorkflowCanvas.parts/CanvasReadabilityControls";
import { parsePortRef, resolveVariadicPorts } from "./WorkflowCanvas.parts/flowNodeBuilder";
import { computeFocusSet, type FocusResult } from "./WorkflowCanvas.parts/focusMode";
import { useCanvasHandlers } from "./WorkflowCanvas.parts/useCanvasHandlers";
import { useFlowCallbacks } from "./WorkflowCanvas.parts/useFlowCallbacks";
import { useFlowNodes } from "./WorkflowCanvas.parts/useFlowNodes";
import { WorkflowMiniMap } from "./WorkflowCanvas.parts/WorkflowMiniMap";

const nodeTypes = {
  block: BlockNode,
  _annotation: AnnotationNode,
  // ADR-044 §3 — both `subworkflow` and `subworkflow_broken` render via the
  // SAME component; the broken placeholder is driven by `data.broken`.
  subworkflow: SubWorkflowNode,
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
  onResizeNode: (nodeId: string, size: { width: number; height: number }) => void;
  onUpdateNodeConfig: (nodeId: string, config: Record<string, unknown>) => void;
  onConnect: (connection: WorkflowEdge) => Promise<void>;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edge: WorkflowEdge) => void;
  onRunBlock: (blockId: string) => void;
  onRestartBlock: (blockId: string) => void;
  onErrorClick: (blockId: string) => void;
  /**
   * ADR-050 FR-013 — warning-status click handler. Selects the node and opens
   * the BottomPanel Config detail. Optional so existing call sites compile.
   */
  onWarningClick?: (blockId: string) => void;
  /** Fires on empty-canvas click. App.tsx folds the bottom panel here. */
  onPaneClick?: () => void;
  /** ADR-043 FR-014 — `blockId -> output payload` for LossySaveWarning chip. */
  blockOutputs?: Record<string, Record<string, unknown>>;
  /**
   * ADR-044 — run-scope prefix for status/error lookups when this canvas is the
   * expanded child of a subworkflow node (the flattened run keys carry the
   * parent prefix). Empty for a top-level workflow. Forwarded to `useFlowNodes`.
   */
  runScopePrefix?: string;
  // --- ADR-050 §3 focus mode + tidy layout (all optional) ----------------
  /** Focus-mode view state from the UI slice (FR-017/FR-018). */
  focusMode?: { enabled: boolean; selectedIds: string[]; depth: number };
  /** Enter focus mode around the current selection. */
  onEnterFocusMode?: (selectedIds: string[]) => void;
  /** Exit focus mode and restore normal canvas visibility. */
  onExitFocusMode?: () => void;
  /**
   * ADR-050 §3.2 / FR-022 / FR-024 — apply a batch of node layout positions in
   * one history entry. Writes only `node.layout`. Used by the tidy action.
   */
  onTidyLayout?: (positions: Record<string, { x: number; y: number }>) => void;
  /**
   * ADR-044 §3 / spec US 1 acceptance #3 — double-clicking a (healthy)
   * subworkflow node opens its referenced file (`config.ref.path`) in a canvas
   * tab. OPTIONAL so existing call sites compile; absent ⇒ double-click is a
   * no-op for subworkflow nodes.
   */
  onOpenSubworkflow?: (refPath: string, runPrefix?: string) => void;
  /**
   * ADR-044 §10 / spec US 6 acceptance #2 — broken-ref "locate file…"
   * affordance. Invoked by the placeholder's button and by double-clicking a
   * broken node. Full repoint persistence is deferred (TODO(#890)).
   */
  onLocateSubworkflow?: (nodeId: string) => void;
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
      const targetNode = nodes.find((node) => node.id === target.nodeId);
      const sourceSchema = sourceNode ? schemas[sourceNode.block_type] : undefined;
      const targetSchema = targetNode ? schemas[targetNode.block_type] : undefined;
      // #889 + Hotfix 2026-05-23: resolve the source port from the node's
      // effective output ports — same path BlockNode renders. The store's
      // ``mergeNodeConfig`` keeps user-editable params under
      // ``node.config.params``, so we read the params envelope and pass
      // it to both ``resolveVariadicPorts`` (variadic blocks store ports
      // at ``params.{input,output}_ports``) and the dynamic-port driving
      // value lookup (``params.core_type`` for LoadData / SaveData).
      // Reading ``node.config`` directly meant edge color/style fell back
      // to the static schema spec while BlockNode rendered the real
      // per-instance type — that was the visible "edge color mismatches
      // port color" symptom.
      const sourceParams = (sourceNode?.config.params as Record<string, unknown> | undefined) ?? {};
      const targetParams = (targetNode?.config.params as Record<string, unknown> | undefined) ?? {};
      const variadicSourcePorts =
        sourceNode && sourceSchema
          ? resolveVariadicPorts(
              sourceSchema.output_ports ?? [],
              sourceParams,
              "output",
              sourceSchema,
            )
          : (sourceSchema?.output_ports ?? []);
      const sourceDynamicPorts = sourceSchema?.dynamic_ports ?? null;
      const sourceConfigKey = sourceDynamicPorts?.source_config_key;
      const sourceDrivingConfigValue =
        sourceConfigKey != null ? (sourceParams[sourceConfigKey] as string | undefined) : undefined;
      const effectiveSourcePorts = computeEffectivePorts(
        sourceDynamicPorts,
        sourceDrivingConfigValue,
        variadicSourcePorts,
        "output",
      );
      const sourcePort = effectiveSourcePorts.find((port) => port.name === source.portName);

      // Mirror the source-side effective-port resolution for the target so
      // we can re-validate type compatibility on every render. Previously
      // edges kept their original color/style even after the user changed
      // a config that broke the type match (e.g. LoadData ``core_type``
      // Array → Text). Now incompatible edges turn dashed-red with a
      // tooltip explaining the mismatch; clicking the edge still deletes
      // it via ``handleEdgeClick``.
      const variadicTargetPorts =
        targetNode && targetSchema
          ? resolveVariadicPorts(
              targetSchema.input_ports ?? [],
              targetParams,
              "input",
              targetSchema,
            )
          : (targetSchema?.input_ports ?? []);
      const targetDynamicPorts = targetSchema?.dynamic_ports ?? null;
      const targetConfigKey = targetDynamicPorts?.source_config_key;
      const targetDrivingConfigValue =
        targetConfigKey != null ? (targetParams[targetConfigKey] as string | undefined) : undefined;
      const effectiveTargetPorts = computeEffectivePorts(
        targetDynamicPorts,
        targetDrivingConfigValue,
        variadicTargetPorts,
        "input",
      );
      const targetPort = effectiveTargetPorts.find((port) => port.name === target.portName);

      // Only run the compat check when both ports resolved; missing-port
      // edges are reported by workflow validation at save time and we
      // should not double-flag them here. The type hierarchy is shared
      // across blocks (registered globally), so either schema's copy
      // works — prefer the source's.
      const typeHierarchy = sourceSchema?.type_hierarchy ?? targetSchema?.type_hierarchy;
      const invalid =
        sourcePort != null &&
        targetPort != null &&
        !arePortTypesCompatible(
          sourcePort.accepted_types,
          targetPort.accepted_types,
          typeHierarchy,
        );

      const color = invalid
        ? "#dc2626"
        : resolveTypeColor(sourcePort?.accepted_types ?? [], sourceSchema?.type_hierarchy);
      return {
        id: `${edge.source}->${edge.target}`,
        source: source.nodeId,
        sourceHandle: source.portName,
        target: target.nodeId,
        targetHandle: target.portName,
        type: "typed",
        data: {
          color,
          dashed: invalid,
          invalid,
          invalidReason: invalid
            ? `Incompatible types: source produces ${sourcePort?.accepted_types.join(", ") || "Any"}, target accepts ${targetPort?.accepted_types.join(", ") || "Any"}`
            : undefined,
        },
      };
    });
  }, [edges, nodes, schemas]);
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  const reactFlow = useReactFlow();
  // #1799 — the plot target picker sets this transient highlight (hover/select
  // a target row). Read directly from the store to avoid threading a prop down
  // through ProjectWorkspace. The canvas rings the node (via useFlowNodes) and
  // pans it into view above the bottom panel.
  const highlightedNodeId = useAppStore((s) => s.highlightedNodeId);
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
    onWarningClick,
    onPaneClick,
    onRestartBlock,
    onRunBlock,
    onSelectNode,
    onUpdateNodeConfig,
    onUpdateNodePosition,
    onResizeNode,
    selectedNodeId,
    blockOutputs,
    runScopePrefix,
    focusMode,
    onEnterFocusMode,
    onExitFocusMode,
    onTidyLayout,
    onOpenSubworkflow,
    onLocateSubworkflow,
  } = props;

  // Track positions locally during drag so nodes follow the cursor smoothly.
  const [dragPositions, setDragPositions] = useState<Record<string, { x: number; y: number }>>({});
  // Live size during a NodeResizer drag, mirroring dragPositions. ReactFlow is
  // controlled here, so the in-progress resize must be fed back through the
  // derived nodes or the body stays locked at the persisted size until release.
  const [dragSizes, setDragSizes] = useState<Record<string, { width: number; height: number }>>({});

  const flowCallbacks = useFlowCallbacks({
    onRunBlock,
    onRestartBlock,
    onDeleteNode,
    onErrorClick,
    onUpdateNodeConfig,
    onWarningClick,
  });

  const baseFlowNodes = useFlowNodes({
    nodes,
    edges,
    blocks,
    schemas,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    selectedNodeId,
    highlightedNodeId,
    blockOutputs,
    runScopePrefix,
    dragPositions,
    dragSizes,
    onUpdateNodeConfig,
    // ADR-044 §10 — per-node "locate file…" factory for broken placeholders.
    makeOnLocateSubworkflow: onLocateSubworkflow
      ? (nodeId: string) => () => onLocateSubworkflow(nodeId)
      : undefined,
    ...flowCallbacks,
  });

  // #1799 — pan the highlighted node into view when the picker selects/hovers a
  // target. Guard `getNode`: a broken plot (or empty workflowId) can reference a
  // node that is not on the current canvas — then this is a safe no-op. Keep the
  // current zoom so the canvas only translates, never zooms unexpectedly.
  useEffect(() => {
    if (!highlightedNodeId) return;
    const node = reactFlow.getNode(highlightedNodeId);
    if (!node) return;
    const width = node.measured?.width ?? node.width ?? 0;
    const height = node.measured?.height ?? node.height ?? 0;
    void reactFlow.setCenter(node.position.x + width / 2, node.position.y + height / 2, {
      zoom: reactFlow.getZoom(),
      // Owner UX: a slower pan reads as a smooth glide rather than a jarring snap.
      duration: 700,
    });
  }, [highlightedNodeId, reactFlow]);

  const baseFlowEdges = useFlowEdges(edges, nodes, schemas);

  // ADR-050 §3.1 — derive the focus set from the captured selection + edges.
  // Pure read; never mutates workflow state (FR-018).
  const focus = useMemo<FocusResult>(
    () =>
      // #bug — omit `depth` so focus covers the whole connected chain
      // (computeFocusSet defaults to the full component). The depth field is
      // retained on the focus state for a future hop-limit control.
      computeFocusSet({
        selectedIds: focusMode?.enabled ? focusMode.selectedIds : [],
        allNodeIds: nodes.map((node) => node.id),
        edges,
      }),
    [focusMode?.enabled, focusMode?.selectedIds, nodes, edges],
  );
  const focusActive = (focusMode?.enabled ?? false) && focus.active;

  const flowNodes = useMemo(
    () => (focusActive ? applyFocusToNodes(baseFlowNodes, focus) : baseFlowNodes),
    [baseFlowNodes, focus, focusActive],
  );
  const flowEdges = useMemo(
    () => (focusActive ? applyFocusToEdges(baseFlowEdges, focus) : baseFlowEdges),
    [baseFlowEdges, focus, focusActive],
  );

  // ADR-050 §3.2 / FR-020..FR-023 — explicit tidy. Computes deterministic
  // positions then writes only `node.layout` through the batch store action.
  const runTidy = async (scope: "focus" | "whole"): Promise<void> => {
    if (!onTidyLayout) return;
    const scopeNodeIds = scope === "focus" && focusActive ? focus.visibleNodeIds : undefined;
    const positions = await computeAutoLayout({ nodes, edges, scopeNodeIds });
    if (Object.keys(positions).length > 0) onTidyLayout(positions);
  };

  const handlers = useCanvasHandlers({
    reactFlow,
    edges,
    nodes,
    runScopePrefix,
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
  });

  const showReadabilityControls = Boolean(onTidyLayout || onEnterFocusMode);

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
        onNodeDoubleClick={handlers.handleNodeDoubleClick}
        onNodeDragStop={handlers.handleNodeDragStop}
        onNodesDelete={handlers.handleNodesDelete}
        onPaneClick={handlers.handlePaneClick}
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        {minimapVisible && <WorkflowMiniMap />}
        <Controls />
        <Background color="#d8d2c4" gap={20} size={1.2} />
        {showReadabilityControls ? (
          <CanvasReadabilityControls
            focusActive={focusActive}
            canFocus={Boolean(selectedNodeId)}
            hiddenNodeCount={focus.hiddenNodeCount}
            hiddenEdgeCount={focus.hiddenEdgeCount}
            onEnterFocus={() => {
              if (selectedNodeId) onEnterFocusMode?.([selectedNodeId]);
            }}
            onExitFocus={() => onExitFocusMode?.()}
            onTidy={() => void runTidy("focus")}
            onTidyWhole={() => void runTidy("whole")}
          />
        ) : null}
      </ReactFlow>
    </div>
  );
}
