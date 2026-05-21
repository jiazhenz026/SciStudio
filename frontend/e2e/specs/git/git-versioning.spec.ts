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

const WORKFLOW_ID = "main";

test.describe("Git E2E discovery @git", () => {
  test("GIT-001 status updates after workflow modification and stash UI/API stays absent @git", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    const stashRequests = trackStashRequests(page);

    await openProjectInUi(page, project);
    await putWorkflow(request, workflowFixture("manual-change"));
    await openGitTab(page);

    await expect(page.getByTestId("git-status-badge")).toHaveAttribute("data-status", "dirty");
    await expect(page.getByTestId("git-tab-stashes-button")).toHaveCount(0);
    expect(stashRequests, "Git UI must not call removed /api/git/stash endpoints").toEqual([]);

    const status = await apiJson<GitStatus>(request, "/api/git/status");
    expect(status.dirty).toBe(true);
    expect([...status.modified, ...status.untracked]).toContain("workflows/main.yaml");
  });

  test("GIT-002 commit dialog commits workflow changes @git", async ({ page, request }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));

    await openProjectInUi(page, project);
    await putWorkflow(request, workflowFixture("manual-change"));
    await openGitTab(page);

    await expect(page.getByTestId("git-status-badge")).toHaveAttribute("data-status", "dirty");
    await page.getByTestId("git-tab-commit-button").click();
    await expect(page.getByTestId("commit-dialog")).toBeVisible();
    await expect(page.getByTestId("commit-dialog-files")).toContainText("workflows/main.yaml");

    await page.getByTestId("commit-dialog-message").fill("test: commit workflow change");
    await page.getByTestId("commit-dialog-submit").click();

    await expect(page.getByTestId("commit-dialog")).toHaveCount(0);
    await expect(page.getByTestId("git-status-badge")).toHaveAttribute("data-status", "clean");

    const [head] = await apiJson<GitCommit[]>(request, "/api/git/log?limit=1");
    expect(head.subject).toBe("test: commit workflow change");
  });

  test("GIT-003 restores workflow file from inline history action @git", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    const baseSha = await commitCurrentTree(request, "test: base workflow");
    await putWorkflow(request, workflowFixture("expanded"));
    await commitCurrentTree(request, "test: expanded workflow");

    await openProjectInUi(page, project);
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("expanded"));

    page.once("dialog", (dialog) => dialog.accept());
    await restoreCommitFromHistory(page, request, baseSha);

    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));
    await expect(page.getByTestId("git-status-badge")).toHaveAttribute("data-status", "dirty");
  });

  test("GIT-004 branch picker switch refreshes workflow canvas @git", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    await createFeatureBranchWithWorkflow(request, "feature-refresh", workflowFixture("branched"));

    await openProjectInUi(page, project);
    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("base"));

    await switchBranchFromPicker(page, "feature-refresh");

    await expectCanvasMatchesWorkflow(page, request, WORKFLOW_ID, workflowFixture("branched"));
    await expect(page.getByTestId("branch-picker-trigger")).toContainText("feature-refresh");
  });

  test("GIT-005 conflict view appears for conflicted merge and preserves recovery actions @git", async ({
    page,
    request,
  }, testInfo) => {
    const project = await createProjectWithWorkflow(request, testInfo, workflowFixture("base"));
    await createFeatureBranchWithWorkflow(request, "feature-conflict", workflowFixture("branched"));
    await putWorkflow(request, workflowFixture("manual-change"));
    await commitCurrentTree(request, "test: conflicting main workflow");

    await openProjectInUi(page, project);
    await openGitTab(page);
    await page.getByTestId("branch-picker-trigger").click();
    await page.getByTestId("branch-picker-merge-feature-conflict").click();

    await expect(page.getByTestId("merge-flow")).toBeVisible();
    await expect(page.getByTestId("merge-flow-conflict")).toBeVisible();
    await expect(page.getByTestId("conflict-resolve-view")).toBeVisible();
    await expect(page.getByTestId("conflict-row-workflows/main.yaml")).toHaveAttribute(
      "data-status",
      "unresolved",
    );
    await expect(page.getByTestId("conflict-complete-button")).toBeDisabled();
    await expect(page.getByTestId("conflict-abort-button")).toBeEnabled();
  });
});

async function createProjectWithWorkflow(
  request: APIRequestContext,
  testInfo: TestInfo,
  workflow: WorkflowPayload,
): Promise<ProjectResponse> {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-e2e-git-"));
  const name = `e2e-git-${Date.now()}-${testInfo.retry}`;
  const project = await apiJson<ProjectResponse>(request, "/api/projects/", {
    method: "POST",
    data: { name, description: "E2E Git discovery", path: parent },
  });
  await testInfo.attach("project-path", { body: project.path, contentType: "text/plain" });
  await apiJson<ProjectResponse>(request, `/api/projects/${encodeURIComponent(project.id)}`);
  await putWorkflow(request, workflow);
  await commitCurrentTree(request, "test: seed workflow");
  return project;
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

async function restoreCommitFromHistory(page: Page, request: APIRequestContext, commitSha: string): Promise<void> {
  await openGitTab(page);
  await page.getByTestId("git-history-view-list").click();
  await page.getByTestId("git-history-filter").selectOption("all");
  const shortSha = await shortShaFor(request, commitSha);
  await page.getByTestId(`git-history-row-restore-${shortSha}`).click();
}

async function switchBranchFromPicker(page: Page, branchName: string): Promise<void> {
  await openGitTab(page);
  await page.getByTestId("branch-picker-trigger").click();
  await page.getByTestId(`branch-picker-item-${branchName}`).click();
}

function trackStashRequests(page: Page): string[] {
  const requests: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/git/stash")) requests.push(url);
  });
  return requests;
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

function workflowFixture(kind: "base" | "expanded" | "branched" | "manual-change"): WorkflowPayload {
  const common = {
    id: WORKFLOW_ID,
    version: "1.0.0",
    metadata: {},
  };
  if (kind === "base") {
    return {
      ...common,
      description: "base workflow",
      nodes: [node("load", "code_block", 80, 100), node("threshold", "code_block", 420, 100)],
      edges: [{ source: "load:result", target: "threshold:data" }],
    };
  }
  if (kind === "expanded") {
    return {
      ...common,
      description: "expanded workflow",
      nodes: [
        node("load", "code_block", 80, 100),
        node("threshold", "code_block", 420, 100),
        node("save", "code_block", 760, 100),
      ],
      edges: [
        { source: "load:result", target: "threshold:data" },
        { source: "threshold:result", target: "save:data" },
      ],
    };
  }
  if (kind === "branched") {
    return {
      ...common,
      description: "branch workflow",
      nodes: [node("branch-load", "code_block", 120, 160), node("branch-save", "code_block", 520, 160)],
      edges: [{ source: "branch-load:result", target: "branch-save:data" }],
    };
  }
  return {
    ...common,
    description: "manual main workflow",
    nodes: [node("manual-main", "code_block", 220, 180)],
    edges: [],
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
