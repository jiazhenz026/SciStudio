/**
 * Version-vector action factories for workflowSlice. Extracted in #1413
 * / #1414.
 *
 * The ADR-045 version-vector contract on
 * `workflowBaseVersion` / `workflowPendingVersion` /
 * `workflowPendingSourceId` is preserved verbatim — see
 * `workflowSlice.versionVector.test.ts` for the invariants this module
 * must not regress.
 */
import type { StoreApi } from "zustand";

import type { AppStore, WorkflowSlice } from "../types";

type Setter = StoreApi<AppStore>["setState"];

export function createMarkWorkflowSaved(set: Setter): WorkflowSlice["markWorkflowSaved"] {
  return () =>
    set((state) => {
      if (
        state.workflowBaseVersion !== null &&
        state.workflowPendingVersion !== null &&
        state.workflowPendingVersion > state.workflowBaseVersion + 1
      ) {
        return {};
      }
      return { workflowDirty: false };
    });
}

export function createBeginWorkflowSave(set: Setter): WorkflowSlice["beginWorkflowSave"] {
  return (workflowId, sourceId) =>
    set((state) => {
      if (state.workflowId !== workflowId) return {};
      return {
        workflowPendingVersion:
          state.workflowBaseVersion === null
            ? state.workflowPendingVersion
            : Math.max(
                state.workflowBaseVersion + 1,
                state.workflowPendingVersion ?? state.workflowBaseVersion,
              ),
        workflowPendingSourceId: sourceId,
      };
    });
}

export function createConfirmWorkflowVersion(set: Setter): WorkflowSlice["confirmWorkflowVersion"] {
  return (version, sourceId = null) =>
    set((state) => {
      const hasNewerLocalEdits =
        state.workflowPendingVersion !== null && state.workflowPendingVersion > version;
      return {
        workflowBaseVersion: version,
        workflowPendingVersion: hasNewerLocalEdits ? state.workflowPendingVersion : version,
        workflowPendingSourceId:
          state.workflowPendingSourceId === sourceId ? null : state.workflowPendingSourceId,
        workflowDirty: hasNewerLocalEdits ? state.workflowDirty : false,
        workflowConflict: null,
      };
    });
}
