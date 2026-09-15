/**
 * #2433 — the frontend follows runs by run id, and leaving a project ends its runs.
 *
 * Before #2433 a run kept executing after a project switch and its events carried
 * only `workflow_id`, so they landed on the next project's same-named workflow
 * (audit repro "F-cross-project"). A run of a workflow and a later run of the same
 * workflow were indistinguishable too.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  mockBackend,
  type MockBackend,
  type MockRequest,
} from "../../__tests__/contract/mockBackend";
import { useProjectActions, type ProjectActions } from "../../App.parts/useProjectActions";
import { handleInteractivePrompt } from "../../hooks/useWebSocket.parts/handleLifecycle";
import { confirmLeavingProject, leaveProjectMessage } from "../../lib/leaveProject";
import { resetAppStore } from "../../testUtils";
import type { ProjectResponse, WorkflowEventMessage, WorkflowResponse } from "../../types/api";
import { useAppStore } from "../index";

type LiveRun = { run_id: string; workflow_id: string };

/** What the fake backend answers; each test sets what it needs. */
let liveRuns: LiveRun[] = [];
let endedRunIds: string[] = [];
/** The backend's active project, which another window may have changed. */
let activeProjectId: string | null = null;
let backend: MockBackend;

function event(overrides: Partial<WorkflowEventMessage> = {}): WorkflowEventMessage {
  return {
    type: "block_done",
    block_id: "load_one",
    workflow_id: "main",
    data: {},
    timestamp: "2026-09-15T00:00:00Z",
    ...overrides,
  };
}

function workflow(id: string): WorkflowResponse {
  return { id, version: "1.0.0", description: "", metadata: {}, nodes: [], edges: [] };
}

function project(id: string): ProjectResponse {
  return {
    id,
    name: `Project ${id}`,
    path: `/tmp/${id}`,
    description: "",
    last_opened: "2026-09-15T00:00:00Z",
    workflow_count: 1,
    workflows: ["main"],
    current_workflow_id: null,
  };
}

/** The store sequence of `useProjectActions.openProject` after the switch. */
function switchTo(p: ProjectResponse): void {
  const store = useAppStore.getState();
  store.setWorkflow(null);
  store.resetExecution();
  useAppStore.setState({ tabs: [], activeTabId: null });
  store.setCurrentProject(p);
  useAppStore.getState().openTab(workflow("main"));
}

beforeEach(() => {
  resetAppStore();
  useAppStore.getState().resetExecution();
  useAppStore.setState({ endedRunIds: [], terminalTabs: [], activeTerminalTabId: null });
  liveRuns = [];
  endedRunIds = [];
  activeProjectId = null;
  backend = mockBackend({
    "GET /api/projects/active/runs": () => ({
      project_id: activeProjectId ?? useAppStore.getState().currentProject?.id ?? null,
      runs: liveRuns,
    }),
    "POST /api/projects/active/end-runs": () => {
      liveRuns = [];
      return { ended_run_ids: endedRunIds };
    },
    "GET /api/projects/{project_id}": (request: MockRequest) =>
      project(decodeURIComponent(request.path.split("/").pop() ?? "")),
  });
});

afterEach(() => {
  cleanup();
  backend.restore();
});

describe("run identity in the execution state", () => {
  it("F-cross-project: a late event of a run ended by the switch does not reach the next project", async () => {
    switchTo(project("A"));
    const store = useAppStore.getState();
    store.consumeEvent(event({ type: "workflow_started", block_id: null, run_id: "run-A" }));
    liveRuns = [{ run_id: "run-A", workflow_id: "main" }];
    endedRunIds = ["run-A"];

    expect(await confirmLeavingProject(useAppStore, { confirm: () => true })).toBe(true);
    switchTo(project("B"));
    // The socket delivers the cancelled run's last events after the switch.
    useAppStore
      .getState()
      .consumeEvent(
        event({ run_id: "run-A", data: { outputs: { out: { data_ref: "data-from-project-A" } } } }),
      );
    useAppStore
      .getState()
      .consumeEvent(event({ type: "workflow_completed", block_id: null, run_id: "run-A" }));

    const state = useAppStore.getState();
    expect(state.currentProject?.id).toBe("B");
    expect(state.blockOutputs).toEqual({});
    expect(state.executionByWorkflow).toEqual({});
  });

  it("ignores another run of the workflow while the followed run is going", () => {
    switchTo(project("A"));
    const store = useAppStore.getState();
    store.consumeEvent(event({ type: "workflow_started", block_id: null, run_id: "run-2" }));
    store.consumeEvent(
      event({ type: "block_error", run_id: "run-1", data: { error: "old failure" } }),
    );
    store.consumeEvent(event({ type: "workflow_completed", block_id: null, run_id: "run-1" }));

    let state = useAppStore.getState();
    expect(state.isRunning).toBe(true);
    expect(state.runId).toBe("run-2");
    expect(state.blockErrors).toEqual({});
    expect(state.logEntries).toEqual([]);

    store.consumeEvent(event({ type: "workflow_completed", block_id: null, run_id: "run-2" }));
    // A page that reconnected mid-run missed run-3's start; its events still land.
    store.consumeEvent(event({ type: "block_running", run_id: "run-3" }));
    state = useAppStore.getState();
    expect(state.isRunning).toBe(false);
    expect(state.runId).toBe("run-3");
    expect(state.blockStates).toEqual({ load_one: "running" });
  });

  it("keeps a later run's prompt when an earlier run of the workflow completes, and drops an ended run's prompt", () => {
    switchTo(project("A"));
    const upsert = useAppStore.getState().upsertInteractivePrompt;
    useAppStore
      .getState()
      .consumeEvent(event({ type: "workflow_started", block_id: null, run_id: "run-2" }));
    handleInteractivePrompt(
      event({ type: "interactive_prompt", block_id: "pick", run_id: "run-2" }),
      {
        upsertInteractivePrompt: upsert,
      },
    );
    useAppStore.getState().markRunsEnded(["run-gone"]);
    handleInteractivePrompt(
      event({
        type: "interactive_prompt",
        workflow_id: "other",
        block_id: "pick",
        run_id: "run-gone",
      }),
      { upsertInteractivePrompt: upsert },
    );

    const prompts = Object.values(useAppStore.getState().interactivePrompts);
    expect(prompts.map((prompt) => prompt.runId)).toEqual(["run-2"]);
  });
});

describe("leaving a project with live runs", () => {
  it("does not ask when the project has no live runs", async () => {
    useAppStore.setState({ currentProject: project("A") });
    const confirm = vi.fn(() => true);

    expect(await confirmLeavingProject(useAppStore, { confirm })).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
    expect(backend.callsTo("POST /api/projects/active/end-runs")).toHaveLength(0);
  });

  it("keeps the runs when the user chooses to stay", async () => {
    useAppStore.setState({ currentProject: project("A") });
    liveRuns = [{ run_id: "r1", workflow_id: "main" }];

    expect(await confirmLeavingProject(useAppStore, { confirm: () => false })).toBe(false);
    expect(backend.callsTo("POST /api/projects/active/end-runs")).toHaveLength(0);
  });

  it("is bound to the project and runs the user confirmed (Codex review on #2439)", async () => {
    useAppStore.setState({ currentProject: project("A") });
    liveRuns = [
      { run_id: "r1", workflow_id: "main" },
      { run_id: "r2", workflow_id: "qc" },
    ];
    endedRunIds = ["r1", "r2"];

    expect(await confirmLeavingProject(useAppStore, { confirm: () => true })).toBe(true);
    const [call] = backend.callsTo("POST /api/projects/active/end-runs");
    expect(call.body).toEqual({ project_id: "A", run_ids: ["r1", "r2"] });
  });

  it("cancels nothing when another window opened a different project", async () => {
    useAppStore.setState({ currentProject: project("A") });
    activeProjectId = "B";
    liveRuns = [{ run_id: "b-run", workflow_id: "main" }];
    const confirm = vi.fn(() => true);

    await expect(confirmLeavingProject(useAppStore, { confirm })).rejects.toThrow(
      "Another window opened a different project",
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(backend.callsTo("POST /api/projects/active/end-runs")).toHaveLength(0);
  });

  it("names the runs and says what switching does", () => {
    const message = leaveProjectMessage("Project A", [
      { run_id: "r1", workflow_id: "main" },
      { run_id: "r2", workflow_id: "qc" },
    ]);
    expect(message).toContain('2 workflow runs are still running in "Project A" (main, qc)');
    expect(message).toContain("cancels them and closes this project's AI terminals");
  });

  it("openProject asks, ends the runs, switches and closes the terminals", async () => {
    let actions: ProjectActions | null = null;
    function Harness() {
      actions = useProjectActions({
        currentProject: project("A"),
        setCurrentProject: (p) => useAppStore.getState().setCurrentProject(p),
        setWorkflow: vi.fn(),
        resetExecution: vi.fn(),
        openTab: vi.fn(),
        openFileTab: vi.fn(),
        closeProjectDialog: vi.fn(),
        setLastError: vi.fn(),
        refreshProjects: vi.fn(async () => undefined),
        refreshBlocks: vi.fn(async () => undefined),
        setBusy: vi.fn(),
        promptInput: vi.fn(async () => null),
      });
      return null;
    }
    render(<Harness />);
    useAppStore.setState({ currentProject: project("A") });
    useAppStore.getState().addTerminalTab();
    liveRuns = [{ run_id: "r1", workflow_id: "main" }];
    endedRunIds = ["r1"];

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await act(async () => {
      await actions!.openProject("B");
    });
    expect(backend.callsTo("GET /api/projects/{project_id}")).toHaveLength(0);
    expect(useAppStore.getState().terminalTabs).toHaveLength(1);

    confirm.mockReturnValueOnce(true);
    await act(async () => {
      await actions!.openProject("B");
    });
    expect(backend.callsTo("POST /api/projects/active/end-runs")).toHaveLength(1);
    expect(backend.callsTo("GET /api/projects/{project_id}").map((call) => call.path)).toEqual([
      "/api/projects/B",
    ]);
    expect(useAppStore.getState().endedRunIds).toContain("r1");
    expect(useAppStore.getState().terminalTabs).toEqual([]);

    // Re-opening the open project is not a switch: nothing is asked or ended.
    useAppStore.setState({ currentProject: project("B") });
    const asked = backend.callsTo("GET /api/projects/active/runs").length;
    await act(async () => {
      await actions!.openProject("B");
    });
    expect(backend.callsTo("GET /api/projects/active/runs")).toHaveLength(asked);
    confirm.mockRestore();
  });
});
