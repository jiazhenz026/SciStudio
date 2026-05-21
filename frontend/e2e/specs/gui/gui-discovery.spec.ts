import { expect, test } from "../../support/scistudio";
import {
  failingLoadImageWorkflow,
  invalidThresholdWorkflow,
  minimalLoadThresholdSaveWorkflow,
  slowCancellableWorkflow,
} from "../../fixtures/workflows";

/*
 * Expected harness contract.
 *
 * The harness is owned by the E2E-Harness lane, so this spec intentionally
 * does not define support helpers here. The imported fixture should expose a
 * per-test `studio` object with real GUI/API/project-dir operations:
 *
 * - createProject({ namePrefix })
 * - openProject(project)
 * - installWorkflowFixture(project, fixture)
 * - loadWorkflowFromTree(workflowId)
 * - canvasSnapshot()
 * - api.getWorkflow(workflowId)
 * - api.getRuns({ workflowId })
 * - api.getRun(runId)
 * - disk.readWorkflow(workflowPath)
 * - disk.writeWorkflow(workflowPath, workflow)
 * - projectTree.writeFile/deleteFile/readFile/list
 * - runWorkflowAndWait(workflowId, options)
 * - startWorkflow(workflowId), cancelWorkflow(workflowId), waitForWorkflowStatus(...)
 * - openBottomTab(tab), activeBottomTab()
 * - selectNode(nodeId), updateSelectedNodeConfig(patch), saveWorkflow()
 * - expectProjectTreeContains/NotContains(path)
 * - expectCanvasNodeStatus(nodeId, status)
 * - expectVisibleWorkflowError(pattern)
 * - disconnectWorkflowSocket()/reconnectWorkflowSocket()
 *
 * When E2E-Harness lands, these tests should run without mocking product
 * state: project files, API responses, WebSocket events, and canvas snapshots
 * must all come from the running SciStudio app.
 */

type WorkflowGraph = {
  workflowId: string;
  nodes: string[];
  edgeCount: number;
};

function graphFromWorkflow(workflow: {
  id: string;
  nodes: Array<{ id: string }>;
  edges: Array<{ source: string; target: string }>;
}): WorkflowGraph {
  return {
    workflowId: workflow.id,
    nodes: workflow.nodes.map((node) => node.id).sort(),
    edgeCount: workflow.edges.length,
  };
}

function graphFromCanvas(snapshot: {
  workflowId: string | null;
  nodes: Array<{ id: string }>;
  edges: Array<{ source: string; target: string }>;
}): WorkflowGraph {
  return {
    workflowId: snapshot.workflowId ?? "",
    nodes: snapshot.nodes.map((node) => node.id).sort(),
    edgeCount: snapshot.edges.length,
  };
}

async function openMinimalWorkflow(studio: any) {
  const project = await studio.createProject({ namePrefix: "gui-discovery" });
  await studio.installWorkflowFixture(project, minimalLoadThresholdSaveWorkflow);
  await studio.openProject(project);
  await studio.loadWorkflowFromTree(minimalLoadThresholdSaveWorkflow.workflowId);
  await expectCanvasSyncedWithDisk(
    studio,
    minimalLoadThresholdSaveWorkflow.workflowPath,
  );
  return {
    project,
    workflowId: minimalLoadThresholdSaveWorkflow.workflowId,
    workflowPath: minimalLoadThresholdSaveWorkflow.workflowPath,
  };
}

async function expectCanvasSyncedWithDisk(
  studio: any,
  workflowPath: string,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const [canvas, disk] = await Promise.all([
          studio.canvasSnapshot(),
          studio.disk.readWorkflow(workflowPath),
        ]);
        return {
          canvas: graphFromCanvas(canvas),
          disk: graphFromWorkflow(disk),
        };
      },
      { message: `canvas should match ${workflowPath}` },
    )
    .toEqual(
      await (async () => {
        const disk = await studio.disk.readWorkflow(workflowPath);
        return {
          canvas: graphFromWorkflow(disk),
          disk: graphFromWorkflow(disk),
        };
      })(),
    );
}

async function expectCanvasSyncedWithApiAndDisk(
  studio: any,
  workflowId: string,
  workflowPath: string,
): Promise<void> {
  await expectCanvasSyncedWithDisk(studio, workflowPath);
  const [canvas, apiWorkflow] = await Promise.all([
    studio.canvasSnapshot(),
    studio.api.getWorkflow(workflowId),
  ]);
  expect(graphFromCanvas(canvas)).toEqual(graphFromWorkflow(apiWorkflow));
}

test.describe("SciStudio GUI E2E discovery @gui", () => {
  test("GUI-001 @gui @GUI-001 opens and creates an empty project", async ({
    page,
    studio,
  }) => {
    await studio.goto();
    const project = await studio.createProjectViaDialog({
      namePrefix: "gui-empty",
    });

    await expect(page.getByText(project.name).first()).toBeVisible();
    await expect(page.getByText("Project").first()).toBeVisible();
    await studio.expectProjectTreeContains("workflows");

    await expect
      .poll(async () => studio.api.getProject(project.id), {
        message: "created project should be visible through the backend API",
      })
      .toMatchObject({
        id: project.id,
        path: project.path,
      });
  });

  test("GUI-002 @gui @GUI-002 loads the minimal workflow", async ({
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);

    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
    const canvas = await studio.canvasSnapshot();
    expect(canvas.nodes.map((node: { id: string }) => node.id).sort()).toEqual([
      "load_image",
      "save_threshold",
      "threshold",
    ]);
  });

  test("GUI-003 @gui @GUI-003 runs load image -> threshold -> save", async ({
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);

    const result = await studio.runWorkflowAndWait(workflowId, {
      expectedStatus: "completed",
      source: "toolbar",
    });

    expect(result.status).toBe("completed");
    await studio.expectCanvasNodeStatus("load_image", "done");
    await studio.expectCanvasNodeStatus("threshold", "done");
    await studio.expectCanvasNodeStatus("save_threshold", "done");
    await studio.expectProjectTreeContains(
      minimalLoadThresholdSaveWorkflow.expectedOutputPath,
    );
    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
  });

  test("GUI-004 @gui @GUI-004 shows lineage after a completed run", async ({
    page,
    studio,
  }) => {
    const { workflowId } = await openMinimalWorkflow(studio);
    await studio.runWorkflowAndWait(workflowId, { expectedStatus: "completed" });

    await studio.openBottomTab("lineage");
    await expect(page.getByTestId("lineage-tab")).toBeVisible();
    const run = await studio.selectLatestLineageRun({ workflowId });

    await expect(page.getByTestId("run-detail")).toBeVisible();
    await expect(page.getByTestId("run-detail-blocks")).toContainText(
      "Blocks (3)",
    );

    const apiRun = await studio.api.getRun(run.runId);
    expect(apiRun.run.workflow_id).toBe(workflowId);
    expect(apiRun.run.status).toBe("completed");
    expect(apiRun.blocks.map((block: { block_id: string }) => block.block_id)).toEqual(
      expect.arrayContaining(["load_image", "threshold", "save_threshold"]),
    );
  });

  test("GUI-005 @gui @GUI-005 previews run artifacts", async ({
    page,
    studio,
  }) => {
    const { workflowId } = await openMinimalWorkflow(studio);
    const run = await studio.runWorkflowAndWait(workflowId, {
      expectedStatus: "completed",
    });

    await studio.selectNode("threshold");
    const preview = await studio.openOutputPreview("threshold", {
      refFromRun: run,
    });

    await expect(page.getByText("Preview")).toBeVisible();
    await expect(page.getByRole("img", { name: /preview/i })).toBeVisible();
    const apiPreview = await studio.api.getDataPreview(preview.ref);
    expect(apiPreview.ref).toBe(preview.ref);
    expect(apiPreview.preview.kind).toBe("image");
  });

  test("GUI-006 @gui @GUI-006 edits block config, saves, and refreshes canvas from disk", async ({
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);

    await studio.selectNode("threshold");
    await studio.updateSelectedNodeConfig({ threshold: 0.42 });
    await studio.saveWorkflow();

    await expect
      .poll(async () => {
        const disk = await studio.disk.readWorkflow(workflowPath);
        return disk.nodes.find((node: any) => node.id === "threshold")
          ?.config?.params?.threshold;
      })
      .toBe(0.42);
    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
  });

  test("GUI-007 @gui @GUI-007 reloads an externally changed workflow YAML", async ({
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);
    const original = await studio.disk.readWorkflow(workflowPath);
    const externallyMutated = {
      ...original,
      nodes: original.nodes.map((node: any) =>
        node.id === "threshold"
          ? {
              ...node,
              config: {
                ...node.config,
                params: { ...node.config.params, threshold: 0.73 },
              },
            }
          : node,
      ),
    };

    await studio.disk.writeWorkflow(workflowPath, externallyMutated);
    await studio.reloadWorkflowFromTree(workflowId);

    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
    const canvasNode = await studio.canvasNode("threshold");
    expect(canvasNode.config.params.threshold).toBe(0.73);
  });

  test("GUI-008 @gui @GUI-008 displays invalid workflow config errors", async ({
    studio,
  }) => {
    const project = await studio.createProject({ namePrefix: "gui-invalid" });
    await studio.installWorkflowFixture(project, invalidThresholdWorkflow);
    await studio.openProject(project);

    await studio.loadWorkflowFromTree(invalidThresholdWorkflow.workflowId, {
      expectFailure: true,
    });

    const result = await studio.runWorkflowAndWait(
      invalidThresholdWorkflow.workflowId,
      { expectedStatus: "failed" },
    );

    expect(result.status).toBe("failed");
    await studio.expectVisibleWorkflowError(/threshold|method|validation|unknown/i);
  });

  test("GUI-009 @gui @GUI-009 displays failed workflow state", async ({
    page,
    studio,
  }) => {
    const project = await studio.createProject({ namePrefix: "gui-failed" });
    await studio.installWorkflowFixture(project, failingLoadImageWorkflow);
    await studio.openProject(project);
    await studio.loadWorkflowFromTree(failingLoadImageWorkflow.workflowId);

    const result = await studio.runWorkflowAndWait(
      failingLoadImageWorkflow.workflowId,
      { expectedStatus: "failed" },
    );

    expect(result.status).toBe("failed");
    await studio.expectCanvasNodeStatus("load_image", "error");
    await expect(page.getByText(/failed|error/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^run$/i })).toBeEnabled();
  });

  test("GUI-010 @gui @GUI-010 reruns a failed workflow deterministically", async ({
    studio,
  }) => {
    const project = await studio.createProject({ namePrefix: "gui-rerun" });
    await studio.installWorkflowFixture(project, failingLoadImageWorkflow);
    await studio.openProject(project);
    await studio.loadWorkflowFromTree(failingLoadImageWorkflow.workflowId);

    const firstRun = await studio.runWorkflowAndWait(
      failingLoadImageWorkflow.workflowId,
      { expectedStatus: "failed" },
    );
    await studio.openBottomTab("lineage");
    await studio.selectLineageRun(firstRun.runId);
    const secondRun = await studio.rerunSelectedLineageRun({
      expectedStatus: "failed",
    });

    expect(secondRun.runId).not.toBe(firstRun.runId);
    expect(secondRun.status).toBe("failed");
    const runs = await studio.api.getRuns({
      workflowId: failingLoadImageWorkflow.workflowId,
    });
    expect(runs.runs.map((run: { run_id: string }) => run.run_id)).toEqual(
      expect.arrayContaining([firstRun.runId, secondRun.runId]),
    );
  });

  test("GUI-011 @gui @GUI-011 cancels a running workflow", async ({
    page,
    studio,
  }) => {
    test.slow();
    const project = await studio.createProject({ namePrefix: "gui-cancel" });
    await studio.installWorkflowFixture(project, slowCancellableWorkflow);
    await studio.openProject(project);
    await studio.loadWorkflowFromTree(slowCancellableWorkflow.workflowId);

    const running = await studio.startWorkflow(slowCancellableWorkflow.workflowId);
    await studio.waitForWorkflowStatus(running.runId, "running");
    await expect(page.getByRole("button", { name: /running/i })).toBeVisible();

    const cancelled = await studio.cancelWorkflow(slowCancellableWorkflow.workflowId);

    expect(cancelled.cancelled_blocks.length).toBeGreaterThan(0);
    await studio.waitForWorkflowStatus(running.runId, /cancelled|failed/);
    await expect(page.getByRole("button", { name: /^run$/i })).toBeEnabled();
  });

  test("GUI-012 @gui @GUI-012 keeps bottom-tab state across workflow edits", async ({
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);

    await studio.openBottomTab("logs");
    expect(await studio.activeBottomTab()).toBe("logs");
    await studio.selectNode("threshold");
    await studio.updateSelectedNodeConfig({ threshold: 0.51 });
    await studio.saveWorkflow();

    expect(await studio.activeBottomTab()).toBe("logs");
    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
  });

  test("GUI-013 @gui @GUI-013 handles WebSocket disconnect and reconnect", async ({
    page,
    studio,
  }) => {
    const { workflowId, workflowPath } = await openMinimalWorkflow(studio);

    await studio.disconnectWorkflowSocket();
    await expect(page.getByText("WS")).toBeVisible();
    await studio.expectWebSocketState("disconnected");

    const diskWorkflow = await studio.disk.readWorkflow(workflowPath);
    await studio.disk.writeWorkflow(workflowPath, {
      ...diskWorkflow,
      metadata: { ...diskWorkflow.metadata, e2e_ws_marker: "reconnect" },
    });
    await studio.reconnectWorkflowSocket();
    await studio.expectWebSocketState("connected");

    await expectCanvasSyncedWithApiAndDisk(studio, workflowId, workflowPath);
  });

  test("GUI-014 @gui @GUI-014 refreshes the project tree after file operations", async ({
    studio,
  }) => {
    await openMinimalWorkflow(studio);
    const notePath = "notes/gui-tree-refresh.md";

    await studio.projectTree.writeFile(notePath, "# GUI tree refresh\n");
    await studio.expectProjectTreeContains(notePath);
    expect(await studio.projectTree.readFile(notePath)).toContain(
      "GUI tree refresh",
    );

    await studio.projectTree.deleteFile(notePath);
    await studio.expectProjectTreeNotContains(notePath);
  });

  test("GUI-015 @gui @GUI-015 preserves modal and dialog behavior", async ({
    page,
    studio,
  }) => {
    await studio.goto();
    await studio.openNewProjectDialog();

    await page.getByRole("button", { name: /create project/i }).click();
    await expect(page.getByText(/parent directory is required/i)).toBeVisible();

    const createProjectDialog = page.locator(".fixed.inset-0").filter({
      has: page.getByRole("heading", { name: /create a new workspace/i }),
    });
    await createProjectDialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: /create a new workspace/i }),
    ).toBeHidden();

    const project = await studio.createProject({ namePrefix: "gui-dialog" });
    await studio.openProjectDialogWithRecentProjects();
    const confirm = studio.captureNextConfirm({ accept: false });
    await studio.clickDeleteRecentProject(project.id);
    expect(await confirm).toMatch(/delete project/i);
    expect(await studio.api.getProject(project.id)).toMatchObject({
      id: project.id,
    });
  });
});
