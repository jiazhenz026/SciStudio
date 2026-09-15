import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  runFromHereRefusalMessage,
  useWorkflowExecutionActions,
} from "./useWorkflowExecutionActions";

const apiMocks = vi.hoisted(() => ({
  cancelWorkflow: vi.fn(),
  executeFrom: vi.fn(),
  executeWorkflow: vi.fn(),
  pauseWorkflow: vi.fn(),
  resumeWorkflow: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  api: apiMocks,
}));

function renderActions() {
  const deps = {
    currentProject: {
      id: "p1",
      name: "Project",
      description: "",
      path: "C:\\Project",
      workflow_count: 1,
      workflows: ["main"],
      current_workflow_id: "main",
    },
    workflowId: "main",
    selectedNodeId: "node-1",
    saveWorkflow: vi.fn().mockResolvedValue(undefined),
    setLastError: vi.fn(),
    workflowPayloadId: "main",
  };
  const hook = renderHook(() => useWorkflowExecutionActions(deps));
  return { deps, hook };
}

describe("useWorkflowExecutionActions", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("reports a started run so an expanded subworkflow tab shows its own run (#2394)", async () => {
    apiMocks.executeWorkflow.mockResolvedValueOnce({ workflow_id: "@subworkflows@qc.yaml" });
    const onRunStarted = vi.fn();
    const hook = renderHook(() =>
      useWorkflowExecutionActions({
        currentProject: {
          id: "p1",
          name: "Project",
          description: "",
          path: "/p",
          workflow_count: 1,
          workflows: ["main"],
          current_workflow_id: "main",
        },
        workflowId: "@subworkflows@qc.yaml",
        selectedNodeId: null,
        saveWorkflow: vi.fn().mockResolvedValue(undefined),
        setLastError: vi.fn(),
        workflowPayloadId: "@subworkflows@qc.yaml",
        onRunStarted,
      }),
    );

    await act(async () => {
      await hook.result.current.runWorkflow();
    });
    expect(apiMocks.executeWorkflow).toHaveBeenCalledWith("@subworkflows@qc.yaml", {
      overwriteNodeIds: [],
    });
    expect(onRunStarted).toHaveBeenCalledTimes(1);

    apiMocks.executeWorkflow.mockRejectedValueOnce(new Error("Workflow is already running"));
    await act(async () => {
      await hook.result.current.runWorkflow();
    });
    expect(onRunStarted).toHaveBeenCalledTimes(1);
  });

  it("lists each upstream block with a readable label when Run from here is refused (#2448)", async () => {
    vi.useFakeTimers();
    const refusal = Object.assign(new Error("Cannot run from 'node-1': 2 upstream output(s)"), {
      status: 409,
      detail: {
        error: "run_from_here_unmet",
        message: "Cannot run from 'node-1': 2 upstream output(s)",
        block_id: "node-1",
        unmet: [
          {
            node_id: "load-1",
            block_type: "load_data",
            reason: "output_missing",
            detail: "its stored output no longer exists: /p/a.zarr",
          },
          {
            node_id: "norm-1",
            block_type: "normalize",
            reason: "definition_changed",
            detail: "its definition changed since its output was produced",
          },
        ],
      },
    });
    apiMocks.executeFrom.mockRejectedValueOnce(refusal);
    const setLastError = vi.fn();
    const hook = renderHook(() =>
      useWorkflowExecutionActions({
        currentProject: null,
        workflowId: "main",
        selectedNodeId: "node-1",
        saveWorkflow: vi.fn().mockResolvedValue(undefined),
        setLastError,
        workflowPayloadId: "main",
        workflowNodes: [
          { id: "load-1", block_type: "load_data", config: { label: "Raw counts" } },
          { id: "norm-1", block_type: "normalize", config: {} },
          { id: "node-1", block_type: "cluster", config: {} },
        ],
        blockSchemas: {
          normalize: { name: "Normalize" } as never,
        },
      }),
    );

    await act(async () => {
      await hook.result.current.handleRunBlock("node-1");
    });
    act(() => {
      vi.runOnlyPendingTimers();
    });

    expect(setLastError).toHaveBeenCalledWith(
      [
        "Cannot run from here. Run these upstream blocks first; their outputs cannot be reused:",
        "• Raw counts: its stored output no longer exists: /p/a.zarr",
        "• Normalize (norm-1): its definition changed since its output was produced",
      ].join("\n"),
    );
  });

  it("returns null for errors that are not a Run from here refusal", () => {
    expect(runFromHereRefusalMessage(new Error("boom"))).toBeNull();
    expect(runFromHereRefusalMessage({ detail: { error: "other", unmet: [] } })).toBeNull();
    expect(runFromHereRefusalMessage(null)).toBeNull();
    expect(
      runFromHereRefusalMessage({
        detail: { error: "run_from_here_unmet", unmet: [{ node_id: "gone", reason: "never_ran" }] },
      }),
    ).toContain("• gone: never_ran");
  });

  it("keeps Run from here precondition errors visible after async save side effects", async () => {
    vi.useFakeTimers();
    apiMocks.executeFrom.mockRejectedValueOnce(
      new Error("Cannot run from 'node-1': 1 upstream output(s) cannot be reused"),
    );
    const { deps, hook } = renderActions();

    await act(async () => {
      await hook.result.current.startFromSelected();
    });

    expect(deps.setLastError).not.toHaveBeenCalled();
    act(() => {
      vi.runOnlyPendingTimers();
    });
    expect(deps.setLastError).toHaveBeenCalledWith(
      "Cannot run from 'node-1': 1 upstream output(s) cannot be reused",
    );
  });
});
