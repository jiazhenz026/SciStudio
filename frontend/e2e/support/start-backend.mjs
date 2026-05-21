import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const frontendDir = process.cwd();
const repoRoot = path.resolve(frontendDir, "..");
const artifactDir = path.resolve(process.env.SCISTUDIO_E2E_ARTIFACT_DIR ?? path.join(frontendDir, ".e2e-artifacts"));
const logsDir = path.join(artifactDir, "service-logs");
const backendPort = process.env.SCISTUDIO_E2E_BACKEND_PORT ?? "8000";

fs.mkdirSync(logsDir, { recursive: true });
const log = fs.createWriteStream(path.join(logsDir, "backend.log"), { flags: "a" });

function cleanEnv(source) {
  return Object.fromEntries(Object.entries(source).filter(([key, value]) => key && !key.startsWith("=") && value !== undefined));
}

const packagePaths = [
  path.join(repoRoot, "src"),
  path.join(repoRoot, "packages", "scistudio-blocks-imaging", "src"),
  path.join(repoRoot, "packages", "scistudio-blocks-srs", "src"),
];
const existingPythonPath = process.env.PYTHONPATH ? [process.env.PYTHONPATH] : [];
const env = {
  ...cleanEnv(process.env),
  PYTHONPATH: [...packagePaths, ...existingPythonPath].join(path.delimiter),
  SCISTUDIO_CORS_ORIGINS: process.env.SCISTUDIO_CORS_ORIGINS ?? "*",
  SCISTUDIO_ENGINE_API_URL: `http://127.0.0.1:${backendPort}`,
  SCISTUDIO_LOG_LEVEL: process.env.SCISTUDIO_LOG_LEVEL ?? "INFO",
};

const child = spawn(
  process.env.PYTHON ?? "python",
  [
    "-m",
    "uvicorn",
    "scistudio.api.app:create_app",
    "--factory",
    "--host",
    "127.0.0.1",
    "--port",
    backendPort,
  ],
  {
    cwd: repoRoot,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  },
);

child.stdout.pipe(log);
child.stderr.pipe(log);
child.stdout.pipe(process.stdout);
child.stderr.pipe(process.stderr);

function shutdown(signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
child.on("exit", (code, signal) => {
  log.end();
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
