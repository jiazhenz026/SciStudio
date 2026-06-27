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

/**
 * ADR-044 §3 — data carried by a `subworkflow` (or broken placeholder) canvas
 * node. Ports are derived from the referenced subworkflow's `exposed_ports`
 * (response-only `resolved_ports`), so they are NOT user-editable on the parent
 * canvas. The handle ids equal `inputPorts[].name` / `outputPorts[].name` so
 * existing colon-ref edge logic (`<node_id>:<port_name>`) works unchanged.
 */
export interface SubWorkflowNodeData extends Record<string, unknown> {
  label: string;
  /** "subworkflow" or "subworkflow_broken" — the backend block type. */
  blockType: string;
  /** Project-relative referenced file path (`config.ref.path`), or null. */
  refPath: string | null;
  /** True for `subworkflow_broken` nodes / unresolved refs (red placeholder). */
  broken: boolean;
  /** Derived exposed input ports (empty when broken). */
  inputPorts: BlockPortResponse[];
  /** Derived exposed output ports (empty when broken). */
  outputPorts: BlockPortResponse[];
  /** Type hierarchy for port colour resolution (shared registry copy). */
  typeHierarchy?: BlockSchemaResponse["type_hierarchy"];
  /**
   * ADR-044 — aggregated run status of the flattened inner blocks
   * (`idle`/`running`/`done`/`error`/`cancelled`). The collapsed container has
   * no run id of its own; this is rolled up from the inner blocks' states so
   * the node shows whether its sub-pipeline ran. Absent ⇒ "idle".
   */
  status?: string;
  selected?: boolean;
  onDelete?: () => void;
  /**
   * ADR-044 FR-011 (US5) + §10 / US6 AS2 — the shared choose/import
   * subworkflow affordance. On a node with no ref it reads "Choose subworkflow
   * file…"; on a broken-ref placeholder it reads "Locate file…". Both run the
   * same flow: pick an external file, import it into `<project>/subworkflows/`,
   * repoint `config.ref.path`, and refresh the node's resolved-port handles.
   */
  onLocateFile?: () => void;
}

export type SubWorkflowCanvasNode = Node<SubWorkflowNodeData>;

/** Data carried by an _annotation node on the canvas. */
export interface AnnotationNodeData extends Record<string, unknown> {
  text: string;
  onUpdateText?: (text: string) => void;
}
