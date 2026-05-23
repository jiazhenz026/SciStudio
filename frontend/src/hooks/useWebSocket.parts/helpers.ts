/**
 * Pure helpers for ``useWebSocket``. Extracted in #1413 / #1414.
 *
 * The ADR-045 version-vector reconcile contract on
 * ``workflow.changed`` / ``file.changed`` echoes is preserved verbatim
 * — see ``useWebSocket.versionVector.test.ts``.
 */
import { useAppStore } from "../../store";
import type { VersionedChangeSource } from "../../store/types";
import type { WorkflowEventMessage } from "../../types/api";

export function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function versionedData(payload: WorkflowEventMessage): Record<string, unknown> {
  return (payload.data ?? {}) as Record<string, unknown>;
}

export function eventSource(data: Record<string, unknown>): VersionedChangeSource | null {
  return stringOrNull(data.source) as VersionedChangeSource | null;
}

export function workflowIsDirty(): boolean {
  const state = useAppStore.getState();
  return (
    state.workflowDirty ||
    (typeof state.workflowBaseVersion === "number" &&
      typeof state.workflowPendingVersion === "number" &&
      state.workflowPendingVersion > state.workflowBaseVersion)
  );
}

export function fileIsDirty(tabId: string): boolean {
  const state = useAppStore.getState();
  const tab = state.tabs.find((t) => t.id === tabId);
  if (!tab || tab.kind !== "file") return false;
  return (
    tab.dirty ||
    (typeof tab.baseVersion === "number" &&
      typeof tab.pendingVersion === "number" &&
      tab.pendingVersion > tab.baseVersion)
  );
}
