import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendDir, "..");
const artifactDir = process.env.SCISTUDIO_E2E_ARTIFACT_DIR
  ? path.resolve(process.env.SCISTUDIO_E2E_ARTIFACT_DIR)
  : path.resolve(frontendDir, ".e2e-artifacts");
const backendPort = Number(process.env.SCISTUDIO_E2E_BACKEND_PORT ?? 8000);
const frontendPort = Number(process.env.SCISTUDIO_E2E_FRONTEND_PORT ?? 5173);
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default {
  testDir: path.join(frontendDir, "e2e"),
  testMatch: ["**/*.e2e.ts"],
  outputDir: path.join(artifactDir, "test-results"),
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(artifactDir, "playwright-report"), open: "never" }],
    ["json", { outputFile: path.join(artifactDir, "results.json") }],
    ["junit", { outputFile: path.join(artifactDir, "results.xml") }],
  ],
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: "node e2e/support/start-backend.mjs",
      cwd: frontendDir,
      env: {
        SCISTUDIO_E2E_ARTIFACT_DIR: artifactDir,
        SCISTUDIO_E2E_BACKEND_PORT: String(backendPort),
      },
      url: `http://127.0.0.1:${backendPort}/api/projects/`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "node e2e/support/start-frontend.mjs",
      cwd: frontendDir,
      env: {
        SCISTUDIO_E2E_ARTIFACT_DIR: artifactDir,
        SCISTUDIO_E2E_BACKEND_PORT: String(backendPort),
        SCISTUDIO_E2E_FRONTEND_PORT: String(frontendPort),
      },
      url: frontendUrl,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        viewport: { width: 1280, height: 720 },
      },
    },
  ],
};
