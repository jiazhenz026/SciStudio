"use strict";

// Unit tests for the pure launch-mode logic (desktop/background-mode.js, issue
// #2280, spec adr-055-local-background-runtime). Run with:
// npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const bm = require("../background-mode");

const { MODES, SERVICE_STATUS, STARTUP_SETTINGS } = bm;
const desktopRoot = path.join(__dirname, "..");
const read = (name) => fs.readFileSync(path.join(desktopRoot, name), "utf8");
const { spawn } = require("node:child_process");

// --------------------------------------------------------------------------- //
// The remembered choice (owner decision 1).
// --------------------------------------------------------------------------- //

test("parseModePreference: nothing remembered means ask at launch", () => {
  for (const record of [null, undefined, "desktop", 7, {}]) {
    assert.deepEqual(bm.parseModePreference(record), { mode: null, askAtLaunch: true });
  }
});

test("parseModePreference: a remembered 'don't ask again' choice is honoured", () => {
  assert.deepEqual(bm.parseModePreference({ mode: "desktop", askAtLaunch: false }), {
    mode: MODES.DESKTOP,
    askAtLaunch: false
  });
  assert.deepEqual(bm.parseModePreference({ mode: "external-ai", askAtLaunch: false }), {
    mode: MODES.EXTERNAL_AI,
    askAtLaunch: false
  });
});

test("parseModePreference: a last pick without 'don't ask again' still asks", () => {
  assert.deepEqual(bm.parseModePreference({ mode: "external-ai" }), {
    mode: MODES.EXTERNAL_AI,
    askAtLaunch: true
  });
});

test("parseModePreference: a corrupt mode can never lock the user out of the picker", () => {
  assert.deepEqual(bm.parseModePreference({ mode: "headless", askAtLaunch: false }), {
    mode: null,
    askAtLaunch: true
  });
});

test("serializeModePreference: writes a versioned record that reads back unchanged", () => {
  const written = bm.serializeModePreference({ mode: "external-ai", askAtLaunch: false });
  assert.deepEqual(written, { version: 1, mode: "external-ai", askAtLaunch: false });
  assert.deepEqual(bm.parseModePreference(JSON.parse(JSON.stringify(written))), {
    mode: MODES.EXTERNAL_AI,
    askAtLaunch: false
  });
});

test("parseModePick: accepts only a known mode", () => {
  assert.deepEqual(bm.parseModePick({ mode: "desktop", remember: true }), {
    mode: MODES.DESKTOP,
    remember: true
  });
  assert.deepEqual(bm.parseModePick({ mode: "external-ai" }), {
    mode: MODES.EXTERNAL_AI,
    remember: false
  });
  assert.equal(bm.parseModePick({ mode: "other", remember: true }), null);
  assert.equal(bm.parseModePick(undefined), null);
  assert.equal(bm.parseModePick("desktop"), null);
});

test("preferenceAfterPick: the pick becomes the preselection; remember stops the picker", () => {
  assert.deepEqual(bm.preferenceAfterPick({ mode: MODES.EXTERNAL_AI, remember: false }), {
    mode: MODES.EXTERNAL_AI,
    askAtLaunch: true
  });
  assert.deepEqual(bm.preferenceAfterPick({ mode: MODES.DESKTOP, remember: true }), {
    mode: MODES.DESKTOP,
    askAtLaunch: false
  });
});

test("startupSettingOf: what the Startup Mode menus show as checked", () => {
  assert.equal(bm.startupSettingOf(null), STARTUP_SETTINGS.ASK);
  assert.equal(bm.startupSettingOf({ mode: "desktop", askAtLaunch: true }), STARTUP_SETTINGS.ASK);
  assert.equal(bm.startupSettingOf({ mode: "desktop", askAtLaunch: false }), STARTUP_SETTINGS.DESKTOP);
  assert.equal(
    bm.startupSettingOf({ mode: "external-ai", askAtLaunch: false }),
    STARTUP_SETTINGS.EXTERNAL_AI
  );
});

test("applyStartupSetting: the remembered choice stays changeable after 'don't ask again'", () => {
  const remembered = { mode: MODES.EXTERNAL_AI, askAtLaunch: false };
  // Back to the picker, keeping the last mode preselected.
  assert.deepEqual(bm.applyStartupSetting(remembered, "ask"), {
    mode: MODES.EXTERNAL_AI,
    askAtLaunch: true
  });
  // Switch the fixed mode.
  assert.deepEqual(bm.applyStartupSetting(remembered, "desktop"), {
    mode: MODES.DESKTOP,
    askAtLaunch: false
  });
  // A bogus setting changes nothing.
  assert.deepEqual(bm.applyStartupSetting(remembered, "nonsense"), remembered);
});

// --------------------------------------------------------------------------- //
// Startup resolution and relaunch carry-over (owner decisions 1 and 5).
// --------------------------------------------------------------------------- //

test("resolveStartupMode: a first launch asks, with desktop preselected", () => {
  assert.deepEqual(bm.resolveStartupMode({ argvMode: null, preference: null }), {
    kind: "picker",
    suggested: MODES.DESKTOP
  });
});

test("resolveStartupMode: the last pick is preselected when the user asks every launch", () => {
  assert.deepEqual(
    bm.resolveStartupMode({ preference: { mode: "external-ai", askAtLaunch: true } }),
    { kind: "picker", suggested: MODES.EXTERNAL_AI }
  );
});

test("resolveStartupMode: a remembered choice skips the picker", () => {
  assert.deepEqual(
    bm.resolveStartupMode({ preference: { mode: "external-ai", askAtLaunch: false } }),
    { kind: "mode", mode: MODES.EXTERNAL_AI, source: "remembered" }
  );
});

test("resolveStartupMode: a relaunch comes back in its mode without asking", () => {
  // The user asks at every launch but picked external AI this time; an OTA
  // relaunch must not strand the background service at a picker.
  assert.deepEqual(
    bm.resolveStartupMode({
      argvMode: "external-ai",
      preference: { mode: "external-ai", askAtLaunch: true }
    }),
    { kind: "mode", mode: MODES.EXTERNAL_AI, source: "argv" }
  );
  // It also beats a remembered choice for the other mode.
  assert.deepEqual(
    bm.resolveStartupMode({ argvMode: "desktop", preference: { mode: "external-ai", askAtLaunch: false } }),
    { kind: "mode", mode: MODES.DESKTOP, source: "argv" }
  );
});

test("parseLaunchModeArg: reads the flag, last one wins, junk is ignored", () => {
  assert.equal(bm.parseLaunchModeArg(["app.exe"]), null);
  assert.equal(bm.parseLaunchModeArg(["app.exe", "--scistudio-launch-mode=external-ai"]), MODES.EXTERNAL_AI);
  assert.equal(
    bm.parseLaunchModeArg(["app.exe", "--scistudio-launch-mode=desktop", "--scistudio-launch-mode=external-ai"]),
    MODES.EXTERNAL_AI
  );
  assert.equal(bm.parseLaunchModeArg(["app.exe", "--scistudio-launch-mode=daemon"]), null);
  assert.equal(bm.parseLaunchModeArg(undefined), null);
});

test("relaunchArgs: keeps Electron's default args and replaces any earlier mode flag", () => {
  // Packaged: argv[0] is the executable, which app.relaunch adds itself.
  assert.deepEqual(
    bm.relaunchArgs(["C:\\SciStudio\\SciStudio.exe", "--scistudio-launch-mode=desktop", "--x"], "external-ai"),
    ["--x", "--scistudio-launch-mode=external-ai"]
  );
  // Dev: `electron <desktop dir>` keeps its app path.
  assert.deepEqual(bm.relaunchArgs(["electron", "/repo/desktop"], "desktop"), [
    "/repo/desktop",
    "--scistudio-launch-mode=desktop"
  ]);
  // No mode yet (the picker never answered): keep Electron's default.
  assert.equal(bm.relaunchArgs(["SciStudio.exe"], null), null);
});

test("relaunchArgs + resolveStartupMode: a relaunch round-trips the running mode", () => {
  for (const mode of bm.MODE_VALUES) {
    const args = bm.relaunchArgs(["SciStudio.exe"], mode);
    const next = bm.resolveStartupMode({
      argvMode: bm.parseLaunchModeArg(["SciStudio.exe", ...args]),
      preference: { mode: null, askAtLaunch: true }
    });
    assert.deepEqual(next, { kind: "mode", mode, source: "argv" });
  }
});

// --------------------------------------------------------------------------- //
// One backend per machine (owner decision 4).
// --------------------------------------------------------------------------- //

test("requestedModeForSecondLaunch: only a flag or a remembered choice expresses a mode", () => {
  assert.equal(bm.requestedModeForSecondLaunch({ argvMode: null, preference: null }), null);
  assert.equal(
    bm.requestedModeForSecondLaunch({ preference: { mode: "desktop", askAtLaunch: true } }),
    null
  );
  assert.equal(
    bm.requestedModeForSecondLaunch({ preference: { mode: "desktop", askAtLaunch: false } }),
    MODES.DESKTOP
  );
  assert.equal(
    bm.requestedModeForSecondLaunch({
      argvMode: "external-ai",
      preference: { mode: "desktop", askAtLaunch: false }
    }),
    MODES.EXTERNAL_AI
  );
});

test("requestedModeFromSecondInstance: additionalData first, then the second process's argv", () => {
  assert.equal(
    bm.requestedModeFromSecondInstance({ argv: [], additionalData: { requestedMode: "desktop" } }),
    MODES.DESKTOP
  );
  assert.equal(
    bm.requestedModeFromSecondInstance({
      argv: ["SciStudio.exe", "--scistudio-launch-mode=external-ai"],
      additionalData: { requestedMode: null }
    }),
    MODES.EXTERNAL_AI
  );
  assert.equal(bm.requestedModeFromSecondInstance({ argv: ["SciStudio.exe"], additionalData: null }), null);
  assert.equal(bm.requestedModeFromSecondInstance({}), null);
});

test("routeSecondInstance: external-AI mode reveals the connection window or attaches a desktop window", () => {
  const route = (requestedMode, mainWindowOpen = false) =>
    bm.routeSecondInstance({ runningMode: MODES.EXTERNAL_AI, requestedMode, mainWindowOpen });
  // No preference and an explicit external-AI request both reveal the
  // connection window -- also the Linux path when no tray host exists.
  assert.equal(route(null), "show-connection-window");
  assert.equal(route(MODES.EXTERNAL_AI), "show-connection-window");
  assert.equal(route(MODES.EXTERNAL_AI, true), "show-connection-window");
  // Desktop requested: attach a window to the running backend, or reveal the
  // one that is already attached.
  assert.equal(route(MODES.DESKTOP), "attach-desktop-window");
  assert.equal(route(MODES.DESKTOP, true), "focus-main-window");
});

test("routeSecondInstance: desktop mode keeps today's behaviour unless external AI is asked for", () => {
  const route = (requestedMode, mainWindowOpen) =>
    bm.routeSecondInstance({ runningMode: MODES.DESKTOP, requestedMode, mainWindowOpen });
  assert.equal(route(null, true), "focus-main-window");
  assert.equal(route(MODES.DESKTOP, true), "focus-main-window");
  // Still starting: nothing but the splash to show.
  assert.equal(route(null, false), "focus-splash");
  // Never a second backend: the running one gets the tray and connection window.
  assert.equal(route(MODES.EXTERNAL_AI, true), "promote-to-external-ai");
});

test("routeSecondInstance: while the first instance is still at its picker", () => {
  assert.equal(bm.routeSecondInstance({ runningMode: null, requestedMode: MODES.EXTERNAL_AI }), "focus-splash");
  assert.equal(bm.routeSecondInstance({}), "focus-splash");
});

test("routeActivate: macOS reopening routes like a second launch (AU1 P3-6 / AU2 P3-5)", () => {
  // External AI running: a remembered desktop choice attaches a desktop window,
  // anything else reveals the connection window.
  assert.equal(
    bm.routeActivate({ runningMode: MODES.EXTERNAL_AI, requestedMode: MODES.DESKTOP }),
    "attach-desktop-window"
  );
  assert.equal(bm.routeActivate({ runningMode: MODES.EXTERNAL_AI, requestedMode: null }), "show-connection-window");
  // An open desktop window is simply revealed, in either mode.
  assert.equal(
    bm.routeActivate({ runningMode: MODES.EXTERNAL_AI, requestedMode: MODES.DESKTOP, mainWindowOpen: true }),
    "focus-main-window"
  );
  assert.equal(bm.routeActivate({ runningMode: MODES.DESKTOP, mainWindowOpen: true }), "focus-main-window");
});

test("routeActivate: a dock click never switches a desktop session to external AI", () => {
  assert.equal(
    bm.routeActivate({ runningMode: MODES.DESKTOP, requestedMode: MODES.EXTERNAL_AI, mainWindowOpen: false }),
    "focus-splash"
  );
  assert.equal(bm.routeActivate({ runningMode: null }), "focus-splash");
});

// --------------------------------------------------------------------------- //
// Process liveness and the loader's boot marker.
// --------------------------------------------------------------------------- //

test("isChildRunning: judged by the exit status, not by `killed` (AU1/AU2 P2-2)", () => {
  assert.equal(bm.isChildRunning({ killed: true, exitCode: null, signalCode: null }), true, "sent is not exited");
  assert.equal(bm.isChildRunning({ killed: false, exitCode: 0, signalCode: null }), false);
  assert.equal(bm.isChildRunning({ killed: true, exitCode: null, signalCode: "SIGKILL" }), false);
  assert.equal(bm.isChildRunning(null), false);
});

test("Node marks a child `killed` before it has exited, which is why liveness uses the exit status", async () => {
  const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 30000)"], { stdio: "ignore" });
  await new Promise((resolve) => child.once("spawn", resolve));
  child.kill("SIGTERM");
  assert.equal(child.killed, true, "Node sets killed as soon as the signal is sent");
  assert.equal(bm.isChildRunning(child), true, "the child has not exited yet");
  await new Promise((resolve) => child.once("exit", resolve));
  assert.equal(bm.isChildRunning(child), false);
});

test("releasesBootMarkerOnQuit: only after the picker rendered, and never over a shell fault (AU1 P2-1)", () => {
  assert.equal(bm.releasesBootMarkerOnQuit({ pickerRendered: true, shellFaulted: false }), true);
  assert.equal(bm.releasesBootMarkerOnQuit({ pickerRendered: false, shellFaulted: false }), false, "failed before the picker");
  assert.equal(bm.releasesBootMarkerOnQuit({ pickerRendered: true, shellFaulted: true }), false, "#2179 fault stands");
  assert.equal(bm.releasesBootMarkerOnQuit({}), false);
});

// --------------------------------------------------------------------------- //
// Window-closed lifetime per mode. The verdict is the same on every platform;
// what does differ by platform is exercised in main-orchestration.test.js.
// --------------------------------------------------------------------------- //

const LIVE = [
  SERVICE_STATUS.STARTING,
  SERVICE_STATUS.RUNNING,
  SERVICE_STATUS.UNRESPONSIVE,
  SERVICE_STATUS.STOPPING
];
const DOWN = [SERVICE_STATUS.STOPPED, SERVICE_STATUS.CRASHED, SERVICE_STATUS.FAILED];

test("windowAllClosedAction: desktop mode quits, as it always has", () => {
  for (const status of Object.values(SERVICE_STATUS)) {
    assert.equal(bm.windowAllClosedAction({ mode: MODES.DESKTOP, status }), "quit", status);
  }
  // Still at the picker: closing the splash is a quit.
  assert.equal(bm.windowAllClosedAction({ mode: null, status: SERVICE_STATUS.STARTING }), "quit");
});

test("windowAllClosedAction: external-AI mode stays resident while it owns a live backend", () => {
  for (const status of LIVE) {
    assert.equal(bm.windowAllClosedAction({ mode: MODES.EXTERNAL_AI, status }), "stay", status);
  }
});

test("windowAllClosedAction: external-AI mode quits once there is no backend left to own", () => {
  for (const status of DOWN) {
    assert.equal(bm.windowAllClosedAction({ mode: MODES.EXTERNAL_AI, status }), "quit", status);
  }
});

test("windowAllClosedAction takes no platform, so no test can pretend it varies by one (AU2 P3-4)", () => {
  // It used to accept `platform` and discard it, which made per-platform loops
  // over it unable to fail.
  const signature = bm.windowAllClosedAction.toString().split(")")[0];
  assert.doesNotMatch(signature, /platform/);
});

test("quitOnServiceChange: with no window open, a service that goes down quits (owner decision 2026-09-11)", () => {
  for (const status of DOWN) {
    assert.equal(bm.quitOnServiceChange({ mode: MODES.EXTERNAL_AI, status, openWindowCount: 0 }), true, status);
  }
  for (const status of LIVE) {
    assert.equal(bm.quitOnServiceChange({ mode: MODES.EXTERNAL_AI, status, openWindowCount: 0 }), false, status);
  }
});

test("quitOnServiceChange: an open window keeps the app and shows the state with Restart", () => {
  for (const status of Object.values(SERVICE_STATUS)) {
    assert.equal(bm.quitOnServiceChange({ mode: MODES.EXTERNAL_AI, status, openWindowCount: 1 }), false, status);
  }
});

test("quitOnServiceChange: desktop mode never quits from a status change; its windows decide", () => {
  for (const status of Object.values(SERVICE_STATUS)) {
    assert.equal(bm.quitOnServiceChange({ mode: MODES.DESKTOP, status, openWindowCount: 0 }), false, status);
    assert.equal(bm.quitOnServiceChange({ mode: null, status, openWindowCount: 0 }), false, status);
  }
});

// --------------------------------------------------------------------------- //
// Service status and the connection window view.
// --------------------------------------------------------------------------- //

test("connectionAddress: the ready origin with explicit AI presentation", () => {
  assert.equal(bm.connectionAddress("http://127.0.0.1:51234/"), "http://127.0.0.1:51234/?ui=ai");
  assert.equal(bm.connectionAddress("http://127.0.0.1:8123/index.html?x=1"), "http://127.0.0.1:8123/?ui=ai");
  assert.equal(bm.connectionAddress("http://127.0.0.1/"), null);
  assert.equal(bm.connectionAddress("not a url"), null);
  assert.equal(bm.connectionAddress(null), null);
});

test("statusAfterExit: explicit stop, crash, and a start that never got going", () => {
  assert.equal(bm.statusAfterExit({ status: SERVICE_STATUS.STOPPING, stopRequested: true }), SERVICE_STATUS.STOPPED);
  assert.equal(bm.statusAfterExit({ status: SERVICE_STATUS.RUNNING, stopRequested: false }), SERVICE_STATUS.CRASHED);
  assert.equal(bm.statusAfterExit({ status: SERVICE_STATUS.UNRESPONSIVE }), SERVICE_STATUS.CRASHED);
  assert.equal(bm.statusAfterExit({ status: SERVICE_STATUS.STARTING }), SERVICE_STATUS.FAILED);
});

test("statusAfterProbe: only a service believed to be up is re-judged", () => {
  assert.equal(bm.statusAfterProbe({ status: SERVICE_STATUS.RUNNING, probeOk: false }), SERVICE_STATUS.UNRESPONSIVE);
  assert.equal(bm.statusAfterProbe({ status: SERVICE_STATUS.UNRESPONSIVE, probeOk: true }), SERVICE_STATUS.RUNNING);
  assert.equal(bm.statusAfterProbe({ status: SERVICE_STATUS.RUNNING, probeOk: true }), SERVICE_STATUS.RUNNING);
  for (const status of [SERVICE_STATUS.STARTING, SERVICE_STATUS.STOPPING, SERVICE_STATUS.STOPPED, SERVICE_STATUS.CRASHED]) {
    assert.equal(bm.statusAfterProbe({ status, probeOk: true }), status);
    assert.equal(bm.statusAfterProbe({ status, probeOk: false }), status);
  }
});

test("connectionView: the address is shown only once the service is running", () => {
  const address = "http://127.0.0.1:51234";
  for (const status of Object.values(SERVICE_STATUS)) {
    const view = bm.connectionView({ status, address });
    if (status === SERVICE_STATUS.RUNNING) {
      assert.equal(view.address, address);
      assert.equal(view.canCopy, true);
      assert.equal(view.canOpenDesktop, true);
    } else {
      assert.equal(view.address, null, status);
      assert.equal(view.canCopy, false, status);
      assert.equal(view.canOpenDesktop, false, status);
    }
  }
});

test("connectionView: stop while up, restart once down, with the failure detail", () => {
  const running = bm.connectionView({ status: SERVICE_STATUS.RUNNING, address: "http://127.0.0.1:1" });
  assert.equal(running.canStop, true);
  assert.equal(running.canRestart, false);

  const unresponsive = bm.connectionView({ status: SERVICE_STATUS.UNRESPONSIVE, detail: "busy" });
  assert.equal(unresponsive.canStop, true);
  assert.equal(unresponsive.detail, "busy");

  for (const status of [SERVICE_STATUS.STOPPED, SERVICE_STATUS.CRASHED, SERVICE_STATUS.FAILED]) {
    const view = bm.connectionView({ status, detail: "exit code 1" });
    assert.equal(view.canStop, false, status);
    assert.equal(view.canRestart, true, status);
  }
  assert.equal(bm.connectionView({ status: SERVICE_STATUS.CRASHED, detail: "x" }).detail, "x");

  const starting = bm.connectionView({ status: SERVICE_STATUS.STARTING, detail: "stale" });
  assert.equal(starting.canStop, false);
  assert.equal(starting.canRestart, false);
  assert.equal(starting.detail, null);
});

test("connectionView: labels, unknown status and the startup setting", () => {
  assert.equal(bm.connectionView({ status: SERVICE_STATUS.CRASHED }).label, "Stopped unexpectedly");
  const unknown = bm.connectionView({ status: "weird" });
  assert.equal(unknown.status, SERVICE_STATUS.STARTING);
  assert.equal(unknown.startupSetting, STARTUP_SETTINGS.ASK);
  assert.equal(
    bm.connectionView({ status: SERVICE_STATUS.RUNNING, startupSetting: "external-ai" }).startupSetting,
    STARTUP_SETTINGS.EXTERNAL_AI
  );
});

// --------------------------------------------------------------------------- //
// Contracts across the files that cannot import this module.
// --------------------------------------------------------------------------- //

test("connection-preload.js declares the same channel names as background-mode.js", () => {
  const preload = read("connection-preload.js");
  const action = /const CONNECTION_ACTION_CHANNEL = "([^"]+)";/.exec(preload);
  const state = /const CONNECTION_STATE_CHANNEL = "([^"]+)";/.exec(preload);
  assert.ok(action && state, "both channel literals must exist");
  assert.equal(action[1], bm.CONNECTION_ACTION_CHANNEL);
  assert.equal(state[1], bm.CONNECTION_STATE_CHANNEL);
});

test("connection-preload.js requires nothing but electron (it is sandboxed)", () => {
  // A relative require in a sandboxed preload aborts it before the bridge is
  // exposed (#2179), leaving the connection window dead.
  const requires = [...read("connection-preload.js").matchAll(/require\((["'])([^"']+)\1\)/g)].map((m) => m[2]);
  assert.deepEqual(requires, ["electron"]);
});

test("connection.html only sends actions the main process accepts", () => {
  const html = read("connection.html");
  const sent = [...html.matchAll(/act\("([a-z-]+)"/g)].map((m) => m[1]);
  assert.ok(sent.length >= 7, "expected the page to wire its buttons");
  for (const action of sent) {
    assert.ok(bm.CONNECTION_ACTIONS.includes(action), `unknown connection action "${action}"`);
  }
  // Every startup option the page offers is a setting the main process knows.
  const options = [...html.matchAll(/<option value="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(options.sort(), [...bm.STARTUP_SETTING_VALUES].sort());
});

test("splash.html offers exactly the two launch modes and the picker main.js calls", () => {
  const html = read("splash.html");
  const modes = [...html.matchAll(/data-mode="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(modes.sort(), [...bm.MODE_VALUES].sort());
  assert.match(html, /window\.__scistudioSplashPickMode = /);
  assert.match(read("main.js"), /window\.__scistudioSplashPickMode\(/);
  // The picker is clickable only outside the frameless window's drag region.
  assert.match(html, /#picker \{[^}]*-webkit-app-region: no-drag/);
});
