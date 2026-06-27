/**
 * useFlowNodes — builds the ReactFlow `nodes` array from workflow nodes.
 * Extracted from WorkflowCanvas in #1413.
 */
import type { Node } from "@xyflow/react";
import { useMemo } from "react";

import type {
  BlockSchemaResponse,
  BlockSummary,
  WorkflowEdge,
  WorkflowNode,
} from "../../types/api";
import {
  buildAnnotationNode,
  buildBlockNode,
  computeUpstreamOmeFields,
  defaultLayout,
  paramsOf,
} from "./flowNodeBuilder";

/** Derive canvas display label for a node. */
function resolveLabel(
  node: WorkflowNode,
  summary?: BlockSummary,
  schema?: BlockSchemaResponse,
): string {
  if (node.block_type === "io_block") {
    const params = (node.config.params as Record<string, unknown> | undefined) ?? {};
    const direction = params.direction as string | undefined;
    if (direction === "output") return "Save Block";
    return "Load Block";
  }
  return summary?.name ?? schema?.name ?? node.block_type;
}

export interface UseFlowNodesOpts {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  blocks: BlockSummary[];
  schemas: Record<string, BlockSchemaResponse>;
  blockStates: Record<string, string>;
  blockErrors: Record<string, string>;
  blockErrorSummaries: Record<string, string>;
  selectedNodeId: string | null;
  /** #1799 — node the plot picker is hovering/selecting; rings it on the canvas. */
  highlightedNodeId: string | null;
  blockOutputs?: Record<string, Record<string, unknown>>;
  dragPositions: Record<string, { x: number; y: number }>;
  /** Live size during a NodeResizer drag (keyed by node id). */
  dragSizes: Record<string, { width: number; height: number }>;
  onUpdateNodeConfig: (nodeId: string, patch: Record<string, unknown>) => void;
  makeOnRun: (nodeId: string) => () => void;
  makeOnRestart: (nodeId: string) => () => void;
  makeOnDelete: (nodeId: string) => () => void;
  makeOnErrorClick: (nodeId: string) => () => void;
  makeOnUpdateConfig: (nodeId: string) => (patch: Record<string, unknown>) => void;
  /**
   * ADR-050 §2.5 / FR-013 — factory for the warning-status activation handler
   * (select node + open BottomPanel Config). OPTIONAL so FE-2's existing call
   * sites compile before the integration merge wires it through
   * `useFlowCallbacks`. Defaults to undefined ⇒ no warning click handler.
   */
  makeOnWarningClick?: (nodeId: string) => (() => void) | undefined;
}

export function useFlowNodes(opts: UseFlowNodesOpts): Node[] {
  const {
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
    dragPositions,
    dragSizes,
    onUpdateNodeConfig,
    makeOnRun,
    makeOnRestart,
    makeOnDelete,
    makeOnErrorClick,
    makeOnUpdateConfig,
    makeOnWarningClick,
  } = opts;

  return useMemo(() => {
    // The group feature was removed; drop any `_group` node still persisted in
    // an older test workflow so it does not render as a default React Flow box.
    const visibleNodes = nodes.filter((node) => node.block_type !== "_group");
    return visibleNodes.map((node, index) => {
      const storePos = node.layout ?? defaultLayout(index);
      const position = dragPositions[node.id] ?? storePos;
      const params = paramsOf(node);

      if (node.block_type === "_annotation") {
        return buildAnnotationNode({
          node,
          position,
          size: dragSizes[node.id],
          params,
          selectedNodeId,
          onUpdateNodeConfig,
        });
      }

      const summary = blocks.find((block) => block.type_name === node.block_type);
      const schema = schemas[node.block_type];
      const upstreamOmeFields = computeUpstreamOmeFields({
        nodeId: node.id,
        edges,
        blockOutputs,
      });

      return buildBlockNode({
        node,
        position,
        params,
        summary,
        schema,
        status: blockStates[node.id] ?? "idle",
        errorMessage: blockErrors[node.id],
        errorSummary: blockErrorSummaries[node.id],
        label: resolveLabel(node, summary, schema),
        upstreamOmeFields,
        selectedNodeId,
        highlighted: highlightedNodeId === node.id,
        callbacks: {
          onRun: makeOnRun(node.id),
          onRestart: makeOnRestart(node.id),
          onDelete: makeOnDelete(node.id),
          onUpdateConfig: makeOnUpdateConfig(node.id),
          onErrorClick: makeOnErrorClick(node.id),
          // ADR-050 §2.5 — optional warning-status handler; undefined until
          // FE-2 wires `makeOnWarningClick` at integration.
          onWarningClick: makeOnWarningClick?.(node.id),
        },
      });
    });
  }, [
    blocks,
    blockStates,
    blockErrors,
    blockErrorSummaries,
    blockOutputs,
    dragPositions,
    dragSizes,
    edges,
    makeOnDelete,
    makeOnErrorClick,
    makeOnRestart,
    makeOnRun,
    makeOnUpdateConfig,
    makeOnWarningClick,
    nodes,
    onUpdateNodeConfig,
    schemas,
    selectedNodeId,
    highlightedNodeId,
  ]);
}
