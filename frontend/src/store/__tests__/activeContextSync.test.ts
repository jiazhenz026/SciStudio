/**
 * #2395 — the active-workflow context a page publishes to the agent.
 *
 * - F-5: the sync dedupes on (project, workflow). Every new project starts on a
 *   workflow named `main`, so deduping on the id alone sent no POST when the
 *   user moved to another project's `main`, and the agent's
 *   `get_active_workflow_context` stayed empty.
 * - Owner scope addition: store initialisation used to POST `null`, so every
 *   freshly loaded browser page cleared the agent's context. A page now
 *   publishes only when a workflow is actually selected or changed in it; a
 *   page attached through an `open_gui` deep link (#2385) never publishes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  mockBackend,
  type MockBackend,
  type MockRequest,
} from "../../__tests__/contract/mockBackend";
import { createActiveWorkflowSync, type ActiveWorkflowContext } from "../activeWorkflowSync";
import type { ProjectResponse, WorkflowResponse } from "../../types/api";

function workflow(id: string): WorkflowResponse {
  return { id, version: "1.0.0", description: "", metadata: {}, nodes: [], edges: [] };
}

function project(id: string): ProjectResponse {
  return {
    id,
    name: id,
    path: `/tmp/${id}`,
    description: "",
    last_opened: "",
    workflow_count: 0,
    workflows: [],
    current_workflow_id: null,
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

let backend: MockBackend | undefined;

function installBackend(): MockBackend {
  backend = mockBackend({
    "POST /api/ai/active-context": (request: MockRequest) => ({
      workflow_id: (request.body as { workflow_id: string | null }).workflow_id,
    }),
  });
  return backend;
}

function postedWorkflowIds(): Array<string | null> {
  return (backend?.callsTo("POST /api/ai/active-context") ?? []).map(
    (call) => (call.body as { workflow_id: string | null }).workflow_id,
  );
}

/** Load a fresh store module, as a newly opened page does. */
async function loadFreshStore() {
  vi.resetModules();
  return (await import("../index")).useAppStore;
}

afterEach(() => {
  backend?.restore();
  backend = undefined;
  window.history.replaceState(null, "", "/");
});

describe("store-level active-context publishing", () => {
  beforeEach(() => {
    installBackend();
  });

  it("a freshly loaded page does not clear the agent's context", async () => {
    const useAppStore = await loadFreshStore();
    await tick();

    expect(useAppStore.getState().workflowId).toBeNull();
    expect(postedWorkflowIds()).toEqual([]);
  });

  it("opening a project and its workflow publishes, and a new project's `main` publishes again", async () => {
    const useAppStore = await loadFreshStore();

    // The `openProject` store sequence on a fresh page.
    useAppStore.getState().setCurrentProject(project("A"));
    useAppStore.getState().openTab(workflow("main"));
    await vi.waitFor(() => expect(postedWorkflowIds()).toEqual(["main"]));

    // The `submitProjectDialog` (mode "new") store sequence: same workflow id.
    useAppStore.getState().resetExecution();
    useAppStore.setState({ tabs: [], activeTabId: null });
    useAppStore.getState().setCurrentProject(project("B"));
    useAppStore.getState().openTab(workflow("main"));
    await vi.waitFor(() => expect(postedWorkflowIds()).toEqual(["main", "main"]));

    // An unrelated store change does not re-post the same (project, workflow).
    useAppStore.getState().setPlotPreviewTarget(null);
    await tick();
    expect(postedWorkflowIds()).toEqual(["main", "main"]);
  });

  it("a page attached through the open_gui deep link never publishes", async () => {
    window.history.replaceState(null, "", "/?project=%2Ftmp%2FA&workflow=main");
    const useAppStore = await loadFreshStore();

    useAppStore.getState().setCurrentProject(project("A"));
    useAppStore.getState().openTab(workflow("main"));
    useAppStore.getState().openTab(workflow("qc"));
    await tick();

    expect(postedWorkflowIds()).toEqual([]);
  });
});

describe("createActiveWorkflowSync", () => {
  const none: ActiveWorkflowContext = { projectId: null, workflowId: null };

  function makeSync(initial: ActiveWorkflowContext = none, attached = false) {
    const post = vi.fn(async (_workflowId: string | null) => undefined);
    const sync = createActiveWorkflowSync(initial, { post, isAttached: () => attached });
    return { post, sync };
  }

  it("treats the starting context as already in sync", () => {
    const { post, sync } = makeSync({ projectId: "A", workflowId: "main" });
    sync({ projectId: "A", workflowId: "main" });
    expect(post).not.toHaveBeenCalled();
  });

  it("publishes a workflow change and a project change with the same workflow id", () => {
    const { post, sync } = makeSync();
    sync({ projectId: "A", workflowId: "main" });
    sync({ projectId: "A", workflowId: "qc" });
    sync({ projectId: "B", workflowId: "qc" });
    expect(post.mock.calls.map(([id]) => id)).toEqual(["main", "qc", "qc"]);
  });

  it("publishes closing a workflow once, not every no-workflow step of a project switch", () => {
    const { post, sync } = makeSync({ projectId: "A", workflowId: "main" });
    sync({ projectId: "A", workflowId: null });
    sync({ projectId: "B", workflowId: null });
    sync({ projectId: null, workflowId: null });
    expect(post.mock.calls.map(([id]) => id)).toEqual([null]);
  });

  it("never publishes from an attached page", () => {
    const { post, sync } = makeSync(none, true);
    sync({ projectId: "A", workflowId: "main" });
    sync({ projectId: null, workflowId: null });
    expect(post).not.toHaveBeenCalled();
  });
});
