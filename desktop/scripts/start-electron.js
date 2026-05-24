const path = require("node:path");
const { spawn } = require("node:child_process");

delete process.env.ELECTRON_RUN_AS_NODE;

const electron = require("electron");
const child = spawn(electron, [path.resolve(__dirname, "..")], {
  env: process.env,
  stdio: "inherit",
  windowsHide: false,
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
