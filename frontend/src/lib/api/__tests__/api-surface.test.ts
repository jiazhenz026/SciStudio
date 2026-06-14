/**
 * Public-surface coverage for the post-#1422 `lib/api.ts` re-export
 * shell. Pins the key set, so a future domain-module addition cannot
 * silently drop a method that downstream consumers expect to find on
 * `api`.
 *
 * The list below is the public surface as of #1422 (Wave 2). Adding a
 * new key requires extending the expected set in this test.
 */
import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";

import { api, ApiError } from "../../api";

const EXPECTED_API_KEYS = [
  // projects
  "listProjects",
  "createProject",
  "openProject",
  "updateProject",
  "deleteProject",
  "getProjectTree",
  // blocks
  "listBlocks",
  "getBlockSchema",
  "validateConnection",
  // workflows
  "listWorkflows",
  "importWorkflowFile",
  "importWorkflowFromPath",
  "createWorkflow",
  "getWorkflow",
  "updateWorkflow",
  "deleteWorkflow",
  "executeWorkflow",
  "pauseWorkflow",
  "resumeWorkflow",
  "cancelWorkflow",
  "cancelBlock",
  "executeFrom",
  "exportWorkflowToPath",
  // data
  "uploadData",
  "getDataMetadata",
  // data — ADR-048 SPEC 2 / #1606 plot-job run + preview wiring.
  // The legacy one-shot `getDataPreview` was removed under #1604; the catalog
  // is previewed exclusively through the routed previewer session API.
  "listPlotTargets",
  "createPlot",
  "runPlotJob",
  "listPlots",
  // filesystem
  "browseFilesystem",
  "revealInExplorer",
  "openNativeDialog",
  "openNativeSaveDialog",
  // code
  "getProjectFile",
  "putProjectFile",
  "getBlockTemplate",
  "lintPython",
  // lineage
  "lineage",
  // git
  "gitCommit",
  "gitLog",
  "gitDiff",
  "gitRestore",
  "gitBranches",
  "gitBranchSwitch",
  "gitBranchCreate",
  "gitBranchDelete",
  "gitStatus",
  "gitMerge",
  "gitCherryPick",
  "gitMergeStageFile",
  "gitMergeComplete",
  "gitMergeAbort",
] as const;

describe("api public surface (#1422 split)", () => {
  it("exposes every documented domain method", () => {
    for (const key of EXPECTED_API_KEYS) {
      expect(api).toHaveProperty(key);
    }
  });

  it("exposes the lineage namespace methods", () => {
    expect(api.lineage).toHaveProperty("getRuns");
    expect(api.lineage).toHaveProperty("getRun");
    expect(api.lineage).toHaveProperty("getRunMethods");
    expect(api.lineage).toHaveProperty("validateRerun");
    expect(api.lineage).toHaveProperty("rerunRun");
  });

  it("re-exports ApiError as a constructable subclass of Error", () => {
    const err = new ApiError("boom", 503);
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(503);
    expect(err.message).toBe("boom");
  });
});

describe("apiFetch error handling (#1422 split: core.ts)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws ApiError with the structured detail message on validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: () => Promise.resolve({ detail: { message: "field bad", errors: [] } }),
      }),
    );
    await expect(api.listProjects()).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "field bad",
    });
  });

  it("returns parsed JSON on 200 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve([{ id: "p1" }]),
      }),
    );
    const out = await api.listProjects();
    expect(out).toEqual([{ id: "p1" }]);
  });

  it("passes create_parent_dirs for constrained new-file scaffolds", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ mtime: 1, size: 6 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.putProjectFile("p1", "blocks/new_block.py", "x = 1\n", { createParentDirs: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "x = 1\n",
      create_parent_dirs: true,
    });
  });
});
