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
  "reloadBlocks",
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
  // data — #2095 previewer discovery + reload, #2049 per-type previewer
  // choice; surfaced by the left-panel Previewers tab (#2113).
  "listPreviewers",
  "reloadPreviewers",
  "listPreviewerChoices",
  "setPreviewerChoice",
  "clearPreviewerChoice",
  // data — ADR-048 SPEC 2 / #1606 plot-job run + preview wiring.
  // The legacy one-shot `getDataPreview` was removed under #1604; the catalog
  // is previewed exclusively through the routed previewer session API.
  "listPlotTargets",
  "createPlot",
  "deletePlot",
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
  // packages — #1784 Package Manager
  "installLocalPackage",
  "listInstalledPackages",
  "checkPackageUpdates",
  "updatePackage",
  "rollbackPackage",
  "deletePackage",
  // tutorials — ADR-053 Learning Center (#2057). The single-tutorial
  // `bootstrapRunFirstWorkflowTutorial` was removed with the hardcoded
  // implementation (FR-001, FR-003); these are the general surface that
  // replaced it, one per row of the HTTP contract the frontend calls.
  "getTutorialCatalogue",
  "getActiveTutorialSession",
  "startTutorialSession",
  "evaluateActiveTutorialStep",
  "reportTutorialUiEvent",
  "continueActiveTutorialStep",
  "leaveActiveTutorialSession",
  "getTutorialProgress",
  "previewTutorialDataClear",
  "clearTutorialData",
  "getTutorialUnlock",
  "dismissTutorialUnlock",
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
    expect(api.lineage).toHaveProperty("validateRestore");
    // ADR-038 Addendum 1 §11.5 (#2033): Re-run is withdrawn from the client
    // surface along with the `validateRerun` stub that never called a
    // backend route.
    expect(api.lineage).not.toHaveProperty("rerunRun");
    expect(api.lineage).not.toHaveProperty("validateRerun");
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
      detail: { message: "field bad", errors: [] },
    });
  });

  it("keeps a structured detail on the error so callers can read its fields (#2448)", async () => {
    const detail = {
      error: "run_from_here_unmet",
      message: "Cannot run from 'final'",
      block_id: "final",
      unmet: [
        { node_id: "transform", block_type: "process_block", reason: "never_ran", detail: "x" },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        statusText: "Conflict",
        json: () => Promise.resolve({ detail }),
      }),
    );
    await expect(api.executeFrom("main", "final")).rejects.toMatchObject({
      status: 409,
      message: "Cannot run from 'final'",
      detail,
    });
  });

  it("leaves detail undefined for a plain-string error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: () => Promise.resolve({ detail: "nope" }),
      }),
    );
    const error = await api.listProjects().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).detail).toBeUndefined();
  });

  it("appends the HTTP status code to opaque server errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.resolve({ detail: "Internal Server Error" }),
      }),
    );
    await expect(api.listProjects()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "Internal Server Error (HTTP 500)",
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
