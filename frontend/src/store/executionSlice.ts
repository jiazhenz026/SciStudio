import type { StateCreator } from "zustand";

import type { AppStore, ExecutionSlice } from "./types";
import {
  extractBlockError,
  maybeAppendErrorLog,
  nextBlockOutputs,
  nextBlockStates,
  nextErrorMaps,
  nextIsRunning,
} from "./executionSlice.parts/eventReducer";

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
      const extraction = extractBlockError(event);
      const { nextErrors, nextSummaries } = nextErrorMaps(
        event,
        extraction,
        state.blockErrors,
        state.blockErrorSummaries,
      );
      const { logEntries: nextLogs, appended } = maybeAppendErrorLog(
        event,
        extraction,
        state.logEntries,
      );
      // Mirror appendLog's badge-coupling: bump unread iff we actually
      // produced a Logs-panel row AND the user isn't already looking.
      const bumpUnread = appended && state.activeBottomTab !== "logs";

      return {
        blockStates: nextBlockStates(event, state.blockStates),
        blockOutputs: nextBlockOutputs(event, state.blockOutputs),
        blockErrors: nextErrors,
        blockErrorSummaries: nextSummaries,
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
