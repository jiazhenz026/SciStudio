import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { VersionConflictState } from "../store/types";
import type { ProjectResponse, WorkflowResponse } from "../types/api";
import { useWorkflowSync } from "./useWorkflowSync";

const apiMocks = vi.hoisted(() => ({
  createWorkflow: vi.fn(),
  getBlockSchema: vi.fn(),
  listBlocks: vi.fn(),
  listProjects: vi.fn(),
  openProject: vi.fn(),
  reloadBlocks: vi.fn(),
  updateWorkflow: vi.fn(),
}));

// Only the conflict gate in saveWorkflow reads the store, via getState. Mock it
// narrowly so the test does not pull in the real store (whose init needs a
// fuller ../lib/api surface than this file mocks).
const storeMocks = vi.hoisted(() => ({
  workflowConflict: null as VersionConflictState | null,
}));

vi.mock("../store", () => ({
  useAppStore: {
    getState: () => ({ workflowConflict: storeMocks.workflowConflict }),
  },
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

const pendingConflict: VersionConflictState = {
  entityClass: "workflow",
  entityId: "main",
  kind: "modified",
  source: "agent",
  sourceId: null,
  baseVersion: 5,
  pendingVersion: 5,
  remoteVersion: 6,
  detectedAt: "2026-06-30T00:00:00Z",
  message: "remote change",
  remoteWorkflow: null,
};

describe("useWorkflowSync", () => {
  afterEach(() => {
    vi.clearAllMocks();
    storeMocks.workflowConflict = null;
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

  it("does not PUT while a version conflict is pending (#1891 P1)", async () => {
    // Every save entry point — autosave, Ctrl/Cmd+S, Save As — routes through
    // saveWorkflow. With a conflict pending it must no-op so the stale local
    // canvas cannot clobber the remote write before the user resolves it.
    storeMocks.workflowConflict = pendingConflict;
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.saveWorkflow();
    });

    expect(apiMocks.updateWorkflow).not.toHaveBeenCalled();
    expect(apiMocks.createWorkflow).not.toHaveBeenCalled();
    expect(deps.markWorkflowSaved).not.toHaveBeenCalled();
  });

  it("reloadBlocks forces a backend re-scan before re-fetching the catalog (#1910)", async () => {
    // The palette Reload button must POST /api/blocks/reload (backend re-scan)
    // and only then re-fetch, so an in-place drop-in edit shows up. refreshBlocks
    // alone would just re-read the stale cached catalog.
    apiMocks.reloadBlocks.mockResolvedValueOnce({ reloaded: 1, added: [], removed: [] });
    apiMocks.listBlocks.mockResolvedValueOnce({ blocks: [] });
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.reloadBlocks();
    });

    expect(apiMocks.reloadBlocks).toHaveBeenCalledTimes(1);
    // The re-scan happens before the re-fetch.
    expect(apiMocks.reloadBlocks.mock.invocationCallOrder[0]).toBeLessThan(
      apiMocks.listBlocks.mock.invocationCallOrder[0],
    );
    expect(deps.setBlocks).toHaveBeenCalledWith([]);
    expect(deps.setLastError).not.toHaveBeenCalled();
  });

  it("reloadBlocks surfaces a re-scan failure in the error banner (#1910)", async () => {
    apiMocks.reloadBlocks.mockRejectedValueOnce(new Error("reload boom"));
    const { deps, hook } = renderSync();

    await act(async () => {
      await hook.result.current.reloadBlocks();
    });

    expect(deps.setLastError).toHaveBeenCalledWith("reload boom");
    // A failed re-scan must not attempt the catalog re-fetch.
    expect(apiMocks.listBlocks).not.toHaveBeenCalled();
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
