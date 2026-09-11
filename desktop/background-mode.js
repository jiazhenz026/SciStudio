"use strict";

// #2280 (ADR-055 section 7, spec adr-055-local-background-runtime): the two
// launch modes of the installed app.
//
//   desktop      - today's flow: splash, runtime, main window. Closing the last
//                  window quits, and quitting stops the backend.
//   external-ai  - the same runtime chain with no main window. The Electron main
//                  process stays resident as the backend's owner, shows a small
//                  connection window with the address an external AI tool (or a
//                  browser) uses, and a tray icon. Closing windows never stops
//                  the service; only an explicit stop, or quitting, does.
//
// The backend always stops with Electron (owner decision 3 on #2280): there is
// no detached daemon and no re-adoption of an orphan. The POSIX parent watchdog
// (src/scistudio/desktop/parent_watchdog.py) covers a force-killed Electron on
// macOS/Linux; on Windows the backend is a non-detached child, which libuv
// places in a kill-on-close job object, so it dies with Electron too.
//
// The decisions live here as pure functions so they can be unit tested without
// Electron; `main.js` gathers the facts and acts on the verdict, the same split
// as `runtime-port.js` and `ota.js`.

const MODES = Object.freeze({ DESKTOP: "desktop", EXTERNAL_AI: "external-ai" });
const MODE_VALUES = Object.freeze([MODES.DESKTOP, MODES.EXTERNAL_AI]);

// The remembered choice, under userData. `mode` is the last mode picked (the
// picker preselects it); `askAtLaunch: false` is "don't ask again".
const PREFERENCE_FILE = "launch-mode.json";
const PREFERENCE_VERSION = 1;

// What the "Startup Mode" menu (application menu, tray, connection window)
// sets: ask every launch, or always start in one mode.
const STARTUP_SETTINGS = Object.freeze({
  ASK: "ask",
  DESKTOP: MODES.DESKTOP,
  EXTERNAL_AI: MODES.EXTERNAL_AI
});
const STARTUP_SETTING_VALUES = Object.freeze([
  STARTUP_SETTINGS.ASK,
  STARTUP_SETTINGS.DESKTOP,
  STARTUP_SETTINGS.EXTERNAL_AI
]);

// Carries the running mode across `app.relaunch()` (OTA apply, package-update
// relaunch) so the relaunched process comes back in the same mode without
// asking again -- a background service that silently turned into a picker
// after an update would look like the update broke it.
const LAUNCH_MODE_ARG = "--scistudio-launch-mode";

// IPC between the connection window and the main process. Also declared as
// literals in desktop/connection-preload.js -- a sandboxed preload cannot
// require this file -- and a test pins the two together.
const CONNECTION_ACTION_CHANNEL = "scistudio:connection-action";
const CONNECTION_STATE_CHANNEL = "scistudio:connection-state";
const CONNECTION_ACTIONS = Object.freeze([
  "get-state",
  "copy-address",
  "open-desktop",
  "stop",
  "restart",
  "show-logs",
  "set-startup",
  "stop-and-quit"
]);

// Lifecycle of the backend the resident process owns.
const SERVICE_STATUS = Object.freeze({
  STARTING: "starting",
  RUNNING: "running",
  UNRESPONSIVE: "unresponsive",
  STOPPING: "stopping",
  STOPPED: "stopped",
  CRASHED: "crashed",
  FAILED: "failed"
});

const STATUS_LABELS = Object.freeze({
  [SERVICE_STATUS.STARTING]: "Starting…",
  [SERVICE_STATUS.RUNNING]: "Running",
  [SERVICE_STATUS.UNRESPONSIVE]: "Not responding",
  [SERVICE_STATUS.STOPPING]: "Stopping…",
  [SERVICE_STATUS.STOPPED]: "Stopped",
  [SERVICE_STATUS.CRASHED]: "Stopped unexpectedly",
  [SERVICE_STATUS.FAILED]: "Failed to start"
});

// Statuses in which the resident process still owns a live backend. Anything
// else means there is nothing left to keep running.
const LIVE_STATUSES = Object.freeze([
  SERVICE_STATUS.STARTING,
  SERVICE_STATUS.RUNNING,
  SERVICE_STATUS.UNRESPONSIVE,
  SERVICE_STATUS.STOPPING
]);

function normalizeMode(value) {
  return MODE_VALUES.includes(value) ? value : null;
}

function normalizeStartupSetting(value) {
  return STARTUP_SETTING_VALUES.includes(value) ? value : null;
}

/**
 * Read a parsed `launch-mode.json`. Anything missing or unrecognized reads as
 * "nothing remembered, ask at launch" -- the picker is the safe default, and a
 * corrupt file must never lock a user into a mode.
 */
function parseModePreference(record) {
  if (!record || typeof record !== "object") {
    return { mode: null, askAtLaunch: true };
  }
  const mode = normalizeMode(record.mode);
  // "Don't ask again" without a usable mode cannot be honoured.
  const askAtLaunch = mode === null ? true : record.askAtLaunch !== false;
  return { mode, askAtLaunch };
}

function serializeModePreference(preference) {
  const parsed = parseModePreference(preference);
  return { version: PREFERENCE_VERSION, mode: parsed.mode, askAtLaunch: parsed.askAtLaunch };
}

/**
 * Validate what the splash picker returned. Null means the answer is unusable
 * (a splash that predates the picker, a script error), and the caller falls
 * back to the desktop flow rather than quitting.
 */
function parseModePick(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const mode = normalizeMode(raw.mode);
  if (mode === null) {
    return null;
  }
  return { mode, remember: raw.remember === true };
}

/** The preference to store after the picker: the pick always becomes the preselection. */
function preferenceAfterPick(pick) {
  return { mode: pick.mode, askAtLaunch: !pick.remember };
}

/** What the Startup Mode menus show as checked. */
function startupSettingOf(preference) {
  const parsed = parseModePreference(preference);
  return parsed.askAtLaunch ? STARTUP_SETTINGS.ASK : parsed.mode;
}

/**
 * Apply a Startup Mode menu choice. "Ask" keeps the last mode as the
 * preselection; a fixed mode stops the picker from appearing.
 */
function applyStartupSetting(preference, setting) {
  const parsed = parseModePreference(preference);
  const normalized = normalizeStartupSetting(setting);
  if (normalized === null) {
    return parsed;
  }
  if (normalized === STARTUP_SETTINGS.ASK) {
    return { mode: parsed.mode, askAtLaunch: true };
  }
  return { mode: normalized, askAtLaunch: false };
}

/** The mode named on the command line (`--scistudio-launch-mode=<mode>`), last one wins. */
function parseLaunchModeArg(argv) {
  if (!Array.isArray(argv)) {
    return null;
  }
  let found = null;
  const prefix = `${LAUNCH_MODE_ARG}=`;
  for (const arg of argv) {
    if (typeof arg === "string" && arg.startsWith(prefix)) {
      found = normalizeMode(arg.slice(prefix.length));
    }
  }
  return found;
}

/**
 * Arguments for `app.relaunch({ args })` that bring the process back in `mode`.
 * Electron's default is `process.argv.slice(1)`; this keeps that and replaces
 * any earlier launch-mode flag. Null when there is no mode to carry, so the
 * caller keeps Electron's default.
 */
function relaunchArgs(argv, mode) {
  const normalized = normalizeMode(mode);
  if (normalized === null) {
    return null;
  }
  const rest = Array.isArray(argv) ? argv.slice(1) : [];
  const prefix = `${LAUNCH_MODE_ARG}=`;
  const kept = rest.filter((arg) => !(typeof arg === "string" && arg.startsWith(prefix)));
  return [...kept, `${prefix}${normalized}`];
}

/**
 * Decide how this launch starts: in a mode straight away, or by asking.
 *
 * A mode carried on the command line (a relaunch) wins, then a remembered
 * "don't ask again" choice; otherwise the splash asks, preselecting the last
 * pick (desktop for a first launch).
 */
function resolveStartupMode({ argvMode = null, preference = null } = {}) {
  const carried = normalizeMode(argvMode);
  if (carried !== null) {
    return { kind: "mode", mode: carried, source: "argv" };
  }
  const parsed = parseModePreference(preference);
  if (!parsed.askAtLaunch && parsed.mode !== null) {
    return { kind: "mode", mode: parsed.mode, source: "remembered" };
  }
  return { kind: "picker", suggested: parsed.mode || MODES.DESKTOP };
}

/**
 * The mode a second launch asks the running instance for. The second process
 * quits before it could show a picker (it never gets the single-instance
 * lock), so only an explicit flag or a remembered "don't ask again" choice
 * counts; otherwise it expresses no preference.
 */
function requestedModeForSecondLaunch({ argvMode = null, preference = null } = {}) {
  const carried = normalizeMode(argvMode);
  if (carried !== null) {
    return carried;
  }
  const parsed = parseModePreference(preference);
  return parsed.askAtLaunch ? null : parsed.mode;
}

/** Read the requested mode out of Electron's `second-instance` event. */
function requestedModeFromSecondInstance({ argv = [], additionalData = null } = {}) {
  if (additionalData && typeof additionalData === "object") {
    const fromData = normalizeMode(additionalData.requestedMode);
    if (fromData !== null) {
      return fromData;
    }
  }
  return parseLaunchModeArg(argv);
}

/**
 * Route a second launch to the running instance. One backend per machine: a
 * second launch never starts another one.
 *
 *   focus-splash            - the first instance is still choosing or starting
 *   focus-main-window       - reveal the desktop window that already exists
 *   show-connection-window  - external-AI mode: reveal the connection window.
 *                             This is also how a Linux desktop with no tray host
 *                             gets back to a resident instance.
 *   attach-desktop-window   - external-AI mode, desktop requested: open the
 *                             desktop window on the running backend
 *   promote-to-external-ai  - desktop mode, external AI requested: keep the
 *                             running backend, add the tray and connection
 *                             window, and stay resident from now on
 */
function routeSecondInstance({ runningMode = null, requestedMode = null, mainWindowOpen = false } = {}) {
  const running = normalizeMode(runningMode);
  const requested = normalizeMode(requestedMode);
  if (running === MODES.EXTERNAL_AI) {
    if (requested === MODES.DESKTOP) {
      return mainWindowOpen ? "focus-main-window" : "attach-desktop-window";
    }
    return "show-connection-window";
  }
  if (running === MODES.DESKTOP) {
    if (requested === MODES.EXTERNAL_AI) {
      return "promote-to-external-ai";
    }
    return mainWindowOpen ? "focus-main-window" : "focus-splash";
  }
  return "focus-splash";
}

/**
 * Route the macOS `activate` event (#2280, AU1 P3-6 / AU2 P3-5).
 *
 * On macOS, opening an already-running app from Finder or the Dock activates
 * the existing process instead of starting a second one, so `second-instance`
 * never fires there. `activate` is routed like a second launch instead, with
 * one difference: a dock click never switches a running desktop session to
 * external-AI mode.
 */
function routeActivate({ runningMode = null, requestedMode = null, mainWindowOpen = false } = {}) {
  if (mainWindowOpen) {
    return "focus-main-window";
  }
  const route = routeSecondInstance({ runningMode, requestedMode, mainWindowOpen: false });
  return route === "promote-to-external-ai" ? "focus-splash" : route;
}

/**
 * What `window-all-closed` does.
 *
 * Desktop mode keeps today's behaviour on every platform, macOS included:
 * quit, and quitting stops the backend. External-AI mode stays resident while
 * it owns a live backend -- that is the mode's whole promise -- and quits once
 * the service is stopped or dead, because a resident process with no backend
 * and no window has nothing left to own and, on a Linux desktop without a tray
 * host, would be invisible.
 *
 * The verdict is the same on every platform, so it takes no platform. What does
 * differ by platform lives in main.js (macOS `activate` through routeActivate,
 * the Windows tray left-click, the macOS template image) and is covered by
 * desktop/test/main-orchestration.test.js.
 */
function windowAllClosedAction({ mode = null, status = null } = {}) {
  if (normalizeMode(mode) !== MODES.EXTERNAL_AI) {
    return "quit";
  }
  return LIVE_STATUSES.includes(status) ? "stay" : "quit";
}

/**
 * Should a service status change quit the app? (#2280, owner decision
 * 2026-09-11 on AU1 P2-3 / AU2 P2-1 / Codex 3985756074.)
 *
 * The same rule as window-all-closed, applied on every status change while no
 * window is open: in external-AI mode, a service that stops, crashes, or fails
 * after the last window closed -- including a Stop still in flight when the
 * connection window was closed -- quits the app. With a window open, the
 * window shows the stopped or crashed state with Restart instead. Desktop mode
 * never quits from here; its windows decide.
 */
function quitOnServiceChange({ mode = null, status = null, openWindowCount = 0 } = {}) {
  if (normalizeMode(mode) !== MODES.EXTERNAL_AI || openWindowCount > 0) {
    return false;
  }
  return windowAllClosedAction({ mode, status }) === "quit";
}

/**
 * Is this child process still running? (#2280, AU1/AU2 P2-2)
 *
 * Node sets `ChildProcess.killed` as soon as a signal is *sent*, not when the
 * process exits, so it cannot say whether SIGTERM worked. Only the exit status
 * can.
 */
function isChildRunning(child) {
  return Boolean(child) && child.exitCode === null && child.signalCode === null;
}

/**
 * May a user-initiated quit release the frozen loader's shell boot marker?
 * (#2280, AU1 P2-1)
 *
 * The loader writes the marker before it requires a patched shell, and a marker
 * still set at the next launch quarantines that patch (ota.shellMarkerAction →
 * "keep"). The launch-mode picker is a pre-readiness stop the user can end by
 * quitting. A shell that rendered the picker and then handled the user's quit
 * or close is not a shell fault, so the quit releases the marker. A shell that
 * fails before the picker renders, or that recorded a fault (a preload that
 * threw, #2179), keeps it. A crash never runs a quit handler at all, so it
 * keeps it too.
 */
function releasesBootMarkerOnQuit({ pickerRendered = false, shellFaulted = false } = {}) {
  return pickerRendered === true && shellFaulted !== true;
}

/**
 * The address to show and copy: the origin the backend actually bound, taken
 * from its ready line -- never the remembered port, which may have been lost to
 * another process. The backend binds 127.0.0.1 only, so the address uses it
 * rather than `localhost`, which some HTTP clients resolve to ::1 first.
 */
function connectionAddress(readyUrl) {
  if (typeof readyUrl !== "string" || !readyUrl) {
    return null;
  }
  try {
    const parsed = new URL(readyUrl);
    if (!parsed.port) {
      return null;
    }
    return `${parsed.protocol}//${parsed.hostname}:${parsed.port}`;
  } catch {
    return null;
  }
}

/** Status once the backend process has exited. */
function statusAfterExit({ status = null, stopRequested = false } = {}) {
  if (stopRequested) {
    return SERVICE_STATUS.STOPPED;
  }
  if (status === SERVICE_STATUS.STARTING) {
    return SERVICE_STATUS.FAILED;
  }
  return SERVICE_STATUS.CRASHED;
}

/**
 * Status after re-validating a service believed to be up (connection window
 * focus, tray open). Only running/unresponsive move; a probe says nothing about
 * a service that is starting, stopping, or already down.
 */
function statusAfterProbe({ status = null, probeOk = false } = {}) {
  if (status === SERVICE_STATUS.RUNNING || status === SERVICE_STATUS.UNRESPONSIVE) {
    return probeOk ? SERVICE_STATUS.RUNNING : SERVICE_STATUS.UNRESPONSIVE;
  }
  return status;
}

/**
 * What the connection window and the tray render. The address is shown only
 * while the service is running -- i.e. after the ready line and the HTTP
 * readiness probe both passed -- so it is never offered before it works.
 */
function connectionView({ status = SERVICE_STATUS.STARTING, address = null, detail = null, startupSetting = STARTUP_SETTINGS.ASK } = {}) {
  const known = Object.prototype.hasOwnProperty.call(STATUS_LABELS, status) ? status : SERVICE_STATUS.STARTING;
  const running = known === SERVICE_STATUS.RUNNING;
  const down = [SERVICE_STATUS.STOPPED, SERVICE_STATUS.CRASHED, SERVICE_STATUS.FAILED].includes(known);
  const shownAddress = running ? address || null : null;
  return {
    status: known,
    label: STATUS_LABELS[known],
    address: shownAddress,
    canCopy: Boolean(shownAddress),
    canOpenDesktop: Boolean(shownAddress),
    canStop: running || known === SERVICE_STATUS.UNRESPONSIVE,
    canRestart: down,
    detail: down || known === SERVICE_STATUS.UNRESPONSIVE ? detail || null : null,
    startupSetting: normalizeStartupSetting(startupSetting) || STARTUP_SETTINGS.ASK
  };
}

module.exports = {
  CONNECTION_ACTIONS,
  CONNECTION_ACTION_CHANNEL,
  CONNECTION_STATE_CHANNEL,
  LAUNCH_MODE_ARG,
  LIVE_STATUSES,
  MODES,
  MODE_VALUES,
  PREFERENCE_FILE,
  PREFERENCE_VERSION,
  SERVICE_STATUS,
  STARTUP_SETTINGS,
  STARTUP_SETTING_VALUES,
  STATUS_LABELS,
  applyStartupSetting,
  connectionAddress,
  connectionView,
  isChildRunning,
  normalizeMode,
  normalizeStartupSetting,
  parseLaunchModeArg,
  parseModePick,
  parseModePreference,
  preferenceAfterPick,
  quitOnServiceChange,
  relaunchArgs,
  releasesBootMarkerOnQuit,
  requestedModeForSecondLaunch,
  requestedModeFromSecondInstance,
  resolveStartupMode,
  routeActivate,
  routeSecondInstance,
  serializeModePreference,
  startupSettingOf,
  statusAfterExit,
  statusAfterProbe,
  windowAllClosedAction
};
