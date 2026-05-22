import type { StateCreator } from "zustand";

import type { AppStore, ExecutionSlice } from "./types";

export const createExecutionSlice: StateCreator<AppStore, [], [], ExecutionSlice> = (set) => ({
  blockStates: {},
  blockOutputs: {},
  blockErrors: {},
  blockErrorSummaries: {},
  executionMessages: [],
  logEntries: [],
  isRunning: false,
  interactivePrompt: null,
  consumeEvent: (event) =>
    set((state) => {
      const nextStates = event.block_id
        ? {
            ...state.blockStates,
            [event.block_id]: event.type.replace("block_", ""),
          }
        : state.blockStates;
      const outputs =
        event.block_id && event.data.outputs && typeof event.data.outputs === "object"
          ? {
              ...state.blockOutputs,
              [event.block_id]: event.data.outputs as Record<string, unknown>,
            }
          : state.blockOutputs;

      // Track workflow-level running state from lifecycle events.
      let nextIsRunning = state.isRunning;
      if (event.type === "workflow_started") {
        nextIsRunning = true;
      } else if (event.type === "workflow_completed") {
        nextIsRunning = false;
      }

      // Extract and store error message when a block_error event arrives.
      const isBlockError = event.type === "block_error" && event.block_id != null;
      const errorText =
        isBlockError && typeof event.data.error === "string" ? event.data.error : undefined;
      const nextErrors =
        isBlockError && errorText != null
          ? { ...state.blockErrors, [event.block_id as string]: errorText }
          : state.blockErrors;
      const summaryText =
        isBlockError && typeof event.data.error_summary === "string"
          ? event.data.error_summary
          : undefined;
      const nextSummaries =
        isBlockError && summaryText != null
          ? { ...state.blockErrorSummaries, [event.block_id as string]: summaryText }
          : state.blockErrorSummaries;

      // Append a structured log entry for block_error so the Logs panel
      // shows the full error text alongside the standard log stream.
      const addsLogRow = isBlockError && errorText != null;
      const nextLogs = addsLogRow
        ? [
            ...state.logEntries,
            {
              timestamp: event.timestamp,
              level: "error",
              message: errorText,
              workflow_id: event.workflow_id ?? null,
              block_id: event.block_id ?? null,
            },
          ].slice(-400)
        : state.logEntries;
      // Mirror appendLog's badge-coupling: bump unread iff we actually
      // produced a Logs-panel row AND the user isn't already looking.
      const bumpUnread = addsLogRow && state.activeBottomTab !== "logs";

      return {
        blockStates: nextStates,
        blockOutputs: outputs,
        blockErrors: nextErrors,
        blockErrorSummaries: nextSummaries,
        logEntries: nextLogs,
        isRunning: nextIsRunning,
        executionMessages: [
          ...state.executionMessages,
          `${event.type}:${event.block_id ?? "workflow"}`,
        ].slice(-100),
        ...(bumpUnread ? { unreadLogsCount: state.unreadLogsCount + 1 } : {}),
      };
    }),
  appendLog: (entry) =>
    set((state) => {
      // Coupling the unread badge with the actual append fixes the
      // "8 unread but Logs panel is empty" mismatch: previously the WS
      // handler bumped ``unreadLogsCount`` for every ``block_*`` /
      // ``workflow_*`` event regardless of whether a log entry was
      // produced. Now the badge increments exactly when a row is added,
      // so badge count = unread rows.
      const shouldBump = state.activeBottomTab !== "logs";
      return {
        logEntries: [...state.logEntries, entry].slice(-400),
        ...(shouldBump ? { unreadLogsCount: state.unreadLogsCount + 1 } : {}),
      };
    }),
  resetExecution: () =>
    set({
      blockStates: {},
      blockOutputs: {},
      blockErrors: {},
      blockErrorSummaries: {},
      executionMessages: [],
      logEntries: [],
      isRunning: false,
      interactivePrompt: null,
    }),
  setInteractivePrompt: (prompt) => set({ interactivePrompt: prompt }),
});
