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
 *
 * ADR-054 FR-013 — emptying the tab list is a wholesale wipe with no per-tab
 * hook, and deliberately stays that way. A MiniApp tab's backend context (and
 * its `panel.py` process) is ended by its pane's unmount, in `PanelFrame`'s
 * effect cleanup, so this wipe ends every MiniApp open at the switch without
 * needing to know they were there. Adding a per-tab teardown here would only
 * cover this one path and miss the others.
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
