/**
 * ADR-039 §3.8 + ADR-045 reconcile handler for ``file.changed`` events.
 * Extracted from ``useWebSocket`` in #1413 / #1414.
 *
 * The version-vector reconcile contract (base/pending version, own-source
 * echo confirmation, dirty-vs-clean refresh branch) is preserved verbatim
 * — see ``useWebSocket.versionVector.test.ts``.
 */
import { api } from "../../lib/api";
import type { ProjectFileResponse } from "../../lib/api";
import { useAppStore } from "../../store";
import type { FileTab, VersionConflictState } from "../../store/types";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

import {
  eventSource,
  fileIsDirty,
  isStructuralTreeChange,
  numberOrNull,
  stringOrNull,
  versionedData,
} from "./helpers";

export interface FileChangedDeps {
  appendLog: (entry: LogEntry) => void;
}

interface FileEventContext {
  path: string;
  kind: string;
  eventVersion: number | null;
  source: ReturnType<typeof eventSource>;
  sourceId: string | null;
  payload: WorkflowEventMessage;
  projectId: string;
  appendLog: FileChangedDeps["appendLog"];
}

function buildFileConflict(
  tab: FileTab,
  ctx: FileEventContext,
  remoteContent: string | null,
): VersionConflictState {
  return {
    entityClass: "file",
    entityId: ctx.path,
    kind: ctx.kind,
    source: ctx.source,
    sourceId: ctx.sourceId,
    baseVersion: tab.baseVersion ?? null,
    pendingVersion: tab.pendingVersion ?? tab.baseVersion ?? null,
    remoteVersion: ctx.eventVersion,
    detectedAt: ctx.payload.timestamp,
    message:
      ctx.eventVersion === null
        ? `File '${ctx.path}' changed remotely without ADR-045 version data; local edits were preserved.`
        : `File '${ctx.path}' changed remotely at version ${ctx.eventVersion}; local edits were preserved.`,
    remoteContent,
  };
}

function handleCleanTab(tab: FileTab, ctx: FileEventContext): void {
  if (ctx.kind === "deleted" || ctx.kind === "moved") {
    const conflict: VersionConflictState = {
      entityClass: "file",
      entityId: ctx.path,
      kind: ctx.kind,
      source: ctx.source,
      sourceId: ctx.sourceId,
      baseVersion: tab.baseVersion ?? null,
      pendingVersion: tab.pendingVersion ?? tab.baseVersion ?? null,
      remoteVersion: ctx.eventVersion,
      detectedAt: ctx.payload.timestamp,
      message: `File '${ctx.path}' was ${ctx.kind} remotely; local tab content was left unchanged.`,
    };
    useAppStore.getState().markFileRemoteConflict(tab.id, conflict);
    ctx.appendLog({
      timestamp: ctx.payload.timestamp,
      level: "warn",
      message: conflict.message,
      workflow_id: null,
      block_id: null,
    });
    return;
  }
  api
    .getProjectFile(ctx.projectId, ctx.path)
    .then((fresh) => {
      useAppStore.getState().applyFileRemoteContent(tab.id, fresh);
    })
    .catch((err) => {
      ctx.appendLog({
        timestamp: ctx.payload.timestamp,
        level: "error",
        message: `Failed to refresh file '${ctx.path}' after disk change: ${
          err instanceof Error ? err.message : String(err)
        }`,
        workflow_id: null,
        block_id: null,
      });
    });
}

function handleDirtyTab(tab: FileTab, ctx: FileEventContext): void {
  const recordFileConflict = (remote: ProjectFileResponse | null) => {
    const latest = useAppStore.getState().tabs.find((t) => t.id === tab.id);
    if (!latest || latest.kind !== "file") return;
    const conflict = buildFileConflict(latest, ctx, remote?.content ?? null);
    useAppStore.getState().markFileRemoteConflict(tab.id, conflict);
    ctx.appendLog({
      timestamp: ctx.payload.timestamp,
      level: "warn",
      message: conflict.message,
      workflow_id: null,
      block_id: null,
    });
  };

  if (ctx.kind === "deleted" || ctx.kind === "moved") {
    recordFileConflict(null);
    return;
  }
  api
    .getProjectFile(ctx.projectId, ctx.path)
    .then((fresh) => recordFileConflict(fresh))
    .catch(() => recordFileConflict(null));
}

function reconcileTab(tab: FileTab, ctx: FileEventContext): void {
  if (
    ctx.eventVersion !== null &&
    typeof tab.baseVersion === "number" &&
    ctx.eventVersion <= tab.baseVersion
  ) {
    return;
  }

  if (ctx.eventVersion !== null && ctx.sourceId !== null && ctx.sourceId === tab.pendingSourceId) {
    if (typeof tab.pendingVersion !== "number" || ctx.eventVersion <= tab.pendingVersion) {
      useAppStore.getState().confirmFileVersion(tab.id, ctx.eventVersion, ctx.sourceId);
      return;
    }
  }

  if (!fileIsDirty(tab.id)) {
    handleCleanTab(tab, ctx);
    return;
  }
  handleDirtyTab(tab, ctx);
}

export function handleFileChanged(payload: WorkflowEventMessage, deps: FileChangedDeps): void {
  const data = versionedData(payload);
  const path = stringOrNull(data.path) ?? stringOrNull(data.entity_id);
  if (!path) return;

  // Refresh the project tree only on a structural change (created/deleted/
  // renamed). A "modified" content event leaves the tree structure unchanged
  // and must not thrash it during a run's repeated saves (#1751).
  const kind = (data.kind as string | undefined) ?? "modified";
  if (isStructuralTreeChange(kind)) {
    useAppStore.getState().bumpProjectTreeRefresh();
  }
  const state = useAppStore.getState();
  const projectId = state.currentProject?.id;
  const matchingTabs = state.tabs.filter((tab) => tab.kind === "file" && tab.filePath === path);
  if (!projectId || matchingTabs.length === 0) return;

  const ctx: FileEventContext = {
    path,
    kind,
    eventVersion: numberOrNull(data.version),
    source: eventSource(data),
    sourceId: stringOrNull(data.source_id),
    payload,
    projectId,
    appendLog: deps.appendLog,
  };

  for (const tab of matchingTabs) {
    if (tab.kind !== "file") continue;
    reconcileTab(tab, ctx);
  }
}
