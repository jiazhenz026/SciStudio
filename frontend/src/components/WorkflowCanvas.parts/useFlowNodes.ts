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
  buildSubWorkflowNode,
  computeUpstreamOmeFields,
  defaultLayout,
  paramsOf,
} from "./flowNodeBuilder";
import { aggregateSubworkflowStatus } from "./subworkflowRunView";

/**
 * ADR-044 — block types rendered by `SubWorkflowNode` instead of `BlockNode`.
 * `subworkflow_block` is the authoring container's registry type_name (see
 * `blocks.registry._spec._type_name_for_class`); `subworkflow_broken` is the
 * parser-emitted placeholder for an unresolved ref.
 */
export const SUBWORKFLOW_BLOCK_TYPES = new Set(["subworkflow_block", "subworkflow_broken"]);

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

/**
 * ADR-044 — label a subworkflow container from its referenced filename stem
 * (`config.ref.path` → basename without the `.yaml`/`.yml`/`.swf.yaml` suffix),
 * falling back to the node id. Mirrors the workflow-id-as-label convention the
 * ProjectTree uses for `.yaml` files.
 */
function resolveSubWorkflowLabel(node: WorkflowNode): string {
  const ref = node.config.ref as { path?: string } | undefined;
  const refPath = ref?.path;
  if (refPath) {
    const base = refPath.split("/").pop() ?? refPath;
    const stem = base.replace(/\.(swf\.)?(yaml|yml)$/i, "");
    if (stem) return stem;
  }
  return node.id;
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
  blockOutputs?: Record<string, Record<string, unknown>>;
  /**
   * ADR-044 — run-scope prefix for status/error lookups. Empty for a top-level
   * workflow; `"<subworkflowNodeId>__"` (composed for nesting) when this canvas
   * is the expanded child of a subworkflow node, so each child node maps to its
   * flattened run id `<prefix><nodeId>`. `blockOutputs` is pre-scoped by the
   * caller (aliased to plain node ids), so only state/error lookups need it.
   */
  runScopePrefix?: string;
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
  /**
   * ADR-044 §10 — factory for a subworkflow `subworkflow_broken` placeholder's
   * "locate file…" handler. OPTIONAL so existing call sites compile; defaults
   * to a no-op affordance handler when absent.
   */
  makeOnLocateSubworkflow?: (nodeId: string) => () => void;
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
    blockOutputs,
    runScopePrefix = "",
    dragPositions,
    dragSizes,
    onUpdateNodeConfig,
    makeOnRun,
    makeOnRestart,
    makeOnDelete,
    makeOnErrorClick,
    makeOnUpdateConfig,
    makeOnWarningClick,
    makeOnLocateSubworkflow,
  } = opts;

  // ADR-044 — a shared type-hierarchy copy drives subworkflow port colours.
  // The hierarchy is registered globally, so any block schema's copy works.
  const sharedTypeHierarchy = Object.values(schemas).find(
    (schema) => (schema.type_hierarchy?.length ?? 0) > 0,
  )?.type_hierarchy;

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

      // ADR-044 §3 — subworkflow containers render via SubWorkflowNode with
      // ports derived from the referenced file's exposed_ports
      // (response-only `node.resolved_ports`), routed BEFORE the generic
      // buildBlockNode path.
      if (SUBWORKFLOW_BLOCK_TYPES.has(node.block_type)) {
        return buildSubWorkflowNode({
          node,
          position,
          label: resolveSubWorkflowLabel(node),
          selectedNodeId,
          typeHierarchy: sharedTypeHierarchy,
          // ADR-044 — roll the flattened inner blocks' states up into one glyph.
          status: aggregateSubworkflowStatus(blockStates, `${runScopePrefix}${node.id}__`),
          onDelete: makeOnDelete(node.id),
          onLocateFile: makeOnLocateSubworkflow?.(node.id) ?? (() => {}),
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
        // ADR-044 — in an expanded child canvas the run keys carry the parent
        // prefix; runScopePrefix is "" for a top-level workflow.
        status: blockStates[`${runScopePrefix}${node.id}`] ?? "idle",
        errorMessage: blockErrors[`${runScopePrefix}${node.id}`],
        errorSummary: blockErrorSummaries[`${runScopePrefix}${node.id}`],
        label: resolveLabel(node, summary, schema),
        upstreamOmeFields,
        selectedNodeId,
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
    runScopePrefix,
    dragPositions,
    dragSizes,
    edges,
    makeOnDelete,
    makeOnErrorClick,
    makeOnRestart,
    makeOnRun,
    makeOnUpdateConfig,
    makeOnWarningClick,
    makeOnLocateSubworkflow,
    nodes,
    onUpdateNodeConfig,
    schemas,
    selectedNodeId,
    sharedTypeHierarchy,
  ]);
}
