import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProjectResponse, WorkflowResponse } from "../types/api";
import { useWorkflowSync } from "./useWorkflowSync";

const apiMocks = vi.hoisted(() => ({
  createWorkflow: vi.fn(),
  getBlockSchema: vi.fn(),
  listBlocks: vi.fn(),
  listProjects: vi.fn(),
  openProject: vi.fn(),
  updateWorkflow: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  },
  api: apiMocks,
}));

const workflow: WorkflowResponse = {
  id: "main",
  version: "1.0.0",
  description: "",
  nodes: [],
  edges: [],
  metadata: {},
};

const project: ProjectResponse = {
  id: "project-1",
  name: "Project",
  description: "",
  path: "C:\\Project",
  workflow_count: 1,
  workflows: ["main"],
  current_workflow_id: "main",
};

function renderSync(overrides: Partial<{ currentProject: ProjectResponse | null }> = {}) {
  const deps = {
    currentProject: overrides.currentProject ?? project,
    setCurrentProject: vi.fn(),
    setBlocks: vi.fn(),
    setBlockSchema: vi.fn(),
    setProjects: vi.fn(),
    markWorkflowSaved: vi.fn(),
    setLastError: vi.fn(),
    workflowPayload: workflow,
    workflowId: workflow.id,
  };
  const hook = renderHook(() => useWorkflowSync(deps));
  return { deps, hook };
}

describe("useWorkflowSync", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("reopens the current project and retries when backend session lost", async () => {
    const { ApiError } = await import("../lib/api");
    const saved = { ...workflow };
    const reopened = { ...project, workflow_count: 2 };
    apiMocks.updateWorkflow
      .mockRejectedValueOnce(new ApiError("No project is currently open.", 409))
      .mockResolvedValueOnce(saved);
    apiMocks.openProject.mockResolvedValueOnce(reopened);
    apiMocks.listProjects.mockResolvedValueOnce([reopened]);
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.saveWorkflow();
    });

    expect(apiMocks.openProject).toHaveBeenCalledWith(project.id);
    expect(apiMocks.updateWorkflow).toHaveBeenCalledTimes(2);
    expect(deps.setCurrentProject).toHaveBeenCalledWith(reopened);
    expect(deps.markWorkflowSaved).toHaveBeenCalled();
    // The save succeeds with no prior save error, so it must NOT clear the
    // banner — otherwise a concurrent autosave would wipe an unrelated
    // run/execute error (the "banner flashes then vanishes" bug).
    expect(deps.setLastError).not.toHaveBeenCalled();
  });

  it("clears its own validation banner only after a failed save, never otherwise", async () => {
    // A failed save records its error; the next successful save clears it. But
    // a success with no prior save error must NOT clear (so a concurrent
    // autosave cannot wipe an unrelated run/execute error).
    const { ApiError } = await import("../lib/api");
    apiMocks.updateWorkflow
      .mockRejectedValueOnce(new ApiError("validation failed: bad node", 422))
      .mockResolvedValueOnce(workflow);
    apiMocks.listProjects.mockResolvedValueOnce([project]);
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.saveWorkflow();
    });
    expect(deps.setLastError).toHaveBeenCalledWith("validation failed: bad node");

    deps.setLastError.mockClear();
    await act(async () => {
      await hook.result.current.saveWorkflow();
    });
    // The previous save errored, so this success clears its own banner.
    expect(deps.setLastError).toHaveBeenCalledWith(null);
  });

  it("falls back to create only when update returns 404", async () => {
    const { ApiError } = await import("../lib/api");
    apiMocks.updateWorkflow.mockRejectedValueOnce(new ApiError("Not found", 404));
    apiMocks.createWorkflow.mockResolvedValueOnce(workflow);
    apiMocks.listProjects.mockResolvedValueOnce([project]);
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.saveWorkflow();
    });

    expect(apiMocks.createWorkflow).toHaveBeenCalledWith(workflow);
    expect(apiMocks.openProject).not.toHaveBeenCalled();
    expect(deps.markWorkflowSaved).toHaveBeenCalled();
  });
});
