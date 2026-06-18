/**
 * Focus-mode display application (ADR-050 §3.1 / FR-018).
 *
 * Pure helpers that translate a {@link FocusResult} into ReactFlow display
 * props on the *derived* node/edge arrays. Extracted from `WorkflowCanvas.tsx`
 * so the dim/hide application is unit-testable on its own (no component mount).
 *
 * These functions NEVER mutate workflow state — they only set `className` /
 * `style` (opacity) on copies of the ReactFlow display objects (dispatch
 * checklist §4.3). The underlying focus-set is computed by `focusMode.ts`.
 *
 * The default `Node` element type matches the heterogeneous flow-node array
 * that `useFlowNodes` produces (block / annotation / group nodes share one
 * ReactFlow array, with `data: Record<string, unknown>`).
 */
import type { Edge, Node } from "@xyflow/react";

import type { FocusResult } from "./focusMode";

/** CSS class applied to out-of-focus nodes so styling stays declarative. */
export const FOCUS_DIMMED_CLASS = "scistudio-focus-dimmed";
/** Opacity applied to dimmed out-of-focus block nodes. */
export const FOCUS_DIMMED_NODE_OPACITY = 0.18;
/** Opacity applied to edges that touch the focus boundary. */
export const FOCUS_DIMMED_EDGE_OPACITY = 0.12;

/**
 * Dim out-of-focus nodes. When focus is inactive the array is returned
 * unchanged (referential identity preserved). Dimmed nodes get
 * {@link FOCUS_DIMMED_CLASS} + reduced opacity and `pointerEvents: none`;
 * in-focus nodes are returned as-is.
 */
export function applyFocusToNodes(flowNodes: Node[], focus: FocusResult): Node[] {
  if (!focus.active) return flowNodes;
  return flowNodes.map((node) => {
    if (!focus.dimmedNodeIds.has(node.id)) return node;
    return {
      ...node,
      className: [node.className, FOCUS_DIMMED_CLASS].filter(Boolean).join(" "),
      style: {
        ...(node.style ?? {}),
        opacity: FOCUS_DIMMED_NODE_OPACITY,
        pointerEvents: "none" as const,
      },
    };
  });
}

/** Dim edges that touch the focus boundary (one endpoint outside the set). */
export function applyFocusToEdges(flowEdges: Edge[], focus: FocusResult): Edge[] {
  if (!focus.active) return flowEdges;
  return flowEdges.map((edge) => {
    if (!focus.dimmedEdgeIds.has(edge.id)) return edge;
    return { ...edge, style: { ...(edge.style ?? {}), opacity: FOCUS_DIMMED_EDGE_OPACITY } };
  });
}
