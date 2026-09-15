import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { build } from "vite";
import react from "@vitejs/plugin-react";

const root = path.resolve(import.meta.dirname, "..");
const python = process.env.PANEL_TEST_PYTHON ?? "python";
if (process.env.TEST_WORKER_INDEX === undefined)
  await build({
    configFile: false,
    root: import.meta.dirname,
    plugins: [react()],
    build: {
      outDir: path.join(root, ".workflow/local/panel-browser-build"),
      emptyOutDir: true,
      rollupOptions: {
        input: path.join(import.meta.dirname, "e2e/helpers/panel-browser-host.html"),
      },
    },
  });
const deployments = [
  { name: "root-default", port: 8191, prefix: "", replacement: false },
  { name: "root-replacement", port: 8192, prefix: "", replacement: true },
  { name: "prefix-default", port: 8193, prefix: "/user/browser/scistudio", replacement: false },
  { name: "prefix-replacement", port: 8194, prefix: "/user/browser/scistudio", replacement: true },
];
export default defineConfig({
  testDir: "./e2e/specs",
  testMatch: "panel-runtime.spec.ts",
  timeout: 30000,
  fullyParallel: false,
  workers: 1,
  outputDir: "../.workflow/local/panel-browser-results",
  reporter: [["list"]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: deployments.map(({ port, prefix, replacement }) => ({
    command: `"${python}" e2e/helpers/panel-backend.py --port ${port} --prefix "${prefix}" ${replacement ? "--replacement" : ""}`,
    env: { PYTHONPATH: `${root}/src:${root}` },
    url: `http://127.0.0.1:${port}${prefix}/__panel_test__/health`,
    reuseExistingServer: false,
    timeout: 30000,
  })),
  projects: deployments.map(({ name, port, prefix }) => ({
    name,
    use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${port}${prefix}/` },
  })),
});
