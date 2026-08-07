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
import { askFileDestination, type FileDestination } from "../components/promotion/dialogChannel";
import { ApiError, api } from "../lib/api";
import { chooseSubworkflowFile } from "../lib/chooseSubworkflowFile";
import { probeProjectFileExistence, probeUserLibraryFileExistence } from "../lib/fileExistence";
import { useAppStore } from "../store";
import type { ProjectResponse, UserLibraryTarget, WorkflowResponse } from "../types/api";

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
  openTab: (
    workflow: WorkflowResponse,
    displayName?: string,
    runPrefix?: string,
    tabKey?: string,
  ) => void;
  openFileTab: (path: string, options?: { readOnly?: boolean }) => void;
  closeProjectDialog: () => void;
  setLastError: (message: string | null) => void;
  refreshProjects: () => Promise<void>;
  /**
   * Re-fetch the block catalog (summaries + schemas). Called on project
   * open/create so the new project's project-scoped custom blocks and any
   * package blocks are in the catalog before the canvas renders their nodes
   * — otherwise those nodes fall back to a generic, port-less placeholder
   * until the user manually reloads the palette (bug #2 / #8).
   */
  refreshBlocks: () => Promise<void>;
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
  /** ADR-053 FR-032 — "New data type", the type-side twin of the above. */
  createNewDataType: () => Promise<void>;
  createNewNote: () => Promise<void>;
  importWorkflow: () => Promise<void>;
  /**
   * ADR-044 §3 — open a subworkflow node's referenced file (`config.ref.path`,
   * project-relative) in a canvas tab on double-click.
   */
  openSubworkflow: (refPath: string) => void;
  /**
   * ADR-044 FR-011 (US5) + §10 / US6 AS2 — run the shared choose/import
   * subworkflow flow for a node that has no usable ref ("Choose subworkflow
   * file…") OR a broken ref ("Locate file…"). Picks an external file via the
   * native dialog, imports it into `<project>/subworkflows/`, repoints
   * `config.ref.path`, and refreshes the node's resolved ports in place.
   */
  locateSubworkflow: (nodeId: string) => void;
}

/**
 * ADR-044 — derive the workflow id (filename stem) from a project-relative
 * `config.ref.path`. `loadWorkflowById` resolves a workflow by its id, which is
 * the filename stem (matching ProjectTree's `.yaml` double-click convention),
 * so a ref path like `subworkflows/bar.swf.yaml` resolves to id `bar`.
 */
export function subworkflowRefToWorkflowId(refPath: string): string {
  const base = refPath.split("/").pop() ?? refPath;
  const stem = base.replace(/\.(swf\.)?(yaml|yml)$/i, "");
  return stem || base;
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
    refreshBlocks,
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
        // #2/#8: refresh the block catalog for the newly opened project so its
        // custom/package blocks resolve to proper IO/process nodes with ports
        // before the workflow renders (avoids the generic gray placeholder).
        await refreshBlocks();
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
      refreshBlocks,
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
        // Bug 5: clear the previous project's open tabs + execution state before
        // switching to the newly created project (mirror openProject()).
        resetExecution();
        useAppStore.setState({ tabs: [], activeTabId: null });
        setCurrentProject(project);
        openTab(emptyWorkflow("main"));
        await refreshProjects();
        await refreshBlocks();
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
    refreshBlocks,
    resetExecution,
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

/**
 * ADR-053 §8 — everything that differs between "New custom block" and
 * "New data type".
 *
 * FR-033 requires the two flows to share their prompt, validation,
 * collision-probe, write-dispatch, and open-file steps, and to differ only in
 * "the target subdirectory and template kind". This record is that difference,
 * written down: {@link createDropinFile} below is the flow, and it reads every
 * varying value from here. Two parallel copies would drift the first time
 * either one changed — which is the whole reason FR-033 exists.
 */
interface DropinFileKind {
  /** Dialog heading, and the noun used in the destination question (FR-029). */
  title: string;
  noun: string;
  defaultStem: string;
  /** Project-relative drop-in directory, e.g. `blocks/`. */
  projectDirectory: string;
  /** The library directory the same tier maps to, for the E4 option copy. */
  libraryDirectory: string;
  /** The user library target the library destination writes to (FR-006). */
  target: UserLibraryTarget;
  /** FR-028: the type template mirrors the block template's response shape. */
  fetchTemplate: () => Promise<{ content: string }>;
}

const NEW_BLOCK_KIND: DropinFileKind = {
  title: "New custom block",
  noun: "block",
  defaultStem: "my_block",
  projectDirectory: "blocks/",
  libraryDirectory: "~/.scistudio/blocks/",
  target: "blocks",
  fetchTemplate: () => api.getBlockTemplate("basic"),
};

const NEW_TYPE_KIND: DropinFileKind = {
  title: "New data type",
  noun: "data type",
  defaultStem: "my_data_type",
  projectDirectory: "types/",
  libraryDirectory: "~/.scistudio/types/",
  target: "types",
  fetchTemplate: () => api.getTypeTemplate("basic"),
};

/** Shared filename validation — a drop-in must be importable by its stem. */
function validateDropinStem(value: string): string | null {
  if (!value) return "Filename must not be empty.";
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    return "Filename must be a Python identifier (letters, digits, underscores).";
  }
  return null;
}

interface DropinFileDeps {
  project: ProjectResponse;
  promptInput: ProjectActionsDeps["promptInput"];
  openFileTab: ProjectActionsDeps["openFileTab"];
  openUserLibraryFileTab: (target: UserLibraryTarget, filename: string) => void;
}

/**
 * ADR-053 §8 — the one new-drop-in-file flow (FR-029 – FR-033).
 *
 * Steps, in order, all shared by both kinds:
 *
 *  1. **Ask where it goes** (FR-029, entry point E4). Spec §8 calls this "the
 *     cheapest possible moment to teach that the library exists, because the
 *     user is already deciding where their work lives".
 *  2. Prompt for a filename and validate it as a Python identifier.
 *  3. **Probe the chosen destination** (FR-031) — the project endpoint or its
 *     user-library counterpart, one probe protocol either way.
 *  4. Fetch the template for this kind (FR-028 for types).
 *  5. Write to the chosen destination (FR-030).
 *  6. Open the new file for editing, through the tab path that destination
 *     can actually save back to.
 */
async function createDropinFile(kind: DropinFileKind, deps: DropinFileDeps): Promise<void> {
  const { project, promptInput, openFileTab, openUserLibraryFileTab } = deps;

  const destination: FileDestination | null = await askFileDestination({
    title: kind.title,
    noun: kind.noun,
    projectName: project.name,
    projectDirectory: kind.projectDirectory,
    libraryDirectory: kind.libraryDirectory,
  });
  if (destination === null) return;

  const stem = await promptInput({
    title: kind.title,
    label: "Filename (without .py)",
    defaultValue: kind.defaultStem,
    validate: validateDropinStem,
  });
  if (stem === null) return;

  const filename = `${stem}.py`;
  const projectPath = `${kind.projectDirectory}${filename}`;
  const where = destination === "library" ? "your library" : "this project";

  // Audit 2026-05-14 P1 #2 (project) / ADR-053 FR-031 (library) — probe before
  // PUT, against whichever destination was chosen.
  const probe =
    destination === "library"
      ? await probeUserLibraryFileExistence(kind.target, filename)
      : await probeProjectFileExistence(project.id, projectPath);
  if (probe.kind === "exists") {
    window.alert(
      `A ${kind.noun} named "${filename}" already exists in ${where}. Pick another name.`,
    );
    return;
  }
  if (probe.kind === "unknown") {
    window.alert(`Failed to check for an existing ${kind.noun}: ${probe.message}`);
    return;
  }

  try {
    const template = await kind.fetchTemplate();
    if (destination === "library") {
      await api.putUserLibraryFile(kind.target, filename, template.content, { overwrite: false });
      openUserLibraryFileTab(kind.target, filename);
    } else {
      await api.putProjectFile(project.id, projectPath, template.content, {
        createParentDirs: true,
      });
      openFileTab(projectPath);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    window.alert(`Failed to create ${kind.noun}: ${message}`);
  }
}

interface FileActionDeps {
  currentProject: ProjectResponse | null;
  openFileTab: ProjectActionsDeps["openFileTab"];
  promptInput: ProjectActionsDeps["promptInput"];
}

function useFileActions({ currentProject, openFileTab, promptInput }: FileActionDeps) {
  const openUserLibraryFileTab = useAppStore((state) => state.openUserLibraryFileTab);

  /**
   * ADR-036 §3.7 / §3.12 (I36c) + ADR-053 FR-029 – FR-031 —
   * "New custom block", now destination-aware.
   */
  const createNewCustomBlock = useCallback(async () => {
    if (!currentProject) return;
    await createDropinFile(NEW_BLOCK_KIND, {
      project: currentProject,
      promptInput,
      openFileTab,
      openUserLibraryFileTab,
    });
  }, [currentProject, openFileTab, openUserLibraryFileTab, promptInput]);

  /**
   * ADR-053 FR-032 — "New data type".
   *
   * The same call, one argument different (FR-033). Everything the two flows
   * share is shared because there is only one of it.
   */
  const createNewDataType = useCallback(async () => {
    if (!currentProject) return;
    await createDropinFile(NEW_TYPE_KIND, {
      project: currentProject,
      promptInput,
      openFileTab,
      openUserLibraryFileTab,
    });
  }, [currentProject, openFileTab, openUserLibraryFileTab, promptInput]);

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

  return { createNewCustomBlock, createNewDataType, createNewNote };
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

  const { createNewCustomBlock, createNewDataType, createNewNote } = useFileActions({
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

  // ADR-044 §3 / US1 AS3 — double-click a (healthy) subworkflow node → open its
  // referenced file in a canvas tab. The ref path is project-relative and may
  // live under `subworkflows/` (FR-011 imports) or `workflows/`, so we open it
  // by PATH (not by workflow id, which only resolves `workflows/<id>.yaml`).
  const openSubworkflow = useCallback(
    async (refPath: string, runPrefix?: string) => {
      const displayName = subworkflowRefToWorkflowId(refPath);
      try {
        const workflow = await api.getWorkflowByPath(refPath);
        // ADR-044 — pass the parent's run-scope prefix so the expanded child
        // canvas maps each inner node to its flattened run id `<prefix><id>`.
        // Do NOT resetExecution here: the whole point of expanding is to see the
        // parent run's live/last status, which lives in the (global) execution
        // state keyed by the prefixed ids. Resetting would blank it out.
        //
        // Key the tab by the unique ref PATH (not the shared workflow.id):
        // several imported copies under `subworkflows/` carry the same internal
        // id, so id-based dedup would open the wrong file. Path-keyed tabs open
        // exactly the referenced copy.
        openTab(workflow, displayName, runPrefix, refPath);
        setLastError(null);
      } catch (error) {
        setLastError((error as Error).message);
      }
    },
    [openTab, setLastError],
  );

  // ADR-044 FR-011 (US5) + §10 / US6 AS2 — the shared choose/import-subworkflow
  // flow. Picks an external file via the native dialog, imports it into
  // `<project>/subworkflows/`, repoints `config.ref.path` (top-level, via
  // `setNodeRef`), and refreshes the node's exposed-port handles in place (via
  // `setNodeResolvedPorts`) so a broken / no-ref node un-breaks immediately.
  // Reads the store actions directly so the canvas affordance and the Config-tab
  // editor share ONE implementation (see `lib/chooseSubworkflowFile`).
  const setNodeRef = useAppStore((state) => state.setNodeRef);
  const setNodeResolvedPorts = useAppStore((state) => state.setNodeResolvedPorts);
  const locateSubworkflow = useCallback(
    (nodeId: string) => {
      void chooseSubworkflowFile(nodeId, { setNodeRef, setNodeResolvedPorts, setLastError });
    },
    [setNodeRef, setNodeResolvedPorts, setLastError],
  );

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
    createNewDataType,
    createNewNote,
    importWorkflow,
    openSubworkflow,
    locateSubworkflow,
  };
}
