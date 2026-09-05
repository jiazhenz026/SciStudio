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
  /**
   * #1988 — true when `blockType` resolved to NOTHING in this environment
   * (neither a `BlockSummary` nor a `BlockSchemaResponse` came back): the
   * package is not installed, the drop-in file is gone, or an agent named a
   * block that does not exist. Distinct from a block that resolved fine but
   * reports `base_category: "unknown"` because it inherits `Block` directly —
   * that one works and is drawn as an ordinary node.
   */
  unresolved?: boolean;
  /**
   * #1988 — a Lucide icon name guessed from `blockType` for an unresolved node
   * (IO only), so a loader still reads as a loader. Weaker than the block's own
   * `summary.ui_icon`, which is authoritative whenever the block resolved.
   */
  uiIconHint?: string;
  summary?: BlockSummary;
  schema?: BlockSchemaResponse;
  config?: Record<string, unknown>;
  inputPorts: BlockPortResponse[];
  outputPorts: BlockPortResponse[];
  status?: string;
  /**
   * #1974 — epoch-ms instant at which this block entered the running state,
   * sourced from the `block_running` engine event. Set ONLY while the block is
   * running; `NodeStatusSurface` renders a transient elapsed-time counter
   * beside the running spinner and drops it as soon as this is undefined.
   * Never persisted, never a final duration, never a run history.
   */
  runStartedAt?: number;
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
  /**
   * #1799 — transient highlight from the plot target picker (hover/select a
   * target row). Distinct from `selected`; renders a ring without changing the
   * Config/Preview selection. Drawn by `BlockNode` alongside the square body.
   */
  highlighted?: boolean;
  onRun?: () => void;
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

// ---------------------------------------------------------------------------
// ADR-054 spec 4 (T-001) — the Explore tab's view enumerations.
//
// These are *view* vocabularies, not wire ones: the wire types live in
// `types/api.ts` beside the routes they mirror. The two are deliberately
// separate because the runtime reports "needs restart" as a flag beside a
// kernel state, and the shell shows it as one more state to render.
// ---------------------------------------------------------------------------

/**
 * Which of the two arrangements an Explore tab is in (spec §3 Key Entities).
 *
 *   - `"session"` — the ordinary tab: toolbar, strip, panel slots, notebook.
 *   - `"pause"`   — an interactive block's pause (FR-024): the same host and
 *     toolbar with the notebook pane absent and confirm/cancel offered.
 */
export type ExploreTabMode = "session" | "pause";

/**
 * The kernel state the shell renders (FR-016).
 *
 * The first five are the runtime's own `KernelState`. `"needs-restart"` is the
 * shell's rendering of `needs_restart: true` — the runtime reports it as a
 * flag beside the state, and a person is being told one thing, so the shell
 * collapses the pair into one value to draw.
 */
export type ExploreKernelDisplayState =
  | "not-started"
  | "starting"
  | "idle"
  | "busy"
  | "dead"
  | "needs-restart";

/**
 * Where one cell is in its run (FR-010, FR-013).
 *
 * Written only from `explore.cell_state` and `explore.cell_output` events
 * (FR-034): the shell never advances a cell out of `queued` on its own.
 */
export type ExploreCellRunState = "never-run" | "queued" | "running" | "idle" | "error";

/**
 * The three marks the runtime computes and the shell draws (FR-012).
 *
 * The values are the wire values of `scistudio.explore.session.CellMark`; the
 * frontend never derives one (FR-034).
 */
export type ExploreCellMarkKind = "never_run" | "stale" | "out_of_order";

/**
 * Where the tab's own load is (FR-001's re-fetch on restore).
 *
 *   - `"opening"`  — the open or restore request is in flight.
 *   - `"ready"`    — a session response has landed.
 *   - `"failed"`   — the open or restore was refused; `error` says why.
 *   - `"closed"`   — a `session_closed` event arrived for this session.
 */
export type ExploreShellState = "opening" | "ready" | "failed" | "closed";
