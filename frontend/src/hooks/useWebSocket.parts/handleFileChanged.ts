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
import { panelIdForProjectPath } from "../../panels/panelPaths";
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

  /*
   * ADR-054 FR-030/FR-032 — a change inside a panel's directory reloads that
   * panel, wherever the change came from.
   *
   * Before the open-tab reconcile below and outside its early return, because
   * the whole point is that nobody has the panel open in an editor: the person
   * saved it from the panel editor, or the agent wrote it on their behalf. A
   * reload that only fired for files someone happened to have open would be
   * exactly the half-working trigger FR-032 exists to rule out.
   *
   * The event's own `source` is deliberately not consulted. A first-party save
   * is suppressed by the backend before it ever reaches here, so anything that
   * arrives is a change the mounted panel has not seen.
   */
  const changedPanelId = panelIdForProjectPath(path);
  if (changedPanelId !== null) {
    useAppStore.getState().notePanelDocumentChanged(changedPanelId);
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
