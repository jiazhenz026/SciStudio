const { app, BrowserWindow, dialog, session } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const readline = require("readline");

const READY_EVENT = "scistudio.ready";
const READY_TIMEOUT_MS = 120000;
const DEFAULT_DEV_FRONTEND_URL = "http://127.0.0.1:5173";

let mainWindow = null;
let runtimeProcess = null;
let isQuitting = false;

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
  const stagedSrc = path.join(resources, "app", "src");
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
  console.warn(`[scistudio] Ignoring invalid SCISTUDIO_DESKTOP_RUNTIME_PORT=${requested}`);
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

    const tryNext = () => {
      if (index >= candidates.length) {
        fail(
          new Error(
            `Unable to launch SciStudio runtime. stderr:\n${stderrLines.join("\n")}`
          )
        );
        return;
      }

      const candidate = candidates[index];
      index += 1;
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
          resolve({ child, ready, candidate });
        } else {
          console.log(`[scistudio] ${line}`);
        }
      });

      const stderr = readline.createInterface({ input: child.stderr });
      stderr.on("line", (line) => {
        sawOutput = true;
        stderrLines.push(`[${candidate.label}] ${line}`);
        console.error(`[scistudio] ${line}`);
      });

      child.on("error", (error) => {
        if (error.code === "ENOENT" && !settled) {
          tryNext();
          return;
        }
        fail(error);
      });

      child.on("exit", (code, signal) => {
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
  try {
    const parsed = new URL(url);
    if (!frontendUrl) {
      parsed.searchParams.set("_scistudio_desktop_boot", String(Date.now()));
    }
    return parsed.toString();
  } catch {
    return url;
  }
}

async function recoverBlankFirstPaint(window) {
  const isBlank = await window.webContents
    .executeJavaScript(
      "(() => { const root = document.getElementById('root'); return Boolean(document.body) && document.body.innerText.trim().length === 0 && (!root || root.childElementCount === 0); })()",
      true
    )
    .catch(() => false);
  if (isBlank) {
    window.webContents.reloadIgnoringCache();
  }
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

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.once("did-finish-load", () => {
    recoverBlankFirstPaint(mainWindow);
  });

  mainWindow.webContents.once("did-fail-load", (_event, _code, _description, validatedUrl) => {
    console.error(`[scistudio] failed to load ${validatedUrl}; retrying once`);
    mainWindow.webContents.reloadIgnoringCache();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.loadURL(url);
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
    const { ready } = await startRuntime();
    await session.defaultSession.clearCache();
    const url = launchUrl(ready.url);
    createWindow(url);
  } catch (error) {
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
