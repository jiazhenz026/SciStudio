/**
 * Pure helpers for workflowSlice. Extracted in #1413 / #1414.
 *
 * These functions own snapshot/history/version-vector bookkeeping per
 * ADR-045 so the slice factory stays under the 150-LOC lint cap. The
 * version-vector contract (`workflowBaseVersion`, `workflowPendingVersion`,
 * `workflowPendingSourceId`) is preserved verbatim — see the
 * `workflowSlice.versionVector` test for the invariants.
 */
import type { VersionedWorkflowResponse } from "../../lib/api";
import type { WorkflowNode } from "../../types/api";
import type { AppStore, WorkflowHistoryEntry } from "../types";

export function snapshot(state: AppStore): WorkflowHistoryEntry {
  return {
    nodes: state.workflowNodes.map((node) => ({
      ...node,
      config: { ...node.config },
      layout: node.layout ? { ...node.layout } : null,
    })),
    edges: state.workflowEdges.map((edge) => ({ ...edge })),
    description: state.workflowDescription,
  };
}

export function pushHistory(state: AppStore): Pick<AppStore, "workflowHistory" | "workflowFuture"> {
  return {
    workflowHistory: [...state.workflowHistory, snapshot(state)].slice(-40),
    workflowFuture: [],
  };
}

export function stateVersionOf(
  workflow: VersionedWorkflowResponse | null | undefined,
): number | null {
  return typeof workflow?.state_version === "number" ? workflow.state_version : null;
}

export function nextPendingVersion(
  base: number | null,
  pending: number | null,
  saveInFlight: boolean,
): number | null {
  if (base === null) return pending;
  if (saveInFlight) return Math.max(base + 2, pending ?? base + 2);
  return base + 1;
}

export function markDirty(
  state: AppStore,
): Pick<AppStore, "workflowDirty" | "workflowPendingVersion" | "workflowConflict"> {
  return {
    workflowDirty: true,
    workflowPendingVersion: nextPendingVersion(
      state.workflowBaseVersion,
      state.workflowPendingVersion,
      state.workflowPendingSourceId !== null,
    ),
    workflowConflict: null,
  };
}

/**
 * #11: normalize loaded workflow nodes to the canonical ``config: { params }``
 * shape the GUI uses internally.
 *
 * Nodes created in the GUI store config as ``{ params: {...} }`` (see
 * ``createAddNode`` / ``mergeNodeConfig``), but a workflow YAML authored by the
 * agent or by hand stores config FLAT (``config: { path: ..., method: ... }``).
 * The backend tolerates both, but the config panel and ``paramsOf`` read
 * ``node.config.params`` — so a loaded flat node shows EMPTY/SCHEMA-DEFAULT
 * values (e.g. an empty path, ``polynomial`` instead of the real ``arPLS``) and
 * an edit would mix flat keys with a fresh ``params`` object. Wrapping flat
 * configs on load makes display + edit consistent. Idempotent: a node already in
 * the ``{ params }`` shape is returned unchanged.
 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function normalizeLoadedNodes(nodes: WorkflowNode[]): WorkflowNode[] {
  return nodes.map((node) => {
    // Annotation nodes carry GUI-only config (``params`` + ``style``) and are
    // always created in the canonical shape; never reshape them.
    if (node.block_type === "_annotation") {
      return node;
    }
    const config = isPlainObject(node.config) ? (node.config as Record<string, unknown>) : {};
    if (isPlainObject(config.params)) {
      return node; // already canonical (GUI-created or previously normalized)
    }
    return { ...node, config: { params: { ...config } } };
  });
}

export function mergeNodeConfig(node: WorkflowNode, config: Record<string, unknown>): WorkflowNode {
  return {
    ...node,
    config: {
      ...node.config,
      params: {
        ...((node.config.params as Record<string, unknown> | undefined) ?? {}),
        ...config,
      },
    },
  };
}
