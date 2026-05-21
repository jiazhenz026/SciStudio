import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

function findPlaywrightPackage() {
  const binDirs = (process.env.PATH ?? "").split(path.delimiter);
  for (const binDir of binDirs) {
    const candidate = path.resolve(binDir, "..", "@playwright", "test");
    if (fs.existsSync(path.join(candidate, "cli.js"))) {
      return candidate;
    }
  }
  throw new Error("Unable to locate @playwright/test from npm exec PATH.");
}

const packageRoot = findPlaywrightPackage();
const cliPath = path.join(packageRoot, "cli.js");
const testModule = pathToFileURL(path.join(packageRoot, "index.mjs")).href;

const child = spawn(process.execPath, [cliPath, ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    PLAYWRIGHT_TEST_MODULE: testModule,
  },
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
