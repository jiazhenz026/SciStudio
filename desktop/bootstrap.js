"use strict";

// Frozen bootstrap loader for the hot-updatable Electron shell (issue #2097).
// See docs/specs/desktop-shell-ota-hot-update.md.
//
// THIS FILE SHIPS INSIDE THE ASAR AND CANNOT BE HOT-UPDATED. Changing it needs
// a new installer, so it must stay small, dependency-light, and defensive. It
// has exactly one job: decide which copy of the shell to run, hand that copy
// the facts it can no longer determine for itself, and survive a shell that
// fails to boot.
//
// The baseline shell is the copy already inside the asar, next to this file --
// signed, read-only, and impossible for a patch to corrupt. Nothing extra is
// staged for it. A patch supplies an alternative shell under userData, and the
// loader picks between them.
//
// It deliberately requires `./ota` from the asar rather than from the shell it
// is about to load: the loader decides *which* shell is trustworthy, so it must
// not execute code from a shell to make that decision. A patch shell carries its
// own ota.js for its own use, and the two are allowed to diverge -- the asar
// copy is the frozen one that governs load decisions.

const { app } = require("electron");
const fs = require("fs");
const path = require("path");

const ota = require("./ota");

const BASELINE_FALLBACK = { base: "0.0.0", channel: "stable", build: 0 };

function log(message) {
  try {
    process.stdout.write(`[scistudio][bootstrap] ${message}\n`);
  } catch {
    // stdout may be a closed pipe in a packaged app; never fail on logging.
  }
}

// The installed baseline, read from the asar's package.json. The shell must NOT
// read this for itself: once it lives under a patch directory, `./package.json`
// resolves to the patch's own manifest, the patch would be compared against
// itself, and the #1787 staleness protection would silently stop working.
function baselineVersion() {
  try {
    return ota.parseVersion(require("./package.json").version) || BASELINE_FALLBACK;
  } catch {
    return BASELINE_FALLBACK;
  }
}

function resourcesPath() {
  return app.isPackaged ? process.resourcesPath : path.join(__dirname, "resources");
}

function baselineShellDir() {
  // The asar copy when packaged; the worktree when run from a source checkout.
  // Both are simply "next to this file", which is also why a dev run can never
  // be shadowed by a patch — the same source-of-truth rule as #1801.
  return __dirname;
}

function patchesRoot() {
  return path.join(app.getPath("userData"), "patches");
}

function bootAttemptPath() {
  return path.join(app.getPath("userData"), "shell-boot-attempt.json");
}

function readJsonSafe(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return null;
  }
}

function isShellDir(dir) {
  return Boolean(dir) && fs.existsSync(path.join(dir, "main.js"));
}

// Which shell should run, and at which build. The decision itself is pure and
// lives in ota.resolveShellSource (unit tested in test/ota.test.js); this only
// supplies the filesystem facts it needs.
function resolveShell() {
  const baselineBuild = baselineVersion().build;
  const pointer = readJsonSafe(path.join(patchesRoot(), "active.json"));
  const build = pointer && typeof pointer.build === "number" ? pointer.build : null;
  const patchShell =
    build !== null ? path.join(patchesRoot(), ota.patchDirName(build), "shell") : null;
  const choice = ota.resolveShellSource({
    isPackaged: app.isPackaged,
    pointer,
    baselineBuild,
    patchShellExists: isShellDir(patchShell)
  });
  return {
    ...choice,
    dir: choice.source === "patch" ? patchShell : baselineShellDir()
  };
}

// Crash-loop guard.
//
// The backend's rollback works because Electron survives a bad backend patch and
// can still show a dialog. A bad *shell* patch kills the main process outright,
// so nothing is left running to recover. The marker is therefore written to disk
// BEFORE the shell is required and cleared only once the runtime reaches HTTP
// readiness. Finding a marker for the shell we are about to load means the last
// attempt at that exact build never reached readiness, so it is refused.
function recordBootAttempt(build) {
  try {
    fs.mkdirSync(path.dirname(bootAttemptPath()), { recursive: true });
    fs.writeFileSync(bootAttemptPath(), JSON.stringify({ build }), "utf8");
  } catch (error) {
    // A guard we cannot write is worse than useless if it makes us refuse to
    // start, so proceed unguarded rather than bricking the app.
    log(`could not record the boot attempt: ${error.message}`);
  }
}

function clearBootAttempt() {
  try {
    fs.rmSync(bootAttemptPath(), { force: true });
  } catch {
    // best-effort; a stale marker only costs one baseline fallback
  }
}

function hostFacts(shell) {
  return {
    // Everything here is something the shell cannot work out for itself once it
    // is running from a patch directory, because `__dirname` no longer points
    // into the app bundle.
    baselineVersion: baselineVersion(),
    resourcesPath: resourcesPath(),
    repoRoot: path.resolve(__dirname, ".."),
    appRoot: __dirname,
    activeShellBuild: shell.build,
    shellSource: shell.source,
    // Guarded: a baseline running *because* a patch was refused also reaches
    // readiness, and letting it clear the marker would un-quarantine the broken
    // build. Only the patch the marker names may clear it.
    clearBootAttempt: () => {
      if (ota.mayClearShellMarker(shell)) {
        clearBootAttempt();
      }
    }
  };
}

function startShell(shell) {
  log(`loading ${shell.source} shell (build ${shell.build}) from ${shell.dir}`);
  // eslint-disable-next-line global-require, import/no-dynamic-require
  const mod = require(path.join(shell.dir, "main.js"));
  if (!mod || typeof mod.start !== "function") {
    throw new Error(`shell at ${shell.dir} does not export start()`);
  }
  mod.start(hostFacts(shell));
}

function baselineShell() {
  return { dir: baselineShellDir(), build: baselineVersion().build, source: "baseline" };
}

function boot() {
  const candidate = resolveShell();
  const action = ota.shellMarkerAction(readJsonSafe(bootAttemptPath()), candidate);
  let shell = candidate;

  if (action === "keep") {
    // The marker stays: active.json still points at this build, so deleting it
    // here would let the next launch select the same broken shell again and the
    // app would alternate between crashing and working instead of settling.
    log(`build ${candidate.build} did not reach readiness; staying on the baseline shell`);
    shell = baselineShell();
  } else if (action === "record") {
    // Written BEFORE the require: a shell that kills the main process leaves no
    // opportunity to record anything afterwards.
    recordBootAttempt(candidate.build);
  } else {
    clearBootAttempt();
  }

  try {
    startShell(shell);
    return;
  } catch (error) {
    log(`shell failed to load: ${error && error.stack ? error.stack : String(error)}`);
  }

  if (shell.source === "patch") {
    // Deliberately NOT clearing the marker: this patch just failed to load, so
    // it must stay quarantined for the next launch too.
    try {
      startShell(baselineShell());
      return;
    } catch (error) {
      log(`baseline shell also failed: ${error && error.stack ? error.stack : String(error)}`);
    }
  }
  // Nothing loadable. Quitting is the only honest outcome; the log above is the
  // diagnostic, and reinstalling restores the baseline shell.
  app.quit();
}

boot();
