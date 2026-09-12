/**
 * #2362 — an id that is only unique under a parent must be keyed with it.
 *
 * Two workflows may legitimately contain a node with the same name, two
 * projects share the branch name `main`, and two workflow tabs can carry the
 * same internal `workflowId`. Every store surface below used the child id on
 * its own, so the second thing silently answered for the first.
 *
 * Each test here fails against the pre-#2362 store.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../index";
import type { ProjectResponse, WorkflowEventMessage, WorkflowResponse } from "../../types/api";

function event(overrides: Partial<WorkflowEventMessage> = {}): WorkflowEventMessage {
  return {
    type: "block_done",
    block_id: "load_one",
    workflow_id: "array_wf",
    data: {},
    timestamp: "2026-09-11T00:00:00Z",
    ...overrides,
  };
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
    last_opened: "2026-09-11T00:00:00Z",
    workflow_count: 0,
    workflows: [],
    current_workflow_id: null,
  };
}

beforeEach(() => {
  useAppStore.getState().resetExecution();
  useAppStore.setState({ currentProject: null, tabs: [], activeTabId: null });
  useAppStore.getState().setWorkflow(null);
});

describe("execution state is keyed by workflow (#2362)", () => {
  const arrayRef = { output: { data_ref: "data-array" } };
  const artifactRef = { output: { data_ref: "data-artifact" } };

  it("a run of one workflow does not overwrite another's outputs for a shared node name", () => {
    const store = useAppStore.getState();
    store.setWorkflow(workflow("array_wf"));
    store.consumeEvent(event({ workflow_id: "array_wf", data: { outputs: arrayRef } }));
    store.consumeEvent(event({ workflow_id: "artifact_wf", data: { outputs: artifactRef } }));

    // Still looking at array_wf: its own node's output, not the namesake's.
    expect(useAppStore.getState().blockOutputs.load_one).toEqual(arrayRef);

    useAppStore.getState().setWorkflow(workflow("artifact_wf"));
    expect(useAppStore.getState().blockOutputs.load_one).toEqual(artifactRef);

    useAppStore.getState().setWorkflow(workflow("array_wf"));
    expect(useAppStore.getState().blockOutputs.load_one).toEqual(arrayRef);
  });

  it("switching to a workflow that never ran shows no output for the shared node name", () => {
    const store = useAppStore.getState();
    store.setWorkflow(workflow("array_wf"));
    store.consumeEvent(event({ data: { outputs: arrayRef } }));

    useAppStore.getState().setWorkflow(workflow("untouched_wf"));
    expect(useAppStore.getState().blockOutputs.load_one).toBeUndefined();
    expect(useAppStore.getState().blockStates.load_one).toBeUndefined();
  });

  it("status, errors, and the elapsed-time stamp are per workflow too", () => {
    const store = useAppStore.getState();
    store.setWorkflow(workflow("array_wf"));
    store.consumeEvent(event({ type: "block_running", workflow_id: "array_wf" }));
    store.consumeEvent(
      event({
        type: "block_error",
        workflow_id: "artifact_wf",
        data: { error: "ValueError: artifact_wf blew up", error_summary: "artifact_wf blew up" },
      }),
    );

    const onArray = useAppStore.getState();
    expect(onArray.blockStates.load_one).toBe("running");
    expect(onArray.blockErrors.load_one).toBeUndefined();
    // The other workflow's event must not clear this one's running stamp.
    expect(onArray.blockRunStartedAt.load_one).toBeTypeOf("number");

    useAppStore.getState().setWorkflow(workflow("artifact_wf"));
    const onArtifact = useAppStore.getState();
    expect(onArtifact.blockStates.load_one).toBe("error");
    expect(onArtifact.blockErrors.load_one).toContain("artifact_wf blew up");
    expect(onArtifact.blockRunStartedAt.load_one).toBeUndefined();
  });

  it("resetExecution clears every workflow's bucket", () => {
    const store = useAppStore.getState();
    store.setWorkflow(workflow("array_wf"));
    store.consumeEvent(event({ data: { outputs: arrayRef } }));
    store.consumeEvent(event({ workflow_id: "artifact_wf", data: { outputs: artifactRef } }));

    useAppStore.getState().resetExecution();
    expect(useAppStore.getState().executionByWorkflow).toEqual({});
    expect(useAppStore.getState().blockOutputs).toEqual({});
  });
});

describe("git history is scoped to its project (#2362)", () => {
  it("a project switch drops the previous project's commits for the same branch name", () => {
    useAppStore.getState().setCurrentProject(project("alpha"));
    useAppStore.setState({
      logCache: { main: [{ sha: "a".repeat(40), subject: "alpha only" }] as never },
      logFailed: { main: true },
      logLoading: { main: false },
      branches: [{ name: "main", head_sha: "a".repeat(40), is_current: true }] as never,
      currentBranch: "main",
    });

    useAppStore.getState().setCurrentProject(project("beta"));

    const after = useAppStore.getState();
    expect(after.logCache.main).toBeUndefined();
    // `logFailed` latched the other way: it made loadLog early-return forever.
    expect(after.logFailed.main).toBeUndefined();
    expect(after.branches).toBeNull();
    expect(after.currentBranch).toBeNull();
  });

  it("re-setting the same project keeps its cache", () => {
    useAppStore.getState().setCurrentProject(project("alpha"));
    useAppStore.setState({ logCache: { main: [] } });
    useAppStore.getState().setCurrentProject({ ...project("alpha"), name: "renamed" });
    expect(useAppStore.getState().logCache.main).toEqual([]);
  });
});

describe("a workflow tab id identifies one tab (#2362)", () => {
  it("two copies of one subworkflow opened together get distinct ids", () => {
    const store = useAppStore.getState();
    // `tab-<workflowId>-<Date.now()>`: same workflow id, same millisecond.
    store.openTab(workflow("shared"), "copy A", undefined, "subworkflows/a.yaml");
    store.openTab(workflow("shared"), "copy B", undefined, "subworkflows/b.yaml");

    const ids = useAppStore.getState().tabs.map((t) => t.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });

  it("closing one of them leaves the other open", () => {
    const store = useAppStore.getState();
    store.openTab(workflow("shared"), "copy A", undefined, "subworkflows/a.yaml");
    store.openTab(workflow("shared"), "copy B", undefined, "subworkflows/b.yaml");

    const [tabA] = useAppStore.getState().tabs;
    useAppStore.getState().closeTab(tabA.id);
    expect(useAppStore.getState().tabs).toHaveLength(1);
  });
});

describe("a preview tab captures into the tab it came from (#2362)", () => {
  it("does not clobber a second workflow tab that shares the same workflowId", () => {
    // Two imported copies of one subworkflow: distinct `tabKey` (their ref
    // paths), identical internal `workflowId` — the case `openTab` dedups on
    // `tabKey` precisely because the id is not unique.
    const store = useAppStore.getState();
    store.openTab(workflow("shared"), "copy A", undefined, "subworkflows/a.yaml");
    store.openTab(
      { ...workflow("shared"), nodes: [{ id: "only_in_b" }] as never },
      "copy B",
      undefined,
      "subworkflows/b.yaml",
    );

    const tabs = useAppStore.getState().tabs.filter((t) => t.kind === "workflow");
    expect(tabs).toHaveLength(2);
    expect(new Set(tabs.map((t) => (t as { workflowId: string }).workflowId))).toEqual(
      new Set(["shared"]),
    );
    const [tabA, tabB] = tabs;

    // Focus copy A, then open a preview over it and sync.
    useAppStore.getState().switchTab(tabA.id);
    useAppStore
      .getState()
      .openPreviewTab(
        { kind: "data_ref", ref: "data-1", recorded_type: "Array", type_chain: ["Array"] },
        "data-1",
      );
    useAppStore.setState({ workflowNodes: [{ id: "only_in_a" }] as never });
    useAppStore.getState().syncActiveTab();

    const after = useAppStore.getState().tabs;
    const capturedA = after.find((t) => t.id === tabA.id) as {
      workflowNodes: { id: string }[];
    };
    const capturedB = after.find((t) => t.id === tabB.id) as {
      workflowNodes: { id: string }[];
    };
    expect(capturedA.workflowNodes.map((n) => n.id)).toEqual(["only_in_a"]);
    expect(capturedB.workflowNodes.map((n) => n.id)).toEqual(["only_in_b"]);
  });
});
