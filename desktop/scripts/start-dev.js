const { spawn } = require("node:child_process");
const path = require("node:path");
const { npmSpawnArgs } = require("./npm-spawn");

delete process.env.ELECTRON_RUN_AS_NODE;

const repoRoot = path.resolve(__dirname, "..", "..");
const frontendUrl = process.env.SCISTUDIO_DESKTOP_FRONTEND_URL || "http://127.0.0.1:5173";
const runtimePort = process.env.SCISTUDIO_DESKTOP_RUNTIME_PORT || "8000";
const apiProxyTarget = process.env.SCISTUDIO_API_PROXY || `http://127.0.0.1:${runtimePort}`;

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

// #2093: npmSpawnArgs decides command/args/shell per platform so the Windows
// npm.cmd shim is reachable without tripping EINVAL or DEP0190.
const viteSpawn = npmSpawnArgs(process.platform, [
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
const vite = spawnChild(viteSpawn.command, viteSpawn.args, {
  shell: viteSpawn.shell,
  env: {
    ...process.env,
    SCISTUDIO_API_PROXY: apiProxyTarget,
  },
});

const electronSpawn = npmSpawnArgs(process.platform, ["--prefix", "desktop", "run", "start"]);
const electron = spawnChild(
  electronSpawn.command,
  electronSpawn.args,
  {
    shell: electronSpawn.shell,
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
