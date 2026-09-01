// Extracted from App.tsx to keep App() under its max-lines-per-function
// budget. The desktop application menu (useDesktopMenuActions) needs the same
// close-the-project logic without importing the App component module.

import { useAppStore } from "../store";
import type { ProjectResponse, WorkflowResponse } from "../types/api";

export function emptyWorkflow(id = "main"): WorkflowResponse {
  return {
    id,
    version: "1.0.0",
    description: "",
    nodes: [],
    edges: [],
    metadata: {},
  };
}

/**
 * Close the active project: clear the project, reset the canvas/execution, and
 * drop the previous project's open workflow tabs (bug #5). Defaults to the
 * store's own actions so call sites don't have to thread them through.
 */
export function closeCurrentProject(actions?: {
  setCurrentProject: (project: ProjectResponse | null) => void;
  setWorkflow: (workflow: WorkflowResponse | null) => void;
  resetExecution: () => void;
}): void {
  const { setCurrentProject, setWorkflow, resetExecution } = actions ?? useAppStore.getState();
  setCurrentProject(null);
  setWorkflow(emptyWorkflow());
  resetExecution();
  useAppStore.setState({ tabs: [], activeTabId: null });
}
