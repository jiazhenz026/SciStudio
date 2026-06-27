/**
 * Pure helpers and tab capture/restore utilities for tabSlice. Extracted
 * in #1413 / #1414.
 *
 * The ADR-045 version-vector contract is preserved verbatim — see
 * `tabSlice.versionVector.test.ts` for the invariants this module must
 * not regress.
 */
import type { VersionedWorkflowResponse } from "../../lib/api";
import type { AppStore, FileTab, TabState, WorkflowTab } from "../types";

/**
 * Capture the current workflow + UI state into a WorkflowTab snapshot.
 */
export function captureWorkflowTab(state: AppStore): WorkflowTab {
  return {
    kind: "workflow",
    id: state.activeTabId ?? state.workflowId ?? "main",
    workflowId: state.workflowId ?? "main",
    workflowName: state.workflowName,
    workflowDescription: state.workflowDescription,
    workflowVersion: state.workflowVersion,
    workflowMetadata: state.workflowMetadata,
    workflowNodes: state.workflowNodes,
    workflowEdges: state.workflowEdges,
    workflowDirty: state.workflowDirty,
    workflowBaseVersion: state.workflowBaseVersion,
    workflowPendingVersion: state.workflowPendingVersion,
    workflowPendingSourceId: state.workflowPendingSourceId,
    workflowConflict: state.workflowConflict,
    workflowHistory: state.workflowHistory,
    workflowFuture: state.workflowFuture,
    selectedNodeId: state.selectedNodeId,
  };
}

export function captureActiveTab(state: AppStore, tab: TabState): TabState {
  if (tab.kind === "workflow") {
    // ADR-044 — `tabKey` and `runPrefix` are per-tab identity fields, not part
    // of the workflow slice that `captureWorkflowTab` rebuilds from. Preserve
    // them from the existing tab object so a capture cycle (switch/open) does
    // not blank the tab's dedup identity or its expanded-view run prefix.
    return { ...captureWorkflowTab(state), tabKey: tab.tabKey, runPrefix: tab.runPrefix };
  }
  return tab;
}

export function restoreTab(tab: TabState): Partial<AppStore> {
  if (tab.kind === "workflow") {
    return {
      workflowId: tab.workflowId,
      workflowName: tab.workflowName,
      workflowDescription: tab.workflowDescription,
      workflowVersion: tab.workflowVersion,
      workflowMetadata: tab.workflowMetadata,
      workflowNodes: tab.workflowNodes,
      workflowEdges: tab.workflowEdges,
      workflowDirty: tab.workflowDirty,
      workflowBaseVersion: tab.workflowBaseVersion ?? null,
      workflowPendingVersion: tab.workflowPendingVersion ?? tab.workflowBaseVersion ?? null,
      workflowPendingSourceId: tab.workflowPendingSourceId ?? null,
      workflowConflict: tab.workflowConflict ?? null,
      workflowHistory: tab.workflowHistory,
      workflowFuture: tab.workflowFuture,
      selectedNodeId: tab.selectedNodeId,
      activeTabId: tab.id,
    };
  }
  return { activeTabId: tab.id };
}

export function languageForPath(filePath: string): FileTab["language"] {
  const lower = filePath.toLowerCase();
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".r")) return "r";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".md")) return "markdown";
  return "text";
}

export function basename(filePath: string): string {
  const parts = filePath.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || filePath;
}

export function fileTabIdFor(filePath: string, readOnly: boolean): string {
  return readOnly ? `source:${filePath}` : `file:${filePath}`;
}

/**
 * Replace the existing tab matching `id` and switch to it.
 */
export function replaceTab(state: AppStore, id: string, next: TabState): Partial<AppStore> {
  return {
    tabs: state.tabs.map((t) => (t.id === id ? next : t)),
  };
}

export function workflowStateVersion(workflow: VersionedWorkflowResponse): number | null {
  return typeof workflow.state_version === "number" ? workflow.state_version : null;
}

export function fileStateVersion(response: { state_version?: number }): number | null {
  return typeof response.state_version === "number" ? response.state_version : null;
}

export function nextPendingVersion(
  base: number | null | undefined,
  pending: number | null | undefined,
): number | null {
  if (typeof base !== "number") return pending ?? null;
  if (typeof pending !== "number") return base + 1;
  return Math.max(base + 1, pending + 1);
}

/** State applied when the last tab is closed and the canvas resets. */
export const EMPTY_TAB_STATE: Partial<AppStore> = {
  tabs: [],
  activeTabId: null,
  workflowId: null,
  workflowName: "Untitled",
  workflowDescription: "",
  workflowVersion: "1.0.0",
  workflowMetadata: {},
  workflowNodes: [],
  workflowEdges: [],
  workflowDirty: false,
  workflowBaseVersion: null,
  workflowPendingVersion: null,
  workflowPendingSourceId: null,
  workflowConflict: null,
  workflowHistory: [],
  workflowFuture: [],
  selectedNodeId: null,
};
