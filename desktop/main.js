const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  clipboard,
  dialog,
  ipcMain,
  nativeImage,
  nativeTheme,
  session,
  shell
} = require("electron");
const { spawn, spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const net = require("net");
const os = require("os");
const path = require("path");
const readline = require("readline");

const ota = require("./ota");
const { MENU_ACTION_CHANNEL, buildMenuTemplate, buildTrayMenuTemplate } = require("./menu");
const runtimePortModule = require("./runtime-port");
const backgroundMode = require("./background-mode");

// #1784: the in-app Package Manager stages a package update on disk (into the
// scanned installed-packages dir) and then asks the main process to relaunch so
// a fresh interpreter imports the new code. Registered once at module load;
// safeLog is hoisted and only called when the handler fires.
ipcMain.handle("scistudio:relaunch", async () => {
  safeLog("[scistudio] relaunch requested by renderer (package update)");
  // #1867: stop the backend before exiting. app.exit() does NOT emit
  // `before-quit`, so without this the child backend is never signalled and is
  // reparented to init as an orphan on every package-update relaunch. Mirrors
  // the OTA relaunch path. #2280: both now share stopRuntimeAndRelaunch, which
  // also brings the process back in the mode it was running in.
  await stopRuntimeAndRelaunch();
});

// #2280: the external-AI connection window's actions. Registered once at module
// load like the relaunch handler; handleConnectionAction only answers the
// connection window's own webContents.
ipcMain.handle(backgroundMode.CONNECTION_ACTION_CHANNEL, (event, action, payload) =>
  handleConnectionAction(event, action, payload)
);

const READY_EVENT = "scistudio.ready";
const READY_TIMEOUT_MS = 120000;
const HTTP_READY_TIMEOUT_MS = 30000;
const DEFAULT_DEV_FRONTEND_URL = "http://127.0.0.1:5173";

// #2097: mirrored verbatim from the repository LICENSE and pyproject.toml,
// with a test pinning the three together so they cannot drift apart.
const LICENSE_NAME = "Apache License 2.0";
const COPYRIGHT = "Copyright 2026 Jiazhen Zhang";

// #1775: OTA hot-update (backend + embedded frontend).
const OTA_MANIFEST_TIMEOUT_MS = 8000;
const OTA_DOWNLOAD_TIMEOUT_MS = 120000;
const OTA_MAX_REDIRECTS = 5;

// #2327: stopRuntime first asks the backend to stop gracefully -- SIGTERM on
// POSIX; on Windows, which cannot deliver a SIGTERM, it closes the backend's
// stdin (SCISTUDIO_STOP_ON_STDIN_EOF) -- and force-kills it (SIGKILL, or
// `taskkill /T /F`) only if it is still running this long after. The backend's
// shutdown budget: its long-lived streams end on the stop request (well under
// 2 s), live workflow runs get 10 s to record their outcome
// (ApiRuntime.shutdown_workflow_runs), AI terminal sessions 3 s, and command
// processes a 5 s grace -- 20 s at most, so the force-kill waits 25 s.
// #2280: liveness is judged by exit status.
const STOP_ESCALATION_MS = 25000;
// #2280: how long a relaunch -- and, #2327, a quit -- waits for the backend to
// exit. It must outlast STOP_ESCALATION_MS so the force-kill lands inside it;
// the bound exists only so a process the kernel cannot reap (stuck in
// uninterruptible I/O) can never hang an update or a quit forever.
const RELAUNCH_STOP_TIMEOUT_MS = 30000;
// #2280: how long the splash may take to load before the launch-mode picker is
// abandoned and the desktop flow starts instead.
const SPLASH_PICKER_LOAD_TIMEOUT_MS = 15000;

let mainWindow = null;
let splashWindow = null;
let runtimeProcess = null;
let isQuitting = false;
// #2327: "idle" -> "stopping" (the quit waits for the backend) -> "done".
let quitStopState = "idle";
let cachedMacLoginShellEnv = null;

// #2280: launch mode and the external-AI surfaces. `launchMode` stays null
// while the splash is still asking.
let launchMode = null;
let connectionWindow = null;
// Held at module level on purpose: a Tray that gets garbage-collected vanishes
// from the menu bar / notification area (owner decision 2 calls this out for
// macOS).
let tray = null;
// The backend this process owns, in either mode. Tracked in desktop mode too,
// so switching a running desktop session to external-AI mode starts from the
// real service state.
let serviceState = {
  status: backgroundMode.SERVICE_STATUS.STARTING,
  readyUrl: null,
  address: null,
  detail: null
};
let serviceChild = null;
let serviceStartInFlight = false;
let stopRequested = false;
// Set by the first action the connection page sends over IPC: proof that the
// page script, its sandboxed preload and the IPC handler all work.
let connectionBridgeReady = false;
let backgroundShellVouched = false;
let backgroundUpdateChecked = false;
// #2280 (AU1 P2-1): set once the splash has rendered the launch-mode picker.
let pickerRendered = false;
// #2280: backends that were told to stop and have not exited yet. A relaunch
// waits on every one of them, so a Stop that is still in flight counts too.
const exitingRuntimeChildren = new Set();

// #2097: facts injected by the frozen bootstrap loader (desktop/bootstrap.js).
// Once this file runs from an OTA patch directory, `__dirname` no longer points
// into the app bundle and `./package.json` is the patch's own manifest, so the
// installed baseline, the resources path and the bundle root can only come from
// the loader. Reading them locally is what would break the #1787 staleness
// check, by comparing a patch against itself.
let hostFacts = null;

function host() {
  if (!hostFacts) {
    throw new Error("desktop/main.js was loaded without bootstrap.js calling start()");
  }
  return hostFacts;
}

// #1867: single-instance lock. A second launch must never spawn a second
// backend (which would then orphan on quit). The whenReady handler bails early
// when the lock was not acquired.
//
// #2280: one backend per machine, in either mode (owner decision 4). The second
// process quits before it could show a picker, so it passes the mode it would
// have started in -- an explicit flag or a remembered "don't ask again" choice
// -- and the running instance routes it (backgroundMode.routeSecondInstance):
// focus the desktop window, reveal the connection window, or attach a desktop
// window to the running backend.
const gotSingleInstanceLock = app.requestSingleInstanceLock({
  requestedMode: secondLaunchRequestedMode()
});
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, argv, _workingDirectory, additionalData) => {
    handleSecondInstance(argv, additionalData);
  });
}

// #1867: last-resort synchronous reap. If the main process is exiting while the
// backend is still tracked (e.g. the SIGTERM escalation timer in stopRuntime was
// dropped when the process exited first), kill it now. The 'exit' event only
// permits synchronous work, so this sends SIGKILL directly. A clean stopRuntime
// nulls runtimeProcess first, making this a no-op on the normal path.
process.on("exit", () => {
  if (runtimeProcess && !runtimeProcess.killed && process.platform !== "win32") {
    try {
      runtimeProcess.kill("SIGKILL");
    } catch {
      // best-effort; the process is already going away
    }
  }
});

function installPipeGuard(stream) {
  if (!stream || typeof stream.on !== "function") {
    return;
  }
  stream.on("error", (error) => {
    if (!error || error.code === "EPIPE") {
      return;
    }
  });
}

installPipeGuard(process.stdout);
installPipeGuard(process.stderr);

const MAX_LOG_BYTES = 10 * 1024 * 1024; // rotate the desktop log at ~10 MB

function desktopLogDir() {
  // #1741: align with the Python logs_dir() so desktop + backend logs co-locate.
  // app.getPath("logs") resolves to ~/Library/Logs/SciStudio (macOS),
  // %APPDATA%/SciStudio/logs (Windows), ~/.config/SciStudio/logs (Linux). Falls
  // back to the temp dir before the app is ready.
  try {
    return app.isReady() ? app.getPath("logs") : os.tmpdir();
  } catch {
    return os.tmpdir();
  }
}

function logFilePath() {
  return path.join(desktopLogDir(), "scistudio-desktop.log");
}

function rotateIfNeeded(filePath) {
  try {
    const stat = fs.statSync(filePath);
    if (stat.size >= MAX_LOG_BYTES) {
      const rotated = `${filePath}.1`;
      try {
        fs.rmSync(rotated, { force: true });
      } catch {
        // Rotation is best-effort.
      }
      fs.renameSync(filePath, rotated);
    }
  } catch {
    // File may not exist yet, or stat/rename failed; ignore.
  }
}

function safeWrite(stream, message) {
  const line = `${message}\n`;
  try {
    const filePath = logFilePath();
    rotateIfNeeded(filePath);
    fs.appendFileSync(filePath, line);
  } catch {
    // Best-effort diagnostic log only.
  }
  try {
    if (!stream || stream.destroyed || !stream.writable) {
      return;
    }
    stream.write(line);
  } catch {
    // Packaged GUI apps may inherit a closed console pipe. Logging must never
    // crash the Electron main process.
  }
}

function safeLog(message) {
  safeWrite(process.stdout, message);
}

function safeError(message) {
  safeWrite(process.stderr, message);
}

function resourcesDir() {
  return host().resourcesPath;
}

function repoRoot() {
  return host().repoRoot;
}

function appIconPath() {
  // #2097: assets/ stays in the asar and does not travel with a shell patch, so
  // this resolves against the bundle root rather than this file's directory.
  return path.join(host().appRoot, "assets", "icon.png");
}

// Forward a menu action to the renderer; the frontend dispatches it via
// window.scistudioDesktop.onMenuAction (App.parts/useDesktopMenuActions.ts).
// Before the main window exists (splash still up) the action is dropped — the
// user has no project state to act on yet anyway.
function sendMenuAction(action) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(MENU_ACTION_CHANNEL, action);
  }
}

function installApplicationMenu() {
  const template = buildMenuTemplate({
    platform: process.platform,
    appName: app.name,
    sendMenuAction,
    checkForUpdates: maybeCheckForUpdate,
    showAbout,
    // #2280: switch a desktop session to external-AI mode, or reopen the
    // connection window; and the remembered launch choice.
    showConnectionWindow: openExternalAiConnection,
    startupSetting: currentStartupSetting(),
    setStartupSetting,
  });
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// --------------------------------------------------------------------------- //
// #1775: OTA hot-update for the backend source tree (which embeds the frontend).
//
// Patches are full snapshots published per channel (see scripts/ota_publish.py).
// We stage them under userData/patches/build<N>/src and point PYTHONPATH there,
// never touching the read-only app bundle. A pointer (active.json) selects the
// live patch; a known-good marker enables rollback if a patch fails to boot.
// --------------------------------------------------------------------------- //
function baselineVersion() {
  // #2097: supplied by the loader from the asar's package.json. Reading
  // `./package.json` here would resolve to the running patch's own manifest.
  return host().baselineVersion;
}

function loadOtaConfig() {
  const cfg = readJsonSafe(path.join(resourcesDir(), "ota-config.json"));
  if (!cfg || typeof cfg !== "object") {
    return { enabled: false, channel: "dev", manifestUrl: null };
  }
  return cfg;
}

function patchesRoot() {
  return path.join(app.getPath("userData"), "patches");
}

function activePointerPath() {
  return path.join(patchesRoot(), "active.json");
}

function knownGoodPath() {
  return path.join(patchesRoot(), "known-good.json");
}

function readJsonSafe(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

function writeJsonAtomic(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(value));
  fs.renameSync(tmp, filePath);
}

// #1787: remove a superseded patch directory and its active pointer so a stale
// patch can never shadow a newer bundled baseline. Best-effort; getActivePatch
// already treats a missing pointer or dir as "no active patch".
function discardStalePatch(dir) {
  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch {
    // Best-effort cleanup; a leftover dir is harmless once the pointer is gone.
  }
  try {
    fs.rmSync(activePointerPath(), { force: true });
  } catch {
    // Best-effort; a stale pointer to a missing dir is ignored by getActivePatch.
  }
}

// Resolve the currently active patch, validating that its source tree exists and
// that it has not been superseded by a freshly installed bundle (see #1787). The
// pure decision lives in ota.resolveActivePatch; here we gather the on-disk facts
// and act on a "stale" verdict by discarding the patch.
function getActivePatch() {
  if (!app.isPackaged) {
    // Dev (unpackaged, run from a source checkout): ignore any userData OTA
    // patch entirely so the worktree src is authoritative and effectiveBuild
    // falls back to the baseline (0). Non-destructive — the user's active.json
    // is left intact for when they next run a packaged build. The packaged
    // path below is unchanged.
    return null;
  }
  const pointer = readJsonSafe(activePointerPath());
  const build = pointer && typeof pointer.build === "number" ? pointer.build : null;
  const dir = build !== null ? path.join(patchesRoot(), ota.patchDirName(build)) : null;
  const srcDir = dir ? path.join(dir, "src") : null;
  const srcExists = srcDir ? fs.existsSync(path.join(srcDir, "scistudio")) : false;
  const decision = ota.resolveActivePatch(pointer, baselineVersion().build, srcExists);
  if (decision.kind === "stale") {
    // #1787: the installed bundle is >= the patch build, so honoring the patch
    // would let its stale source shadow the newer bundled source (the patch
    // srcDir sits first on PYTHONPATH). Discard it so the baseline wins.
    discardStalePatch(dir);
    return null;
  }
  if (decision.kind !== "active") {
    return null;
  }
  return { build, dir, srcDir };
}

// Highest build the running app effectively serves: the applied patch if any,
// otherwise the installer baseline.
function effectiveBuild() {
  const active = getActivePatch();
  return Math.max(baselineVersion().build, active ? active.build : 0);
}

// #2179: set when the shell itself fails after the backend is already
// answering. `recordKnownGood` is what disarms the loader's crash-loop
// quarantine, so it must not fire while this holds a reason.
let shellFault = null;

function noteShellFault(reason) {
  if (shellFault) {
    return;
  }
  shellFault = reason;
  safeError(`[scistudio] shell fault: ${reason}`);
}

function recordKnownGood(build) {
  // #2097: clearing the loader's crash-loop marker here (rather than merely on
  // startup) is what makes "this shell build never reached readiness" mean
  // exactly that.
  //
  // #2179: it used to fire as soon as the backend answered. But the readiness
  // probe validates the *Python runtime*, and this vouches for the *Electron
  // shell* -- two halves of one snapshot that fail independently. A patch that
  // broke the preload, the window, or the menu still got recorded as good, so
  // the quarantine never engaged and the next launch loaded it again. It now
  // runs only once the renderer has painted, and refuses outright while a shell
  // fault stands.
  if (shellFault) {
    safeError(`[scistudio] not recording build ${build} as known-good: ${shellFault}`);
    return;
  }
  try {
    host().clearBootAttempt();
  } catch (error) {
    safeError(`[scistudio] failed to clear the shell boot marker: ${error.message}`);
  }
  try {
    writeJsonAtomic(knownGoodPath(), { build });
  } catch (error) {
    safeError(`[scistudio] failed to record known-good build: ${error.message}`);
  }
}

// #2280 (AU1 P2-1): the launch-mode picker is a pre-readiness stop the user can
// end by quitting (Cmd+Q, or closing the splash). Without this, that quit left
// the loader's boot marker set and the next launch quarantined a working
// patched shell for good. Runs from before-quit only, so a crash -- which runs
// no quit handler -- still leaves the marker; and releasesBootMarkerOnQuit
// refuses while a shell fault stands (#2179) or before the picker rendered.
// The host's clearBootAttempt is itself guarded by mayClearShellMarker.
function releaseBootMarkerOnQuit() {
  if (!backgroundMode.releasesBootMarkerOnQuit({ pickerRendered, shellFaulted: Boolean(shellFault) })) {
    return;
  }
  try {
    host().clearBootAttempt();
  } catch (error) {
    safeError(`[scistudio] failed to clear the shell boot marker on quit: ${error.message}`);
  }
}

// Roll back the active pointer to the last known-good patch, or remove it so the
// runtime falls back to the bundled baseline. Returns the build rolled back to,
// or null when falling back to baseline.
function revertActivePatch() {
  const known = readJsonSafe(knownGoodPath());
  const active = readJsonSafe(activePointerPath());
  if (known && typeof known.build === "number" && (!active || known.build !== active.build)) {
    const dir = path.join(patchesRoot(), ota.patchDirName(known.build));
    if (fs.existsSync(path.join(dir, "src", "scistudio"))) {
      writeJsonAtomic(activePointerPath(), { build: known.build });
      return known.build;
    }
  }
  try {
    fs.rmSync(activePointerPath(), { force: true });
  } catch {
    // Best-effort; a stale pointer to a missing dir is already ignored by
    // getActivePatch().
  }
  return null;
}

// GET with redirect following (GitHub release asset URLs redirect to a CDN).
function otaHttpGet(url, timeoutMs, redirectsLeft, callback) {
  let parsed = null;
  try {
    parsed = new URL(url);
  } catch (error) {
    callback(error);
    return;
  }
  const client = parsed.protocol === "https:" ? https : http;
  const req = client.get(parsed, { timeout: timeoutMs }, (res) => {
    const status = res.statusCode || 0;
    if ([301, 302, 303, 307, 308].includes(status) && res.headers.location) {
      res.resume();
      if (redirectsLeft <= 0) {
        callback(new Error("too many redirects"));
        return;
      }
      otaHttpGet(new URL(res.headers.location, parsed).toString(), timeoutMs, redirectsLeft - 1, callback);
      return;
    }
    if (status < 200 || status >= 300) {
      res.resume();
      callback(new Error(`HTTP ${status} for ${url}`));
      return;
    }
    callback(null, res);
  });
  req.on("timeout", () => req.destroy(new Error("request timed out")));
  req.on("error", callback);
}

function fetchText(url, timeoutMs) {
  return new Promise((resolve, reject) => {
    otaHttpGet(url, timeoutMs, OTA_MAX_REDIRECTS, (err, res) => {
      if (err) {
        reject(err);
        return;
      }
      let data = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => resolve(data));
      res.on("error", reject);
    });
  });
}

function downloadTo(url, destPath, timeoutMs) {
  return new Promise((resolve, reject) => {
    otaHttpGet(url, timeoutMs, OTA_MAX_REDIRECTS, (err, res) => {
      if (err) {
        reject(err);
        return;
      }
      const out = fs.createWriteStream(destPath);
      out.on("error", reject);
      out.on("finish", () => out.close(() => resolve()));
      res.on("error", reject);
      res.pipe(out);
    });
  });
}

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
    stream.on("error", reject);
  });
}

function extractTarGz(tarPath, destDir) {
  return new Promise((resolve, reject) => {
    const tarCmd = process.platform === "win32" ? "tar.exe" : "tar";
    const child = spawn(tarCmd, ["-xzf", tarPath, "-C", destDir], {
      windowsHide: true,
      stdio: ["ignore", "ignore", "pipe"]
    });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`tar exited ${code}${stderr.trim() ? `: ${stderr.trim()}` : ""}`));
    });
  });
}

// Download, verify, and stage a patch into userData; flip the active pointer.
async function downloadAndApply(manifest) {
  const root = patchesRoot();
  fs.mkdirSync(root, { recursive: true });
  const tmpDir = fs.mkdtempSync(path.join(root, ".dl-"));
  try {
    const tarPath = path.join(tmpDir, "patch.tar.gz");
    await downloadTo(manifest.url, tarPath, OTA_DOWNLOAD_TIMEOUT_MS);

    const digest = await sha256File(tarPath);
    if (manifest.sha256 && digest.toLowerCase() !== String(manifest.sha256).toLowerCase()) {
      throw new Error(`sha256 mismatch (expected ${manifest.sha256}, got ${digest})`);
    }

    const stageDir = path.join(tmpDir, "stage");
    fs.mkdirSync(stageDir, { recursive: true });
    await extractTarGz(tarPath, stageDir);
    if (!fs.existsSync(path.join(stageDir, "src", "scistudio"))) {
      throw new Error("patch archive missing src/scistudio");
    }

    const finalDir = path.join(root, ota.patchDirName(manifest.build));
    fs.rmSync(finalDir, { recursive: true, force: true });
    fs.renameSync(stageDir, finalDir);
    writeJsonAtomic(activePointerPath(), { build: manifest.build });
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // Temp cleanup is best-effort.
    }
  }
}

// #1868: pre-window mandatory-update gate. Runs before the runtime/window so a
// required build can block entry. Returns true when startup should continue,
// false when the app is updating or quitting.
//
// Fail-open by design: OTA disabled, no manifest URL, or any fetch/parse failure
// (offline, bad manifest) returns true. Only a successfully fetched manifest that
// `evaluateUpdate` marks `mandatory` can block. Optional (non-mandatory) updates
// are left to the post-window maybeCheckForUpdate so this gate never nags.
async function maybeEnforceMandatoryUpdate() {
  const config = loadOtaConfig();
  if (!config.enabled || !config.manifestUrl) {
    return true;
  }

  let manifest = null;
  try {
    manifest = JSON.parse(await fetchText(config.manifestUrl, OTA_MANIFEST_TIMEOUT_MS));
  } catch (error) {
    safeLog(`[scistudio] mandatory update check skipped (fail-open): ${error.message}`);
    return true;
  }

  const baseline = baselineVersion();
  const local = effectiveBuild();
  const decision = ota.evaluateUpdate(config, manifest, baseline, local);
  if (!decision.mandatory) {
    return true;
  }
  safeLog(`[scistudio] mandatory update required: kind=${decision.kind} remote build=${manifest.build}`);

  if (decision.kind === "incompatible") {
    // Can't hot-patch across a base bump: the only path forward is a reinstall.
    await dialog.showMessageBox({
      type: "warning",
      title: "Update required",
      message: "A required SciStudio update is available.",
      detail:
        `Version ${ota.displayBuildVersion(manifest.base, decision.build)} requires a newer base ` +
        `version (${decision.minBase}) than this installation (${baseline.base}). ` +
        `Please download and reinstall SciStudio to continue.`,
      buttons: ["Quit"],
      defaultId: 0
    });
    app.quit();
    return false;
  }
  if (decision.kind !== "patch") {
    return true;
  }

  const choice = await dialog.showMessageBox({
    type: "warning",
    title: "Update required",
    message: `SciStudio must update to ${ota.displayBuildVersion(manifest.base, manifest.build)} to continue.`,
    detail:
      (manifest.notes ? `${manifest.notes}\n\n` : "") + "SciStudio will restart to apply the update.",
    buttons: ["Update now", "Quit"],
    defaultId: 0,
    cancelId: 1
  });
  if (choice.response !== 0) {
    app.quit();
    return false;
  }

  try {
    await downloadAndApply(manifest);
  } catch (error) {
    safeError(`[scistudio] mandatory update apply failed: ${error.message}`);
    await dialog.showMessageBox({
      type: "error",
      title: "Update failed",
      message: "SciStudio could not apply the required update.",
      detail: `${error.message}\n\nPlease try again or reinstall SciStudio.`,
      buttons: ["Quit"],
      defaultId: 0
    });
    app.quit();
    return false;
  }

  safeLog(`[scistudio] applied mandatory OTA build ${manifest.build}; relaunching`);
  // #2280: stop-then-relaunch, carrying the chosen launch mode across it.
  await stopRuntimeAndRelaunch();
  return false;
}

// Launch-time update check. Silent on dev builds and when offline.
async function maybeCheckForUpdate() {
  const config = loadOtaConfig();
  if (!config.enabled || !config.manifestUrl) {
    safeLog("[scistudio] OTA disabled; skipping update check");
    return;
  }

  let manifest = null;
  try {
    manifest = JSON.parse(await fetchText(config.manifestUrl, OTA_MANIFEST_TIMEOUT_MS));
  } catch (error) {
    safeLog(`[scistudio] update check skipped: ${error.message}`);
    return;
  }

  const baseline = baselineVersion();
  const local = effectiveBuild();
  const decision = ota.evaluateUpdate(config, manifest, baseline, local);
  safeLog(
    `[scistudio] update decision=${decision.kind} local build=${local} remote build=${manifest.build}`
  );

  if (decision.kind === "incompatible") {
    await dialog.showMessageBox(mainWindow || undefined, {
      type: "info",
      title: "Update available",
      message: "A newer SciStudio version is available.",
      detail:
        `Version ${ota.displayBuildVersion(manifest.base, decision.build)} requires a newer base ` +
        `version (${decision.minBase}) than this installation (${baseline.base}). ` +
        `Please download and reinstall SciStudio to update.`,
      buttons: ["OK"],
      defaultId: 0
    });
    return;
  }
  if (decision.kind !== "patch") {
    return;
  }

  const choice = await dialog.showMessageBox(mainWindow || undefined, {
    type: "question",
    title: "Update available",
    message: `Update SciStudio to ${ota.displayBuildVersion(manifest.base, manifest.build)}?`,
    detail:
      (manifest.notes ? `${manifest.notes}\n\n` : "") +
      "SciStudio will restart to apply the update.",
    buttons: ["Update now", "Later"],
    defaultId: 0,
    cancelId: 1
  });
  if (choice.response !== 0) {
    return;
  }

  try {
    await downloadAndApply(manifest);
  } catch (error) {
    safeError(`[scistudio] update apply failed: ${error.message}`);
    await dialog.showMessageBox(mainWindow || undefined, {
      type: "error",
      title: "Update failed",
      message: "SciStudio could not apply the update.",
      detail: error.message,
      buttons: ["OK"],
      defaultId: 0
    });
    return;
  }

  safeLog(`[scistudio] applied OTA build ${manifest.build}; relaunching`);
  // #2280 (owner decision 5): in external-AI mode this is the background
  // instance; it is stopped before the relaunch, which comes back in the same
  // mode.
  await stopRuntimeAndRelaunch();
}

// Start the runtime; if an applied OTA patch fails to boot, roll back and retry
// once so a bad patch can never brick the install.
async function startRuntimeWithRollback() {
  const active = getActivePatch();
  try {
    return await startRuntime();
  } catch (error) {
    if (!active) {
      throw error;
    }
    safeError(
      `[scistudio] runtime failed with OTA patch build ${active.build}; rolling back: ${error.message}`
    );
    const fellBackTo = revertActivePatch();
    safeError(
      `[scistudio] rolled back to ${fellBackTo !== null ? `build ${fellBackTo}` : "bundled baseline"}; retrying runtime`
    );
    return startRuntime();
  }
}

function pythonCandidates() {
  const resources = resourcesDir();
  const candidates = [];

  const addExistingCandidate = (command, label) => {
    if (command && fs.existsSync(command)) {
      candidates.push({ command, argsPrefix: [], label });
    }
  };

  if (process.env.SCISTUDIO_DESKTOP_PYTHON) {
    candidates.push({
      command: process.env.SCISTUDIO_DESKTOP_PYTHON,
      argsPrefix: [],
      label: "SCISTUDIO_DESKTOP_PYTHON"
    });
  }

  if (process.platform === "win32") {
    candidates.push({
      command: path.join(resources, "python", "python.exe"),
      argsPrefix: [],
      label: "staged python.exe"
    });
    candidates.push({ command: "python", argsPrefix: [], label: "python" });
    candidates.push({ command: "py", argsPrefix: ["-3"], label: "py -3" });
  } else {
    candidates.push({
      command: path.join(resources, "python", "bin", "python"),
      argsPrefix: [],
      label: "staged python"
    });
    candidates.push({
      command: path.join(resources, "python", "python"),
      argsPrefix: [],
      label: "staged python root"
    });
    if (process.platform === "darwin") {
      addExistingCandidate("/opt/anaconda3/envs/scistudio/bin/python", "conda scistudio");
      addExistingCandidate("/opt/anaconda3/envs/SciStudio/bin/python", "conda SciStudio");
      addExistingCandidate(
        path.join(os.homedir(), "anaconda3", "envs", "scistudio", "bin", "python"),
        "home conda scistudio"
      );
      addExistingCandidate(
        path.join(os.homedir(), "miniconda3", "envs", "scistudio", "bin", "python"),
        "home miniconda scistudio"
      );
    }
    candidates.push({ command: "python3", argsPrefix: [], label: "python3" });
    candidates.push({ command: "python", argsPrefix: [], label: "python" });
  }

  return candidates;
}

function commonUserCliDirs(userHome) {
  const dirs = [];
  if (userHome) {
    dirs.push(
      path.join(userHome, ".local", "bin"),
      path.join(userHome, "bin"),
      path.join(userHome, ".npm-global", "bin"),
      path.join(userHome, ".volta", "bin"),
      path.join(userHome, ".bun", "bin"),
      path.join(userHome, "AppData", "Roaming", "npm")
    );
  }

  if (process.platform !== "win32") {
    dirs.push(
      "/opt/homebrew/bin",
      "/opt/homebrew/sbin",
      "/usr/local/bin",
      "/usr/local/sbin",
      "/opt/local/bin",
      "/opt/local/sbin"
    );
  }
  return dirs;
}

function parseNullSeparatedEnv(payload) {
  const env = {};
  for (const record of payload.split("\0")) {
    if (!record) {
      continue;
    }
    const equalsAt = record.indexOf("=");
    if (equalsAt <= 0) {
      continue;
    }
    const key = record.slice(0, equalsAt);
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      continue;
    }
    env[key] = record.slice(equalsAt + 1);
  }
  return env;
}

function macLoginShellEnv() {
  if (process.platform !== "darwin") {
    return {};
  }
  if (cachedMacLoginShellEnv !== null) {
    return cachedMacLoginShellEnv;
  }

  cachedMacLoginShellEnv = {};
  const userInfo = (() => {
    try {
      return os.userInfo();
    } catch {
      return {};
    }
  })();
  const shell = process.env.SHELL || userInfo.shell || "/bin/zsh";
  const marker = "__SCISTUDIO_ENV_START__\0";
  const script = "printf '__SCISTUDIO_ENV_START__\\0'; /usr/bin/env -0";

  try {
    const result = spawnSync(shell, ["-l", "-c", script], {
      cwd: os.homedir(),
      env: process.env,
      encoding: "utf8",
      timeout: 3000,
      windowsHide: true
    });
    if (result.error || result.status !== 0 || !result.stdout) {
      return cachedMacLoginShellEnv;
    }
    const markerAt = result.stdout.indexOf(marker);
    const payload =
      markerAt >= 0 ? result.stdout.slice(markerAt + marker.length) : result.stdout;
    cachedMacLoginShellEnv = parseNullSeparatedEnv(payload);
  } catch (error) {
    safeError(`[scistudio] Failed to read macOS login shell environment: ${error.message}`);
  }
  return cachedMacLoginShellEnv;
}

function runtimeEnv() {
  const resources = resourcesDir();
  const stagedSrc = path.join(resources, "backend", "src");
  const checkoutSrc = path.join(repoRoot(), "src");
  // #1775: an applied OTA patch shadows the bundled baseline by sitting first on
  // PYTHONPATH; the bundle is never modified. #1801: in dev (unpackaged) the
  // worktree src wins outright — neither a userData patch nor a stale staged
  // copy may shadow it. getActivePatch() already returns null in dev.
  const activePatch = getActivePatch();
  const pythonPathEntries = ota.pythonPathFor({
    isPackaged: app.isPackaged,
    patchSrc: activePatch ? activePatch.srcDir : null,
    stagedSrc,
    checkoutSrc
  });
  const loginShellEnv = macLoginShellEnv();
  const baseEnv = {
    ...loginShellEnv,
    ...process.env
  };
  const existingPythonPath = baseEnv.PYTHONPATH;
  const userHome = baseEnv.USERPROFILE || baseEnv.HOME || os.homedir() || "";
  const pathEntries = [];

  if (existingPythonPath) {
    pythonPathEntries.push(existingPythonPath);
  }
  pathEntries.push(...commonUserCliDirs(userHome));
  pathEntries.push(loginShellEnv.PATH || "");
  pathEntries.push(process.env.PATH || "");

  const env = {
    ...baseEnv,
    PATH: pathEntries.filter(Boolean).join(path.delimiter),
    PYTHONPATH: pythonPathEntries.join(path.delimiter),
    SCISTUDIO_BUNDLED: "1",
    SCISTUDIO_DESKTOP_RESOURCES: resources,
    // #1775: report the effective (post-patch) build via the #1742 version
    // override so /version and --version reflect the applied OTA patch.
    SCISTUDIO_BUILD_NUMBER: String(effectiveBuild()),
    // #1741: route backend logs to the same directory as the desktop log so the
    // diagnostic bundle captures both the Electron and Python sides.
    SCISTUDIO_LOG_DIR: desktopLogDir()
  };
  if (process.platform === "win32") {
    // #2327: stopRuntime asks for a graceful stop by closing stdin, because
    // Windows cannot deliver a SIGTERM (src/scistudio/api/runtime/_stop_request.py).
    env.SCISTUDIO_STOP_ON_STDIN_EOF = "1";
  }
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}

// #1986: the file that carries the bound port from one launch to the next, so
// the renderer origin (and with it every localStorage-backed UI preference)
// survives a restart. See desktop/runtime-port.js for why.
function runtimePortPath() {
  return path.join(app.getPath("userData"), "runtime-port.json");
}

function envRuntimePort() {
  const requested = process.env.SCISTUDIO_DESKTOP_RUNTIME_PORT;
  if (!requested) {
    return null;
  }
  const parsed = runtimePortModule.normalizeEnvPort(requested);
  if (parsed === null) {
    safeError(`[scistudio] Ignoring invalid SCISTUDIO_DESKTOP_RUNTIME_PORT=${requested}`);
  }
  return parsed;
}

function rememberedRuntimePort() {
  return runtimePortModule.parseRememberedPort(readJsonSafe(runtimePortPath()));
}

// Probe rather than assume: a remembered port can be taken by anything between
// two launches, and handing the backend an occupied port would leave the app
// unable to start at all.
function isPortFree(port) {
  return new Promise((resolve) => {
    const probe = net.createServer();
    probe.once("error", () => resolve(false));
    probe.once("listening", () => probe.close(() => resolve(true)));
    probe.listen(port, "127.0.0.1");
  });
}

async function resolveRuntimePort() {
  const envPort = envRuntimePort();
  if (envPort !== null) {
    return runtimePortModule.selectRuntimePort({ envPort });
  }
  const rememberedPort = rememberedRuntimePort();
  const rememberedPortFree = rememberedPort !== null ? await isPortFree(rememberedPort) : false;
  if (rememberedPort !== null && !rememberedPortFree) {
    safeError(
      `[scistudio] remembered runtime port ${rememberedPort} is in use; falling back to an ephemeral port`
    );
  }
  return runtimePortModule.selectRuntimePort({ envPort, rememberedPort, rememberedPortFree });
}

function rememberRuntimePort(boundPort) {
  const decision = {
    envPort: envRuntimePort(),
    boundPort,
    rememberedPort: rememberedRuntimePort()
  };
  if (!runtimePortModule.shouldRememberPort(decision)) {
    return;
  }
  try {
    writeJsonAtomic(runtimePortPath(), { port: boundPort });
    safeLog(`[scistudio] remembered runtime port ${boundPort}`);
  } catch (error) {
    // Best-effort: failing to remember the port costs the next launch its
    // persisted UI state, which must not stop this one from running.
    safeError(`[scistudio] failed to remember runtime port: ${error.message}`);
  }
}

function forgetRuntimePort() {
  try {
    fs.rmSync(runtimePortPath(), { force: true });
  } catch {
    // Best-effort; a stale remembered port is re-probed on the next launch.
  }
}

function runtimeArgs(candidate, port) {
  return [
    ...candidate.argsPrefix,
    "-m",
    "scistudio.cli.main",
    "gui",
    "--port",
    port,
    "--bundled"
  ];
}

function ptyProbeArgs(candidate) {
  return [
    ...candidate.argsPrefix,
    "-c",
    "import importlib.util, sys; sys.exit(0 if (importlib.util.find_spec('winpty') or importlib.util.find_spec('pywinpty')) else 86)"
  ];
}

function verifyPtyCapablePython(candidate) {
  if (process.platform !== "win32") {
    return Promise.resolve({ ok: true });
  }

  return new Promise((resolve) => {
    const child = spawn(candidate.command, ptyProbeArgs(candidate), {
      cwd: repoRoot(),
      env: runtimeEnv(),
      windowsHide: true,
      stdio: ["ignore", "ignore", "pipe"]
    });
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill();
      resolve({ ok: false, reason: "timed out probing pywinpty" });
    }, 5000);

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timeout);
      resolve({ ok: false, reason: error.message });
    });
    child.on("exit", (code) => {
      clearTimeout(timeout);
      if (code === 0) {
        resolve({ ok: true });
        return;
      }
      const detail = stderr.trim();
      resolve({
        ok: false,
        reason:
          code === 86
            ? "missing pywinpty/winpty"
            : `pywinpty probe exited ${code}${detail ? `: ${detail}` : ""}`
      });
    });
  });
}

function spawnRuntimeCandidate(candidate, port) {
  const child = spawn(candidate.command, runtimeArgs(candidate, port), {
    cwd: repoRoot(),
    env: runtimeEnv(),
    windowsHide: true,
    // #2327: on Windows stdin is the stop-request channel (requestGracefulStop);
    // POSIX stops the backend with SIGTERM and keeps stdin closed.
    stdio: [process.platform === "win32" ? "pipe" : "ignore", "pipe", "pipe"]
  });
  if (child.stdin) {
    // Ending the stdin of a backend that already exited must not become an
    // unhandled EPIPE in the main process.
    child.stdin.on("error", () => {});
  }
  return child;
}

function parseReadyLine(line) {
  try {
    const message = JSON.parse(line);
    if (message && message.event === READY_EVENT && message.url) {
      return message;
    }
  } catch {
    return null;
  }
  return null;
}

// #1986: prefer the port the previous launch bound so the renderer origin — and
// therefore every localStorage-backed UI preference — stays stable. The port can
// be lost to another process between the free-port probe and the backend's own
// bind, so a failure on a remembered port is retried once on an ephemeral one
// rather than being surfaced as "SciStudio failed to start".
async function startRuntime() {
  const port = await resolveRuntimePort();
  try {
    return await startRuntimeOnPort(port);
  } catch (error) {
    if (
      port === "0" ||
      envRuntimePort() !== null ||
      !runtimePortModule.isPortUnavailableFailure(error.message)
    ) {
      throw error;
    }
    safeError(
      `[scistudio] runtime did not start on remembered port ${port}; retrying on an ephemeral port: ${error.message}`
    );
    forgetRuntimePort();
    return startRuntimeOnPort("0");
  }
}

function startRuntimeOnPort(port) {
  const candidates = pythonCandidates();
  const stderrLines = [];
  safeLog(`[scistudio] starting runtime on port ${port === "0" ? "auto" : port}`);

  return new Promise((resolve, reject) => {
    let index = 0;
    let settled = false;
    let timeout = null;

    const fail = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      reject(error);
    };

    const tryNext = async () => {
      if (index >= candidates.length) {
        const windowsPtyHint =
          process.platform === "win32"
            ? "\nWindows desktop PTY requires a bundled Python at resources/python/python.exe or a system Python selected via SCISTUDIO_DESKTOP_PYTHON with pywinpty installed."
            : "";
        fail(
          new Error(
            `Unable to launch SciStudio runtime.${windowsPtyHint}\nstderr:\n${stderrLines.join("\n")}`
          )
        );
        return;
      }

      const candidate = candidates[index];
      index += 1;
      safeLog(`[scistudio] trying runtime candidate ${candidate.label}`);
      const ptyProbe = await verifyPtyCapablePython(candidate);
      if (!ptyProbe.ok) {
        stderrLines.push(`[${candidate.label}] skipped: ${ptyProbe.reason}`);
        safeError(`[scistudio] runtime candidate ${candidate.label} skipped: ${ptyProbe.reason}`);
        tryNext();
        return;
      }
      const child = spawnRuntimeCandidate(candidate, port);
      let sawOutput = false;
      runtimeProcess = child;

      const stdout = readline.createInterface({ input: child.stdout });
      stdout.on("line", (line) => {
        sawOutput = true;
        const ready = parseReadyLine(line);
        if (ready && !settled) {
          settled = true;
          clearTimeout(timeout);
          safeLog(`[scistudio] runtime ready at ${ready.url}`);
          resolve({ child, ready, candidate });
        } else {
          safeLog(`[scistudio] ${line}`);
        }
      });

      const stderr = readline.createInterface({ input: child.stderr });
      stderr.on("line", (line) => {
        sawOutput = true;
        stderrLines.push(`[${candidate.label}] ${line}`);
        safeError(`[scistudio] ${line}`);
      });

      child.on("error", (error) => {
        safeError(`[scistudio] runtime candidate ${candidate.label} error: ${error.message}`);
        if (error.code === "ENOENT" && !settled) {
          tryNext();
          return;
        }
        fail(error);
      });

      child.on("exit", (code, signal) => {
        safeError(
          `[scistudio] runtime candidate ${candidate.label} exited code=${code} signal=${signal}`
        );
        if (settled || isQuitting) {
          return;
        }
        if (!sawOutput && code === null && signal === null) {
          return;
        }
        tryNext();
      });
    };

    timeout = setTimeout(() => {
      stopRuntime();
      fail(new Error("Timed out waiting for SciStudio runtime ready line."));
    }, READY_TIMEOUT_MS);

    tryNext();
  });
}

function cacheBuildPath() {
  return path.join(app.getPath("userData"), "cache-build.json");
}

// #2068: this used to be an unconditional clearCache() on every launch, which
// threw away the frontend bundle each time and made every start pay a full
// re-download and re-parse. The served assets only change when the effective
// build changes (a new baseline or a newly applied OTA patch), so that is the
// only moment the cache has to be dropped — which is what e538c071 was after.
async function clearCacheOnBuildChange() {
  const build = effectiveBuild();
  if (!ota.shouldClearCache(readJsonSafe(cacheBuildPath()), build)) {
    return;
  }
  safeLog(`[scistudio] clearing HTTP cache for build ${build}`);
  await session.defaultSession.clearCache();
  try {
    writeJsonAtomic(cacheBuildPath(), { build });
  } catch (error) {
    // Best-effort: failing to record it only costs the next launch one more
    // cache clear, which must not stop this one from starting.
    safeError(`[scistudio] failed to record cache build: ${error.message}`);
  }
}

function launchUrl(runtimeUrl) {
  const frontendUrl = process.env.SCISTUDIO_DESKTOP_FRONTEND_URL;
  const url = frontendUrl && frontendUrl.trim() ? frontendUrl.trim() : runtimeUrl;
  if (frontendUrl) {
    return url;
  }
  return cacheBustedUrl(url, 0);
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function probeHttp(url) {
  return new Promise((resolve) => {
    let parsed = null;
    try {
      parsed = new URL(url);
    } catch {
      resolve(false);
      return;
    }

    const client = parsed.protocol === "https:" ? https : http;
    const req = client.request(
      parsed,
      { method: "GET", timeout: 2000 },
      (res) => {
        res.resume();
        resolve(Boolean(res.statusCode && res.statusCode < 500));
      }
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
    req.end();
  });
}

// #2280: `keepWaiting` lets a caller stop early -- the background service stops
// polling as soon as its backend exits instead of spending the whole timeout.
async function waitForHttpReady(url, keepWaiting = null) {
  const deadline = Date.now() + HTTP_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (keepWaiting && !keepWaiting()) {
      return;
    }
    if (await probeHttp(url)) {
      return;
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for SciStudio HTTP endpoint: ${url}`);
}

function cacheBustedUrl(url, attempt) {
  try {
    const parsed = new URL(url);
    parsed.searchParams.set("_scistudio_desktop_boot", `${Date.now()}-${attempt}`);
    return parsed.toString();
  } catch {
    return url;
  }
}

async function pageHasRendered(window) {
  return window.webContents
    .executeJavaScript(
      "(() => { const root = document.getElementById('root'); return Boolean(root && root.childElementCount > 0) || document.body.innerText.trim().length > 0; })()",
      true
    )
    .catch(() => false);
}

// #2179: `onRendered` is called only on the path that proves the shell worked --
// the renderer finished loading *and* painted. The retry and error-page paths
// deliberately do not call it: a window showing an error page is not evidence
// that this shell build is worth rolling back to.
function loadBeforeShowing(window, url, attempt = 0, onRendered = null) {
  const show = () => {
    if (!window.isDestroyed() && !window.isVisible()) {
      window.show();
    }
    // #2068: hand over only once the real window is up, so the two are never
    // both absent and the user sees no gap.
    closeSplash();
  };

  window.webContents.once("did-finish-load", async () => {
    const rendered = await pageHasRendered(window);
    if (rendered || attempt >= 1) {
      show();
      if (rendered && typeof onRendered === "function") {
        onRendered();
      }
      return;
    }
    safeError("[scistudio] blank first paint before window show; retrying once");
    loadBeforeShowing(window, cacheBustedUrl(url, attempt + 1), attempt + 1, onRendered);
  });

  window.webContents.once("did-fail-load", (_event, _code, _description, validatedUrl) => {
    if (attempt >= 1) {
      safeError(`[scistudio] failed to load ${validatedUrl}; showing error page`);
      show();
      return;
    }
    safeError(`[scistudio] failed to load ${validatedUrl}; retrying once`);
    loadBeforeShowing(window, cacheBustedUrl(url, attempt + 1), attempt + 1, onRendered);
  });

  window.loadURL(url);
}

// #2068: the main window is deliberately hidden until the SPA has painted, and
// everything before that — mandatory-update check, interpreter start, import
// chain, registry scans — is silent. Measured at ~16s on a healthy launch, all
// of it with nothing on screen. The splash owns that window of time and reports
// the phase the main process is already in.
function createSplashWindow() {
  const splash = new BrowserWindow({
    width: 380,
    height: 260,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    frame: false,
    show: false,
    center: true,
    skipTaskbar: true,
    title: "SciStudio",
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#171a21" : "#f7f8fb",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  splash.once("ready-to-show", () => {
    if (!splash.isDestroyed()) {
      splash.show();
    }
  });
  // The status set before the page finished loading would have been dropped by
  // executeJavaScript, so replay the latest one once the function exists.
  splash.webContents.on("did-finish-load", () => {
    applySplashStatus(splash);
  });
  splash.loadFile(path.join(__dirname, "splash.html"));
  return splash;
}

let splashStatusText = "Starting…";

function applySplashStatus(splash) {
  if (!splash || splash.isDestroyed()) {
    return;
  }
  splash.webContents
    .executeJavaScript(
      `window.__scistudioSplashStatus && window.__scistudioSplashStatus(${JSON.stringify(splashStatusText)})`,
      true
    )
    .catch(() => {
      // The splash is cosmetic; a failed status update must never break startup.
    });
}

function splashStatus(message) {
  splashStatusText = message;
  safeLog(`[scistudio] splash: ${message}`);
  applySplashStatus(splashWindow);
}

function closeSplash() {
  if (!splashWindow || splashWindow.isDestroyed()) {
    splashWindow = null;
    return;
  }
  const splash = splashWindow;
  splashWindow = null;
  splash.close();
}

// #2097: the About dialog and the menu that reaches it.
//
// There was no menu code at all, so Electron's default menu applied. That menu
// shows `app.getVersion()` on macOS -- the version baked into the packaged
// package.json, i.e. the INSTALLER BASELINE -- and offers no About item at all
// on Windows or Linux. Reporting the baseline is wrong here by construction:
// once a patch is applied the app is running a different build than the one
// that was installed, which is the entire point of OTA.
//
// So About reports the effective build, and names the installed baseline
// separately whenever the two differ -- the pair a support conversation needs.
function aboutText() {
  const baseline = baselineVersion();
  const effective = effectiveBuild();
  const lines = [`Version ${ota.displayBuildVersion(baseline.base, effective)}`];
  if (effective !== baseline.build) {
    lines.push(
      `Installed ${ota.displayBuildVersion(baseline.base, baseline.build)}, updated without reinstalling`
    );
  }
  lines.push("");
  lines.push(
    `Electron ${process.versions.electron} · Chromium ${process.versions.chrome} · Node ${process.versions.node}`
  );
  lines.push("");
  lines.push(LICENSE_NAME);
  lines.push(COPYRIGHT);
  return lines.join("\n");
}

async function showAbout() {
  await dialog.showMessageBox({
    type: "info",
    title: "About SciStudio",
    message: "SciStudio",
    detail: aboutText(),
    buttons: ["OK"],
    defaultId: 0,
    cancelId: 0
  });
}

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    title: "SciStudio",
    icon: appIconPath(),
    backgroundColor: "#f7f8fb",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.js")
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  // #2179: Electron reports a preload that threw, and nothing here used to
  // listen. The main window is sandboxed, so its preload gets a restricted
  // `require` -- a shell patch that adds a relative import to preload.js aborts
  // before `contextBridge.exposeInMainWorld`, `window.scistudioDesktop`
  // disappears, and every bridge with it. None of that stops the backend
  // answering, so without this the broken build was recorded as known-good.
  mainWindow.webContents.on("preload-error", (_event, preloadPath, error) => {
    noteShellFault(`preload ${path.basename(preloadPath)} failed: ${error.message}`);
  });

  // #1741: capture renderer-process console output so frontend logs persist in
  // a packaged app, where beta testers have no DevTools to read.
  mainWindow.webContents.on("console-message", (_event, level, message, lineNumber, sourceId) => {
    const tag = level >= 3 ? "error" : level === 2 ? "warn" : "info";
    safeWrite(
      level >= 2 ? process.stderr : process.stdout,
      `[renderer:${tag}] ${message} (${sourceId}:${lineNumber})`
    );
  });

  // #2179: the shell has proved itself only now -- window created, preload
  // clean, renderer painted. This is what disarms the crash-loop quarantine.
  loadBeforeShowing(mainWindow, url, 0, () => recordKnownGood(effectiveBuild()));
}

function stopRuntime() {
  if (!runtimeProcess) {
    return;
  }

  const child = runtimeProcess;
  runtimeProcess = null;
  if (!backgroundMode.isChildRunning(child)) {
    return;
  }
  exitingRuntimeChildren.add(child);
  child.once("exit", () => {
    exitingRuntimeChildren.delete(child);
  });

  requestGracefulStop(child);
  // #2280 (AU1/AU2 P2-2): escalate on liveness. The guard used to be
  // `!child.killed`, but Node sets `killed` the moment SIGTERM is *sent*, so
  // the escalation never fired and a backend that ignored SIGTERM kept running.
  setTimeout(() => {
    if (backgroundMode.isChildRunning(child)) {
      safeError(`[scistudio] runtime still running ${STOP_ESCALATION_MS} ms after the stop request; force-killing it`);
      forceKillRuntime(child);
    }
  }, STOP_ESCALATION_MS).unref();
}

// #2327: ask the backend to shut down gracefully, so its lifespan ends live
// workflow runs with a terminal lineage status. POSIX delivers SIGTERM. On
// Windows Node's kill() terminates outright, so the request is closing stdin,
// which the backend watches when SCISTUDIO_STOP_ON_STDIN_EOF is set.
function requestGracefulStop(child) {
  if (process.platform === "win32") {
    try {
      if (child.stdin && !child.stdin.destroyed) {
        child.stdin.end();
      }
    } catch (error) {
      safeError(`[scistudio] could not ask the runtime to stop: ${error.message}`);
    }
    return;
  }
  child.kill("SIGTERM");
}

function forceKillRuntime(child) {
  if (process.platform === "win32") {
    const killer = spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore"
    });
    killer.on("error", (error) => safeError(`[scistudio] taskkill failed: ${error.message}`));
    return;
  }
  child.kill("SIGKILL");
}

// #2280: stopRuntime, then wait for every backend that is still exiting --
// including one an earlier Stop already signalled (AU2 P3-2) -- to actually
// exit. A relaunch that raced the old backend would find the remembered port
// still taken, come back on a new one, and invalidate the address an external
// AI tool is holding. Resolves true once they have all exited, false if the
// last-resort bound ran out first.
function stopRuntimeAndWait(timeoutMs) {
  stopRuntime();
  const pending = [...exitingRuntimeChildren].filter((child) => backgroundMode.isChildRunning(child));
  if (pending.length === 0) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    let remaining = pending.length;
    const timer = setTimeout(() => resolve(false), timeoutMs);
    for (const child of pending) {
      child.once("exit", () => {
        remaining -= 1;
        if (remaining === 0) {
          clearTimeout(timer);
          resolve(true);
        }
      });
    }
  });
}

// #2327: whether a backend is still running -- the current one, or one a Stop
// already signalled.
function runtimeStillRunning() {
  if (runtimeProcess && backgroundMode.isChildRunning(runtimeProcess)) {
    return true;
  }
  return [...exitingRuntimeChildren].some((child) => backgroundMode.isChildRunning(child));
}

// #2327: a quit that waits for the backend still looks immediate.
function hideWindowsForQuit() {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) {
      window.hide();
    }
  }
}

// #2280 (owner decision 5): every relaunch -- mandatory and optional OTA, and
// the #1784 package-update relaunch -- stops the backend (the background
// instance included) before exiting, and brings the process back in the mode it
// was running in rather than at the picker.
async function stopRuntimeAndRelaunch() {
  isQuitting = true;
  const exited = await stopRuntimeAndWait(RELAUNCH_STOP_TIMEOUT_MS);
  if (!exited) {
    safeError(`[scistudio] the backend had not exited after ${RELAUNCH_STOP_TIMEOUT_MS} ms; relaunching anyway`);
  }
  const args = backgroundMode.relaunchArgs(process.argv, launchMode);
  if (args) {
    app.relaunch({ args });
  } else {
    app.relaunch();
  }
  app.exit(0);
}

// --------------------------------------------------------------------------- //
// #2280 (ADR-055 section 7, spec adr-055-local-background-runtime): launch
// modes and the external-AI background runtime.
//
// Desktop mode is today's flow. External-AI mode runs the same runtime chain
// with no main window, keeps this process resident as the backend's owner, and
// shows a tray icon and a small connection window with the address. The
// backend stops with this process in both modes (owner decision 3): quitting
// runs stopRuntime, a force-killed Electron is covered by the POSIX parent
// watchdog and, on Windows, by the kill-on-close job object libuv puts every
// non-detached child in. The decisions are pure in desktop/background-mode.js.
// --------------------------------------------------------------------------- //
function launchModePath() {
  return path.join(app.getPath("userData"), backgroundMode.PREFERENCE_FILE);
}

function readModePreference() {
  return backgroundMode.parseModePreference(readJsonSafe(launchModePath()));
}

function writeModePreference(preference) {
  try {
    writeJsonAtomic(launchModePath(), backgroundMode.serializeModePreference(preference));
  } catch (error) {
    // Best-effort: failing to remember the choice only means being asked again.
    safeError(`[scistudio] failed to remember the launch mode: ${error.message}`);
  }
}

function currentStartupSetting() {
  return backgroundMode.startupSettingOf(readModePreference());
}

// Owner decision 1: the remembered choice stays changeable -- from the
// application menu, the tray, and the connection window.
function setStartupSetting(setting) {
  const next = backgroundMode.applyStartupSetting(readModePreference(), setting);
  writeModePreference(next);
  safeLog(`[scistudio] startup mode set to ${backgroundMode.startupSettingOf(next)}`);
  installApplicationMenu();
  updateTray();
  pushConnectionState();
}

// Runs at module load, in every process, before the single-instance lock.
function secondLaunchRequestedMode() {
  try {
    return backgroundMode.requestedModeForSecondLaunch({
      argvMode: backgroundMode.parseLaunchModeArg(process.argv),
      preference: readModePreference()
    });
  } catch {
    return null;
  }
}

// Returns the launch mode, or null when the splash was closed while asking.
async function chooseLaunchMode() {
  const decision = backgroundMode.resolveStartupMode({
    argvMode: backgroundMode.parseLaunchModeArg(process.argv),
    preference: readModePreference()
  });
  if (decision.kind === "mode") {
    safeLog(`[scistudio] launch mode ${decision.mode} (${decision.source})`);
    return decision.mode;
  }
  const outcome = await pickModeOnSplash(decision.suggested);
  if (outcome.kind === "closed") {
    return null;
  }
  if (outcome.kind !== "picked") {
    // The picker never became usable: fall back to today's flow rather than
    // keep the app from starting.
    return backgroundMode.MODES.DESKTOP;
  }
  const { pick } = outcome;
  writeModePreference(backgroundMode.preferenceAfterPick(pick));
  // The Startup Mode radio must reflect a fresh "don't ask again".
  installApplicationMenu();
  safeLog(`[scistudio] launch mode ${pick.mode} (picked${pick.remember ? ", remembered" : ""})`);
  return pick.mode;
}

// Asks on the splash itself. splash.html's picker returns a promise that
// executeJavaScript waits on, so the splash still needs no preload (#2068).
// Resolves one of:
//   { kind: "picked", pick }  - the user chose a mode
//   { kind: "closed" }        - the splash was closed while asking (a quit)
//   { kind: "unusable" }      - the splash failed to load, took too long, or
//                               has no working picker; the caller starts the
//                               desktop flow, so a broken picker can never keep
//                               the app from starting (AU1 P3-4)
// `pickerRendered` is set once the picker is confirmed on screen; see
// releaseBootMarkerOnQuit.
function pickModeOnSplash(suggested) {
  const splash = splashWindow;
  if (!isOpen(splash)) {
    return Promise.resolve({ kind: "unusable" });
  }
  safeLog("[scistudio] splash: asking for the launch mode");
  return new Promise((resolve) => {
    let settled = false;
    let loadTimer = null;
    const finish = (outcome) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(loadTimer);
      splash.removeListener("closed", onClosed);
      resolve(outcome);
    };
    const onClosed = () => finish({ kind: "closed" });
    splash.once("closed", onClosed);
    const giveUp = (reason) => {
      if (!settled) {
        safeError(`[scistudio] launch-mode picker unavailable (${reason}); starting the desktop app`);
      }
      finish({ kind: "unusable" });
    };

    const ask = async () => {
      clearTimeout(loadTimer);
      if (settled || splash.isDestroyed()) {
        return;
      }
      const present = await splash.webContents
        .executeJavaScript("typeof window.__scistudioSplashPickMode === 'function'", true)
        .catch(() => false);
      if (settled) {
        return;
      }
      if (present !== true) {
        giveUp("the splash has no picker");
        return;
      }
      pickerRendered = true;
      splash.webContents
        .executeJavaScript(`window.__scistudioSplashPickMode(${JSON.stringify(suggested)})`, true)
        .then((raw) => {
          const pick = backgroundMode.parseModePick(raw);
          if (!pick) {
            giveUp("the splash returned no usable launch mode");
            return;
          }
          finish({ kind: "picked", pick });
        })
        .catch((error) => {
          if (splash.isDestroyed()) {
            finish({ kind: "closed" });
            return;
          }
          giveUp(error.message);
        });
    };
    if (splash.webContents.isLoading()) {
      splash.webContents.once("did-finish-load", ask);
      splash.webContents.once("did-fail-load", () => giveUp("the splash failed to load"));
      loadTimer = setTimeout(() => giveUp("the splash did not load in time"), SPLASH_PICKER_LOAD_TIMEOUT_MS);
    } else {
      ask();
    }
  });
}

function isOpen(window) {
  return Boolean(window) && !window.isDestroyed();
}

function revealWindow(window) {
  if (!isOpen(window)) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  window.show();
  window.focus();
}

function handleSecondInstance(argv, additionalData) {
  const requestedMode = backgroundMode.requestedModeFromSecondInstance({ argv, additionalData });
  const route = backgroundMode.routeSecondInstance({
    runningMode: launchMode,
    requestedMode,
    mainWindowOpen: isOpen(mainWindow)
  });
  safeLog(`[scistudio] second launch (requested ${requestedMode || "no mode"}): ${route}`);
  applyInstanceRoute(route);
}

// Acts on a routeSecondInstance / routeActivate verdict.
function applyInstanceRoute(route) {
  if (route === "focus-main-window") {
    revealWindow(mainWindow);
  } else if (route === "show-connection-window") {
    showConnectionWindow();
  } else if (route === "attach-desktop-window") {
    openDesktopWindow();
  } else if (route === "promote-to-external-ai") {
    promoteToExternalAi();
  } else if (isOpen(splashWindow) && splashWindow.isVisible()) {
    revealWindow(splashWindow);
  }
}

function currentConnectionView() {
  return backgroundMode.connectionView({ ...serviceState, startupSetting: currentStartupSetting() });
}

function pushConnectionState() {
  if (isOpen(connectionWindow)) {
    connectionWindow.webContents.send(
      backgroundMode.CONNECTION_STATE_CHANNEL,
      currentConnectionView()
    );
  }
}

function setServiceState(patch) {
  serviceState = { ...serviceState, ...patch };
  pushConnectionState();
  updateTray();
  maybeVouchForShellInBackground();
  maybeQuitWithoutWindows();
}

// #2280, owner decision 2026-09-11 (AU1 P2-3 / AU2 P2-1 / Codex 3985756074):
// window-all-closed only judges the moment the last window closes. A service
// that stops, crashes, or fails afterwards -- or a Stop still in flight when
// the connection window was closed -- must quit the app too, so the same rule
// is applied on every status change while no window is open.
function maybeQuitWithoutWindows() {
  if (isQuitting) {
    return;
  }
  const quit = backgroundMode.quitOnServiceChange({
    mode: launchMode,
    status: serviceState.status,
    openWindowCount: BrowserWindow.getAllWindows().length
  });
  if (quit) {
    safeLog(`[scistudio] service ${serviceState.status} with no window open; quitting`);
    app.quit();
  }
}

function markServiceRunning(ready) {
  setServiceState({
    status: backgroundMode.SERVICE_STATUS.RUNNING,
    readyUrl: ready.url,
    address: backgroundMode.connectionAddress(ready.url),
    detail: null
  });
}

// #2179/#2280: in desktop mode the shell vouches for itself once the main
// window paints (createWindow). External-AI mode has no main window, so it
// vouches once its own window is proven -- the connection page sent its first
// action over IPC, which takes its script, its sandboxed preload and the IPC
// handler all working (AU1 P3-3) -- AND the backend is running. Readiness
// alone never records it (desktop/test/shell-known-good.test.js). Without this
// a patched shell would never be recorded as known-good in this mode, and the
// loader would quarantine a working patch on the next launch.
function maybeVouchForShellInBackground() {
  if (backgroundShellVouched || launchMode !== backgroundMode.MODES.EXTERNAL_AI) {
    return;
  }
  if (!connectionBridgeReady || serviceState.status !== backgroundMode.SERVICE_STATUS.RUNNING) {
    return;
  }
  backgroundShellVouched = true;
  recordKnownGood(effectiveBuild());
}

// Follow the backend once it has printed its ready line. A crash while this
// process stays resident surfaces as a crashed status with a restart action
// (FR-008) instead of a silently dead address.
function trackRuntime(child) {
  serviceChild = child;
  child.once("exit", (code, signal) => {
    if (serviceChild !== child) {
      return;
    }
    serviceChild = null;
    if (runtimeProcess === child) {
      // Nothing left to stop, and a later stopRuntime must not taskkill a PID
      // the OS may already have handed to another process.
      runtimeProcess = null;
    }
    // A death while a background start is still in flight is reported by
    // startBackgroundService itself, with the exit status, in one state change.
    if (isQuitting || serviceStartInFlight) {
      return;
    }
    const status = backgroundMode.statusAfterExit({ status: serviceState.status, stopRequested });
    safeLog(`[scistudio] runtime exited code=${code} signal=${signal}; service ${status}`);
    setServiceState({
      status,
      detail:
        status === backgroundMode.SERVICE_STATUS.STOPPED
          ? null
          : `The SciStudio service exited (code ${code}, signal ${signal}). The desktop log has the details.`
    });
  });
}

// Resolves once `child` has exited (at once if it already has).
function childExited(child) {
  return new Promise((resolve) => {
    if (!backgroundMode.isChildRunning(child)) {
      resolve();
      return;
    }
    child.once("exit", () => resolve());
  });
}

function throwIfExitedWhileStarting(child) {
  if (!backgroundMode.isChildRunning(child)) {
    throw new Error(
      `The SciStudio service exited while starting (code ${child.exitCode}, signal ${child.signalCode}). The desktop log has the details.`
    );
  }
}

// External-AI mode's start and restart: the same chain the desktop flow uses --
// python candidates, runtime env, OTA rollback, ready line, HTTP readiness, port
// memory -- with no main window at the end. The address is published only once
// both readiness layers passed.
async function startBackgroundService() {
  if (serviceStartInFlight || serviceChild) {
    return;
  }
  const { STARTING, STOPPED, FAILED } = backgroundMode.SERVICE_STATUS;
  serviceStartInFlight = true;
  stopRequested = false;
  setServiceState({ status: STARTING, readyUrl: null, address: null, detail: null });
  try {
    const { ready, child } = await startRuntimeWithRollback();
    trackRuntime(child);
    safeLog(`[scistudio] waiting for HTTP readiness at ${ready.url}`);
    // AU1 P3-5 / AU2 P3-1: a backend that dies during readiness ends the wait
    // at once and fails with its real exit status, so Restart works
    // immediately. It used to spend the whole 30 s readiness timeout, refuse
    // Restart meanwhile, and then overwrite the exit reason with the timeout.
    const httpReady = waitForHttpReady(ready.url, () => backgroundMode.isChildRunning(child));
    httpReady.catch(() => {});
    await Promise.race([httpReady, childExited(child)]);
    throwIfExitedWhileStarting(child);
    // #1986: keep the origin stable across launches, and so the address.
    rememberRuntimePort(runtimePortModule.boundPortFromReady(ready));
    // A desktop window may attach later; it must not load a cached old bundle.
    await clearCacheOnBuildChange();
    throwIfExitedWhileStarting(child);
    markServiceRunning(ready);
    if (isOpen(mainWindow)) {
      // A restart can come back on another port; keep an attached desktop
      // window on the live backend.
      mainWindow.loadURL(launchUrl(ready.url));
    }
    if (!backgroundUpdateChecked) {
      backgroundUpdateChecked = true;
      maybeCheckForUpdate().catch((error) => {
        safeError(`[scistudio] update check error: ${error.message}`);
      });
    }
  } catch (error) {
    safeError(
      `[scistudio] background service failed to start: ${error instanceof Error ? error.stack : String(error)}`
    );
    // Never leave a half-started backend behind; detach tracking first so its
    // exit does not overwrite the failure shown below.
    serviceChild = null;
    stopRuntime();
    if (!isQuitting) {
      setServiceState(
        stopRequested
          ? { status: STOPPED, detail: null }
          : { status: FAILED, detail: error instanceof Error ? error.message : String(error) }
      );
    }
  } finally {
    serviceStartInFlight = false;
  }
}

// FR-004: explicit stop goes through the existing stopRuntime tree-kill, and
// the exit it causes turns the status into a visible "Stopped".
// Both ways of stopping the service -- Stop Service, and Stop and Quit (AU1
// P3-7 / AU2 P3-3) -- ask first while a desktop window is attached, because
// that window's unsaved work depends on the service. True when there is no such
// window or the user agreed.
async function confirmStopUnderDesktopWindow(quitting) {
  if (!isOpen(mainWindow)) {
    return true;
  }
  const choice = await dialog.showMessageBox(isOpen(connectionWindow) ? connectionWindow : undefined, {
    type: "warning",
    title: quitting ? "Quit SciStudio?" : "Stop the SciStudio service?",
    message: quitting ? "Stop the SciStudio service and quit?" : "Stop the SciStudio service?",
    detail: quitting
      ? "The open desktop window will close. Save your work first."
      : "The open desktop window uses this service and will stop working. Save your work first.",
    buttons: [quitting ? "Stop and Quit" : "Stop Service", "Cancel"],
    defaultId: 1,
    cancelId: 1
  });
  return choice.response === 0;
}

async function stopBackgroundService() {
  const { RUNNING, UNRESPONSIVE, STOPPING, STOPPED } = backgroundMode.SERVICE_STATUS;
  if (![RUNNING, UNRESPONSIVE].includes(serviceState.status)) {
    return;
  }
  if (!(await confirmStopUnderDesktopWindow(false))) {
    return;
  }
  stopRequested = true;
  if (!serviceChild) {
    setServiceState({ status: STOPPED, detail: null });
    return;
  }
  setServiceState({ status: STOPPING, detail: null });
  safeLog("[scistudio] stopping the background service");
  stopRuntime();
}

function restartBackgroundService() {
  if (!currentConnectionView().canRestart) {
    return;
  }
  safeLog("[scistudio] restarting the background service");
  startBackgroundService();
}

// The connection window re-validates on focus (sleep/wake, a backend that
// stopped answering); only a service believed to be up is probed.
async function revalidateServiceStatus() {
  const { RUNNING, UNRESPONSIVE } = backgroundMode.SERVICE_STATUS;
  const isUp = () => [RUNNING, UNRESPONSIVE].includes(serviceState.status);
  if (!isUp() || !serviceState.readyUrl) {
    pushConnectionState();
    return;
  }
  const probeOk = await probeHttp(serviceState.readyUrl);
  if (!isUp()) {
    return;
  }
  const status = backgroundMode.statusAfterProbe({ status: serviceState.status, probeOk });
  if (status === serviceState.status) {
    pushConnectionState();
    return;
  }
  setServiceState({
    status,
    detail: probeOk
      ? null
      : "The service is running but did not answer. It may be busy; stop and restart it if this persists."
  });
}

function copyServiceAddress() {
  const view = currentConnectionView();
  if (!view.canCopy) {
    return false;
  }
  clipboard.writeText(view.address);
  return true;
}

// "Open in desktop mode": a desktop window on the running backend. With nothing
// to attach to yet, the connection window shows why instead.
function openDesktopWindow() {
  if (isOpen(mainWindow)) {
    revealWindow(mainWindow);
    return;
  }
  if (serviceState.status !== backgroundMode.SERVICE_STATUS.RUNNING || !serviceState.readyUrl) {
    showConnectionWindow();
    return;
  }
  const url = launchUrl(serviceState.readyUrl);
  safeLog(`[scistudio] attaching a desktop window to ${url}`);
  createWindow(url);
}

// Quitting runs before-quit, and so the existing stopRuntime.
async function stopAndQuit() {
  safeLog("[scistudio] stop and quit requested");
  if (!(await confirmStopUnderDesktopWindow(true))) {
    safeLog("[scistudio] stop and quit cancelled");
    return;
  }
  app.quit();
}

async function handleConnectionAction(event, action, payload) {
  if (!isOpen(connectionWindow) || event.sender !== connectionWindow.webContents) {
    return null;
  }
  if (!backgroundMode.CONNECTION_ACTIONS.includes(action)) {
    safeError(`[scistudio] ignoring unknown connection action ${String(action)}`);
    return currentConnectionView();
  }
  if (!connectionBridgeReady) {
    // AU1 P3-3: the page's first action reaching this handler proves the page
    // script, its preload and the IPC path -- more than the preload's bridge
    // merely existing.
    connectionBridgeReady = true;
    maybeVouchForShellInBackground();
  }
  if (action === "copy-address") {
    copyServiceAddress();
  } else if (action === "open-desktop") {
    openDesktopWindow();
  } else if (action === "stop") {
    await stopBackgroundService();
  } else if (action === "restart") {
    restartBackgroundService();
  } else if (action === "show-logs") {
    const failure = await shell.openPath(desktopLogDir());
    if (failure) {
      safeError(`[scistudio] could not open the log directory: ${failure}`);
    }
  } else if (action === "set-startup") {
    setStartupSetting(payload);
  } else if (action === "stop-and-quit") {
    await stopAndQuit();
  }
  return currentConnectionView();
}

function showConnectionWindow() {
  if (isOpen(connectionWindow)) {
    revealWindow(connectionWindow);
    return;
  }
  const window = new BrowserWindow({
    width: 480,
    height: 400,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    title: "SciStudio — External AI",
    icon: appIconPath(),
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#171a21" : "#f7f8fb",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "connection-preload.js")
    }
  });
  connectionWindow = window;
  // Windows and Linux attach the application menu to every window; its project
  // entries mean nothing here, and Startup Mode is on the page itself.
  window.removeMenu();
  // A local status page: it never opens or navigates anywhere.
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (navigation) => navigation.preventDefault());
  window.webContents.on("preload-error", (_event, preloadPath, error) => {
    noteShellFault(`preload ${path.basename(preloadPath)} failed: ${error.message}`);
  });
  window.webContents.on("did-finish-load", () => {
    pushConnectionState();
  });
  window.on("focus", () => {
    revalidateServiceStatus().catch((error) => {
      safeError(`[scistudio] status re-validation failed: ${error.message}`);
    });
  });
  window.once("ready-to-show", () => {
    if (!window.isDestroyed()) {
      window.show();
    }
  });
  window.on("closed", () => {
    if (connectionWindow === window) {
      connectionWindow = null;
    }
  });
  window.loadFile(path.join(__dirname, "connection.html"));
}

function trayImage() {
  // Resolved next to this file: the tray images travel with the shell
  // (SHELL_FILES), so a patched shell never depends on an older installed
  // bundle having them.
  if (process.platform === "darwin") {
    // macOS menu-bar convention: a monochrome template image the system tints
    // for light and dark menu bars; the @2x sibling is picked up automatically.
    const image = nativeImage.createFromPath(path.join(__dirname, "assets", "trayTemplate.png"));
    image.setTemplateImage(true);
    return image;
  }
  return nativeImage.createFromPath(path.join(__dirname, "assets", "tray.png"));
}

// Owner decision 2: the tray exists in external-AI mode only.
function ensureTray() {
  if (tray && !tray.isDestroyed()) {
    return;
  }
  try {
    tray = new Tray(trayImage());
  } catch (error) {
    // A desktop without a tray host (e.g. GNOME without the AppIndicator
    // extension) still reaches the instance: launching SciStudio again reopens
    // the connection window through second-instance.
    safeError(`[scistudio] tray unavailable: ${error.message}`);
    tray = null;
    return;
  }
  tray.on("click", () => {
    // Windows opens the context menu on right-click only; a left-click should
    // still get the user somewhere useful.
    if (process.platform === "win32") {
      showConnectionWindow();
    }
  });
  updateTray();
}

function updateTray() {
  if (!tray || tray.isDestroyed()) {
    return;
  }
  const view = currentConnectionView();
  tray.setToolTip(`SciStudio — External AI (${view.label})`);
  tray.setContextMenu(
    Menu.buildFromTemplate(
      buildTrayMenuTemplate({
        view,
        showConnectionWindow,
        copyAddress: copyServiceAddress,
        openDesktopWindow,
        setStartupSetting,
        stopAndQuit
      })
    )
  );
}

function enterExternalAiMode() {
  launchMode = backgroundMode.MODES.EXTERNAL_AI;
  ensureTray();
  showConnectionWindow();
}

// Desktop -> external AI on the running backend (File > External AI
// Connection, or a second launch asking for external AI). The backend is reused
// as-is; from here on closing windows leaves it running.
function promoteToExternalAi() {
  if (launchMode === backgroundMode.MODES.EXTERNAL_AI) {
    showConnectionWindow();
    return;
  }
  safeLog("[scistudio] switching the running app to external-AI mode");
  enterExternalAiMode();
}

function openExternalAiConnection() {
  if (launchMode === null) {
    // Still at the splash; there is no service to connect to yet.
    return;
  }
  promoteToExternalAi();
}

// #2097: entry point called by the frozen bootstrap loader once it has chosen a
// shell. Everything above runs at require time and needs no host facts; every
// lifecycle registration below does, so it waits for this call. The
// single-instance lock above has already run, and the whenReady handler still
// checks it.
function start(injectedHost) {
  hostFacts = injectedHost;

  app.whenReady().then(async () => {
    // #1867: a second instance never acquired the lock; it has already requested
    // quit and must not start a runtime or window.
    if (!gotSingleInstanceLock) {
      return;
    }
    try {
      safeLog("[scistudio] electron ready");
      installApplicationMenu();
      splashWindow = createSplashWindow();
      // #2280: the launch mode is settled first, so an update applied below
      // relaunches straight into it (backgroundMode.relaunchArgs).
      const mode = await chooseLaunchMode();
      if (mode === null) {
        // The splash was closed while it was asking: that is a quit.
        closeSplash();
        app.quit();
        return;
      }
      launchMode = mode;
      // #1868: enforce a mandatory OTA update before starting the runtime/window.
      // Fail-open: returns true (continue) unless a fetched manifest marks the
      // update mandatory and the user declines or it cannot be applied.
      splashStatus("Checking for updates…");
      const proceed = await maybeEnforceMandatoryUpdate();
      if (!proceed) {
        closeSplash();
        return;
      }
      if (launchMode === backgroundMode.MODES.EXTERNAL_AI) {
        // #2280: no main window. The connection window opens before the splash
        // closes, so the splash is never the last window standing, and it
        // reports progress until the address can be shown.
        enterExternalAiMode();
        closeSplash();
        await startBackgroundService();
        return;
      }
      splashStatus("Starting the SciStudio runtime…");
      const { ready, child } = await startRuntimeWithRollback();
      // #2280: tracked in desktop mode too, so switching this session to
      // external-AI mode later starts from the real service state.
      trackRuntime(child);
      safeLog(`[scistudio] waiting for HTTP readiness at ${ready.url}`);
      splashStatus("Loading blocks and data types…");
      await waitForHttpReady(ready.url);
      // #1986: the runtime answered on this port, so it is worth reusing next
      // launch to keep the renderer origin (and its persisted UI state) stable.
      rememberRuntimePort(runtimePortModule.boundPortFromReady(ready));
      markServiceRunning(ready);
      // #1775/#2179: the runtime reaching ready says the *backend* half of the
      // patch works. The shell half is vouched for from createWindow, once the
      // renderer has actually painted.
      await clearCacheOnBuildChange();
      const url = launchUrl(ready.url);
      safeLog(`[scistudio] creating window for ${url}`);
      splashStatus("Loading the interface…");
      createWindow(url);
      // #1775: check for an OTA update after the window is up so startup is never
      // blocked on the network. Fire-and-forget; failures are logged, not fatal.
      maybeCheckForUpdate().catch((error) => {
        safeError(`[scistudio] update check error: ${error.message}`);
      });
    } catch (error) {
      safeError(`[scistudio] startup failed: ${error instanceof Error ? error.stack : String(error)}`);
      closeSplash();
      await dialog.showMessageBox({
        type: "error",
        title: "SciStudio failed to start",
        message: "SciStudio runtime did not start.",
        detail: error instanceof Error ? error.message : String(error)
      });
      app.quit();
    }
  });

  // #2327: quitting asks the backend for a graceful stop and waits for it --
  // up to RELAUNCH_STOP_TIMEOUT_MS, with stopRuntime's force-kill inside that
  // bound -- so the backend's shutdown can end live workflow runs with a
  // terminal lineage status. The windows hide at once, so the quit still looks
  // immediate; the quit resumes once the backend has exited.
  app.on("before-quit", (event) => {
    isQuitting = true;
    if (quitStopState === "done") {
      return;
    }
    if (quitStopState === "idle") {
      // #2280 (AU1 P2-1): before stopRuntime, while the quit is still ours.
      releaseBootMarkerOnQuit();
    }
    if (!runtimeStillRunning()) {
      quitStopState = "done";
      stopRuntime();
      return;
    }
    event.preventDefault();
    hideWindowsForQuit();
    if (quitStopState === "stopping") {
      return;
    }
    quitStopState = "stopping";
    stopRuntimeAndWait(RELAUNCH_STOP_TIMEOUT_MS).then((exited) => {
      if (!exited) {
        safeError(`[scistudio] the backend had not exited ${RELAUNCH_STOP_TIMEOUT_MS} ms into the quit; quitting anyway`);
      }
      quitStopState = "done";
      app.quit();
    });
  });

  app.on("window-all-closed", () => {
    // #2280: desktop mode quits as it always has, on every platform; external-AI
    // mode stays resident while it owns a live backend. A status change after
    // this point is judged again by maybeQuitWithoutWindows.
    const action = backgroundMode.windowAllClosedAction({
      mode: launchMode,
      status: serviceState.status
    });
    if (action === "quit") {
      app.quit();
    }
  });

  app.on("activate", () => {
    // #2280 (AU1 P3-6 / AU2 P3-5): on macOS, opening the running app again from
    // Finder or the Dock activates this process instead of starting a second
    // one, so it is routed here like a second launch: the desktop window, the
    // connection window, or a desktop window attached to the running backend.
    const route = backgroundMode.routeActivate({
      runningMode: launchMode,
      requestedMode: backgroundMode.requestedModeForSecondLaunch({ preference: readModePreference() }),
      mainWindowOpen: isOpen(mainWindow)
    });
    applyInstanceRoute(route);
  });

  // #1741: persist crashes that would otherwise vanish in a packaged app.
  process.on("uncaughtException", (error) => {
    safeError(`[scistudio] uncaughtException: ${error instanceof Error ? error.stack : String(error)}`);
  });

  process.on("unhandledRejection", (reason) => {
    safeError(`[scistudio] unhandledRejection: ${reason instanceof Error ? reason.stack : String(reason)}`);
  });

  app.on("render-process-gone", (_event, _webContents, details) => {
    safeError(`[scistudio] render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`);
  });

  app.on("child-process-gone", (_event, details) => {
    safeError(`[scistudio] child-process-gone: type=${details.type} reason=${details.reason}`);
  });
}

module.exports = { start };
