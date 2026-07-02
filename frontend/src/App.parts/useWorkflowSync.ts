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

import { startTransition, useCallback, useRef } from "react";

import { api, ApiError } from "../lib/api";
import { useAppStore } from "../store";
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
  reloadBlocks: () => Promise<void>;
  saveWorkflow: () => Promise<void>;
  saveWorkflowAs: () => Promise<void>;
}

async function persistWorkflow(workflow: WorkflowResponse): Promise<WorkflowResponse> {
  try {
    return await api.updateWorkflow(workflow.id, workflow);
  } catch (error) {
    if (error instanceof ApiError && error.status !== 404) {
      throw error;
    }
    return await api.createWorkflow(workflow);
  }
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

  // Tracks whether the *previous* save attempt failed validation. A successful
  // save then clears only its own stale validation banner — it must not wipe an
  // error owned by another source (e.g. a run/execute validation error), which
  // caused that banner to flash and vanish when a debounced autosave landed
  // just after a failed run.
  const saveErroredRef = useRef(false);

  // #1421: useCallback so consumers (saveWorkflow, boot effect, ...) get a
  // stable function identity.
  const refreshProjects = useCallback(async () => {
    const projects = await api.listProjects();
    startTransition(() => setProjects(projects));
  }, [setProjects]);

  const refreshBlocks = useCallback(async () => {
    const payload = await api.listBlocks();
    const schemas = await Promise.all(
      payload.blocks.map((block) => api.getBlockSchema(block.type_name)),
    );
    startTransition(() => {
      schemas.forEach((schema) => setBlockSchema(schema));
      setBlocks(payload.blocks);
    });
  }, [setBlocks, setBlockSchema]);

  // #1910: the palette "Reload" button. Unlike ``refreshBlocks`` (which only
  // re-fetches the cached catalog and is also fired by the WS ``blocks.reloaded``
  // handler — so it must NOT itself trigger a reload, or it would loop), this
  // first POSTs ``/api/blocks/reload`` to force a backend re-scan of drop-in
  // block sources, then re-fetches so an in-place edit (e.g. a changed base
  // class → new colour/icon) shows up immediately without waiting on the WS
  // echo. Errors surface in the shared error banner rather than being swallowed.
  const reloadBlocks = useCallback(async () => {
    try {
      await api.reloadBlocks();
      await refreshBlocks();
    } catch (error) {
      setLastError((error as Error).message);
    }
  }, [refreshBlocks, setLastError]);

  // #1421: stable identity across renders.
  const saveWorkflow = useCallback(async () => {
    if (!currentProject) return;
    // #1891 P1: never PUT while a version conflict is pending. Gating at the
    // source covers every entry point — debounced autosave, the Ctrl/Cmd+S
    // shortcut, and Save As (which calls saveWorkflow first) — so none can PUT
    // the stale local canvas and clobber the remote (agent) write before the
    // user resolves the conflict dialog. Read live state via getState so the
    // callback identity stays stable.
    if (useAppStore.getState().workflowConflict) return;
    try {
      let saved: WorkflowResponse;
      let projectForState = currentProject;
      try {
        saved = await persistWorkflow(workflowPayload);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) {
          throw error;
        }
        const reopened = await api.openProject(currentProject.id);
        projectForState = reopened;
        setCurrentProject(reopened);
        saved = await persistWorkflow(workflowPayload);
      }
      markWorkflowSaved();
      // A successful save (HTTP 200) means validation passed, so a *save*
      // validation banner is now stale and clears itself. Only clear when the
      // previous save actually errored, so a concurrent autosave success does
      // not wipe an unrelated (e.g. run/execute) error.
      if (saveErroredRef.current) {
        setLastError(null);
        saveErroredRef.current = false;
      }
      await refreshProjects();
      setCurrentProject({
        ...projectForState,
        current_workflow_id: saved.id,
        workflows: projectForState.workflows.includes(saved.id)
          ? projectForState.workflows
          : [...projectForState.workflows, saved.id],
      });
    } catch (error) {
      setLastError((error as Error).message);
      saveErroredRef.current = true;
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

  return { refreshProjects, refreshBlocks, reloadBlocks, saveWorkflow, saveWorkflowAs };
}
