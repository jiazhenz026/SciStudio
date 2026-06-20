// Extracted from App.tsx as part of the #1422 god-file split.
//
// useProjectActions — bundles the project / workflow / file CRUD callbacks
// the toolbar / palette / tab bar dispatch. Each action keeps the same
// shape and side-effects as the inline implementation; this hook merely
// gives them a single home so App.tsx can stay focused on the render tree
// and the cross-cutting effects.
//
// All async actions surface errors through `setLastError` so the error
// banner above the workspace still reflects them.

import { useCallback } from "react";

import type { PromptRequest } from "../components/PromptDialog";
import { ApiError, api } from "../lib/api";
import { probeProjectFileExistence } from "../lib/fileExistence";
import { useAppStore } from "../store";
import type { ProjectResponse, WorkflowResponse } from "../types/api";

function emptyWorkflow(id = "main"): WorkflowResponse {
  return {
    id,
    version: "1.0.0",
    description: "",
    nodes: [],
    edges: [],
    metadata: {},
  };
}

export interface ProjectActionsDeps {
  currentProject: ProjectResponse | null;
  setCurrentProject: (project: ProjectResponse | null) => void;
  setWorkflow: (workflow: WorkflowResponse | null) => void;
  resetExecution: () => void;
  openTab: (workflow: WorkflowResponse, displayName?: string) => void;
  openFileTab: (path: string, options?: { readOnly?: boolean }) => void;
  closeProjectDialog: () => void;
  setLastError: (message: string | null) => void;
  refreshProjects: () => Promise<void>;
  setBusy: (busy: boolean) => void;
  /** Promise-based prompt (window.prompt is unsupported in Electron). */
  promptInput: (opts: Omit<PromptRequest, "resolve">) => Promise<string | null>;
}

export interface ProjectActions {
  loadWorkflowForProject: (project: ProjectResponse) => Promise<void>;
  loadWorkflowById: (wfId: string, displayName?: string) => Promise<void>;
  openProject: (projectIdOrPath: string) => Promise<void>;
  submitProjectDialog: () => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  newWorkflow: () => void;
  createNewCustomBlock: () => Promise<void>;
  createNewNote: () => Promise<void>;
  importWorkflow: () => Promise<void>;
}

async function ensureNewNoteDirectory(
  projectId: string,
  trimmed: string,
): Promise<{ ok: true; filePath: string } | { ok: false; message: string }> {
  let filePath = `notes/${trimmed}.md`;
  try {
    await api.getProjectTree(projectId, "notes");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      filePath = `${trimmed}.md`;
    } else {
      const message = error instanceof Error ? error.message : String(error);
      return { ok: false, message: `Failed to locate notes directory: ${message}` };
    }
  }
  return { ok: true, filePath };
}

interface WorkflowLoadHelpers {
  openTab: ProjectActionsDeps["openTab"];
  resetExecution: ProjectActionsDeps["resetExecution"];
  setLastError: ProjectActionsDeps["setLastError"];
}

function useWorkflowLoaders({ openTab, resetExecution, setLastError }: WorkflowLoadHelpers) {
  const loadWorkflowForProject = useCallback(
    async (project: ProjectResponse) => {
      if (project.current_workflow_id) {
        const workflow = await api.getWorkflow(project.current_workflow_id);
        // #796: pass the workflow id as displayName fallback so a YAML with
        // an empty `id:` still gets a non-blank tab label.
        openTab(workflow, project.current_workflow_id);
        return;
      }
      openTab(emptyWorkflow("main"), "main");
    },
    [openTab],
  );

  const loadWorkflowById = useCallback(
    async (wfId: string, displayName?: string) => {
      try {
        const workflow = await api.getWorkflow(wfId);
        openTab(workflow, displayName ?? wfId);
        resetExecution();
        setLastError(null);
      } catch (error) {
        setLastError((error as Error).message);
      }
    },
    [openTab, resetExecution, setLastError],
  );

  return { loadWorkflowForProject, loadWorkflowById };
}

interface ProjectLifecycleDeps extends ProjectActionsDeps {
  loadWorkflowForProject: (project: ProjectResponse) => Promise<void>;
}

function useProjectLifecycle(deps: ProjectLifecycleDeps) {
  const {
    currentProject,
    setCurrentProject,
    setWorkflow,
    resetExecution,
    openTab,
    closeProjectDialog,
    setLastError,
    refreshProjects,
    setBusy,
    loadWorkflowForProject,
  } = deps;
  const projectDialog = useAppStore((state) => state.projectDialog);

  const openProject = useCallback(
    async (projectIdOrPath: string) => {
      setBusy(true);
      try {
        const project = await api.openProject(projectIdOrPath);
        // Bug 5: clear current canvas state before loading new project.
        setWorkflow(null);
        resetExecution();
        // Force-clear all tabs from the store.
        useAppStore.setState({ tabs: [], activeTabId: null });

        setCurrentProject(project);
        await refreshProjects();
        await loadWorkflowForProject(project);
        setLastError(null);
        closeProjectDialog();
      } catch (error) {
        setLastError((error as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [
      closeProjectDialog,
      loadWorkflowForProject,
      refreshProjects,
      resetExecution,
      setBusy,
      setCurrentProject,
      setLastError,
      setWorkflow,
    ],
  );

  const submitProjectDialog = useCallback(async () => {
    setBusy(true);
    try {
      if (projectDialog.mode === "new") {
        const project = await api.createProject({
          name: projectDialog.name,
          description: projectDialog.description,
          path: projectDialog.path,
        });
        setCurrentProject(project);
        openTab(emptyWorkflow("main"));
        await refreshProjects();
      } else {
        await openProject(projectDialog.path);
        return;
      }
      closeProjectDialog();
      setLastError(null);
    } catch (error) {
      setLastError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }, [
    closeProjectDialog,
    openProject,
    openTab,
    projectDialog,
    refreshProjects,
    setBusy,
    setCurrentProject,
    setLastError,
  ]);

  const deleteProject = useCallback(
    async (projectId: string) => {
      try {
        await api.deleteProject(projectId);
        if (currentProject?.id === projectId) {
          setCurrentProject(null);
          setWorkflow(null);
          resetExecution();
        }
        await refreshProjects();
      } catch (error) {
        setLastError((error as Error).message);
      }
    },
    [currentProject, refreshProjects, resetExecution, setCurrentProject, setLastError, setWorkflow],
  );

  return { openProject, submitProjectDialog, deleteProject };
}

interface FileActionDeps {
  currentProject: ProjectResponse | null;
  openFileTab: ProjectActionsDeps["openFileTab"];
  promptInput: ProjectActionsDeps["promptInput"];
}

function useFileActions({ currentProject, openFileTab, promptInput }: FileActionDeps) {
  /** ADR-036 §3.7 / §3.12 (I36c) — "New custom block". */
  const createNewCustomBlock = useCallback(async () => {
    if (!currentProject) return;
    const stem = await promptInput({
      title: "New custom block",
      label: "Filename (without .py)",
      defaultValue: "my_block",
      validate: (value) => {
        if (!value) return "Filename must not be empty.";
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
          return "Filename must be a Python identifier (letters, digits, underscores).";
        }
        return null;
      },
    });
    if (stem === null) return;
    const trimmed = stem;
    const filePath = `blocks/${trimmed}.py`;
    // Audit 2026-05-14 P1 #2 — probe before PUT.
    const probe = await probeProjectFileExistence(currentProject.id, filePath);
    if (probe.kind === "exists") {
      window.alert(`A custom block named "${trimmed}.py" already exists. Pick a different name.`);
      return;
    }
    if (probe.kind === "unknown") {
      window.alert(`Failed to check for existing block: ${probe.message}`);
      return;
    }
    try {
      const tpl = await api.getBlockTemplate("basic");
      await api.putProjectFile(currentProject.id, filePath, tpl.content, {
        createParentDirs: true,
      });
      openFileTab(filePath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      window.alert(`Failed to create custom block: ${message}`);
    }
  }, [currentProject, openFileTab, promptInput]);

  /** ADR-036 §3.7 / §3.12 (I36c) — "New note" (markdown). */
  const createNewNote = useCallback(async () => {
    if (!currentProject) return;
    const stem = await promptInput({
      title: "New note",
      label: "Filename (without .md)",
      defaultValue: "note",
      validate: (value) => {
        if (!value) return "Filename must not be empty.";
        if (!/^[A-Za-z0-9._-]+$/.test(value)) {
          return "Note filename may only contain letters, digits, underscores, dots, and hyphens.";
        }
        return null;
      },
    });
    if (stem === null) return;
    const trimmed = stem;
    const dir = await ensureNewNoteDirectory(currentProject.id, trimmed);
    if (!dir.ok) {
      window.alert(dir.message);
      return;
    }
    const filePath = dir.filePath;
    const probe = await probeProjectFileExistence(currentProject.id, filePath);
    if (probe.kind === "exists") {
      window.alert(
        `A note named "${trimmed}.md" already exists at ${filePath}. Pick a different name.`,
      );
      return;
    }
    if (probe.kind === "unknown") {
      window.alert(`Failed to check for existing note: ${probe.message}`);
      return;
    }
    try {
      await api.putProjectFile(currentProject.id, filePath, "");
      openFileTab(filePath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      window.alert(`Failed to create note: ${message}`);
    }
  }, [currentProject, openFileTab, promptInput]);

  return { createNewCustomBlock, createNewNote };
}

export function useProjectActions(deps: ProjectActionsDeps): ProjectActions {
  const {
    currentProject,
    openTab,
    openFileTab,
    resetExecution,
    setCurrentProject,
    setLastError,
    promptInput,
  } = deps;

  const { loadWorkflowForProject, loadWorkflowById } = useWorkflowLoaders({
    openTab,
    resetExecution,
    setLastError,
  });

  const { openProject, submitProjectDialog, deleteProject } = useProjectLifecycle({
    ...deps,
    loadWorkflowForProject,
  });

  const { createNewCustomBlock, createNewNote } = useFileActions({
    currentProject,
    openFileTab,
    promptInput,
  });

  const newWorkflow = useCallback(async () => {
    const name = await promptInput({
      title: "New workflow",
      label: "Workflow name",
      defaultValue: "Untitled",
    });
    if (name === null) return; // cancelled
    const id = name.trim() || "Untitled";
    openTab(emptyWorkflow(id));
    resetExecution();
  }, [openTab, resetExecution, promptInput]);

  const importWorkflow = useCallback(async () => {
    if (!currentProject) return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".yaml,.yml";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const workflow = await api.importWorkflowFile(file);
        openTab(workflow);
        resetExecution();
        setLastError(null);
        setCurrentProject({
          ...currentProject,
          current_workflow_id: workflow.id,
          workflows: currentProject.workflows.includes(workflow.id)
            ? currentProject.workflows
            : [...currentProject.workflows, workflow.id],
        });
      } catch (error) {
        setLastError((error as Error).message);
      }
    };
    input.click();
  }, [currentProject, openTab, resetExecution, setCurrentProject, setLastError]);

  return {
    loadWorkflowForProject,
    loadWorkflowById,
    openProject,
    submitProjectDialog,
    deleteProject,
    newWorkflow,
    createNewCustomBlock,
    createNewNote,
    importWorkflow,
  };
}
