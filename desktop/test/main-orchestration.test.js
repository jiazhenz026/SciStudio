"use strict";

// Behavioural tests for the desktop/main.js orchestration (#2280, AU1 P2-4).
//
// The decisions are pure and unit tested in background-mode.test.js; this file
// tests what main.js DOES with them: which windows exist, what the tray says,
// when the shell is vouched for, when the loader's boot marker is released,
// whether a relaunch waits for the backend, and when the app quits. Each
// scenario in harness/run-scenario.js drives the real main.js in a process of
// its own, with a stubbed `electron` and a Node fake backend; nothing here
// needs Electron, Python, or `npm ci`, so it runs in the Desktop CI job as is.
//
// Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");

const { SCENARIOS } = require("./harness/run-scenario");

const RUNNER = path.join(__dirname, "harness", "run-scenario.js");

function runScenario(name) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [RUNNER, name], {
      cwd: path.join(__dirname, ".."),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.on("close", (code) => resolve({ code, output }));
  });
}

for (const [name, spec] of Object.entries(SCENARIOS)) {
  test(`main.js: ${spec.title}`, { timeout: 90000 }, async () => {
    const { code, output } = await runScenario(name);
    const tail = output.split(/\r?\n/).slice(-40).join("\n");
    assert.equal(code, 0, `scenario "${name}" failed:\n${tail}`);
  });
}
