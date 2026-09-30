"use strict";

// Pure decision logic for installing the next desktop installer from inside the
// app (issue #2396, docs/specs/desktop-in-app-installer.md).
//
// An OTA patch can replace the backend and the shell, never the Electron
// binary, the bundled interpreter or the loader. Crossing that line needs a new
// installer. This module decides whether one is on offer for this machine,
// where it would go, and writes the helper script that swaps it in after the
// app has quit. It has no Electron or filesystem dependencies so it can be unit
// tested directly (test/installer.test.js); main.js owns the downloads, the
// dialogs and the spawn.

const path = require("path");

const ota = require("./ota");

const PLATFORM_KEYS = Object.freeze(["darwin-arm64", "darwin-x64", "win32-x64", "linux-x64"]);

const SHA256_RE = /^[0-9a-f]{64}$/i;

// The helper waits this long for the app to exit. A quit waits up to 30 s for
// the backend (RELAUNCH_STOP_TIMEOUT_MS in main.js), so this leaves room for
// that and for a slow window teardown.
const WAIT_FOR_EXIT_SECONDS = 180;

// The files main.js and the helper script share. The helper writes RESULT_FILE
// and main.js reads it on the next launch -- possibly a launch of the *new*
// installer's shell, so the shape of both files is a contract (spec section 6).
const PENDING_FILE = "pending.json";
const RESULT_FILE = "result.json";

// A pending install with no result is left alone this long: the helper may
// still be running when the user opens the app again by hand.
const PENDING_GRACE_MS = 10 * 60 * 1000;

// Which installer this machine should run.
//
// An x64 build running under Rosetta on Apple Silicon is moved to the arm64
// installer (owner decision, #2396): the translated build is slower and the
// user almost certainly picked the wrong download. Windows ships x64 only, so
// an x64 build under ARM64 emulation stays on it.
function platformKey({ platform, arch, runningUnderArm64Translation }) {
  if (platform === "darwin") {
    return arch === "arm64" || runningUnderArm64Translation ? "darwin-arm64" : "darwin-x64";
  }
  if (platform === "win32") {
    return arch === "x64" || runningUnderArm64Translation ? "win32-x64" : null;
  }
  if (platform === "linux") {
    return arch === "x64" ? "linux-x64" : null;
  }
  return null;
}

function isHttpsUrl(raw) {
  if (typeof raw !== "string") {
    return false;
  }
  try {
    return new URL(raw).protocol === "https:";
  } catch {
    return false;
  }
}

function validAsset(asset) {
  return (
    Boolean(asset) &&
    typeof asset === "object" &&
    isHttpsUrl(asset.url) &&
    typeof asset.sha256 === "string" &&
    SHA256_RE.test(asset.sha256) &&
    Number.isInteger(asset.size) &&
    asset.size > 0
  );
}

// Is an installer on offer for this machine?
//
// `installer` is the manifest's optional `installer` field (spec section 3).
// Returns { kind: "none", reason } or
// { kind: "offer", version, base, build, releasePage, platformKey, asset }.
//
// The installer must be newer than what is running: a higher base, or the same
// base at a higher build than the effective one. The channel is deliberately
// not compared -- moving a user from alpha to beta is exactly what an installer
// is for.
function evaluateInstallerOffer({ installer, baseline, effectiveBuild, platformKey: key }) {
  if (!installer || typeof installer !== "object") {
    return { kind: "none", reason: "no-installer" };
  }
  const version = ota.parseVersion(installer.version);
  if (!version) {
    return { kind: "none", reason: "bad-version" };
  }
  const baseOrder = baseline ? ota.compareBase(version.base, baseline.base) : 1;
  const newer = baseOrder > 0 || (baseOrder === 0 && version.build > (effectiveBuild || 0));
  if (!newer) {
    return { kind: "none", reason: "not-newer" };
  }
  if (!key) {
    return { kind: "none", reason: "unsupported-platform" };
  }
  const assets = installer.assets && typeof installer.assets === "object" ? installer.assets : {};
  const asset = assets[key];
  if (!asset) {
    return { kind: "none", reason: "no-asset" };
  }
  if (!validAsset(asset)) {
    return { kind: "none", reason: "bad-asset" };
  }
  return {
    kind: "offer",
    version: String(installer.version),
    base: version.base,
    build: version.build,
    releasePage: isHttpsUrl(installer.release_page) ? installer.release_page : null,
    platformKey: key,
    asset: { url: asset.url, sha256: asset.sha256.toLowerCase(), size: asset.size }
  };
}

// Where the new installer goes, judged from the running executable.
//
// Returns { kind: "replace-app", appPath } (macOS),
//         { kind: "run-nsis", installDir, appExe } (Windows),
//         { kind: "replace-appimage", appImagePath } (Linux),
// or { kind: "unsupported", reason } when the app cannot be replaced in place.
// Writability is IO and is checked by main.js on top of this.
function resolveInstallTarget({ platform, execPath, env }) {
  if (platform === "darwin") {
    const marker = ".app/Contents/MacOS/";
    const index = String(execPath || "").indexOf(marker);
    if (index < 0) {
      return { kind: "unsupported", reason: "not-an-app-bundle" };
    }
    const appPath = execPath.slice(0, index + ".app".length);
    if (appPath.startsWith("/Volumes/")) {
      // Running straight from the mounted disk image: there is nothing
      // installed to replace, and the image is read-only.
      return { kind: "unsupported", reason: "running-from-disk-image" };
    }
    if (appPath.includes("/AppTranslocation/")) {
      // Gatekeeper translocation runs a quarantined app from a random
      // read-only path; replacing it would not touch the user's copy.
      return { kind: "unsupported", reason: "translocated" };
    }
    return { kind: "replace-app", appPath };
  }
  if (platform === "linux") {
    const appImagePath = env && env.APPIMAGE;
    if (!appImagePath) {
      return { kind: "unsupported", reason: "not-an-appimage" };
    }
    return { kind: "replace-appimage", appImagePath };
  }
  if (platform === "win32") {
    if (!execPath) {
      return { kind: "unsupported", reason: "no-executable" };
    }
    return { kind: "run-nsis", installDir: path.win32.dirname(execPath), appExe: execPath };
  }
  return { kind: "unsupported", reason: "unsupported-platform" };
}

// The downloaded file's name: the asset's own name when it is plain, so a user
// who finds it in userData recognises it, and a fixed name otherwise.
function installerFileName(asset, key) {
  const fallback = {
    "darwin-arm64": "SciStudio-installer.dmg",
    "darwin-x64": "SciStudio-installer.dmg",
    "win32-x64": "SciStudio-installer.exe",
    "linux-x64": "SciStudio-installer.AppImage"
  }[key] || "SciStudio-installer";
  try {
    const name = decodeURIComponent(path.posix.basename(new URL(asset.url).pathname));
    return /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name) ? name : fallback;
  } catch {
    return fallback;
  }
}

// POSIX shell single-quoting: the only character that needs care is the quote.
function shQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

// PowerShell single-quoted strings escape a quote by doubling it.
function psQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function assertPid(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new Error(`invalid pid: ${pid}`);
  }
}

// The macOS helper: wait for the app to exit, mount the dmg, copy the new .app
// beside the old one, swap the two with renames, and open the result. On any
// failure the installed app is left (or put back) in place, the result file
// names the stage, and the old app is opened so it can report it.
//
// `tools` exists for the tests, which run this script against fakes; the
// defaults are the system binaries.
function macInstallScript({ pid, dmgPath, appPath, resultPath, logPath, tools = {} }) {
  assertPid(pid);
  const hdiutil = tools.hdiutil || "/usr/bin/hdiutil";
  const ditto = tools.ditto || "/usr/bin/ditto";
  const open = tools.open || "/usr/bin/open";
  return `#!/bin/sh
# SciStudio in-app installer helper (#2396). Generated; safe to delete.
WAIT_PID=${pid}
DMG=${shQuote(dmgPath)}
APP=${shQuote(appPath)}
RESULT=${shQuote(resultPath)}
HDIUTIL=${shQuote(hdiutil)}
DITTO=${shQuote(ditto)}
OPEN=${shQuote(open)}
MNT=
STAGE=
exec >>${shQuote(logPath)} 2>&1
echo "[installer] $(date) start"

finish() {
  printf '{"ok":%s,"stage":"%s"}\\n' "$1" "$2" > "$RESULT"
}

fail() {
  echo "[installer] failed at $1"
  if [ -n "$MNT" ]; then "$HDIUTIL" detach "$MNT" -force >/dev/null 2>&1; rmdir "$MNT" 2>/dev/null; fi
  if [ -n "$STAGE" ]; then rm -rf "$STAGE"; fi
  finish false "$1"
  "$OPEN" "$APP"
  exit 1
}

i=0
while kill -0 "$WAIT_PID" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -gt ${WAIT_FOR_EXIT_SECONDS * 2} ] && fail wait
  sleep 0.5
done

MNT=$(mktemp -d "\${TMPDIR:-/tmp}/scistudio-update.XXXXXX") || { MNT=; fail mount; }
"$HDIUTIL" attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG" || { rmdir "$MNT"; MNT=; fail mount; }
SRC=
for candidate in "$MNT"/*.app; do
  if [ -d "$candidate" ]; then SRC=$candidate; break; fi
done
[ -n "$SRC" ] || fail mount

PARENT=$(dirname "$APP")
STAGE="$PARENT/.scistudio-update-$$.app"
BACKUP="$PARENT/.scistudio-previous-$$.app"
"$DITTO" "$SRC" "$STAGE" || fail copy
"$HDIUTIL" detach "$MNT" -force >/dev/null 2>&1
rmdir "$MNT" 2>/dev/null
MNT=

mv "$APP" "$BACKUP" || fail swap
if ! mv "$STAGE" "$APP"; then
  mv "$BACKUP" "$APP"
  fail swap
fi
STAGE=
rm -rf "$BACKUP"
rm -f "$DMG"
finish true done
echo "[installer] installed"
"$OPEN" "$APP"
exit 0
`;
}

// The Linux helper: wait, copy the new AppImage next to the old one, rename it
// over the old path (so launchers and desktop entries keep working), and start
// it. The file keeps its old name even though it now holds the new version.
function linuxInstallScript({ pid, sourcePath, appImagePath, resultPath, logPath, tools = {} }) {
  assertPid(pid);
  const launch = tools.launch || null;
  const launchLine = launch
    ? `${shQuote(launch)} "$TARGET"`
    : `nohup "$TARGET" >/dev/null 2>&1 &`;
  return `#!/bin/sh
# SciStudio in-app installer helper (#2396). Generated; safe to delete.
WAIT_PID=${pid}
SRC=${shQuote(sourcePath)}
TARGET=${shQuote(appImagePath)}
RESULT=${shQuote(resultPath)}
TMP="$TARGET.scistudio-update-$$"
exec >>${shQuote(logPath)} 2>&1
echo "[installer] $(date) start"

finish() {
  printf '{"ok":%s,"stage":"%s"}\\n' "$1" "$2" > "$RESULT"
}

relaunch() {
  ${launchLine}
}

fail() {
  echo "[installer] failed at $1"
  rm -f "$TMP"
  finish false "$1"
  relaunch
  exit 1
}

i=0
while kill -0 "$WAIT_PID" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -gt ${WAIT_FOR_EXIT_SECONDS * 2} ] && fail wait
  sleep 0.5
done

cp "$SRC" "$TMP" || fail copy
chmod 755 "$TMP" || fail copy
mv -f "$TMP" "$TARGET" || fail swap
rm -f "$SRC"
finish true done
echo "[installer] installed"
relaunch
exit 0
`;
}

// The Windows helper (PowerShell): wait, run the NSIS installer silently into
// the current install directory, and let it start the app (--force-run). On
// failure the old app is started so it can report the failure. `/D=` must be
// the last argument and is taken verbatim to the end of the command line, so a
// directory with spaces needs no quoting.
function windowsInstallScript({ pid, exePath, installDir, appExe, resultPath, logPath }) {
  assertPid(pid);
  return `# SciStudio in-app installer helper (#2396). Generated; safe to delete.
$ErrorActionPreference = 'Continue'
$waitPid = ${pid}
$exe = ${psQuote(exePath)}
$installDir = ${psQuote(installDir)}
$appExe = ${psQuote(appExe)}
$result = ${psQuote(resultPath)}
$log = ${psQuote(logPath)}

function Write-Log($message) {
  try { Add-Content -LiteralPath $log -Value ("[installer] " + (Get-Date -Format o) + " " + $message) } catch { }
}

function Finish($ok, $stage) {
  # WriteAllText writes UTF-8 without a byte-order mark, which JSON.parse needs.
  [System.IO.File]::WriteAllText($result, '{"ok":' + $ok + ',"stage":"' + $stage + '"}')
}

function Fail($stage) {
  Write-Log ("failed at " + $stage)
  Finish 'false' $stage
  try { Start-Process -FilePath $appExe } catch { }
  exit 1
}

Write-Log 'start'
$process = Get-Process -Id $waitPid -ErrorAction SilentlyContinue
if ($process) {
  if (-not $process.WaitForExit(${WAIT_FOR_EXIT_SECONDS * 1000})) { Fail 'wait' }
}

try {
  $installer = Start-Process -FilePath $exe -ArgumentList @('/S', '--updated', '--force-run', ('/D=' + $installDir)) -PassThru -Wait
} catch {
  Fail 'install'
}
if ($installer.ExitCode -ne 0) {
  Write-Log ("installer exit code " + $installer.ExitCode)
  Fail 'install'
}
Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
Finish 'true' 'done'
Write-Log 'installed'
exit 0
`;
}

// What to tell the user on the launch after an install was attempted.
//
//   pending - main.js's own record, written just before the helper started:
//             { version, releasePage, startedAt }
//   result  - the helper's record: { ok, stage }
//
// Returns { kind: "none" }            nothing was attempted, or it is still running
//         { kind: "installed", version }  the new installer is what is running now
//         { kind: "failed", stage, version, releasePage }
//
// Success is judged by what is running, not by the helper's word: a result that
// says ok on an app still at the old version means the swap did not take.
function describeInstallOutcome({ pending, result, baseline, now }) {
  if (!pending || typeof pending !== "object") {
    return { kind: "none" };
  }
  const target = ota.parseVersion(pending.version);
  const version = pending.version ? String(pending.version) : null;
  const releasePage = isHttpsUrl(pending.releasePage) ? pending.releasePage : null;
  const reached =
    Boolean(target && baseline) &&
    (ota.compareBase(baseline.base, target.base) > 0 ||
      (ota.compareBase(baseline.base, target.base) === 0 && baseline.build >= target.build));
  if (reached) {
    return { kind: "installed", version };
  }
  if (result && typeof result === "object") {
    const stage = result.ok === true ? "verify" : typeof result.stage === "string" ? result.stage : "unknown";
    return { kind: "failed", stage, version, releasePage };
  }
  const startedAt = Number(pending.startedAt);
  if (Number.isFinite(startedAt) && now - startedAt < PENDING_GRACE_MS) {
    return { kind: "none" };
  }
  return { kind: "failed", stage: "unknown", version, releasePage };
}

module.exports = {
  PLATFORM_KEYS,
  PENDING_FILE,
  RESULT_FILE,
  PENDING_GRACE_MS,
  WAIT_FOR_EXIT_SECONDS,
  platformKey,
  evaluateInstallerOffer,
  resolveInstallTarget,
  installerFileName,
  shQuote,
  psQuote,
  macInstallScript,
  linuxInstallScript,
  windowsInstallScript,
  describeInstallOutcome
};
