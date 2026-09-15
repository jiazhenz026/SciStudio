import type { StateCreator } from "zustand";

import type { AppStore, ExecutionSlice } from "./types";
import {
  emptyWorkflowExecution,
  executionViewKey,
  extractBlockError,
  maybeAppendErrorLog,
  nextExecutionByWorkflow,
  nextIsRunning,
  projectExecution,
} from "./executionSlice.parts/eventReducer";

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
  interactivePrompt: null,
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

      return {
        executionByWorkflow,
        // An expanded subworkflow tab shows its parent run's bucket, not the
        // child file's own id (see `executionViewKey`).
        ...projectExecution(executionByWorkflow, executionViewKey(state)),
        logEntries: nextLogs,
        isRunning: nextIsRunning(event, state.isRunning),
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
      isRunning: false,
      interactivePrompt: null,
    }),
  setInteractivePrompt: (prompt) => set({ interactivePrompt: prompt }),
});
