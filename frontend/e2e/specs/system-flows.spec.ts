import { expect, test } from "@playwright/test";

import { installSystemMocks, openMockProject } from "../support/systemMocks";

test("creates a project and loads the persisted workflow surface", async ({ page }) => {
  await openMockProject(page);

  await expect(page.getByText("E2E Project")).toBeVisible();
  await expect(page.getByText("IO Block").first()).toBeVisible();
  await expect(page.getByText("Process Block").first()).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: /E2E Project/ }).click();
  await expect(page.getByText("Process Block").first()).toBeVisible();
});

test("run button posts execute and websocket completion returns the UI to idle", async ({ page }) => {
  await openMockProject(page);

  const executeRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/workflows/main/execute")) executeRequests.push(request.method());
  });

  await page.getByRole("button", { name: "Run" }).click();
  await expect.poll(() => executeRequests.length).toBe(1);
  await page.evaluate(() => {
    window.__scistudioE2EEmitWs?.({ type: "workflow_completed", workflow_id: "main", data: { workflow_id: "main" } });
  });
  await expect(page.getByRole("button", { name: "Run" })).toBeEnabled();
});

test("lineage tab opens a completed run and exposes previewable output metadata", async ({ page }) => {
  test.fail(true, "#1486: Lineage output preview metadata is not visible in browser-level flow yet");
  await openMockProject(page);

  await page.getByRole("button", { name: /Lineage/ }).click();
  await expect(page.getByTestId("lineage-tab")).toBeVisible();
  await page.getByText("main · 1.0s · 2 block(s)").click();
  await expect(page.getByText("process")).toBeVisible();
  await expect(page.getByText("obj-1")).toBeVisible();
});

test("git tab restore posts the selected historical commit", async ({ page }) => {
  test.fail(true, "#1486: browser Git restore flow is expected evidence until the e2e harness is promoted");
  await openMockProject(page);

  const restoreRequests: unknown[] = [];
  page.on("request", async (request) => {
    if (request.url().endsWith("/api/git/restore")) {
      restoreRequests.push(request.postDataJSON());
    }
  });

  await page.getByRole("button", { name: "Git" }).click();
  await expect(page.getByTestId("git-tab")).toBeVisible();
  await page.getByTestId("git-history-row-restore-1111111").click();
  await expect.poll(() => restoreRequests.length).toBe(1);
  expect(restoreRequests[0]).toMatchObject({ commit_sha: "1111111111111111111111111111111111111111" });
});

test("ADR-045 websocket workflow.changed reconciles the visible canvas", async ({ page }) => {
  test.fail(true, "#1486: browser-level external edit reconcile is not yet covered by executable e2e");
  await installSystemMocks(page);
  await page.goto("/");

  await page.evaluate(() => {
    window.__scistudioE2EEmitWs?.({
      type: "workflow.changed",
      workflow_id: "main",
      data: { workflow_id: "main", version_vector: { counter: 2, source_id: "external" } },
    });
  });

  await expect(page.getByText("Process Block").first()).toBeVisible();
});
