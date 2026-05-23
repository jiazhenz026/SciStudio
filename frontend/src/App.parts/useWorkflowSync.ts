// Extracted from App.tsx as part of the #1422 god-file split.
//
// useWorkflowSync — owns the API-backed sync callbacks: `refreshProjects`,
// `refreshBlocks`, and the workflow save / save-as path. Lifted out of
// App.tsx so the network-bound state syncing lives in one place rather
// than being interleaved with UI handlers.
//
// All callbacks use `useCallback` with stable Zustand setter identities so
// they remain referentially equal across renders — that is what lets
// downstream `useEffect`s (autosave, keyboard shortcuts) keep their
// dependency arrays exhaustive without an inline disable.

import { startTransition, useCallback } from "react";

import { api } from "../lib/api";
import type {
  BlockSchemaResponse,
  BlockSummary,
  ProjectResponse,
  WorkflowResponse,
} from "../types/api";

export interface WorkflowSyncDeps {
  currentProject: ProjectResponse | null;
  setCurrentProject: (project: ProjectResponse | null) => void;
  setBlocks: (blocks: BlockSummary[]) => void;
  setBlockSchema: (schema: BlockSchemaResponse) => void;
  setProjects: (projects: ProjectResponse[]) => void;
  markWorkflowSaved: () => void;
  setLastError: (message: string | null) => void;
  workflowPayload: WorkflowResponse;
  workflowId: string | null;
}

export interface WorkflowSync {
  refreshProjects: () => Promise<void>;
  refreshBlocks: () => Promise<void>;
  saveWorkflow: () => Promise<void>;
  saveWorkflowAs: () => Promise<void>;
}

export function useWorkflowSync(deps: WorkflowSyncDeps): WorkflowSync {
  const {
    currentProject,
    setCurrentProject,
    setBlocks,
    setBlockSchema,
    setProjects,
    markWorkflowSaved,
    setLastError,
    workflowPayload,
    workflowId,
  } = deps;

  // #1421: useCallback so consumers (saveWorkflow, boot effect, ...) get a
  // stable function identity.
  const refreshProjects = useCallback(async () => {
    const projects = await api.listProjects();
    startTransition(() => setProjects(projects));
  }, [setProjects]);

  const refreshBlocks = useCallback(async () => {
    const payload = await api.listBlocks();
    startTransition(() => setBlocks(payload.blocks));
    const schemas = await Promise.all(
      payload.blocks.map((block) => api.getBlockSchema(block.type_name)),
    );
    startTransition(() => {
      schemas.forEach((schema) => setBlockSchema(schema));
    });
  }, [setBlocks, setBlockSchema]);

  // #1421: stable identity across renders.
  const saveWorkflow = useCallback(async () => {
    if (!currentProject) return;
    try {
      let saved: WorkflowResponse;
      try {
        saved = await api.updateWorkflow(workflowPayload.id, workflowPayload);
      } catch {
        saved = await api.createWorkflow(workflowPayload);
      }
      markWorkflowSaved();
      await refreshProjects();
      setCurrentProject({
        ...currentProject,
        current_workflow_id: saved.id,
        workflows: currentProject.workflows.includes(saved.id)
          ? currentProject.workflows
          : [...currentProject.workflows, saved.id],
      });
    } catch (error) {
      setLastError((error as Error).message);
    }
  }, [
    currentProject,
    workflowPayload,
    markWorkflowSaved,
    refreshProjects,
    setCurrentProject,
    setLastError,
  ]);

  const saveWorkflowAs = useCallback(async () => {
    if (!currentProject) return;
    try {
      await saveWorkflow();
    } catch {
      // Ignore — saveWorkflow already sets lastError.
    }
    try {
      const defaultName = (workflowId ?? "Untitled") + ".yaml";
      const result = await api.openNativeSaveDialog({
        defaultFilename: defaultName,
        fileFilter: "YAML files (*.yaml)|*.yaml|All files (*.*)|*.*",
      });
      if (!result.paths || result.paths.length === 0) return;
      let savePath = result.paths[0];
      if (!savePath.endsWith(".yaml") && !savePath.endsWith(".yml")) {
        savePath += ".yaml";
      }
      await api.exportWorkflowToPath(workflowPayload.id, savePath);
    } catch (error) {
      setLastError((error as Error).message);
    }
  }, [currentProject, saveWorkflow, workflowId, workflowPayload, setLastError]);

  return { refreshProjects, refreshBlocks, saveWorkflow, saveWorkflowAs };
}
