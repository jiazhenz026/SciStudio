/**
 * #2433 — leaving a project ends its runs, with the user's consent.
 *
 * A run belongs to the project that started it: switching projects cancels
 * every run of the project being left and closes its AI terminals. Before any
 * action that leaves the open project (opening or creating another project,
 * deleting the open one, starting a tutorial), the GUI asks the backend which
 * runs are live — backend truth, not the canvas state — and asks the user only
 * when there are some. Closing the window or losing the connection never gets
 * here: that does not cancel a run (#2327).
 */
import type { LiveRunResponse, ProjectResponse } from "../types/api";
import { api } from "./api";

/**
 * The store state the leave flow reads and writes. Passed in rather than
 * imported, so a store slice can use this without an import cycle.
 */
export interface LeaveProjectStore {
  getState: () => {
    currentProject: ProjectResponse | null;
    markRunsEnded: (runIds: string[]) => void;
  };
}

export interface LeaveProjectOptions {
  /** How to ask; defaults to `window.confirm`. */
  confirm?: (message: string) => boolean;
}

/** The question the user is asked before live runs are cancelled. */
export function leaveProjectMessage(projectName: string, runs: readonly LiveRunResponse[]): string {
  const workflows = [...new Set(runs.map((run) => run.workflow_id))].join(", ");
  const count = runs.length === 1 ? "1 workflow run is" : `${runs.length} workflow runs are`;
  return (
    `${count} still running in "${projectName}" (${workflows}).\n\n` +
    "Switching projects cancels them and closes this project's AI terminals. Switch anyway?"
  );
}

/**
 * Resolve to `true` when the open project may be left: it has no live runs, or
 * the user agreed and its runs have been ended. Resolve to `false` when the user
 * chose to stay. A backend that cannot answer the question does not block the
 * switch; the backend itself still refuses one that would leave a run behind.
 */
export async function confirmLeavingProject(
  store: LeaveProjectStore,
  options: LeaveProjectOptions = {},
): Promise<boolean> {
  const project = store.getState().currentProject;
  if (!project) return true;
  let runs: LiveRunResponse[];
  try {
    runs = (await api.getActiveProjectRuns()).runs;
  } catch {
    return true;
  }
  if (runs.length === 0) return true;
  const ask = options.confirm ?? ((message: string) => window.confirm(message));
  if (!ask(leaveProjectMessage(project.name, runs))) return false;
  const ended = await api.endActiveProjectRuns();
  // Their late socket events must not land on the next project's workflows.
  store.getState().markRunsEnded(ended.ended_run_ids);
  return true;
}

/** Whether `projectIdOrPath` names `project`, the project that is already open. */
export function isOpenProject(project: ProjectResponse | null, projectIdOrPath: string): boolean {
  return project !== null && (project.id === projectIdOrPath || project.path === projectIdOrPath);
}
