import type { Node } from "@xyflow/react";

import type { BlockPortResponse, BlockSchemaResponse, BlockSummary } from "./api";

/**
 * ADR-038 §3.8 + ADR-039 §3.5 — the Lineage tab (ADR-038) and Git tab
 * (ADR-039, #972) are both first-class entries.
 *
 * The "jobs" placeholder was removed by ADR-038 §3.8 (run history now
 * lives in `<project>/.scistudio/lineage.db` and is surfaced in Lineage).
 * ADR-039 was developed in parallel and still referenced `"jobs"` on its
 * track; the integration takes the ADR-038 removal and adds the ADR-039
 * `"git"` tab on top.
 *
 * Hotfix: terminal sessions are a first-class surface instead of being nested
 * under the AI Chat tab.
 */
// #1713 — "plots" is a dedicated card-style panel for the workflow-wide plot
// list (name, linked block, language, relink, broken badge, run, new). It
// replaces the cramped chip row that previously sat atop the Preview panel.
export type BottomTab = "ai" | "terminal" | "config" | "logs" | "plots" | "lineage" | "git";

export interface BlockNodeData extends Record<string, unknown> {
  label: string;
  blockType: string;
  category: string;
  summary?: BlockSummary;
  schema?: BlockSchemaResponse;
  config?: Record<string, unknown>;
  inputPorts: BlockPortResponse[];
  outputPorts: BlockPortResponse[];
  status?: string;
  /** Short error message populated when status is 'error'. Sourced from the
   *  BLOCK_ERROR WebSocket event's \`data.error\` field. Surfaced ONLY through
   *  the unified `NodeStatusSurface` (ADR-050 §2.5); never rendered as inline
   *  text inside the square node body. */
  errorMessage?: string;
  /** Concise summary extracted from the error traceback (last line, max 120 chars).
   *  Surfaced ONLY through `NodeStatusSurface` tooltip detail (ADR-050 §2.5);
   *  not rendered inline in the node body. */
  errorSummary?: string;
  /**
   * ADR-050 §2.5 — highest-priority problem signal for the node, independent
   * of runtime `status`. Computed in `flowNodeBuilder` from runtime status
   * (`error` ⇒ "error") and the lossy-save check (⇒ "warning"). Rendered by
   * the unified `NodeStatusSurface`; never changes node geometry.
   */
  problemSeverity?: "none" | "warning" | "error";
  outputPreviewLabel?: string;
  selected?: boolean;
  onRun?: () => void;
  onRestart?: () => void;
  onDelete?: () => void;
  /** Kept on the type for BottomPanel/test compatibility, but the square node
   *  body MUST NOT render any config editor (ADR-050 §2.3 / FR-003). */
  onUpdateConfig?: (patch: Record<string, unknown>) => void;
  /** ADR-050 §2.5 / FR-012 — error-status activation: select node + open Logs.
   *  Emitted by `NodeStatusSurface`; wired by FE-2's App-level handler. */
  onErrorClick?: () => void;
  /**
   * ADR-050 §2.5 / FR-013 — warning-status activation: select node + open the
   * BottomPanel Config detail. OPTIONAL so existing call sites compile before
   * integration; wired by FE-2 through `useFlowCallbacks` + `makeOnWarningClick`
   * and emitted by the `NodeStatusSurface` warning affordance.
   */
  onWarningClick?: () => void;
  /**
   * ADR-043 FR-014 — Optional list of dotted OME field paths present on
   * the upstream source object. When set on a Save-direction IO node with
   * a selected capability whose `metadata_fidelity` cannot persist some of
   * these fields, `flowNodeBuilder` raises `problemSeverity` to "warning"
   * (ADR-050 §2.5). The verbose dropped-field detail lives in BottomPanel
   * Config (FR-014), not in the node body.
   *
   * Left undefined for nodes that have no upstream connection, no OME
   * metadata, or are not Save-direction IO blocks. Populated by the
   * workflow editor when wiring node data — see WorkflowCanvas.tsx.
   */
  upstreamOmeFields?: string[];
}

export type BlockCanvasNode = Node<BlockNodeData>;

/** Data carried by an _annotation node on the canvas. */
export interface AnnotationNodeData extends Record<string, unknown> {
  text: string;
  onUpdateText?: (text: string) => void;
}
