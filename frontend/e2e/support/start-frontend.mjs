import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const frontendDir = process.cwd();
const artifactDir = path.resolve(process.env.SCISTUDIO_E2E_ARTIFACT_DIR ?? path.join(frontendDir, ".e2e-artifacts"));
const logsDir = path.join(artifactDir, "service-logs");
const frontendPort = process.env.SCISTUDIO_E2E_FRONTEND_PORT ?? "5173";

fs.mkdirSync(logsDir, { recursive: true });
const log = fs.createWriteStream(path.join(logsDir, "frontend.log"), { flags: "a" });
const viteCli = path.join(frontendDir, "node_modules", "vite", "bin", "vite.js");

function cleanEnv(source) {
  return Object.fromEntries(Object.entries(source).filter(([key, value]) => key && !key.startsWith("=") && value !== undefined));
}

const child = spawn(process.execPath, [viteCli, "--host", "127.0.0.1", "--port", frontendPort], {
  cwd: frontendDir,
  env: cleanEnv(process.env),
  stdio: ["ignore", "pipe", "pipe"],
});

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
