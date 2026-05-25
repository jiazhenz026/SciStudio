const { app, BrowserWindow, dialog, session } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const readline = require("readline");

const READY_EVENT = "scistudio.ready";
const READY_TIMEOUT_MS = 120000;
const HTTP_READY_TIMEOUT_MS = 30000;
const DEFAULT_DEV_FRONTEND_URL = "http://127.0.0.1:5173";

let mainWindow = null;
let runtimeProcess = null;
let isQuitting = false;

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

function safeWrite(stream, message) {
  const line = `${message}\n`;
  try {
    fs.appendFileSync(
      path.join(app.isReady() ? app.getPath("userData") : os.tmpdir(), "scistudio-desktop.log"),
      line
    );
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

function pythonCandidates() {
  const resources = resourcesDir();
  const candidates = [];

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
    candidates.push({ command: "python3", argsPrefix: [], label: "python3" });
    candidates.push({ command: "python", argsPrefix: [], label: "python" });
  }

  return candidates;
}

function runtimeEnv() {
  const resources = resourcesDir();
  const stagedSrc = path.join(resources, "backend", "src");
  const checkoutSrc = path.join(repoRoot(), "src");
  const pythonPathEntries = [stagedSrc, checkoutSrc].filter(Boolean);
  const existingPythonPath = process.env.PYTHONPATH;
  const userHome = process.env.USERPROFILE || process.env.HOME || "";
  const pathEntries = [];

  if (existingPythonPath) {
    pythonPathEntries.push(existingPythonPath);
  }
  if (userHome) {
    pathEntries.push(
      path.join(userHome, ".local", "bin"),
      path.join(userHome, "AppData", "Roaming", "npm")
    );
  }
  pathEntries.push(process.env.PATH || "");

  const env = {
    ...process.env,
    PATH: pathEntries.filter(Boolean).join(path.delimiter),
    PYTHONPATH: pythonPathEntries.join(path.delimiter),
    SCISTUDIO_BUNDLED: "1",
    SCISTUDIO_DESKTOP_RESOURCES: resources
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

app.whenReady().then(async () => {
  try {
    safeLog("[scistudio] electron ready");
    const { ready } = await startRuntime();
    safeLog(`[scistudio] waiting for HTTP readiness at ${ready.url}`);
    await waitForHttpReady(ready.url);
    await session.defaultSession.clearCache();
    const url = launchUrl(ready.url);
    safeLog(`[scistudio] creating window for ${url}`);
    createWindow(url);
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
