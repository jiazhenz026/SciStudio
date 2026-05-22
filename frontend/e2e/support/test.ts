import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { writeMinimalImageWorkflowFixture } from "../fixtures/minimalWorkflow";
import { createSyntheticFluorescencePng } from "../fixtures/syntheticFluorescence";

const playwright = await import(process.env.PLAYWRIGHT_TEST_MODULE ?? "@playwright/test");
const base = playwright.test;
const expect = playwright.expect;

type BrowserLog = {
  type: string;
  text: string;
  location?: string;
};

type NetworkLog = {
  method: string;
  url: string;
  status?: number;
  failure?: string;
};

export type ProjectWorkspace = {
  root: string;
  imagePath: string;
  workflowPath: string;
  snapshotPath: string;
};

type Fixtures = {
  projectWorkspace: ProjectWorkspace;
};

async function writeJson(filePath: string, value: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf-8");
}

async function snapshotProject(root: string, outPath: string): Promise<void> {
  const entries: Array<{ path: string; type: string; size?: number }> = [];

  async function walk(dir: string): Promise<void> {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      const fullPath = path.join(dir, entry.name);
      const rel = path.relative(root, fullPath).replace(/\\/g, "/");
      if (entry.isDirectory()) {
        entries.push({ path: rel, type: "directory" });
        await walk(fullPath);
      } else if (entry.isFile()) {
        const stat = await fs.stat(fullPath);
        entries.push({ path: rel, type: "file", size: stat.size });
      }
    }
  }

  await walk(root);
  await writeJson(outPath, { root, entries });
}

function attachLogCollectors(page: any): {
  consoleLog: BrowserLog[];
  networkLog: NetworkLog[];
} {
  const consoleLog: BrowserLog[] = [];
  const networkLog: NetworkLog[] = [];

  page.on("console", (message: any) => {
    const loc = message.location();
    consoleLog.push({
      type: message.type(),
      text: message.text(),
      location: loc.url ? `${loc.url}:${loc.lineNumber}:${loc.columnNumber}` : undefined,
    });
  });
  page.on("pageerror", (error: Error) => {
    consoleLog.push({ type: "pageerror", text: error.stack ?? error.message });
  });
  page.on("requestfailed", (request: any) => {
    networkLog.push({
      method: request.method(),
      url: request.url(),
      failure: request.failure()?.errorText ?? "request failed",
    });
  });
  page.on("response", (response: any) => {
    if (response.status() >= 400) {
      networkLog.push({
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
      });
    }
  });

  return { consoleLog, networkLog };
}

export const test = base.extend<Fixtures>({
  page: async ({ page }: { page: any }, use: (page: any) => Promise<void>, testInfo: any) => {
    const logs = attachLogCollectors(page);
    await testInfo.attach("artifact-root", {
      body: testInfo.outputDir,
      contentType: "text/plain",
    });
    await use(page);
    const consolePath = testInfo.outputPath("browser-console.json");
    const networkPath = testInfo.outputPath("network.json");
    await writeJson(consolePath, logs.consoleLog);
    await writeJson(networkPath, logs.networkLog);
    await testInfo.attach("browser-console", { path: consolePath, contentType: "application/json" });
    await testInfo.attach("network", { path: networkPath, contentType: "application/json" });
  },
  projectWorkspace: async ({}, use: (workspace: ProjectWorkspace) => Promise<void>, testInfo: any) => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), "scistudio-e2e-"));
    const imagePath = path.join(root, "data", "raw", "synthetic-fluorescence.png");
    const workflowPath = path.join(root, "workflows", "minimal-image-threshold-save.yaml");
    const snapshotPath = testInfo.outputPath("project-snapshot.json");

    await createSyntheticFluorescencePng(imagePath);
    await writeMinimalImageWorkflowFixture(workflowPath, {
      inputImagePath: imagePath,
      outputImagePath: path.join(root, "data", "artifacts", "threshold-mask.png"),
    });

    await use({ root, imagePath, workflowPath, snapshotPath });
    await snapshotProject(root, snapshotPath);
    await testInfo.attach("project-snapshot", { path: snapshotPath, contentType: "application/json" });
  },
});

export { expect };

export async function createProject(request: any, workspace: ProjectWorkspace): Promise<{
  id: string;
  name: string;
  path: string;
}> {
  const response = await request.post("/api/projects/", {
    data: {
      name: path.basename(workspace.root),
      description: "SciStudio E2E isolated project fixture",
      path: workspace.root,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as { id: string; name: string; path: string };
}
