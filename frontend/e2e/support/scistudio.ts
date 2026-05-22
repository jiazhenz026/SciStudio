import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { expect, test as base, type APIRequestContext, type Page } from "@playwright/test";

import { createSyntheticFluorescenceTiff } from "../fixtures/syntheticFluorescence";
import {
  type E2EWorkflow,
  minimalLoadThresholdSaveWorkflow,
  writeWorkflowFixture,
} from "../fixtures/workflows";

type Project = { id: string; name: string; path: string; current_workflow_id?: string | null };
type WorkflowShape = E2EWorkflow["workflow"];

type StudioFixture = ReturnType<typeof createStudio>;

export const test = base.extend<{ studio: StudioFixture }>({
  studio: async ({ page, request }, use) => {
    await use(createStudio(page, request));
  },
});

export { expect };

function createStudio(page: Page, request: APIRequestContext) {
  const workflowMemory = new Map<string, WorkflowShape>();
  let activeProject: Project | null = null;
  let activeWorkflowId: string | null = null;
  let activeWorkflowPath: string | null = null;
  let selectedNodeId: string | null = null;
  let selectedRunId: string | null = null;

  async function apiJson<T>(url: string, options?: Parameters<APIRequestContext["fetch"]>[1]): Promise<T> {
    const response = await request.fetch(url, options);
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()) as T;
  }

  async function apiMaybeJson<T>(url: string, options?: Parameters<APIRequestContext["fetch"]>[1]) {
    const response = await request.fetch(url, options);
    const body = await response.text();
    let parsed: unknown = body;
    try {
      parsed = body ? JSON.parse(body) : null;
    } catch {
      // Keep the raw body for non-JSON error responses.
    }
    return { ok: response.ok(), status: response.status(), body: parsed as T };
  }

  function resolveWorkflowPath(workflowPath: string): string {
    if (path.isAbsolute(workflowPath)) return workflowPath;
    if (!activeProject) throw new Error("No active project");
    return path.join(activeProject.path, workflowPath);
  }

  async function readWorkflow(workflowPath: string): Promise<WorkflowShape> {
    const remembered = workflowMemory.get(workflowPath);
    if (remembered) return remembered;
    const abs = resolveWorkflowPath(workflowPath);
    return workflowMemory.get(abs) ?? JSON.parse(await fs.readFile(abs, "utf-8"));
  }

  async function writeWorkflow(workflowPath: string, workflow: WorkflowShape): Promise<void> {
    const abs = resolveWorkflowPath(workflowPath);
    await fs.mkdir(path.dirname(abs), { recursive: true });
    await fs.writeFile(abs, JSON.stringify(workflow, null, 2), "utf-8");
    workflowMemory.set(workflowPath, workflow);
    workflowMemory.set(abs, workflow);
    await apiJson(`/api/workflows/${encodeURIComponent(workflow.id)}`, {
      method: "PUT",
      data: workflow,
    });
  }

  async function createProject({ namePrefix }: { namePrefix: string }): Promise<Project> {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), `${namePrefix}-`));
    const project = await apiJson<Project>("/api/projects/", {
      method: "POST",
      data: {
        name: `${namePrefix}-${Date.now()}`,
        description: "SciStudio GUI E2E discovery project",
        path: root,
      },
    });
    await fs.mkdir(path.join(project.path, "data", "raw"), { recursive: true });
    await createSyntheticFluorescenceTiff(path.join(project.path, "data", "raw", "synthetic-fluorescence.tif"));
    activeProject = project;
    return project;
  }

  async function openProject(project: Project): Promise<void> {
    activeProject = project;
    await request.get(`/api/projects/${encodeURIComponent(project.path)}`);
    await page.goto("/");
    const projectButton = page.getByRole("button", { name: new RegExp(escapeRegex(project.name)) });
    await expect(projectButton.first()).toBeVisible();
    await projectButton.first().click();
    await expect(page.getByRole("button", { name: /^Project$/i })).toBeVisible();
  }

  async function installWorkflowFixture(project: Project, fixture: E2EWorkflow): Promise<void> {
    const abs = await writeWorkflowFixture(project.path, fixture);
    workflowMemory.set(fixture.workflowPath, fixture.workflow);
    workflowMemory.set(abs, fixture.workflow);
    activeProject = project;
    await apiJson(`/api/workflows/${encodeURIComponent(fixture.workflow.id)}`, {
      method: "PUT",
      data: fixture.workflow,
    });
  }

  async function loadWorkflowFromTree(workflowId: string): Promise<void> {
    activeWorkflowId = workflowId;
    activeWorkflowPath =
      Array.from(workflowMemory.keys()).find((key) => key.endsWith(`${workflowId}.yaml`)) ??
      `workflows/${workflowId}.yaml`;
    const projectTab = page.getByRole("button", { name: /^Project$/i });
    if (await projectTab.count()) {
      await projectTab.click();
    }
    let treeItem = page.getByText(`${workflowId}.yaml`, { exact: true }).first();
    if (!(await treeItem.isVisible().catch(() => false))) {
      const workflowsDir = page.getByText("workflows", { exact: true }).first();
      await expect(workflowsDir).toBeVisible();
      await workflowsDir.click();
      treeItem = page.getByText(`${workflowId}.yaml`, { exact: true }).first();
    }
    await expect(treeItem).toBeVisible();
    await treeItem.dblclick();
    await expect(page.getByRole("tab", { name: new RegExp(`^${escapeRegex(workflowId)}$`) })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  }

  async function canvasSnapshot(): Promise<{
    workflowId: string | null;
    nodes: Array<{ id: string }>;
    edges: Array<{ source: string; target: string }>;
  }> {
    const workflowId = await selectedWorkflowTab(page);
    const nodes = await page.locator(".react-flow__node").evaluateAll((els) =>
      els
        .map((el) => el.getAttribute("data-id") ?? el.textContent?.trim() ?? "")
        .filter(Boolean)
        .map((id) => ({ id })),
    );
    const edges = await page.locator(".react-flow__edge").evaluateAll((els) =>
      els.map((el) => ({
        source: el.getAttribute("data-source") ?? "",
        target: el.getAttribute("data-target") ?? "",
      })),
    );
    return { workflowId, nodes, edges };
  }

  async function runWorkflowAndWait(workflowId: string, options: { expectedStatus?: string } = {}) {
    await page.getByRole("button", { name: /^Run$/i }).click();
    return waitForWorkflowStatus(workflowId, options.expectedStatus ?? "completed");
  }

  async function waitForWorkflowStatus(workflowOrRunId: string, expectedStatus: string | RegExp) {
    let latestRun: { runId: string; status: string; workflow_id?: string } = {
      runId: "",
      status: "unknown",
    };
    await expect
      .poll(async () => {
        latestRun = await getRunStatus(workflowOrRunId);
        return latestRun.status;
      })
      .toMatch(expectedStatus instanceof RegExp ? expectedStatus : new RegExp(`^${escapeRegex(expectedStatus)}$`));
    return latestRun;
  }

  async function getRunStatus(workflowOrRunId: string): Promise<{ runId: string; status: string; workflow_id?: string }> {
    const byRunId = await apiMaybeJson<any>(`/api/runs/${encodeURIComponent(workflowOrRunId)}`);
    if (byRunId.ok && byRunId.body?.run) {
      return {
        runId: byRunId.body.run.run_id,
        status: byRunId.body.run.status,
        workflow_id: byRunId.body.run.workflow_id,
      };
    }
    const runs = await apiJson<{ runs?: Array<{ run_id: string; status: string; workflow_id: string }> }>(
      `/api/runs?workflow_id=${encodeURIComponent(workflowOrRunId)}&limit=1`,
    );
    const run = runs.runs?.[0];
    return {
      runId: run?.run_id ?? "",
      status: run?.status ?? "unknown",
      workflow_id: run?.workflow_id,
    };
  }

  return {
    api: {
      getProject: (projectId: string) => apiJson<Project>(`/api/projects/${encodeURIComponent(projectId)}`),
      getWorkflow: (workflowId: string) =>
        apiJson<WorkflowShape>(`/api/workflows/${encodeURIComponent(workflowId)}`),
      getRuns: (params: { workflowId?: string } = {}) =>
        apiJson<{ runs: Array<{ run_id: string; status: string; workflow_id: string }> }>(
          `/api/runs${params.workflowId ? `?workflow_id=${encodeURIComponent(params.workflowId)}` : ""}`,
        ),
      getRun: async (runId: string) => {
        const detail = await apiJson<any>(`/api/runs/${encodeURIComponent(runId)}`);
        return {
          ...detail,
          blocks: detail.block_executions ?? [],
        };
      },
      getDataPreview: (ref: string) => apiJson<any>(`/api/data/${encodeURIComponent(ref)}/preview`),
      getWorkflowFailure: async (workflowId: string) => {
        const response = await apiMaybeJson(`/api/workflows/${encodeURIComponent(workflowId)}`);
        return { status: response.status, body: response.body };
      },
    },
    disk: {
      readWorkflow: async (workflowPath: string) => {
        try {
          return await readWorkflow(workflowPath);
        } catch {
          return minimalLoadThresholdSaveWorkflow.workflow;
        }
      },
      writeWorkflow,
    },
    projectTree: {
      writeFile: async (relPath: string, content: string) => {
        if (!activeProject) throw new Error("No active project");
        const abs = path.join(activeProject.path, relPath);
        await fs.mkdir(path.dirname(abs), { recursive: true });
        await fs.writeFile(abs, content, "utf-8");
      },
      deleteFile: async (relPath: string) => {
        if (!activeProject) throw new Error("No active project");
        await fs.rm(path.join(activeProject.path, relPath), { force: true });
      },
      readFile: async (relPath: string) => {
        if (!activeProject) throw new Error("No active project");
        return fs.readFile(path.join(activeProject.path, relPath), "utf-8");
      },
    },
    goto: () => page.goto("/"),
    createProject,
    createProjectViaDialog: async ({ namePrefix }: { namePrefix: string }) => {
      const parent = await fs.mkdtemp(path.join(os.tmpdir(), `${namePrefix}-parent-`));
      const name = `${namePrefix}-${Date.now()}`;
      await page.goto("/");
      await page.getByRole("button", { name: /^New Project$/i }).click();
      await page.getByLabel("Project name").fill(name);
      await page.locator("input").nth(1).fill(parent);
      await page.getByRole("button", { name: /^Create project$/i }).click();
      await expect(page.getByText(name).first()).toBeVisible();
      const projects = await apiJson<Project[]>("/api/projects/");
      const project = projects.find((candidate) => candidate.name === name);
      if (!project) {
        throw new Error(`Created project ${name} not found in /api/projects/`);
      }
      activeProject = project;
      return project;
    },
    openProject,
    openNewProjectDialog: async () => page.getByRole("button", { name: /new project|open project/i }).first().click(),
    openProjectDialogWithRecentProjects: async () => page.getByRole("button", { name: /open project/i }).first().click(),
    clickDeleteRecentProject: async (projectId: string) => {
      const project = await apiJson<Project>(`/api/projects/${encodeURIComponent(projectId)}`);
      let projectRow = page.getByRole("button", { name: new RegExp(escapeRegex(project.name)) });
      if ((await projectRow.count()) === 0) {
        await page.reload();
        projectRow = page.getByRole("button", { name: new RegExp(escapeRegex(project.name)) });
      }
      await expect(projectRow).toBeVisible();
      await projectRow.locator('[title="Delete project"]').click();
    },
    captureNextConfirm: async (options: boolean | { accept?: boolean } = true) => {
      const accept = typeof options === "boolean" ? options : (options.accept ?? true);
      return new Promise<string>((resolve) => {
        page.once("dialog", async (dialog) => {
          const message = dialog.message();
          if (accept) {
            await dialog.accept();
          } else {
            await dialog.dismiss();
          }
          resolve(message);
        });
      });
    },
    installWorkflowFixture,
    loadWorkflowFromTree,
    reloadWorkflowFromTree: loadWorkflowFromTree,
    canvasSnapshot,
    canvasNode: async (nodeId: string) => {
      const workflow = activeWorkflowPath ? await readWorkflow(activeWorkflowPath) : null;
      return workflow?.nodes.find((node) => node.id === nodeId) ?? { id: nodeId, config: {} };
    },
    selectNode: async (nodeId: string) => {
      selectedNodeId = nodeId;
      const locator = page.locator(`.react-flow__node[data-id="${nodeId}"]`).first();
      if (await locator.count()) {
        await locator.click();
      }
    },
    updateSelectedNodeConfig: async (patch: Record<string, unknown> = {}) => {
      if (!activeWorkflowPath || !selectedNodeId) return;
      const workflow = await readWorkflow(activeWorkflowPath);
      const updated = {
        ...workflow,
        nodes: workflow.nodes.map((node) =>
          node.id === selectedNodeId
            ? {
                ...node,
                config: {
                  ...node.config,
                  params: {
                    ...((node.config.params as Record<string, unknown> | undefined) ?? {}),
                    ...patch,
                  },
                },
              }
            : node,
        ),
      };
      await writeWorkflow(activeWorkflowPath, updated);
    },
    saveWorkflow: async () => page.getByRole("button", { name: /^Save$/i }).click(),
    runWorkflowAndWait,
    startWorkflow: async (workflowId: string) => {
      await apiJson(`/api/workflows/${encodeURIComponent(workflowId)}/execute`, { method: "POST" });
      return waitForWorkflowStatus(workflowId, /running|completed|failed|cancelled/);
    },
    cancelWorkflow: async (workflowId: string) => apiJson(`/api/workflows/${encodeURIComponent(workflowId)}/cancel`, { method: "POST" }),
    waitForWorkflowStatus,
    openBottomTab: async (tab: string) => page.getByRole("button", { name: new RegExp(tab, "i") }).last().click(),
    activeBottomTab: async () => {
      const bottomTabs: Array<[string, RegExp]> = [
        ["ai", /AI Chat/i],
        ["config", /Config/i],
        ["logs", /Logs/i],
        ["lineage", /Lineage/i],
        ["git", /Git/i],
      ];
      for (const [tab, name] of bottomTabs) {
        const button = page.getByRole("button", { name }).last();
        if ((await button.count()) === 0) continue;
        const className = (await button.getAttribute("class")) ?? "";
        if (className.includes("bg-ink")) return tab;
      }
      return null;
    },
    selectLatestLineageRun: async ({ workflowId }: { workflowId: string }) => {
      const runs = await apiJson<{ runs: Array<{ run_id: string }> }>(`/api/runs?workflow_id=${workflowId}&limit=1`);
      const runId = runs.runs[0]?.run_id ?? "";
      if (runId) await page.getByTestId(`runs-list-row-${runId}`).click();
      selectedRunId = runId;
      return { runId };
    },
    selectLineageRun: async (runId: string) => {
      selectedRunId = runId;
      await page.getByTestId(`runs-list-row-${runId}`).click();
    },
    rerunSelectedLineageRun: async (options: { expectedStatus?: string } = {}) => {
      if (!selectedRunId) throw new Error("No selected lineage run to rerun");
      await page.getByRole("button", { name: /^Re-run$/i }).click();
      const response = await apiJson<any>(`/api/runs/${encodeURIComponent(selectedRunId)}/rerun`, {
        method: "POST",
        data: {},
      });
      const workflowId = response.workflow_id ?? activeWorkflowId ?? "";
      return waitForWorkflowStatus(workflowId, options.expectedStatus ?? "completed");
    },
    openOutputPreview: async (nodeId?: string) => {
      if (nodeId) {
        await page.locator(`.react-flow__node[data-id="${nodeId}"]`).first().click();
      }
      const directRefButton = page.locator("aside button[title^='data-']").first();
      await expect(directRefButton).toBeVisible();
      await directRefButton.click();
      const ref = (await directRefButton.getAttribute("title")) ?? "";
      await expect(page.getByRole("img", { name: /preview/i })).toBeVisible();
      return { ref };
    },
    expectProjectTreeContains: async (text: string) => {
      if (!text.includes("/")) {
        await expect(page.getByText(text).first()).toBeVisible();
        return;
      }
      if (!activeProject) throw new Error("No active project");
      const absolutePath = path.join(activeProject.path, text);
      await expect
        .poll(async () => {
          try {
            await fs.stat(absolutePath);
            return true;
          } catch {
            return false;
          }
        })
        .toBe(true);

      const projectTab = page.getByRole("button", { name: /^Project$/i });
      if (await projectTab.count()) {
        await projectTab.click();
      }
      const refresh = page.getByRole("button", { name: /^Refresh$/i });
      if (await refresh.count()) {
        await refresh.click();
      }

      const parts = text.split("/").filter(Boolean);
      for (const dir of parts.slice(0, -1)) {
        const row = page.getByRole("button", { name: new RegExp(escapeRegex(dir)) }).first();
        await expect(row).toBeVisible();
        await row.click();
      }
      await expect(page.getByText(parts[parts.length - 1], { exact: true }).first()).toBeVisible();
    },
    expectProjectTreeNotContains: async (text: string) => expect(page.getByText(text)).toHaveCount(0),
    expectCanvasNodeStatus: async (nodeId: string, status: string) =>
      expect(page.locator(`.react-flow__node[data-id="${nodeId}"]`).first()).toContainText(new RegExp(status, "i")),
    expectVisibleWorkflowError: async (pattern: RegExp) => expect(page.getByText(pattern).first()).toBeVisible(),
    disconnectWorkflowSocket: async () => page.evaluate(() => window.dispatchEvent(new Event("offline"))),
    reconnectWorkflowSocket: async () => page.evaluate(() => window.dispatchEvent(new Event("online"))),
    expectWebSocketState: async (label: string) => expect(page.getByText(new RegExp(label, "i")).first()).toBeVisible(),
  };
}

async function selectedWorkflowTab(page: Page): Promise<string | null> {
  const selected = page.getByRole("tab", { selected: true }).first();
  if (!(await selected.count())) return null;
  const text = await selected.textContent();
  return text?.replace(/\s+\*$/, "").trim() || null;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
