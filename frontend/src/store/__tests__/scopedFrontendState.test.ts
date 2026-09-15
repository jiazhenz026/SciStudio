/**
 * #2395 — frontend state that must be scoped per workflow or per project.
 *
 * Several different workflows may run at the same time (the same workflow may
 * not run twice). Each test here fails against the pre-#2395 store, where the
 * running flag and the interactive prompt were single global slots, and the
 * plot result and Lineage state survived a project switch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  mockBackend,
  type MockBackend,
  type MockRequest,
} from "../../__tests__/contract/mockBackend";

import { useAppStore } from "../index";
import type { InteractivePrompt } from "../types";
import type { ProjectResponse, WorkflowEventMessage, WorkflowResponse } from "../../types/api";
import { handleInteractivePrompt } from "../../hooks/useWebSocket.parts/handleLifecycle";
import {
  interactivePromptKey,
  visibleInteractivePrompt,
} from "../executionSlice.parts/interactivePrompts";

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

function lifecycle(type: string, workflowId: string): WorkflowEventMessage {
  return event({ type, block_id: null, workflow_id: workflowId });
}

function workflow(id: string): WorkflowResponse {
  return { id, version: "1.0.0", description: "", metadata: {}, nodes: [], edges: [] };
}

function project(id: string): ProjectResponse {
  return {
    id,
    name: id,
    path: `/tmp/${id}`,
    description: "",
    last_opened: "2026-09-15T00:00:00Z",
    workflow_count: 1,
    workflows: ["main"],
    current_workflow_id: "main",
  };
}

/** The store sequence of `useProjectActions.openProject`. */
function openProject(p: ProjectResponse): void {
  const store = useAppStore.getState();
  store.setWorkflow(null);
  store.resetExecution();
  useAppStore.setState({ tabs: [], activeTabId: null });
  store.setCurrentProject(p);
  useAppStore.getState().openTab(workflow("main"));
}

function promptEvent(workflowId: string, blockId: string): WorkflowEventMessage {
  return event({
    type: "interactive_prompt",
    workflow_id: workflowId,
    block_id: blockId,
    data: { block_type: "DataRouter" },
  });
}

function receivePrompt(workflowId: string, blockId: string): void {
  handleInteractivePrompt(promptEvent(workflowId, blockId), {
    upsertInteractivePrompt: useAppStore.getState().upsertInteractivePrompt,
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/** A runs-table row as `GET /api/runs` returns it. */
function runRow(runId: string): Record<string, unknown> {
  return {
    run_id: runId,
    workflow_id: "main",
    started_at: "2026-09-15T00:00:00Z",
    finished_at: null,
    status: "completed",
    triggered_by: "user",
  };
}

/** Hands out the next deferred response, else answers at once. */
let heldRuns: Array<Promise<unknown>> = [];
let heldRunDetails: Array<Promise<unknown>> = [];
let backend: MockBackend;

beforeEach(() => {
  heldRuns = [];
  heldRunDetails = [];
  backend = mockBackend({
    "GET /api/runs": () => heldRuns.shift() ?? { runs: [] },
    "GET /api/runs/{run_id}": (request: MockRequest) =>
      heldRunDetails.shift() ?? {
        run: runRow(decodeURIComponent(request.path.split("/").pop() ?? "")),
        block_executions: [],
      },
    "POST /api/ai/active-context": (request: MockRequest) => ({
      workflow_id: (request.body as { workflow_id: string | null }).workflow_id,
    }),
  });
  useAppStore.getState().resetExecution();
  useAppStore.getState().clearLineage();
  useAppStore.setState({ currentProject: null, tabs: [], activeTabId: null });
  useAppStore.getState().setPlotPreviewTarget(null);
  useAppStore.getState().setWorkflow(null);
});

afterEach(() => {
  backend.restore();
});

describe("running state is per workflow (#2395 F-1)", () => {
  it("one workflow finishing does not clear another that is still running", () => {
    openProject(project("A"));
    useAppStore.getState().setWorkflow(workflow("long_wf"));
    const store = useAppStore.getState();
    store.consumeEvent(lifecycle("workflow_started", "long_wf"));
    store.consumeEvent(lifecycle("workflow_started", "short_wf"));
    store.consumeEvent(lifecycle("workflow_completed", "short_wf"));

    expect(useAppStore.getState().isRunning).toBe(true);
    expect(useAppStore.getState().executionByWorkflow.short_wf.isRunning).toBe(false);
    expect(useAppStore.getState().executionByWorkflow.long_wf.isRunning).toBe(true);
  });

  it("a workflow that never ran does not show Running while another runs", () => {
    openProject(project("A"));
    useAppStore.getState().consumeEvent(lifecycle("workflow_started", "long_wf"));

    expect(useAppStore.getState().workflowId).toBe("main");
    expect(useAppStore.getState().isRunning).toBe(false);
  });

  it("switching to the running workflow projects its flag, and back again", () => {
    openProject(project("A"));
    useAppStore.getState().consumeEvent(lifecycle("workflow_started", "long_wf"));

    useAppStore.getState().openTab(workflow("long_wf"));
    expect(useAppStore.getState().isRunning).toBe(true);

    const mainTab = useAppStore
      .getState()
      .tabs.find((tab) => tab.kind === "workflow" && tab.workflowId === "main");
    useAppStore.getState().switchTab(mainTab!.id);
    expect(useAppStore.getState().isRunning).toBe(false);

    useAppStore.getState().consumeEvent(lifecycle("workflow_completed", "long_wf"));
    useAppStore.getState().openTab(workflow("long_wf"));
    expect(useAppStore.getState().isRunning).toBe(false);
  });
});

describe("interactive prompts are held per (workflow, block) (#2395 F-2)", () => {
  it("a second workflow's prompt does not replace the first", () => {
    receivePrompt("wf_a", "router");
    receivePrompt("wf_b", "router");

    const prompts = useAppStore.getState().interactivePrompts;
    expect(Object.values(prompts).map((p) => p.workflowId)).toEqual(["wf_a", "wf_b"]);
  });

  it("removing one prompt keeps the other workflow's prompt pending", () => {
    receivePrompt("wf_a", "router");
    receivePrompt("wf_b", "router");

    useAppStore.getState().removeInteractivePrompt("wf_a", "router");
    const prompts = useAppStore.getState().interactivePrompts;
    expect(Object.keys(prompts)).toEqual([interactivePromptKey("wf_b", "router")]);
  });

  it("a repeated prompt for the same block replaces its own entry only", () => {
    receivePrompt("wf_a", "router");
    receivePrompt("wf_b", "router");
    receivePrompt("wf_a", "router");

    expect(Object.keys(useAppStore.getState().interactivePrompts)).toHaveLength(2);
  });

  it("a workflow's completion drops only its own prompts", () => {
    receivePrompt("wf_a", "router");
    receivePrompt("wf_b", "router");

    useAppStore.getState().consumeEvent(lifecycle("workflow_completed", "wf_a"));
    const prompts = Object.values(useAppStore.getState().interactivePrompts);
    expect(prompts.map((p) => p.workflowId)).toEqual(["wf_b"]);
  });

  it("the window prefers the shown prompt, then the workflow on screen, then arrival order", () => {
    const prompt = (workflowId: string): InteractivePrompt => ({
      blockId: "router",
      blockType: "DataRouter",
      workflowId,
      panelManifest: null,
      panelPayload: {},
      inputSignature: {},
      data: {},
    });
    const prompts = {
      [interactivePromptKey("wf_a", "router")]: prompt("wf_a"),
      [interactivePromptKey("wf_b", "router")]: prompt("wf_b"),
    };

    expect(visibleInteractivePrompt(prompts, "other")?.workflowId).toBe("wf_a");
    expect(visibleInteractivePrompt(prompts, "wf_b")?.workflowId).toBe("wf_b");
    expect(
      visibleInteractivePrompt(prompts, "wf_b", interactivePromptKey("wf_a", "router"))?.workflowId,
    ).toBe("wf_a");
    expect(visibleInteractivePrompt({}, "wf_a")).toBeNull();
  });
});

describe("the plot result is scoped to the project (#2395 F-3)", () => {
  it("a project switch clears a plot target naming a same-named (workflow, node)", () => {
    openProject(project("A"));
    useAppStore.getState().setPlotPreviewTarget({
      kind: "plot_artifact",
      ref: "data-plot-of-A",
      source: { workflow_id: "main", node_id: "load_one", output_port: "out" },
    } as never);

    openProject(project("B"));
    expect(useAppStore.getState().plotPreviewTarget).toBeNull();
  });

  it("re-setting the same project keeps the plot target", () => {
    openProject(project("A"));
    const target = { kind: "plot_artifact", ref: "data-plot-of-A" } as never;
    useAppStore.getState().setPlotPreviewTarget(target);

    useAppStore.getState().setCurrentProject({ ...project("A"), current_workflow_id: "other" });
    expect(useAppStore.getState().plotPreviewTarget).toBe(target);
  });
});

describe("Lineage state is scoped to the project (#2395 F-4)", () => {
  it("a project switch clears the selected run and cached details", async () => {
    openProject(project("A"));
    useAppStore.getState().selectRun("run-of-A");
    await vi.waitFor(() => expect(useAppStore.getState().runDetails["run-of-A"]).toBeDefined());

    openProject(project("B"));
    expect(useAppStore.getState().selectedRunId).toBeNull();
    expect(useAppStore.getState().runDetails).toEqual({});
  });

  it("a runs response for the outgoing project is dropped after the switch", async () => {
    openProject(project("A"));
    const pending = deferred<unknown>();
    heldRuns.push(pending.promise);
    const fetching = useAppStore.getState().fetchRuns();

    openProject(project("B"));
    pending.resolve({ runs: [runRow("run-of-A")] });
    await fetching;

    expect(backend.callsTo("GET /api/runs")).toHaveLength(1);
    expect(useAppStore.getState().runs).toEqual([]);
    expect(useAppStore.getState().runsLoading).toBe(false);
  });

  it("a run-detail response for the outgoing project is dropped after the switch", async () => {
    openProject(project("A"));
    const pending = deferred<unknown>();
    heldRunDetails.push(pending.promise);
    const fetching = useAppStore.getState().fetchRunDetail("run-of-A");

    openProject(project("B"));
    pending.resolve({ run: runRow("run-of-A"), block_executions: [] });
    await fetching;

    expect(backend.callsTo("GET /api/runs/{run_id}")).toHaveLength(1);
    expect(useAppStore.getState().runDetails).toEqual({});
  });
});
