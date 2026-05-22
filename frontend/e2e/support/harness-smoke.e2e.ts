import fs from "node:fs/promises";

import { createProject, expect, test } from "./test";

test("@smoke harness launches the GUI and backend", async ({ page, request }) => {
  const projects = await request.get("/api/projects/");
  expect(projects.ok(), await projects.text()).toBeTruthy();

  await page.goto("/");
  await expect(page.getByText(/SciStudio|Every tool|No project open/i).first()).toBeVisible();
});

test("@smoke fixtures generate a minimal image workflow project", async ({ projectWorkspace }) => {
  const image = await fs.readFile(projectWorkspace.imagePath);
  expect(image.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");

  const workflow = await fs.readFile(projectWorkspace.workflowPath, "utf-8");
  expect(workflow).toContain("workflow:");
  expect(workflow).toContain("imaging.load_image");
  expect(workflow).toContain("imaging.threshold");
  expect(workflow).toContain("imaging.save_image");
});

test("@smoke isolated project fixture can be opened through the real API", async ({ request, projectWorkspace }) => {
  const created = await createProject(request, projectWorkspace);
  expect(created.path).toContain(projectWorkspace.root);

  const opened = await request.get(`/api/projects/${encodeURIComponent(created.path)}`);
  expect(opened.ok(), await opened.text()).toBeTruthy();
});
