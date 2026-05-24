// Extracted from App.tsx as part of the #1422 god-file split.
//
// useWorkflowExecutionActions — bundles the run / pause / resume / cancel /
// startFromSelected / per-block run+restart callbacks the toolbar and the
// workflow canvas dispatch. Each action keeps the same shape and
// side-effects as the inline implementation; this hook merely consolidates
// them so App.tsx can stay focused on lifecycle wiring.

import { useCallback } from "react";

import { api } from "../lib/api";
import type { ProjectResponse } from "../types/api";

export interface WorkflowExecutionDeps {
  currentProject: ProjectResponse | null;
  workflowId: string | null;
  selectedNodeId: string | null;
  saveWorkflow: () => Promise<void>;
  setLastError: (message: string | null) => void;
  workflowPayloadId: string;
}

export interface WorkflowExecutionActions {
  runWorkflow: () => Promise<void>;
  pauseWorkflow: () => Promise<void>;
  resumeWorkflow: () => Promise<void>;
  cancelWorkflow: () => Promise<void>;
  startFromSelected: () => Promise<void>;
  handleRunBlock: (blockId: string) => Promise<void>;
  handleRestartBlock: (blockId: string) => Promise<void>;
}

function surfaceExecutionError(
  setLastError: (message: string | null) => void,
  error: unknown,
): void {
  const message = error instanceof Error ? error.message : String(error);
  window.setTimeout(() => setLastError(message), 0);
}

export function useWorkflowExecutionActions(deps: WorkflowExecutionDeps): WorkflowExecutionActions {
  const {
    currentProject,
    workflowId,
    selectedNodeId,
    saveWorkflow,
    setLastError,
    workflowPayloadId,
  } = deps;

  const runWorkflow = useCallback(async () => {
    if (!currentProject) return;
    try {
      await saveWorkflow();
      await api.executeWorkflow(workflowPayloadId);
      setLastError(null);
      // #793: do NOT auto-switch to the Logs tab.
    } catch (error) {
      surfaceExecutionError(setLastError, error);
    }
  }, [currentProject, saveWorkflow, setLastError, workflowPayloadId]);

  const pauseWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.pauseWorkflow(workflowId);
  }, [workflowId]);

  const resumeWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.resumeWorkflow(workflowId);
  }, [workflowId]);

  const cancelWorkflow = useCallback(async () => {
    if (!workflowId) return;
    await api.cancelWorkflow(workflowId);
  }, [workflowId]);

  const startFromSelected = useCallback(async () => {
    if (!workflowId || !selectedNodeId) return;
    try {
      await saveWorkflow();
      await api.executeFrom(workflowId, selectedNodeId);
      setLastError(null);
    } catch (error) {
      surfaceExecutionError(setLastError, error);
    }
  }, [saveWorkflow, selectedNodeId, setLastError, workflowId]);

  const handleRunBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        await api.executeFrom(workflowId, blockId);
        setLastError(null);
      } catch (error) {
        surfaceExecutionError(setLastError, error);
      }
    },
    [saveWorkflow, setLastError, workflowId],
  );

  const handleRestartBlock = useCallback(
    async (blockId: string) => {
      if (!workflowId) return;
      try {
        await saveWorkflow();
        await api.executeFrom(workflowId, blockId);
        setLastError(null);
      } catch (error) {
        surfaceExecutionError(setLastError, error);
      }
    },
    [saveWorkflow, setLastError, workflowId],
  );

  return {
    runWorkflow,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    startFromSelected,
    handleRunBlock,
    handleRestartBlock,
  };
}
