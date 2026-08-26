"use strict";

// What "this shell build is good" is allowed to mean (issue #2179).
//
// `recordKnownGood` clears the loader's crash-loop marker and fixes the current
// build as the rollback target. It used to fire the moment the backend answered
// HTTP readiness -- but that probe validates the **Python runtime**, while the
// call vouches for the **Electron shell**. They are two halves of one OTA
// snapshot and they fail independently.
//
// Everything the shell does happens after that point: the window is created,
// the preload runs, the renderer paints, the menu is built. A patch that broke
// any of it was still recorded as good, so the quarantine never engaged, the
// loader never fell back, and the next launch loaded the same broken build.
// Found while reviewing #2171, whose sandboxed preload gains a relative
// `require` that Electron cannot resolve -- `window.scistudioDesktop` vanishes
// and the backend answers anyway.
//
// These are source-level assertions for the same reason bootstrap.test.js's
// are: main.js `require("electron")`, which only resolves inside a real
// Electron process. They are aimed at the specific regressions that would be
// silent in production rather than at coverage.
//
// Run with: npm --prefix desktop test   (uses the Node built-in test runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const main = fs.readFileSync(path.join(__dirname, "..", "main.js"), "utf8");

// Comments describe the very thing these tests forbid, so scan code only.
const code = main
  .split("\n")
  .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
  .join("\n");

test("readiness alone no longer records the shell as known-good", () => {
  // The regression this guards is a one-line move back: putting the call next
  // to waitForHttpReady again restores exactly the blind spot.
  const readyAt = code.indexOf("await waitForHttpReady");
  // lastIndexOf: `function createWindow(url)` is declared earlier in the file.
  const windowAt = code.lastIndexOf("createWindow(url);");
  assert.ok(readyAt > 0 && windowAt > readyAt, "the boot path changed shape");
  const between = code.slice(readyAt, windowAt);
  assert.ok(
    !between.includes("recordKnownGood("),
    "recordKnownGood runs before the window exists, so it cannot know the shell worked",
  );
});

test("the shell is vouched for only after the renderer paints", () => {
  // loadBeforeShowing's callback fires on the rendered path only. The retry and
  // error-page paths deliberately do not: a window showing an error page is not
  // evidence this build is worth rolling back to.
  assert.match(code, /loadBeforeShowing\(mainWindow, url, 0, \(\) => recordKnownGood\(/);
  assert.match(code, /if \(rendered && typeof onRendered === "function"\)/);
});

test("a preload that throws is treated as a shell fault", () => {
  // Electron emits this and nothing used to listen. The main window is
  // sandboxed, so its preload gets a restricted `require`; a relative import
  // added by a patch aborts it before contextBridge.exposeInMainWorld.
  assert.match(code, /webContents\.on\("preload-error"/);
  assert.match(code, /noteShellFault\(/);
});

test("recordKnownGood refuses while a fault stands", () => {
  // Without this the listener would only log: the marker would still clear and
  // the broken build would still become the rollback target.
  const start = code.indexOf("function recordKnownGood(");
  assert.ok(start > 0, "recordKnownGood is gone");
  const body = code.slice(start, code.indexOf("\n}", start));
  const guard = body.indexOf("if (shellFault)");
  const clear = body.indexOf("clearBootAttempt");
  const write = body.indexOf("knownGoodPath()");
  assert.ok(guard > 0, "recordKnownGood does not check for a shell fault");
  assert.ok(guard < clear, "the fault check must precede clearing the boot marker");
  assert.ok(guard < write, "the fault check must precede writing the known-good build");
});

test("the fault is sticky, so a later success cannot erase an earlier failure", () => {
  // A preload error followed by a successful paint is still a broken shell.
  const start = code.indexOf("function noteShellFault(");
  assert.ok(start > 0, "noteShellFault is gone");
  const body = code.slice(start, code.indexOf("\n}", start));
  assert.match(body, /if \(shellFault\)\s*\{\s*return;/);
});

test("the main window is still sandboxed", () => {
  // The premise of the preload-error guard. If sandbox were turned off the
  // relative-require failure would disappear along with the isolation that
  // makes it worth having.
  const at = code.indexOf("preload: path.join(__dirname");
  assert.ok(at > 0, "the main window no longer sets a preload");
  const prefs = code.slice(at - 400, at);
  assert.match(prefs, /sandbox: true/);
  assert.match(prefs, /contextIsolation: true/);
});
