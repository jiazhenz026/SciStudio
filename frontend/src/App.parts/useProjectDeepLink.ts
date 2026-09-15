// #2385 — boot into the project named by an `open_gui` deep link.
//
// `open_gui` gives an agent `?project=<path>&workflow=<id>`. This page is then a
// second client of the user's running session, so it attaches to the project
// the backend already has open rather than calling `openProject`: re-opening
// resets the backend's data catalog, registries, and stores under the user's
// desktop window. If the backend has a different project open, or none, the
// page says so and leaves the session alone.
//
// Once attached, every request carries the attached project id. Workflow routes
// resolve through the backend's single active project, so if the user switches
// projects the backend refuses those requests and this page detaches, instead of
// editing the new project while still showing the old one.

import { useEffect, useRef } from "react";

import { api } from "../lib/api";
import { ATTACHED_PROJECT_CHANGED_EVENT, setAttachedProjectBinding } from "../lib/api/core";
import { readProjectDeepLink, sameProjectPath, type ProjectDeepLink } from "../lib/projectDeepLink";
import { useAppStore } from "../store";
import type { ProjectResponse, WorkflowResponse } from "../types/api";

export interface ProjectDeepLinkDeps {
  setCurrentProject: (project: ProjectResponse | null) => void;
  openTab: (workflow: WorkflowResponse, displayName?: string) => void;
  setLastError: (message: string | null) => void;
}

/** Attach to the backend's open project if it is the one `link` names. */
export async function attachProjectDeepLink(
  link: ProjectDeepLink,
  { setCurrentProject, openTab, setLastError }: ProjectDeepLinkDeps,
): Promise<void> {
  let active;
  try {
    active = await api.getActiveProject();
  } catch (error) {
    setLastError(`Could not read the project SciStudio has open: ${(error as Error).message}`);
    return;
  }
  const { project, active_workflow_id: activeWorkflowId } = active;
  if (!project) {
    setLastError(
      `This link opens the project at ${link.project}, but SciStudio has no project open. ` +
        "Open the project in SciStudio, then reload this page.",
    );
    return;
  }
  if (!sameProjectPath(project.path, link.project)) {
    setLastError(
      `This link opens the project at ${link.project}, but SciStudio has "${project.name}" ` +
        `(${project.path}) open. The running session was left unchanged; request a new link.`,
    );
    return;
  }
  // Bind before anything else is read, so a switch in between is refused too.
  setAttachedProjectBinding(project.id);
  // Drop tabs this browser rehydrated from an earlier visit, as openProject does.
  useAppStore.setState({ tabs: [], activeTabId: null });
  setCurrentProject(project);
  const workflowId = link.workflow ?? activeWorkflowId ?? project.current_workflow_id ?? null;
  if (!workflowId) return;
  try {
    const workflow = await api.getWorkflow(workflowId);
    // A refused read already detached the page; do not reopen a tab for it.
    if (useAppStore.getState().currentProject?.id !== project.id) return;
    openTab(workflow, workflowId);
  } catch (error) {
    if (useAppStore.getState().currentProject?.id !== project.id) return;
    setLastError(`Could not open workflow "${workflowId}": ${(error as Error).message}`);
  }
}

/**
 * Leave the attached project after the backend refused a bound request.
 *
 * The binding stays in place: a caller already past its first request (a run
 * that saves, then executes) must keep being refused rather than land on the
 * project the user switched to. Reloading the page is the way back.
 */
export function detachProjectDeepLink({
  setCurrentProject,
  setLastError,
}: Pick<ProjectDeepLinkDeps, "setCurrentProject" | "setLastError">): void {
  const state = useAppStore.getState();
  // Every later refused request fires again; the first one already detached.
  if (!state.currentProject) return;
  const name = state.currentProject.name;
  useAppStore.setState({ tabs: [], activeTabId: null });
  state.setWorkflow(null);
  setCurrentProject(null);
  setLastError(
    `SciStudio no longer has "${name}" open, so this page ` +
      "detached instead of touching another project. Request a new link.",
  );
}

/** One-shot boot effect: attach when the page URL carries a project deep link. */
export function useProjectDeepLink(deps: ProjectDeepLinkDeps): void {
  const { setCurrentProject, openTab, setLastError } = deps;

  useEffect(() => {
    if (!readProjectDeepLink()) return undefined;
    const onChanged = () => detachProjectDeepLink({ setCurrentProject, setLastError });
    window.addEventListener(ATTACHED_PROJECT_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(ATTACHED_PROJECT_CHANGED_EVENT, onChanged);
  }, [setCurrentProject, setLastError]);

  const attemptedRef = useRef(false);
  useEffect(() => {
    if (attemptedRef.current) return;
    attemptedRef.current = true;
    const link = readProjectDeepLink();
    if (!link) return;
    void attachProjectDeepLink(link, { setCurrentProject, openTab, setLastError });
    // One-shot like the boot effect in useAppLifecycleEffects: re-running would
    // re-attach and clobber tabs the viewer opened since.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
