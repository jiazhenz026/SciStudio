import type { StateCreator } from "zustand";

import type { AppStore, ExecutionSlice } from "./types";
import {
  emptyWorkflowExecution,
  executionViewKey,
  extractBlockError,
  maybeAppendErrorLog,
  executionWorkflowKey,
  nextExecutionByWorkflow,
  projectExecution,
} from "./executionSlice.parts/eventReducer";
import {
  removePrompt,
  removeWorkflowPrompts,
  upsertPrompt,
} from "./executionSlice.parts/interactivePrompts";

export const createExecutionSlice: StateCreator<AppStore, [], [], ExecutionSlice> = (set) => ({
  executionByWorkflow: {},
  blockStates: {},
  blockRunStartedAt: {},
  blockOutputs: {},
  blockErrors: {},
  blockErrorSummaries: {},
  executionMessages: [],
  logEntries: [],
  isRunning: false,
  interactivePrompts: {},
  consumeEvent: (event) =>
    set((state) => {
      const extraction = extractBlockError(event);
      const { logEntries: nextLogs, appended } = maybeAppendErrorLog(
        event,
        extraction,
        state.logEntries,
      );
      // Mirror appendLog's badge-coupling: bump unread iff we actually
      // produced a Logs-panel row AND the user isn't already looking.
      const bumpUnread = appended && state.activeBottomTab !== "logs";

      // #2362: the node-keyed facts are recorded under the workflow the event
      // came from, then projected down to the workflow on screen. Two
      // workflows may contain a node with the same name, so a single global
      // map let a run of one silently answer for the other.
      const executionByWorkflow = nextExecutionByWorkflow(
        event,
        state.executionByWorkflow,
        state.workflowId,
      );

      // #2395: a workflow whose run ended can no longer be waiting on an
      // interactive block, so its pending prompts (and only its) are dropped.
      const interactivePrompts =
        event.type === "workflow_completed"
          ? removeWorkflowPrompts(
              state.interactivePrompts,
              executionWorkflowKey(event, state.workflowId),
            )
          : state.interactivePrompts;

      return {
        executionByWorkflow,
        // An expanded subworkflow tab shows its parent run's bucket, not the
        // child file's own id (see `executionViewKey`). #2395: the projection
        // carries the running flag of the workflow on screen too.
        ...projectExecution(executionByWorkflow, executionViewKey(state)),
        interactivePrompts,
        logEntries: nextLogs,
        executionMessages: [
          ...state.executionMessages,
          `${event.type}:${event.block_id ?? "workflow"}`,
        ].slice(-100),
        ...(bumpUnread ? { unreadLogsCount: state.unreadLogsCount + 1 } : {}),
      };
    }),
  appendLog: (entry) =>
    set((state) => {
      // Live hotfix batch: the unread badge now counts ONLY unread errors —
      // info rows were noisy. Bump iff this is an error row and the user is not
      // already on the Logs tab. (Coupling the badge to an actual appended row
      // also avoids the old "8 unread but Logs panel is empty" mismatch.)
      const shouldBump = entry.level === "error" && state.activeBottomTab !== "logs";
      return {
        logEntries: [...state.logEntries, entry].slice(-400),
        ...(shouldBump ? { unreadLogsCount: state.unreadLogsCount + 1 } : {}),
      };
    }),
  resetExecution: () =>
    set({
      executionByWorkflow: {},
      ...emptyWorkflowExecution(),
      executionMessages: [],
      logEntries: [],
      interactivePrompts: {},
    }),
  upsertInteractivePrompt: (prompt) =>
    set((state) => ({ interactivePrompts: upsertPrompt(state.interactivePrompts, prompt) })),
  removeInteractivePrompt: (workflowId, blockId) =>
    set((state) => ({
      interactivePrompts: removePrompt(state.interactivePrompts, workflowId, blockId),
    })),
});
