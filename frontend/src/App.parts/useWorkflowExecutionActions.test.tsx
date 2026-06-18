import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useWorkflowExecutionActions } from "./useWorkflowExecutionActions";

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

  it("keeps Run from here precondition errors visible after async save side effects", async () => {
    vi.useFakeTimers();
    apiMocks.executeFrom.mockRejectedValueOnce(
      new Error("Run the full workflow at least once before using 'Run from here'"),
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
      "Run the full workflow at least once before using 'Run from here'",
    );
  });
});
