"use strict";

// #2280 (AU1 P2-4): behavioural scenarios for the desktop/main.js orchestration.
//
// Each scenario drives the REAL desktop/main.js with a stubbed `electron`
// module (./electron-stub.js) and a fake backend (./fake-backend.js) that
// prints the real ready line and serves HTTP. No Electron app is launched, and
// the only processes touched are the fake backends this runner starts.
//
// main.js keeps module-level state, so every scenario runs in a process of its
// own: desktop/test/main-orchestration.test.js spawns
//   node run-scenario.js <scenario>
// once per scenario and expects exit code 0.

const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const Module = require("node:module");
const os = require("node:os");
const path = require("node:path");

const DESKTOP = path.join(__dirname, "..", "..");
const STUB = path.join(__dirname, "electron-stub.js");
const FAKE_BACKEND = path.join(__dirname, "fake-backend.js");
const PYTHON_SENTINEL = "scistudio-harness-python";
const REAL_PLATFORM = process.platform;
const PATCH_SHELL = Object.freeze({ source: "patch", build: 31 });
const EXTERNAL_AI_ARG = "--scistudio-launch-mode=external-ai";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function makeHarness(spec) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-orchestration-"));
  const userData = path.join(tmp, "userData");
  fs.mkdirSync(path.join(userData, "logs"), { recursive: true });
  const repo = path.join(tmp, "repo");
  fs.mkdirSync(path.join(repo, "src"), { recursive: true });
  const pidFile = path.join(tmp, "pids.txt");

  for (const name of [
    "SCISTUDIO_DESKTOP_RUNTIME_PORT",
    "SCISTUDIO_DESKTOP_FRONTEND_URL",
    "ELECTRON_RUN_AS_NODE",
    "HARNESS_BACKEND_PLAN",
    "HARNESS_IGNORE_SIGTERM",
    "HARNESS_IGNORE_STOP_REQUEST",
    "HARNESS_GRACEFUL_STOP_MS",
    "SCISTUDIO_STOP_ON_STDIN_EOF"
  ]) {
    delete process.env[name];
  }
  process.env.HARNESS_PID_FILE = pidFile;
  const stopLog = path.join(tmp, "stops.txt");
  process.env.HARNESS_STOP_LOG = stopLog;
  process.env.SCISTUDIO_DESKTOP_PYTHON = PYTHON_SENTINEL;
  Object.assign(process.env, spec.env || {});

  // The runtime spawn goes to the Node fake backend; everything else (taskkill)
  // is real. main.js destructures `spawn` at load, so patch before requiring it.
  const realSpawn = childProcess.spawn;
  childProcess.spawn = function spawn(command, args, options) {
    if (command === PYTHON_SENTINEL) {
      return realSpawn(process.execPath, [FAKE_BACKEND, ...(args || [])], options);
    }
    return realSpawn(command, args, options);
  };

  // A backend that ignores SIGTERM. On POSIX this is real: the fake installs a
  // handler. On Windows, Node's kill() always terminates, so the POSIX branch
  // of stopRuntime is taken and SIGTERM is made to do nothing -- after setting
  // `killed`, exactly as Node does for a delivered signal.
  let platform = spec.platform || REAL_PLATFORM;
  if (spec.ignoreSigterm) {
    process.env.HARNESS_IGNORE_SIGTERM = "1";
    if (REAL_PLATFORM === "win32") {
      platform = "linux";
      const { ChildProcess } = childProcess;
      const realKill = ChildProcess.prototype.kill;
      ChildProcess.prototype.kill = function kill(signal) {
        if (signal === undefined || signal === "SIGTERM") {
          this.killed = true;
          return true;
        }
        return realKill.call(this, signal);
      };
    }
  }
  if (platform !== REAL_PLATFORM) {
    Object.defineProperty(process, "platform", { value: platform });
  }

  const originalResolve = Module._resolveFilename;
  Module._resolveFilename = function resolve(request, parent, ...rest) {
    if (request === "electron") {
      return STUB;
    }
    return originalResolve.call(this, request, parent, ...rest);
  };
  const stub = require(STUB);
  stub.state.userData = userData;
  const ota = require(path.join(DESKTOP, "ota.js"));
  const { CONNECTION_ACTION_CHANNEL } = require(path.join(DESKTOP, "background-mode.js"));

  const pids = () => {
    try {
      return fs.readFileSync(pidFile, "utf8").split(/\s+/).filter(Boolean).map(Number);
    } catch {
      return [];
    }
  };
  const alive = (pid) => {
    try {
      process.kill(pid, 0);
      return true;
    } catch (error) {
      return error.code === "EPERM";
    }
  };
  const killPid = (pid) => {
    if (REAL_PLATFORM === "win32") {
      childProcess.spawnSync("taskkill", ["/F", "/PID", String(pid)], { stdio: "ignore" });
      return;
    }
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // already gone
    }
  };
  stub.state.backendAliveProbe = () => pids().some(alive);

  // The frozen loader's crash-loop guard, driven by its own decision functions
  // in desktop/ota.js: the marker is written before a patched shell loads, the
  // host may clear it only for that patch, and the next launch reads it back.
  const shell = spec.patchShell ? PATCH_SHELL : { source: "checkout", build: 0 };
  let marker = ota.shellMarkerAction(null, shell) === "record" ? { build: shell.build } : null;
  const hostCalls = { clearBootAttempt: 0 };
  const hostFacts = {
    baselineVersion: { base: "0.3.4", channel: "alpha", build: 0 },
    resourcesPath: path.join(tmp, "resources"),
    repoRoot: repo,
    appRoot: DESKTOP,
    activeShellBuild: shell.build,
    shellSource: shell.source,
    clearBootAttempt: () => {
      hostCalls.clearBootAttempt += 1;
      if (ota.mayClearShellMarker(shell)) {
        marker = null;
      }
    }
  };

  const live = () => stub.BrowserWindow.getAllWindows();
  const byFile = (name) => live().find((w) => String(w.loaded || "").endsWith(`${path.sep}${name}`));

  const h = {
    stub,
    tmp,
    userData,
    hostCalls,
    pids,
    alive,
    killPid,
    sleep,
    // #2327: "<pid> sigterm" or "<pid> stdin-eof" per graceful stop request.
    stops() {
      try {
        return fs.readFileSync(stopLog, "utf8").split(/\r?\n/).filter(Boolean);
      } catch {
        return [];
      }
    },
    startMain(extraArgv = []) {
      process.argv = [process.execPath, DESKTOP, ...extraArgv];
      require(path.join(DESKTOP, "main.js")).start(hostFacts);
      stub.app.readyResolve();
    },
    connWin: () => byFile("connection.html"),
    splashWin: () => byFile("splash.html"),
    mainWin: () => live().find((w) => w.preloadPath.endsWith(`${path.sep}preload.js`)),
    act(action, payload, sender) {
      return stub.ipcMain.handlers[CONNECTION_ACTION_CHANNEL](
        { sender: sender || h.connWin().webContents },
        action,
        payload
      );
    },
    async status() {
      return h.connWin() ? (await h.act("get-state")).status : null;
    },
    // Reads the tray's status line without any IPC, so it proves nothing on
    // the connection page's behalf.
    trayLabel() {
      const tray = stub.trays[0];
      return tray && tray.menu ? tray.menu.template[0].label : null;
    },
    trayItem(label) {
      return stub.trays[0].menu.template.find((item) => item.label === label);
    },
    pickerAsked: () => stub.state.jsCalls.some((code) => code.includes("window.__scistudioSplashPickMode(")),
    knownGoodWritten: () => fs.existsSync(path.join(userData, "patches", "known-good.json")),
    nextLaunchMarkerAction: () => ota.shellMarkerAction(marker, shell),
    readJson: (name) => JSON.parse(fs.readFileSync(path.join(userData, name), "utf8")),
    writeJson: (name, value) => fs.writeFileSync(path.join(userData, name), JSON.stringify(value)),
    relaunchFromRenderer: () => stub.ipcMain.handlers["scistudio:relaunch"]({}),
    // #2396: point the OTA client at a manifest URL (resources/ota-config.json).
    writeOtaConfig(manifestUrl) {
      fs.mkdirSync(path.join(tmp, "resources"), { recursive: true });
      fs.writeFileSync(
        path.join(tmp, "resources", "ota-config.json"),
        JSON.stringify({ enabled: true, channel: "alpha", manifestUrl })
      );
    },
    // #2396: serve one JSON document on 127.0.0.1; resolves { url(path), close() }.
    serveJson(route, body) {
      const http = require("node:http");
      const server = http.createServer((req, res) => {
        if (req.url === route) {
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify(body));
          return;
        }
        res.writeHead(404);
        res.end();
      });
      return new Promise((resolve) => {
        server.listen(0, "127.0.0.1", () => {
          const { port } = server.address();
          resolve({
            url: (p) => `http://127.0.0.1:${port}${p}`,
            close: () => server.close()
          });
        });
      });
    },
    async until(predicate, ms, label) {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        if (await predicate()) {
          return;
        }
        await sleep(50);
      }
      throw new Error(`timed out after ${ms} ms waiting for: ${label}`);
    },
    async untilRunning(ms = 30000) {
      await h.until(() => String(h.trayLabel() || "").startsWith("Service: Running"), ms, "service running");
    },
    cleanup() {
      for (const pid of pids()) {
        if (alive(pid)) {
          killPid(pid);
        }
      }
      try {
        fs.rmSync(tmp, { recursive: true, force: true });
      } catch {
        // best-effort
      }
    }
  };
  return h;
}

const SCENARIOS = {
  "external-ai-lifecycle": {
    title:
      "external AI: address after readiness, no main window, sender check, stop/restart/crash, attach, relaunch waits",
    async run(h) {
      const { stub } = h;
      stub.state.pick = { mode: "external-ai", remember: false };
      h.startMain();
      await h.untilRunning();
      let view = await h.act("get-state");
      assert.match(view.address, /^http:\/\/127\.0\.0\.1:\d+\/\?ui=ai$/);
      // FR-002 (AU1 M10): external-AI mode never creates the main window.
      assert.equal(h.mainWin(), undefined, "no main window in external-AI mode");
      assert.equal(h.splashWin(), undefined, "the splash closed");
      assert.equal(stub.trays.length, 1);
      assert.equal(h.trayLabel(), `Service: Running at ${view.address}`);
      assert.equal(h.connWin().menuRemoved, true);
      assert.deepEqual(h.readJson("launch-mode.json"), { version: 1, mode: "external-ai", askAtLaunch: true });
      const remembered = h.readJson("runtime-port.json").port;
      assert.equal(view.address, `http://127.0.0.1:${remembered}/?ui=ai`, "the shown address uses the bound port and AI presentation");
      // FR-013: vouched once the connection page proved itself over IPC.
      await h.until(() => h.knownGoodWritten(), 5000, "known-good recorded");

      await h.act("copy-address");
      assert.equal(stub.clipboard.text, view.address);
      // AU1 M8: only the connection window's own webContents is answered.
      const foreign = { id: -1 };
      assert.equal(await h.act("get-state", undefined, foreign), null);
      assert.equal(await h.act("stop", undefined, foreign), null);
      assert.equal(await h.status(), "running", "a foreign sender cannot stop the service");
      assert.equal((await h.act("rm -rf")).status, "running", "unknown actions are ignored");

      // Closing the only window leaves the service running.
      h.connWin().close();
      assert.equal(stub.app.quitCalled, 0, "stays resident");
      // A second launch with no preference reopens the connection window.
      stub.app.emit("second-instance", {}, ["SciStudio"], h.tmp, { requestedMode: null });
      await h.until(() => h.connWin(), 5000, "connection window reopened");
      assert.equal(h.pids().length, 1, "no second backend");

      // Explicit stop through stopRuntime, visibly.
      const first = h.pids()[0];
      await h.act("stop");
      await h.until(async () => (await h.status()) === "stopped", 15000, "stopped");
      await h.until(() => !h.alive(first), 5000, "backend process gone");
      view = await h.act("get-state");
      assert.equal(view.address, null);
      assert.equal(view.canRestart, true);
      assert.equal(stub.app.quitCalled, 0, "a window is open, so a stop does not quit");

      // Restart reuses the readiness chain and the remembered port.
      await h.act("restart");
      await h.until(async () => (await h.status()) === "running", 30000, "restarted");
      assert.equal((await h.act("get-state")).address, `http://127.0.0.1:${remembered}/?ui=ai`);

      // A crash with the window open surfaces with Restart, and does not quit.
      h.killPid(h.pids()[1]);
      await h.until(async () => (await h.status()) === "crashed", 15000, "crashed");
      view = await h.act("get-state");
      assert.equal(view.canRestart, true);
      assert.match(view.detail, /exited/);
      assert.equal(stub.app.quitCalled, 0, "a window is open, so a crash does not quit");
      // Attaching a desktop window with nothing running falls back to the connection window.
      stub.app.emit("second-instance", {}, [], h.tmp, { requestedMode: "desktop" });
      assert.equal(h.mainWin(), undefined);

      await h.act("restart");
      await h.until(async () => (await h.status()) === "running", 30000, "restarted after the crash");
      stub.app.emit("second-instance", {}, [], h.tmp, { requestedMode: "desktop" });
      await h.until(() => h.mainWin() && h.mainWin().visible, 5000, "desktop window attached");
      const desktopUrl = new URL(h.mainWin().loaded);
      assert.equal(desktopUrl.origin, new URL((await h.act("get-state")).address).origin);
      assert.equal(desktopUrl.searchParams.get("ui"), null, "desktop attachment keeps its workbench entry");
      assert.equal(h.pids().length, 3, "attaching spawned no backend");

      // Stop while a desktop window is attached asks first; Cancel keeps it running.
      stub.state.dialogResponse = 1;
      await h.act("stop");
      assert.equal(stub.state.dialogCalls, 1);
      assert.equal(await h.status(), "running");

      // Closing every window keeps a running service.
      h.mainWin().close();
      h.connWin().close();
      assert.equal(stub.app.quitCalled, 0);

      // The package-update relaunch stops the backend and waits for it to exit
      // before relaunching (AU1 M9), carrying the mode.
      await h.relaunchFromRenderer();
      assert.equal(stub.state.relaunches.length, 1);
      assert.equal(stub.state.relaunches[0].backendAlive, false, "the backend had exited before app.relaunch");
      assert.deepEqual(stub.state.relaunches[0].options, { args: [DESKTOP, EXTERNAL_AI_ARG] });
      assert.equal(stub.app.exited, 0);
    }
  },

  "desktop-remembered": {
    title: "desktop remembered: no picker, no tray, closing the window quits and stops the backend",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: false });
      stub.state.pick = () => Promise.reject(new Error("the picker must not be shown"));
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "main window");
      assert.equal(h.pickerAsked(), false);
      assert.equal(stub.trays.length, 0, "no tray in desktop mode");
      assert.equal(h.connWin(), undefined);
      assert.ok(h.knownGoodWritten());
      const startup = stub.Menu.current.template
        .find((item) => item.label === "File")
        .submenu.find((item) => item.label === "Startup Mode");
      assert.equal(startup.submenu.find((item) => item.checked).label, "Always Open the Desktop App");
      stub.app.emit("second-instance", {}, [], h.tmp, { requestedMode: "desktop" });
      assert.equal(stub.trays.length, 0);
      assert.equal(h.pids().length, 1);
      const pid = h.pids()[0];
      h.mainWin().close();
      assert.equal(stub.app.quitCalled, 1);
      await h.until(() => !h.alive(pid), 10000, "backend stopped on quit");
    }
  },

  "open-external": {
    title: "#2361: markdown links open through shell.openExternal; window.open is denied and forwarded",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: false });
      stub.state.pick = () => Promise.reject(new Error("the picker must not be shown"));
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "main window");

      const openExternal = stub.ipcMain.handlers["scistudio:open-external"];
      assert.ok(openExternal, "the preload channel has a main-process handler");

      await openExternal({}, "https://example.com/spec");
      await openExternal({}, "mailto:lab@example.com");
      assert.deepEqual(stub.state.externals, ["https://example.com/spec", "mailto:lab@example.com"]);

      // A scheme the shell must never execute is refused.
      await openExternal({}, "file:///etc/passwd");
      await openExternal({}, "javascript:alert(1)");
      assert.equal(stub.state.externals.length, 2, "only http/https/mailto leave the app");

      // window.open from the page never spawns a child window: an openable URL
      // goes to the shell, anything else is denied without reaching it.
      const handler = h.mainWin().webContents.windowOpenHandler;
      assert.ok(handler, "the main window denies child windows");
      assert.deepEqual(handler({ url: "https://example.com/page" }), { action: "deny" });
      assert.equal(stub.state.externals.at(-1), "https://example.com/page");
      assert.deepEqual(handler({ url: "file:///etc/passwd" }), { action: "deny" });
      assert.equal(stub.state.externals.length, 3, "file: is not forwarded");

      h.mainWin().close();
      assert.equal(stub.app.quitCalled, 1);
    }
  },

  "install-outcome-before-mandatory-update": {
    title: "#2396: a failed install is reported before a mandatory update is enforced again",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: false });
      stub.state.pick = () => Promise.reject(new Error("the picker must not be shown"));
      // The same mandatory base migration that sent the user to the installer.
      const server = await h.serveJson("/manifest.json", {
        channel: "alpha",
        base: "0.3.5",
        build: 40,
        requires: { min_base: "0.3.5", min_build: 40 }
      });
      h.writeOtaConfig(server.url("/manifest.json"));
      const releasePage = "https://github.com/o/r/releases/tag/v0.3.5-beta";
      fs.mkdirSync(path.join(h.userData, "installer"), { recursive: true });
      h.writeJson("installer/pending.json", { version: "0.3.5-beta-build0035", releasePage, startedAt: 1 });
      h.writeJson("installer/result.json", { ok: false, stage: "mount" });

      h.startMain();
      await h.until(() => stub.app.quitCalled > 0, 15000, "the mandatory update quits");
      server.close();

      const [report, enforce] = stub.state.dialogs;
      assert.equal(report.message, "SciStudio could not install the update.", "the failure is reported first");
      assert.match(report.detail, /stage: mount/);
      assert.equal(stub.state.externals[0], releasePage, "Open download page goes to the release page");
      assert.equal(enforce.title, "Update required", "then the mandatory update is enforced");
      assert.equal(fs.existsSync(path.join(h.userData, "installer", "pending.json")), false);
      assert.equal(fs.existsSync(path.join(h.userData, "installer", "result.json")), false);
    }
  },

  "installer-install-reuses-verified-download": {
    title: "#2396: install uses the verified download even when the manifest can no longer be read",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: false });
      stub.state.pick = () => Promise.reject(new Error("the picker must not be shown"));
      const installer = require(path.join(DESKTOP, "installer.js"));
      const key = installer.platformKey({ platform: process.platform, arch: process.arch });
      assert.ok(key, "the harness platform has an installer key");
      // The download is already on disk and intact, so nothing is fetched.
      const bytes = Buffer.from("installer bytes");
      const asset = {
        url: "https://example.invalid/SciStudio-0.3.5-beta-build0035-installer.bin",
        sha256: require("node:crypto").createHash("sha256").update(bytes).digest("hex"),
        size: bytes.length
      };
      fs.mkdirSync(path.join(h.userData, "installer"), { recursive: true });
      fs.writeFileSync(path.join(h.userData, "installer", installer.installerFileName(asset, key)), bytes);
      // build 0 is up to date for this baseline, so neither update check prompts.
      const server = await h.serveJson("/manifest.json", {
        channel: "alpha",
        base: "0.3.4",
        build: 0,
        installer: { version: "0.3.5-beta-build0035", assets: { [key]: asset } }
      });
      h.writeOtaConfig(server.url("/manifest.json"));
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "main window");

      const sender = { isDestroyed: () => false, send: () => {} };
      const offer = await stub.ipcMain.handlers["scistudio:installer-offer"]({ sender });
      assert.equal(offer.available, true);
      const downloaded = await stub.ipcMain.handlers["scistudio:installer-download"]({ sender });
      assert.deepEqual(downloaded, { ok: true });

      // Offline now: the install must not go back to the manifest.
      server.close();
      h.writeOtaConfig("http://127.0.0.1:9/manifest.json");
      const outcome = await stub.ipcMain.handlers["scistudio:installer-install"]({ sender });
      assert.equal(outcome.ok, false);
      assert.doesNotMatch(outcome.error, /no installer is on offer/, "the verified offer was reused");
      // An unpackaged harness run is refused for its location, never for the manifest.
      assert.match(outcome.error, /cannot install the update here \(not-packaged\)/);
      assert.equal(stub.app.quitCalled, 0);

      h.mainWin().close();
    }
  },

  "desktop-promote": {
    title: "desktop -> external AI on the running backend, startup setting changeable, tray Stop and Quit",
    async run(h) {
      const { stub } = h;
      stub.state.pick = { mode: "desktop", remember: true };
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "main window");
      assert.deepEqual(h.readJson("launch-mode.json"), { version: 1, mode: "desktop", askAtLaunch: false });
      stub.Menu.current.template
        .find((item) => item.label === "File")
        .submenu.find((item) => item.label === "External AI Connection…")
        .click();
      await h.until(async () => (await h.status()) === "running", 5000, "switched and running");
      assert.equal(stub.trays.length, 1);
      assert.equal(h.pids().length, 1, "the switch reuses the backend");
      await h.act("set-startup", "ask");
      assert.deepEqual(h.readJson("launch-mode.json"), { version: 1, mode: "desktop", askAtLaunch: true });
      const trayStartup = h.trayItem("Startup Mode");
      assert.equal(trayStartup.submenu.find((item) => item.checked).label, "Ask at Every Launch");
      h.mainWin().close();
      h.connWin().close();
      assert.equal(stub.app.quitCalled, 0, "now resident");
      const pid = h.pids()[0];
      await h.trayItem("Stop and Quit").click();
      assert.equal(stub.app.quitCalled, 1);
      await h.until(() => !h.alive(pid), 10000, "backend stopped");
    }
  },

  "relaunch-arg": {
    title: "a relaunch flag starts external AI without the picker",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: true });
      stub.state.pick = () => Promise.reject(new Error("the picker must not be shown"));
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      assert.equal(h.pickerAsked(), false);
      assert.equal(stub.app.lockData.requestedMode, "external-ai");
      const pid = h.pids()[0];
      await h.act("stop-and-quit");
      assert.equal(stub.app.quitCalled, 1);
      await h.until(() => !h.alive(pid), 10000, "backend stopped");
    }
  },

  "vouch-needs-the-connection-page": {
    title: "external AI records known-good only once the connection page proves itself over IPC (M6, M7)",
    async run(h) {
      const { stub } = h;
      // The page script never runs: the preload may be fine, the page is not.
      stub.state.connectionPageScript = false;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      await sleep(800);
      assert.equal(h.knownGoodWritten(), false, "readiness alone must not vouch for the shell");
      assert.equal(h.hostCalls.clearBootAttempt, 0, "readiness alone must not clear the boot marker");
      // The first action from the page is the proof.
      await h.act("get-state");
      await h.until(() => h.knownGoodWritten(), 5000, "known-good after the page's first action");
    }
  },

  "picker-close-releases-marker": {
    title: "closing the splash at the picker releases a patched shell's boot marker (P2-1)",
    patchShell: true,
    async run(h) {
      const { stub } = h;
      stub.state.pick = () => new Promise(() => {});
      h.startMain();
      await h.until(() => h.pickerAsked(), 5000, "picker shown");
      assert.equal(h.nextLaunchMarkerAction(), "keep", "precondition: the marker is set while asking");
      h.splashWin().close();
      await h.until(() => stub.app.quitCalled >= 1, 5000, "quit");
      await sleep(300);
      assert.equal(h.pids().length, 0, "no backend was started");
      assert.equal(h.nextLaunchMarkerAction(), "record", "the next launch retries the patch");
    }
  },

  "picker-quit-releases-marker": {
    title: "Cmd+Q at the picker releases a patched shell's boot marker (P2-1)",
    patchShell: true,
    async run(h) {
      const { stub } = h;
      stub.state.pick = () => new Promise(() => {});
      h.startMain();
      await h.until(() => h.pickerAsked(), 5000, "picker shown");
      stub.app.quit();
      await sleep(300);
      assert.equal(h.pids().length, 0, "no backend was started");
      assert.equal(h.nextLaunchMarkerAction(), "record", "the next launch retries the patch");
    }
  },

  "failure-before-picker-keeps-marker": {
    title: "a shell that never rendered the picker keeps its boot marker (P2-1)",
    patchShell: true,
    async run(h) {
      const { stub } = h;
      stub.state.splashLoad = "hang";
      h.startMain();
      await sleep(300);
      assert.equal(h.pickerAsked(), false);
      h.splashWin().close();
      await h.until(() => stub.app.quitCalled >= 1, 5000, "quit");
      assert.equal(h.nextLaunchMarkerAction(), "keep", "the next launch quarantines the patch");
    }
  },

  "shell-fault-keeps-marker": {
    title: "a preload fault after the picker keeps the boot marker on quit (#2179 preserved)",
    patchShell: true,
    async run(h) {
      const { stub } = h;
      stub.state.pick = { mode: "desktop", remember: false };
      stub.state.mainPreloadError = true;
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "main window");
      await sleep(200);
      assert.equal(h.knownGoodWritten(), false, "a faulted shell is not recorded as known-good");
      h.mainWin().close();
      await h.until(() => stub.app.quitCalled >= 1, 5000, "quit");
      assert.equal(h.nextLaunchMarkerAction(), "keep", "the next launch quarantines the patch");
    }
  },

  "posix-stop-escalates": {
    title: "Stop ends a backend that ignores SIGTERM through the SIGKILL escalation (P2-2)",
    ignoreSigterm: true,
    async run(h) {
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      const pid = h.pids()[0];
      await h.act("stop");
      assert.equal(await h.status(), "stopping");
      // #2327: the force-kill waits STOP_ESCALATION_MS (25 s) for a graceful stop.
      await h.until(async () => (await h.status()) === "stopped", 35000, "stopped after SIGKILL");
      assert.equal(h.alive(pid), false);
    }
  },

  "posix-relaunch-waits-for-exit": {
    title: "a relaunch waits until a backend that ignores SIGTERM has really exited (P2-2)",
    ignoreSigterm: true,
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      await h.relaunchFromRenderer();
      assert.equal(stub.state.relaunches.length, 1);
      assert.equal(stub.state.relaunches[0].backendAlive, false, "the backend had exited before app.relaunch");
    }
  },

  "posix-relaunch-waits-for-inflight-stop": {
    title: "a relaunch during a Stop still in flight waits for that backend (AU2 P3-2)",
    ignoreSigterm: true,
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      await h.act("stop");
      assert.equal(await h.status(), "stopping");
      await h.relaunchFromRenderer();
      assert.equal(stub.state.relaunches[0].backendAlive, false, "the stopping backend had exited before app.relaunch");
    }
  },

  "startup-death-restarts-at-once": {
    title: "a backend that dies during readiness fails at once with its reason, and Restart works (AU1 P3-5)",
    env: { HARNESS_BACKEND_PLAN: "exit-after-ready,serve" },
    async run(h) {
      h.startMain([EXTERNAL_AI_ARG]);
      await h.until(async () => (await h.status()) === "failed", 10000, "failed");
      const view = await h.act("get-state");
      assert.match(view.detail, /exited while starting/);
      await h.act("restart");
      await h.until(async () => (await h.status()) === "running", 10000, "Restart takes effect at once");
    }
  },

  "stop-and-quit-confirms": {
    title: "Stop and Quit asks first while a desktop window is attached (AU1 P3-7)",
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      stub.app.emit("second-instance", {}, [], h.tmp, { requestedMode: "desktop" });
      await h.until(() => h.mainWin() && h.mainWin().visible, 5000, "desktop window attached");
      stub.state.dialogResponse = 1;
      await h.act("stop-and-quit");
      assert.equal(stub.state.dialogCalls, 1, "the user was asked");
      assert.equal(stub.app.quitCalled, 0, "Cancel keeps the app");
      assert.equal(await h.status(), "running");
      stub.state.dialogResponse = 0;
      const pid = h.pids()[0];
      await h.trayItem("Stop and Quit").click();
      assert.equal(stub.state.dialogCalls, 2);
      assert.equal(stub.app.quitCalled, 1);
      await h.until(() => !h.alive(pid), 10000, "backend stopped");
    }
  },

  "splash-load-failure-falls-back": {
    title: "a splash that fails to load falls back to the desktop flow (AU1 P3-4)",
    async run(h) {
      const { stub } = h;
      stub.state.splashLoad = "fail";
      stub.state.pick = () => Promise.reject(new Error("the picker must not be asked"));
      h.startMain();
      await h.until(() => h.mainWin() && h.mainWin().visible, 30000, "desktop main window");
      assert.equal(h.pickerAsked(), false);
    }
  },

  "macos-activate-routes": {
    title: "macOS: activate routes like a second launch, and the tray uses the template image (AU1 P3-6)",
    platform: "darwin",
    async run(h) {
      const { stub } = h;
      h.writeJson("launch-mode.json", { version: 1, mode: "desktop", askAtLaunch: false });
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      const image = stub.trays[0].image;
      assert.equal(image.template, true);
      assert.ok(image.path.endsWith(`${path.sep}trayTemplate.png`));
      // Reopening from the Dock with desktop remembered attaches a desktop window.
      stub.app.emit("activate");
      await h.until(() => h.mainWin() && h.mainWin().visible, 5000, "desktop window attached on activate");
      assert.equal(h.pids().length, 1);
    }
  },

  "windows-tray-left-click": {
    title: "Windows: a tray left-click reopens the connection window",
    platform: "win32",
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      assert.ok(stub.trays[0].image.path.endsWith(`${path.sep}tray.png`));
      h.connWin().close();
      stub.trays[0].emit("click");
      await h.until(() => h.connWin(), 5000, "connection window reopened");
    }
  },

  "quit-when-backend-dies-without-windows": {
    title: "owner decision: a backend that dies after the last window closed quits the app",
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      h.connWin().close();
      assert.equal(stub.app.quitCalled, 0, "a live service keeps the app");
      h.killPid(h.pids()[0]);
      await h.until(() => stub.app.quitCalled >= 1, 10000, "quit after the crash");
    }
  },

  "quit-when-stop-completes-without-windows": {
    title: "owner decision: a Stop that completes after the window closed quits the app (AU2 race)",
    ignoreSigterm: true,
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      await h.act("stop");
      h.connWin().close();
      assert.equal(stub.app.quitCalled, 0, "still stopping, so window-all-closed stays");
      await h.until(() => stub.app.quitCalled >= 1, 35000, "quit once the stop completed");
    }
  },

  "quit-waits-for-graceful-stop": {
    title: "quitting hides the windows at once and waits for the backend's graceful stop (#2327)",
    env: { HARNESS_GRACEFUL_STOP_MS: "1500" },
    async run(h) {
      const { stub } = h;
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      const pid = h.pids()[0];
      const started = Date.now();
      await h.act("stop-and-quit");
      assert.equal(stub.app.quitCalled, 1);
      assert.equal(stub.app.quitting, false, "the quit waits for the backend");
      assert.ok(
        stub.BrowserWindow.getAllWindows().every((window) => !window.visible),
        "every window hid at once"
      );
      assert.ok(h.alive(pid), "the backend is still shutting down");
      await h.until(() => !h.alive(pid), 10000, "backend exited");
      await h.until(() => stub.app.quitting, 5000, "the quit resumed");
      const asked = process.platform === "win32" ? "stdin-eof" : "sigterm";
      assert.deepEqual(h.stops(), [`${pid} ${asked}`], "the backend was asked to stop, not killed");
      assert.ok(Date.now() - started >= 1400, "the backend had its shutdown time");
    }
  },

  "windows-stop-escalates-to-taskkill": {
    title: "Windows: a backend that ignores the stop request is force-killed after the bound (#2327)",
    onlyOn: "win32",
    env: { HARNESS_IGNORE_STOP_REQUEST: "1" },
    async run(h) {
      h.startMain([EXTERNAL_AI_ARG]);
      await h.untilRunning();
      const pid = h.pids()[0];
      await h.act("stop");
      assert.equal(await h.status(), "stopping");
      await h.sleep(3000);
      assert.ok(h.alive(pid), "not force-killed before the bound");
      await h.until(async () => (await h.status()) === "stopped", 35000, "stopped after taskkill");
      assert.equal(h.alive(pid), false);
    }
  }
};

async function main(name) {
  const spec = SCENARIOS[name];
  if (!spec) {
    process.stdout.write(`unknown scenario ${name}\n`);
    process.exit(2);
  }
  const h = makeHarness(spec);
  let failure = null;
  try {
    await spec.run(h);
  } catch (error) {
    failure = error;
  }
  h.cleanup();
  if (failure) {
    process.stdout.write(`\nSCENARIO ${name}: FAIL\n${failure.stack}\n`);
    process.exit(1);
  }
  process.stdout.write(`\nSCENARIO ${name}: PASS\n`);
  process.exit(0);
}

module.exports = { SCENARIOS };

if (require.main === module) {
  main(process.argv[2]);
}
