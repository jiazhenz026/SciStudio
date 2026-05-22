import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

type WorkflowNode = {
  id: string;
  block_type: string;
  config: Record<string, unknown>;
  layout: { x: number; y: number };
};

type WorkflowEdge = {
  source: string;
  target: string;
};

type WorkflowPayload = {
  id: string;
  version: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: Record<string, unknown>;
};

type ProjectResponse = {
  id: string;
  name: string;
  path: string;
  current_workflow_id: string | null;
};

type GitStatus = {
  dirty: boolean;
  modified: string[];
  staged: string[];
  untracked: string[];
  conflicted: string[];
};

type GitCommit = {
  sha: string;
  short_sha: string;
  subject: string;
};

type LineageRunsResponse = {
  runs: Array<{
    run_id: string;
    workflow_id: string;
    workflow_git_commit: string | null;
  }>;
};

const WORKFLOW_ID = "main";

test.describe("Workflow refresh E2E discovery @workflow-refresh", () => {
  test("WFR-001 Lineage Restore refreshes canvas and shows auto-commit hint @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("empty"));
    const run = await createLineageRunAtCurrentHead(request);
    await putWorkflow(request, workflowFixture("expanded"));
    await commitCurrentTree(request, "test: expanded after lineage run");

    await openProjectInUi(page, project);
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("expanded"));
    await addNoteAndWaitDirty(page, request);

    await page.getByRole("button", { name: /Lineage/ }).click();
    await page.getByTestId(`runs-list-row-${run.run_id}`).click();
    await expect(page.getByTestId("run-detail-restore-button")).toBeEnabled();
    await page.getByTestId("run-detail-restore-button").click();

    await expect(page.getByTestId("run-detail-restore-auto-commit-hint")).toContainText(
      "Your unsaved changes were committed as",
    );
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("empty"));
    await expect(page.getByRole("tab", { name: WORKFLOW_ID })).toHaveAttribute("aria-selected", "true");
  });

  test("WFR-002 Git History inline Diff and Restore refresh canvas @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    const baseSha = await commitCurrentTree(request, "test: base workflow");
    await putWorkflow(request, workflowFixture("expanded"));
    await commitCurrentTree(request, "test: expanded workflow");

    await openProjectInUi(page, project);
    await openGitHistoryList(page);

    const baseShortSha = await shortShaFor(request, baseSha);
    await page.getByTestId(`git-history-row-${baseShortSha}`).click();
    await expect(page.getByTestId("git-diff-modal")).toBeVisible();
    await expect(page.getByTestId("git-diff-viewer")).toContainText("workflows/main.yaml");
    await page.getByTestId("git-diff-close").click();

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByTestId(`git-history-row-restore-${baseShortSha}`).click();

    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));
    await expect(page.getByRole("tab", { name: WORKFLOW_ID })).toHaveAttribute("aria-selected", "true");
  });

  test("WFR-003 dirty restore auto-commits prior canvas before refresh @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    const baseSha = await commitCurrentTree(request, "test: base workflow");
    await putWorkflow(request, workflowFixture("expanded"));
    await commitCurrentTree(request, "test: expanded workflow");

    await openProjectInUi(page, project);
    await addNoteAndWaitDirty(page, request);
    await openGitHistoryList(page);

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByTestId(`git-history-row-restore-${await shortShaFor(request, baseSha)}`).click();

    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));
    const autoCommits = await apiJson<GitCommit[]>(request, "/api/git/log?limit=5");
    expect(autoCommits.some((commit) => commit.subject.startsWith("auto: pre-restore @"))).toBe(true);
    await expect(page.getByTestId("git-status-badge")).toHaveAttribute("data-status", "dirty");
  });

  test("WFR-004 dirty branch switch auto-commits and refreshes canvas @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    await createFeatureBranchWithWorkflow(request, "feature-auto-switch", workflowFixture("branched"));

    await openProjectInUi(page, project);
    await addNoteAndWaitDirty(page, request);
    await switchBranchFromPicker(page, "feature-auto-switch");

    await expect(page.getByTestId("branch-picker-auto-commit-toast")).toContainText(
      "Auto-committed unsaved changes",
    );
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("branched"));

    const mainLog = await apiJson<GitCommit[]>(request, "/api/git/log?branch=main&limit=3");
    expect(mainLog[0].subject.startsWith("auto: pre-switch @")).toBe(true);
  });

  test("WFR-005 invalid restore and stale branch switch preserve old canvas @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    await createFeatureBranchWithWorkflow(request, "deleted-before-click", workflowFixture("branched"));

    await openProjectInUi(page, project);
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));

    const invalidRestore = await request.post("/api/git/restore", {
      data: { commit_sha: "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", files: ["workflows/main.yaml"] },
    });
    expect(invalidRestore.ok(), await invalidRestore.text()).toBe(false);
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));

    await openGitTab(page);
    await page.getByTestId("branch-picker-trigger").click();
    await expect(page.getByTestId("branch-picker-item-deleted-before-click")).toBeVisible();
    await apiJson(request, "/api/git/branches/deleted-before-click?force=true", { method: "DELETE" });
    await page.getByTestId("branch-picker-item-deleted-before-click").click();

    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));
    await expect(page.getByTestId("branch-picker-trigger")).toContainText("main");
  });

  test("WFR-006 repeated restore no-op preserves canvas and tab state @workflow-refresh", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("expanded"));
    const [head] = await apiJson<GitCommit[]>(request, "/api/git/log?limit=1");

    await openProjectInUi(page, project);
    await openGitHistoryList(page);

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByTestId(`git-history-row-restore-${head.short_sha}`).click();
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("expanded"));

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByTestId(`git-history-row-restore-${head.short_sha}`).click();
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("expanded"));

    const after = await apiJson<GitCommit[]>(request, "/api/git/log?limit=1");
    expect(after[0].sha).toBe(head.sha);
    await expect(page.getByTestId("git-history-list")).toBeVisible();
    await expect(page.getByRole("tab", { name: WORKFLOW_ID })).toHaveAttribute("aria-selected", "true");
  });
});

async function createProjectWithWorkflow(
  request: APIRequestContext,
  testInfo: TestInfo,
  workflow: WorkflowPayload,
): Promise<ProjectResponse> {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-e2e-wfr-"));
  const name = `e2e-wfr-${Date.now()}-${testInfo.retry}`;
  const project = await apiJson<ProjectResponse>(request, "/api/projects/", {
    method: "POST",
    data: { name, description: "E2E workflow refresh discovery", path: parent },
  });
  await testInfo.attach("project-path", { body: project.path, contentType: "text/plain" });
  await apiJson<ProjectResponse>(request, `/api/projects/${encodeURIComponent(project.id)}`);
  await putWorkflow(request, workflow);
  await commitCurrentTree(request, "test: seed workflow");
  return project;
}

async function createLineageRunAtCurrentHead(
  request: APIRequestContext,
): Promise<LineageRunsResponse["runs"][number]> {
  await apiJson(request, `/api/workflows/${WORKFLOW_ID}/execute`, { method: "POST" });
  await expect
    .poll(async () => {
      const response = await apiJson<LineageRunsResponse>(request, `/api/runs?workflow_id=${WORKFLOW_ID}&limit=1`);
      return response.runs.length;
    })
    .toBeGreaterThan(0);
  const response = await apiJson<LineageRunsResponse>(request, `/api/runs?workflow_id=${WORKFLOW_ID}&limit=1`);
  expect(response.runs[0].workflow_git_commit).not.toBeNull();
  return response.runs[0];
}

async function openProjectInUi(page: Page, project: ProjectResponse): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(escapeRegex(project.name)) }).click();
  await expect(page.getByRole("tab", { name: WORKFLOW_ID })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".react-flow")).toBeVisible();
}

async function openGitTab(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^Git$/ }).click();
  await expect(page.getByTestId("git-tab")).toBeVisible();
}

async function openGitHistoryList(page: Page): Promise<void> {
  await openGitTab(page);
  await page.getByTestId("git-history-view-list").click();
  await page.getByTestId("git-history-filter").selectOption("all");
  await expect(page.getByTestId("git-history-rows")).toBeVisible();
}

async function addNoteAndWaitDirty(page: Page, request: APIRequestContext): Promise<void> {
  await page.getByRole("button", { name: "Note" }).click();
  await expect
    .poll(async () => {
      const status = await apiJson<GitStatus>(request, "/api/git/status");
      return status.dirty && [...status.modified, ...status.untracked].includes("workflows/main.yaml");
    })
    .toBe(true);
}

async function switchBranchFromPicker(page: Page, branchName: string): Promise<void> {
  await openGitTab(page);
  await page.getByTestId("branch-picker-trigger").click();
  await page.getByTestId(`branch-picker-item-${branchName}`).click();
}

async function createFeatureBranchWithWorkflow(
  request: APIRequestContext,
  branchName: string,
  workflow: WorkflowPayload,
): Promise<void> {
  await apiJson(request, "/api/git/branch/create", {
    method: "POST",
    data: { name: branchName },
  });
  await apiJson(request, "/api/git/branch/switch", {
    method: "POST",
    data: { branch_name: branchName },
  });
  await putWorkflow(request, workflow);
  await commitCurrentTree(request, `test: ${branchName} workflow`);
  await apiJson(request, "/api/git/branch/switch", {
    method: "POST",
    data: { branch_name: "main" },
  });
}

async function putWorkflow(request: APIRequestContext, workflow: WorkflowPayload): Promise<void> {
  await apiJson<WorkflowPayload>(request, `/api/workflows/${encodeURIComponent(workflow.id)}`, {
    method: "PUT",
    data: workflow,
  });
}

async function commitCurrentTree(request: APIRequestContext, message: string): Promise<string> {
  const status = await apiJson<GitStatus>(request, "/api/git/status");
  if (!status.dirty) {
    const [head] = await apiJson<GitCommit[]>(request, "/api/git/log?limit=1");
    return head.sha;
  }
  const response = await apiJson<{ commit_sha: string }>(request, "/api/git/commit", {
    method: "POST",
    data: { message },
  });
  return response.commit_sha;
}

async function apiJson<T>(
  request: APIRequestContext,
  url: string,
  options?: Parameters<APIRequestContext["fetch"]>[1],
): Promise<T> {
  const response = await request.fetch(url, options);
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as T;
}

async function shortShaFor(request: APIRequestContext, commitSha: string): Promise<string> {
  const log = await apiJson<GitCommit[]>(request, "/api/git/log?limit=50");
  return log.find((commit) => commit.sha === commitSha)?.short_sha ?? commitSha.slice(0, 7);
}

async function expectCanvasMatchesWorkflow(
  page: Page,
  request: APIRequestContext,
  workflowId: string,
  expected: WorkflowPayload,
): Promise<void> {
  const fromDisk = await apiJson<WorkflowPayload>(request, `/api/workflows/${encodeURIComponent(workflowId)}`);
  expect(fromDisk.nodes.map((node) => node.id).sort()).toEqual(expected.nodes.map((node) => node.id).sort());
  expect(fromDisk.edges).toEqual(expected.edges);

  await expect(page.locator(".react-flow__node")).toHaveCount(fromDisk.nodes.length, { timeout: 10_000 });
  await expect(page.locator(".react-flow__edge")).toHaveCount(fromDisk.edges.length);
  for (const node of fromDisk.nodes) {
    await expect(page.locator(`.react-flow__node[data-id="${node.id}"]`)).toHaveCount(1);
  }
  await expect(page.getByRole("tab", { name: workflowId })).toHaveAttribute("aria-selected", "true");
}

function workflowFixture(kind: "empty" | "base" | "expanded" | "branched"): WorkflowPayload {
  const common = {
    id: WORKFLOW_ID,
    version: "1.0.0",
    metadata: {},
  };
  if (kind === "empty") {
    return { ...common, description: "empty workflow", nodes: [], edges: [] };
  }
  if (kind === "base") {
    return {
      ...common,
      description: "base workflow",
      nodes: [node("load", "imaging.load_image", 80, 100), node("threshold", "imaging.threshold", 420, 100)],
      edges: [{ source: "load:images", target: "threshold:image" }],
    };
  }
  if (kind === "expanded") {
    return {
      ...common,
      description: "expanded workflow",
      nodes: [
        node("load", "imaging.load_image", 80, 100),
        node("threshold", "imaging.threshold", 420, 100),
        node("save", "imaging.save_image", 760, 100),
      ],
      edges: [
        { source: "load:images", target: "threshold:image" },
        { source: "threshold:mask", target: "save:images" },
      ],
    };
  }
  return {
    ...common,
    description: "branch workflow",
    nodes: [
      node("branch-load", "imaging.load_image", 120, 160),
      node("branch-threshold", "imaging.threshold", 520, 160),
    ],
    edges: [{ source: "branch-load:images", target: "branch-threshold:image" }],
  };
}

function node(id: string, blockType: string, x: number, y: number): WorkflowNode {
  return {
    id,
    block_type: blockType,
    config: { params: {} },
    layout: { x, y },
  };
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
