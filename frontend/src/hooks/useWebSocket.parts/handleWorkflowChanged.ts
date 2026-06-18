/**
 * ADR-034 Phase 2 + ADR-045 reconcile handler for ``workflow.changed``
 * events. Extracted from ``useWebSocket`` in #1413 / #1414 to drop the
 * arrow function below the 150-LOC + complexity 15 caps.
 *
 * The version-vector reconcile contract (base/pending version, own-source
 * echo confirmation, dirty-vs-clean refresh branch) is preserved verbatim
 * — see ``useWebSocket.versionVector.test.ts``.
 */
import { api, consumePendingWorkflowSourceId } from "../../lib/api";
import type { VersionedWorkflowResponse } from "../../lib/api";
import { useAppStore } from "../../store";
import type { VersionConflictState } from "../../store/types";
import type { LogEntry, WorkflowEventMessage } from "../../types/api";

import { eventSource, numberOrNull, stringOrNull, versionedData, workflowIsDirty } from "./helpers";

export interface WorkflowChangedDeps {
  appendLog: (entry: LogEntry) => void;
  setWorkflow: (workflow: VersionedWorkflowResponse | null) => void;
}

function autoOpenCreatedWorkflow(changedId: string): void {
  // #1322 diagnostics: prod-only reports of auto-open intermittently not
  // firing after an agent ``write_workflow``. The WS frame was confirmed
  // correct in the 2026-05-21 hotfix session, so the suspected gap is on
  // the fetch / openTab path (e.g. ``getWorkflow`` racing a not-yet-flushed
  // file, or the dedupe key mismatching). These debug logs make the next
  // recurrence diagnosable per the issue's repro guidance without changing
  // behaviour. See frontend/docs/2026-06-10-autoopen-investigation.md.
  // eslint-disable-next-line no-console
  console.debug("[workflow.changed] auto-open: fetching created workflow", changedId);
  api
    .getWorkflow(changedId)
    .then((fresh) => {
      // eslint-disable-next-line no-console
      console.debug("[workflow.changed] auto-open: opening tab", changedId, {
        fetchedId: fresh?.id,
      });
      useAppStore.getState().openTab(fresh, changedId);
    })
    .catch((err) => {
      // best-effort; user can still open it via the file tree
      // eslint-disable-next-line no-console
      console.debug("[workflow.changed] auto-open: getWorkflow failed", changedId, err);
    });
}

function refreshCurrentWorkflow(
  changedId: string,
  kind: string,
  payload: WorkflowEventMessage,
  deps: WorkflowChangedDeps,
): void {
  api
    .getWorkflow(changedId)
    .then((fresh) => {
      if (useAppStore.getState().workflowId === changedId) {
        deps.setWorkflow(fresh);
      }
    })
    .catch((err) => {
      // Hotfix #1400 part 3: git-checkout replacement can emit
      // transient `deleted` or `moved` before restore makes the file
      // visible again.
      if (kind === "deleted" || kind === "moved") {
        deps.setWorkflow(null);
        deps.appendLog({
          timestamp: payload.timestamp,
          level: "warn",
          message: `Workflow '${changedId}' was ${kind} on disk; canvas cleared.`,
          workflow_id: changedId,
          block_id: null,
        });
        return;
      }
      deps.appendLog({
        timestamp: payload.timestamp,
        level: "error",
        message: `Failed to refresh workflow '${changedId}' after disk change: ${
          err instanceof Error ? err.message : String(err)
        }`,
        workflow_id: changedId,
        block_id: null,
      });
    });
}

interface ConflictArgs {
  changedId: string;
  kind: string;
  source: ReturnType<typeof eventSource>;
  sourceId: string | null;
  eventVersion: number | null;
  payload: WorkflowEventMessage;
  appendLog: WorkflowChangedDeps["appendLog"];
}

function recordWorkflowConflict(
  remoteWorkflow: VersionedWorkflowResponse | null,
  args: ConflictArgs,
): void {
  const { changedId, kind, source, sourceId, eventVersion, payload, appendLog } = args;
  const latest = useAppStore.getState();
  const conflict: VersionConflictState = {
    entityClass: "workflow",
    entityId: changedId,
    kind,
    source,
    sourceId,
    baseVersion: latest.workflowBaseVersion,
    pendingVersion: latest.workflowPendingVersion,
    remoteVersion: eventVersion,
    detectedAt: payload.timestamp,
    message:
      eventVersion === null
        ? `Workflow '${changedId}' changed remotely without ADR-045 version data; local edits were preserved.`
        : `Workflow '${changedId}' changed remotely at version ${eventVersion}; local edits were preserved.`,
    remoteWorkflow,
  };
  useAppStore.getState().markWorkflowRemoteConflict(conflict);
  appendLog({
    timestamp: payload.timestamp,
    level: "warn",
    message: conflict.message,
    workflow_id: changedId,
    block_id: null,
  });
}

function handleDirtyConflict(args: ConflictArgs): void {
  if (args.kind === "deleted" || args.kind === "moved") {
    recordWorkflowConflict(null, args);
    return;
  }
  api
    .getWorkflow(args.changedId)
    .then((fresh) => {
      if (useAppStore.getState().workflowId === args.changedId) {
        recordWorkflowConflict(fresh, args);
      }
    })
    .catch(() => recordWorkflowConflict(null, args));
}

interface WorkflowChangedContext {
  changedId: string;
  kind: string;
  eventVersion: number | null;
  source: ReturnType<typeof eventSource>;
  sourceId: string | null;
  payload: WorkflowEventMessage;
}

function parseWorkflowChangedPayload(payload: WorkflowEventMessage): WorkflowChangedContext | null {
  const data = versionedData(payload);
  const changedId =
    (payload.workflow_id as string | null | undefined) ??
    (data.workflow_id as string | undefined) ??
    (data.entity_id as string | undefined) ??
    null;
  if (!changedId) return null;
  return {
    changedId,
    kind: (data.kind as string | undefined) ?? "modified",
    eventVersion: numberOrNull(data.version),
    source: eventSource(data),
    sourceId: stringOrNull(data.source_id),
    payload,
  };
}

function isUnopenedCreatedWorkflow(ctx: WorkflowChangedContext): boolean {
  if (ctx.kind !== "created") return false;
  return !useAppStore
    .getState()
    .tabs.some((t) => t.kind === "workflow" && t.workflowId === ctx.changedId);
}

function tryConfirmOwnSourceEcho(ctx: WorkflowChangedContext): boolean {
  const state = useAppStore.getState();
  if (
    ctx.eventVersion === null ||
    ctx.sourceId === null ||
    (ctx.sourceId !== state.workflowPendingSourceId &&
      !consumePendingWorkflowSourceId(ctx.changedId, ctx.sourceId))
  ) {
    return false;
  }
  const pending = state.workflowPendingVersion;
  if (pending !== null && ctx.eventVersion > pending) return false;
  useAppStore.getState().confirmWorkflowVersion(ctx.eventVersion, ctx.sourceId);
  return true;
}

function reconcileCurrentWorkflow(ctx: WorkflowChangedContext, deps: WorkflowChangedDeps): void {
  const state = useAppStore.getState();
  const baseVersion = state.workflowBaseVersion;
  if (ctx.eventVersion !== null && baseVersion !== null && ctx.eventVersion <= baseVersion) {
    return;
  }
  if (tryConfirmOwnSourceEcho(ctx)) return;

  if (workflowIsDirty()) {
    handleDirtyConflict({
      changedId: ctx.changedId,
      kind: ctx.kind,
      source: ctx.source,
      sourceId: ctx.sourceId,
      eventVersion: ctx.eventVersion,
      payload: ctx.payload,
      appendLog: deps.appendLog,
    });
    return;
  }

  refreshCurrentWorkflow(ctx.changedId, ctx.kind, ctx.payload, deps);
}

export function handleWorkflowChanged(
  payload: WorkflowEventMessage,
  deps: WorkflowChangedDeps,
): void {
  const ctx = parseWorkflowChangedPayload(payload);
  // Any workflow YAML touch on disk is also a project-tree change.
  useAppStore.getState().bumpProjectTreeRefresh();
  if (!ctx) return;

  // ADR-034: agent-driven ``write_workflow`` (kind=created) for an
  // unopened workflow — auto-open it so the user can see what
  // claude/codex just produced.
  if (isUnopenedCreatedWorkflow(ctx)) {
    autoOpenCreatedWorkflow(ctx.changedId);
    return;
  }

  const currentId = useAppStore.getState().workflowId;
  if (ctx.changedId !== currentId) return;

  reconcileCurrentWorkflow(ctx, deps);
}
