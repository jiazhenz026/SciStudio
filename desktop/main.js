const { app, BrowserWindow, dialog, ipcMain, session, clipboard } = require("electron");
const { spawn, spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const readline = require("readline");

const ota = require("./ota");
// #1848: alpha-only activation gate. Removed in beta (see issue #1848).
const activation = require("./activation");

// #1784: the in-app Package Manager stages a package update on disk (into the
// scanned installed-packages dir) and then asks the main process to relaunch so
// a fresh interpreter imports the new code. Registered once at module load;
// safeLog is hoisted and only called when the handler fires.
ipcMain.handle("scistudio:relaunch", () => {
  safeLog("[scistudio] relaunch requested by renderer (package update)");
  app.relaunch();
  app.exit(0);
});

const READY_EVENT = "scistudio.ready";
const READY_TIMEOUT_MS = 120000;
const HTTP_READY_TIMEOUT_MS = 30000;
const DEFAULT_DEV_FRONTEND_URL = "http://127.0.0.1:5173";

// #1775: OTA hot-update (backend + embedded frontend).
const OTA_MANIFEST_TIMEOUT_MS = 8000;
const OTA_DOWNLOAD_TIMEOUT_MS = 120000;
const OTA_MAX_REDIRECTS = 5;

let mainWindow = null;
let runtimeProcess = null;
let isQuitting = false;
let cachedMacLoginShellEnv = null;

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
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.join(__dirname, "resources");
}

function repoRoot() {
  return path.resolve(__dirname, "..");
}

function appIconPath() {
  return path.join(__dirname, "assets", "icon.png");
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
  try {
    return (
      ota.parseVersion(require("./package.json").version) || {
        base: "0.0.0",
        channel: "stable",
        build: 0
      }
    );
  } catch {
    return { base: "0.0.0", channel: "stable", build: 0 };
  }
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

function recordKnownGood(build) {
  try {
    writeJsonAtomic(knownGoodPath(), { build });
  } catch (error) {
    safeError(`[scistudio] failed to record known-good build: ${error.message}`);
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
  isQuitting = true;
  stopRuntime();
  app.relaunch();
  app.exit(0);
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
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}

function runtimePort() {
  const requested = process.env.SCISTUDIO_DESKTOP_RUNTIME_PORT;
  if (!requested) {
    return "0";
  }
  const parsed = Number.parseInt(requested, 10);
  if (Number.isInteger(parsed) && parsed >= 0 && parsed <= 65535) {
    return String(parsed);
  }
  safeError(`[scistudio] Ignoring invalid SCISTUDIO_DESKTOP_RUNTIME_PORT=${requested}`);
  return "0";
}

function runtimeArgs(candidate) {
  return [
    ...candidate.argsPrefix,
    "-m",
    "scistudio.cli.main",
    "gui",
    "--port",
    runtimePort(),
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

function spawnRuntimeCandidate(candidate) {
  return spawn(candidate.command, runtimeArgs(candidate), {
    cwd: repoRoot(),
    env: runtimeEnv(),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });
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

function startRuntime() {
  const candidates = pythonCandidates();
  const stderrLines = [];
  safeLog("[scistudio] starting runtime");

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
      const child = spawnRuntimeCandidate(candidate);
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

async function waitForHttpReady(url) {
  const deadline = Date.now() + HTTP_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
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

function loadBeforeShowing(window, url, attempt = 0) {
  const show = () => {
    if (!window.isDestroyed() && !window.isVisible()) {
      window.show();
    }
  };

  window.webContents.once("did-finish-load", async () => {
    const rendered = await pageHasRendered(window);
    if (rendered || attempt >= 1) {
      show();
      return;
    }
    safeError("[scistudio] blank first paint before window show; retrying once");
    loadBeforeShowing(window, cacheBustedUrl(url, attempt + 1), attempt + 1);
  });

  window.webContents.once("did-fail-load", (_event, _code, _description, validatedUrl) => {
    if (attempt >= 1) {
      safeError(`[scistudio] failed to load ${validatedUrl}; showing error page`);
      show();
      return;
    }
    safeError(`[scistudio] failed to load ${validatedUrl}; retrying once`);
    loadBeforeShowing(window, cacheBustedUrl(url, attempt + 1), attempt + 1);
  });

  window.loadURL(url);
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

  // #1741: capture renderer-process console output so frontend logs persist in
  // a packaged app, where beta testers have no DevTools to read.
  mainWindow.webContents.on("console-message", (_event, level, message, lineNumber, sourceId) => {
    const tag = level >= 3 ? "error" : level === 2 ? "warn" : "info";
    safeWrite(
      level >= 2 ? process.stderr : process.stdout,
      `[renderer:${tag}] ${message} (${sourceId}:${lineNumber})`
    );
  });

  loadBeforeShowing(mainWindow, url);
}

function stopRuntime() {
  if (!runtimeProcess || runtimeProcess.killed) {
    return;
  }

  const child = runtimeProcess;
  runtimeProcess = null;

  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore"
    });
    return;
  }

  child.kill("SIGTERM");
  setTimeout(() => {
    if (!child.killed) {
      child.kill("SIGKILL");
    }
  }, 5000).unref();
}

// --------------------------------------------------------------------------- //
// #1848: alpha activation gate. Block startup until a valid per-machine token is
// present so a redistributed copy cannot be opened. ALPHA-ONLY; remove the gate
// window, the IPC handlers, the ensureAlphaActivation() call, and the
// ./activation + ./preload-gate + resources/alpha-gate.html files in beta.
// --------------------------------------------------------------------------- //

// Show the activation gate window and resolve true once the machine is
// activated, or false if the user quits the gate. The IPC handlers are scoped to
// the gate's lifetime and removed on close.
function runActivationGate(ctx) {
  return new Promise((resolve) => {
    let settled = false;

    const gateWindow = new BrowserWindow({
      width: 640,
      height: 600,
      resizable: false,
      fullscreenable: false,
      maximizable: false,
      title: "SciStudio — Alpha Activation",
      icon: appIconPath(),
      backgroundColor: "#f7f8fb",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        preload: path.join(__dirname, "preload-gate.js")
      }
    });

    const cleanup = () => {
      ipcMain.removeHandler("scistudio:alpha-gate-info");
      ipcMain.removeHandler("scistudio:alpha-activate");
      ipcMain.removeHandler("scistudio:alpha-copy");
      ipcMain.removeHandler("scistudio:alpha-quit");
    };

    const finish = (ok) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      if (!gateWindow.isDestroyed()) {
        gateWindow.removeAllListeners("closed");
        gateWindow.close();
      }
      resolve(ok);
    };

    ipcMain.handle("scistudio:alpha-gate-info", () => ({
      fingerprint: ctx.fingerprint,
      configured: Boolean(ctx.publicKeyPem)
    }));

    ipcMain.handle("scistudio:alpha-copy", (_event, text) => {
      clipboard.writeText(String(text || ""));
      return true;
    });

    ipcMain.handle("scistudio:alpha-quit", () => {
      finish(false);
      return true;
    });

    ipcMain.handle("scistudio:alpha-activate", (_event, token) => {
      const result = activation.verifyToken(String(token || ""), ctx.fingerprint, ctx.publicKeyPem);
      if (!result.ok) {
        return { ok: false, reason: result.reason };
      }
      try {
        activation.writeStoredToken(ctx.userDataDir, String(token).trim(), result.payload);
      } catch (error) {
        safeError(`[scistudio] failed to persist activation: ${error.message}`);
      }
      safeLog("[scistudio] alpha activation succeeded");
      // Let the renderer paint the success message before tearing down.
      setTimeout(() => finish(true), 500);
      return { ok: true };
    });

    gateWindow.on("closed", () => finish(false));
    gateWindow.loadFile(path.join(resourcesDir(), "alpha-gate.html"));
  });
}

// Returns true when the app may proceed to launch. When the gate is enabled and
// this machine is not yet activated, shows the gate window and waits.
async function ensureAlphaActivation() {
  if (!activation.gateEnabled(app.isPackaged)) {
    return true;
  }
  const fingerprint = activation.machineFingerprint();
  const publicKeyPem = activation.loadPublicKeyPem(resourcesDir());
  const userDataDir = app.getPath("userData");
  const status = activation.checkActivation({ userDataDir, fingerprint, publicKeyPem });
  if (status.activated) {
    safeLog("[scistudio] alpha activation: valid token for this machine");
    return true;
  }
  safeLog(`[scistudio] alpha activation required (${status.reason}); showing gate`);
  return runActivationGate({ fingerprint, publicKeyPem, userDataDir });
}

app.whenReady().then(async () => {
  try {
    safeLog("[scistudio] electron ready");
    // #1848: alpha gate — do not start the runtime or main window until the
    // machine is activated. Quitting the gate quits the app.
    const activated = await ensureAlphaActivation();
    if (!activated) {
      safeLog("[scistudio] alpha activation not completed; quitting");
      app.quit();
      return;
    }
    const { ready } = await startRuntimeWithRollback();
    safeLog(`[scistudio] waiting for HTTP readiness at ${ready.url}`);
    await waitForHttpReady(ready.url);
    // #1775: the runtime reached ready, so whatever patch is active booted
    // cleanly; remember it as the rollback target for future launches.
    recordKnownGood(effectiveBuild());
    await session.defaultSession.clearCache();
    const url = launchUrl(ready.url);
    safeLog(`[scistudio] creating window for ${url}`);
    createWindow(url);
    // #1775: check for an OTA update after the window is up so startup is never
    // blocked on the network. Fire-and-forget; failures are logged, not fatal.
    maybeCheckForUpdate().catch((error) => {
      safeError(`[scistudio] update check error: ${error.message}`);
    });
  } catch (error) {
    safeError(`[scistudio] startup failed: ${error instanceof Error ? error.stack : String(error)}`);
    await dialog.showMessageBox({
      type: "error",
      title: "SciStudio failed to start",
      message: "SciStudio runtime did not start.",
      detail: error instanceof Error ? error.message : String(error)
    });
    app.quit();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  stopRuntime();
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("activate", () => {
  if (mainWindow) {
    mainWindow.show();
  }
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
