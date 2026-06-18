const { spawn } = require("node:child_process");
const path = require("node:path");

delete process.env.ELECTRON_RUN_AS_NODE;

const repoRoot = path.resolve(__dirname, "..", "..");
const frontendUrl = process.env.SCISTUDIO_DESKTOP_FRONTEND_URL || "http://127.0.0.1:5173";
const runtimePort = process.env.SCISTUDIO_DESKTOP_RUNTIME_PORT || "8000";
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

function spawnChild(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: repoRoot,
    stdio: "inherit",
    windowsHide: true,
    ...options,
  });
  child.on("error", (error) => {
    console.error(`[scistudio-dev] ${command} failed:`, error);
    process.exitCode = 1;
  });
  return child;
}

const vite = spawnChild(npmCommand, [
  "--prefix",
  "frontend",
  "run",
  "dev",
  "--",
  "--host",
  "127.0.0.1",
  "--port",
  "5173",
]);

const electron = spawnChild(
  npmCommand,
  ["--prefix", "desktop", "run", "start"],
  {
    env: {
      ...process.env,
      SCISTUDIO_DESKTOP_FRONTEND_URL: frontendUrl,
      SCISTUDIO_DESKTOP_RUNTIME_PORT: runtimePort,
    },
  },
);

function stopAll() {
  for (const child of [electron, vite]) {
    if (!child.killed) {
      child.kill();
    }
  }
}

electron.on("exit", (code) => {
  stopAll();
  process.exit(code ?? 0);
});

process.on("SIGINT", () => {
  stopAll();
  process.exit(130);
});
