"use strict";

// Unit tests for the in-app installer decisions and helper scripts
// (desktop/installer.js, issue #2396). The macOS and Linux helpers are run for
// real against fake tools in a temp directory, so the swap, the rollback and the
// result file are exercised rather than read.
//
// Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const installer = require("../installer");

const SHA = "a".repeat(64);
const asset = (name) => ({ url: `https://github.com/o/r/releases/download/v0.3.5-beta/${name}`, sha256: SHA, size: 1024 });
const INSTALLER = {
  version: "0.3.5-beta-build0035",
  release_page: "https://github.com/o/r/releases/tag/v0.3.5-beta",
  assets: {
    "darwin-arm64": asset("SciStudio-0.3.5-beta-build0035-arm64.dmg"),
    "darwin-x64": asset("SciStudio-0.3.5-beta-build0035-x64.dmg"),
    "win32-x64": asset("SciStudio-Setup-0.3.5-beta-build0035.exe"),
    "linux-x64": asset("SciStudio-0.3.5-beta-build0035.AppImage")
  }
};
const BASELINE_034 = { base: "0.3.4", channel: "alpha", build: 30 };

// --------------------------------------------------------------------------- //
// platformKey
// --------------------------------------------------------------------------- //
test("platformKey: macOS picks the dmg for the architecture", () => {
  assert.equal(installer.platformKey({ platform: "darwin", arch: "arm64" }), "darwin-arm64");
  assert.equal(installer.platformKey({ platform: "darwin", arch: "x64" }), "darwin-x64");
});

test("platformKey: an x64 build under Rosetta moves to arm64", () => {
  assert.equal(
    installer.platformKey({ platform: "darwin", arch: "x64", runningUnderArm64Translation: true }),
    "darwin-arm64"
  );
});

test("platformKey: Windows ships x64 only, including under ARM64 emulation", () => {
  assert.equal(installer.platformKey({ platform: "win32", arch: "x64" }), "win32-x64");
  assert.equal(
    installer.platformKey({ platform: "win32", arch: "x64", runningUnderArm64Translation: true }),
    "win32-x64"
  );
  assert.equal(installer.platformKey({ platform: "win32", arch: "ia32" }), null);
});

test("platformKey: Linux x64 only; other platforms have no installer", () => {
  assert.equal(installer.platformKey({ platform: "linux", arch: "x64" }), "linux-x64");
  assert.equal(installer.platformKey({ platform: "linux", arch: "arm64" }), null);
  assert.equal(installer.platformKey({ platform: "freebsd", arch: "x64" }), null);
});

// --------------------------------------------------------------------------- //
// evaluateInstallerOffer
// --------------------------------------------------------------------------- //
const offer = (overrides = {}) =>
  installer.evaluateInstallerOffer({
    installer: INSTALLER,
    baseline: BASELINE_034,
    effectiveBuild: 31,
    platformKey: "darwin-arm64",
    ...overrides
  });

test("evaluateInstallerOffer: a newer base is offered with this platform's asset", () => {
  const result = offer();
  assert.equal(result.kind, "offer");
  assert.equal(result.version, "0.3.5-beta-build0035");
  assert.equal(result.base, "0.3.5");
  assert.equal(result.build, 35);
  assert.equal(result.platformKey, "darwin-arm64");
  assert.equal(result.releasePage, INSTALLER.release_page);
  assert.deepEqual(result.asset, INSTALLER.assets["darwin-arm64"]);
});

test("evaluateInstallerOffer: no field, or a malformed version, offers nothing", () => {
  assert.equal(offer({ installer: undefined }).reason, "no-installer");
  assert.equal(offer({ installer: { ...INSTALLER, version: "latest" } }).reason, "bad-version");
});

test("evaluateInstallerOffer: never offers the version already running, or an older one", () => {
  const same = { ...INSTALLER, version: "0.3.4-alpha-build0030" };
  assert.equal(offer({ installer: same, effectiveBuild: 30 }).reason, "not-newer");
  const older = { ...INSTALLER, version: "0.3.3-alpha-build0040" };
  assert.equal(offer({ installer: older }).reason, "not-newer");
});

test("evaluateInstallerOffer: the same base is offered only above the effective build", () => {
  const sameBase = { ...INSTALLER, version: "0.3.4-alpha-build0036" };
  assert.equal(offer({ installer: sameBase, effectiveBuild: 35 }).kind, "offer");
  assert.equal(offer({ installer: sameBase, effectiveBuild: 36 }).reason, "not-newer");
});

test("evaluateInstallerOffer: the channel is not compared (alpha to beta is the point)", () => {
  assert.equal(offer({ baseline: { base: "0.3.4", channel: "alpha", build: 30 } }).kind, "offer");
});

test("evaluateInstallerOffer: an unsupported platform or a missing asset offers nothing", () => {
  assert.equal(offer({ platformKey: null }).reason, "unsupported-platform");
  const noLinux = { ...INSTALLER, assets: { ...INSTALLER.assets, "linux-x64": undefined } };
  assert.equal(offer({ installer: noLinux, platformKey: "linux-x64" }).reason, "no-asset");
});

test("evaluateInstallerOffer: an asset without https, a sha256 or a size is refused", () => {
  const bad = (patch) => ({ ...INSTALLER, assets: { "darwin-arm64": { ...INSTALLER.assets["darwin-arm64"], ...patch } } });
  assert.equal(offer({ installer: bad({ url: "http://x/y.dmg" }) }).reason, "bad-asset");
  assert.equal(offer({ installer: bad({ url: "file:///tmp/y.dmg" }) }).reason, "bad-asset");
  assert.equal(offer({ installer: bad({ sha256: "abc" }) }).reason, "bad-asset");
  assert.equal(offer({ installer: bad({ size: 0 }) }).reason, "bad-asset");
  assert.equal(offer({ installer: bad({ size: "1024" }) }).reason, "bad-asset");
});

test("evaluateInstallerOffer: a release page that is not https is dropped, the offer kept", () => {
  const result = offer({ installer: { ...INSTALLER, release_page: "javascript:alert(1)" } });
  assert.equal(result.kind, "offer");
  assert.equal(result.releasePage, null);
});

test("evaluateInstallerOffer: the digest is normalised to lower case", () => {
  const upper = { ...INSTALLER, assets: { "darwin-arm64": { ...INSTALLER.assets["darwin-arm64"], sha256: "A".repeat(64) } } };
  assert.equal(offer({ installer: upper }).asset.sha256, SHA);
});

// --------------------------------------------------------------------------- //
// resolveInstallTarget
// --------------------------------------------------------------------------- //
test("resolveInstallTarget: macOS replaces the .app bundle the executable lives in", () => {
  assert.deepEqual(
    installer.resolveInstallTarget({
      platform: "darwin",
      execPath: "/Applications/SciStudio.app/Contents/MacOS/SciStudio"
    }),
    { kind: "replace-app", appPath: "/Applications/SciStudio.app" }
  );
  assert.equal(
    installer.resolveInstallTarget({
      platform: "darwin",
      execPath: "/Users/me/Apps/My SciStudio.app/Contents/MacOS/SciStudio"
    }).appPath,
    "/Users/me/Apps/My SciStudio.app"
  );
});

test("resolveInstallTarget: macOS refuses the disk image, translocation, and a bare binary", () => {
  const reason = (execPath) => installer.resolveInstallTarget({ platform: "darwin", execPath }).reason;
  assert.equal(reason("/Volumes/SciStudio 0.3.4/SciStudio.app/Contents/MacOS/SciStudio"), "running-from-disk-image");
  assert.equal(
    reason("/private/var/folders/x/AppTranslocation/ABC/d/SciStudio.app/Contents/MacOS/SciStudio"),
    "translocated"
  );
  assert.equal(reason("/usr/local/bin/electron"), "not-an-app-bundle");
});

test("resolveInstallTarget: Linux replaces $APPIMAGE and refuses anything else", () => {
  assert.deepEqual(
    installer.resolveInstallTarget({ platform: "linux", execPath: "/tmp/.mount_x/scistudio", env: { APPIMAGE: "/home/me/SciStudio.AppImage" } }),
    { kind: "replace-appimage", appImagePath: "/home/me/SciStudio.AppImage" }
  );
  assert.equal(installer.resolveInstallTarget({ platform: "linux", execPath: "/usr/bin/scistudio", env: {} }).reason, "not-an-appimage");
});

test("resolveInstallTarget: Windows runs NSIS into the current install directory", () => {
  assert.deepEqual(
    installer.resolveInstallTarget({
      platform: "win32",
      execPath: "C:\\Users\\me\\AppData\\Local\\Programs\\SciStudio\\SciStudio.exe"
    }),
    {
      kind: "run-nsis",
      installDir: "C:\\Users\\me\\AppData\\Local\\Programs\\SciStudio",
      appExe: "C:\\Users\\me\\AppData\\Local\\Programs\\SciStudio\\SciStudio.exe"
    }
  );
});

// --------------------------------------------------------------------------- //
// installerFileName and quoting
// --------------------------------------------------------------------------- //
test("installerFileName: keeps a plain asset name, falls back otherwise", () => {
  assert.equal(
    installer.installerFileName(INSTALLER.assets["win32-x64"], "win32-x64"),
    "SciStudio-Setup-0.3.5-beta-build0035.exe"
  );
  const odd = { url: "https://x/dl/..%2F..%2Fevil.sh" };
  assert.equal(installer.installerFileName(odd, "linux-x64"), "SciStudio-installer.AppImage");
  assert.equal(installer.installerFileName({ url: "not a url" }, "darwin-x64"), "SciStudio-installer.dmg");
});

test("shQuote and psQuote survive quotes and spaces", () => {
  const value = "/Users/o'brien/My Apps/$HOME/`x`";
  const echoed = spawnSync("/bin/sh", ["-c", `printf %s ${installer.shQuote(value)}`], { encoding: "utf8" });
  if (process.platform !== "win32") {
    assert.equal(echoed.stdout, value);
  }
  assert.equal(installer.psQuote("C:\\it's here"), "'C:\\it''s here'");
});

test("the helper scripts refuse a pid that is not a positive integer", () => {
  assert.throws(() => installer.macInstallScript({ pid: "1; rm -rf /", dmgPath: "a", appPath: "b", resultPath: "c", logPath: "d" }));
  assert.throws(() => installer.linuxInstallScript({ pid: 0, sourcePath: "a", appImagePath: "b", resultPath: "c", logPath: "d" }));
  assert.throws(() => installer.windowsInstallScript({ pid: -4, exePath: "a", installDir: "b", appExe: "c", resultPath: "d", logPath: "e" }));
});

// --------------------------------------------------------------------------- //
// The helpers, run for real (POSIX only)
// --------------------------------------------------------------------------- //
const posixOnly = process.platform === "win32" ? "POSIX shell helpers" : false;

// A pid that is guaranteed to have exited: a child we ran to completion.
function exitedPid() {
  return spawnSync(process.execPath, ["-e", ""]).pid;
}

function writeTool(dir, name, body) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, `#!/bin/sh\n${body}\n`, { mode: 0o755 });
  return file;
}

function readResult(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function macFixture({ dmgHasApp = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-installer-mac-"));
  const apps = path.join(root, "Applications");
  const appPath = path.join(apps, "SciStudio.app");
  fs.mkdirSync(path.join(appPath, "Contents"), { recursive: true });
  fs.writeFileSync(path.join(appPath, "Contents", "version"), "old");
  const dmgPath = path.join(root, "update.dmg");
  fs.writeFileSync(dmgPath, "dmg");
  const bin = path.join(root, "bin");
  fs.mkdirSync(bin);
  const opened = path.join(root, "opened");
  // attach ... -mountpoint MNT DMG: materialise a volume holding the new app.
  const hdiutil = writeTool(
    bin,
    "hdiutil",
    `if [ "$1" = attach ]; then
  while [ "$1" != -mountpoint ]; do shift; done
  MNT=$2
  ${dmgHasApp ? 'mkdir -p "$MNT/SciStudio.app/Contents" && printf new > "$MNT/SciStudio.app/Contents/version"' : ":"}
  exit 0
fi
if [ "$1" = detach ]; then rm -rf "$2"/*.app; exit 0; fi
exit 1`
  );
  const ditto = writeTool(bin, "ditto", 'cp -R "$1" "$2"');
  const open = writeTool(bin, "open", `printf '%s\\n' "$1" >> ${installer.shQuote(opened)}`);
  return {
    root,
    appPath,
    dmgPath,
    opened,
    resultPath: path.join(root, "result.json"),
    logPath: path.join(root, "install.log"),
    tools: { hdiutil, ditto, open }
  };
}

function runScript(script) {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-installer-script-")), "install.sh");
  fs.writeFileSync(file, script, { mode: 0o700 });
  return spawnSync("/bin/sh", [file], { encoding: "utf8", timeout: 30000 });
}

test("macInstallScript: swaps the new app in, removes the dmg, and opens it", { skip: posixOnly }, () => {
  const fx = macFixture();
  const run = runScript(installer.macInstallScript({ pid: exitedPid(), ...fx }));
  assert.equal(run.status, 0, fs.existsSync(fx.logPath) ? fs.readFileSync(fx.logPath, "utf8") : run.stderr);
  assert.equal(fs.readFileSync(path.join(fx.appPath, "Contents", "version"), "utf8"), "new");
  assert.deepEqual(readResult(fx.resultPath), { ok: true, stage: "done" });
  assert.equal(fs.existsSync(fx.dmgPath), false);
  assert.equal(fs.readFileSync(fx.opened, "utf8").trim(), fx.appPath);
  // No stage or backup copy is left next to the app.
  assert.deepEqual(fs.readdirSync(path.dirname(fx.appPath)), ["SciStudio.app"]);
});

test("macInstallScript: a dmg with no app keeps the old app and reports the stage", { skip: posixOnly }, () => {
  const fx = macFixture({ dmgHasApp: false });
  const run = runScript(installer.macInstallScript({ pid: exitedPid(), ...fx }));
  assert.equal(run.status, 1);
  assert.equal(fs.readFileSync(path.join(fx.appPath, "Contents", "version"), "utf8"), "old");
  assert.deepEqual(readResult(fx.resultPath), { ok: false, stage: "mount" });
  assert.equal(fs.existsSync(fx.dmgPath), true, "the download is kept for a retry");
  assert.equal(fs.readFileSync(fx.opened, "utf8").trim(), fx.appPath, "the old app is reopened to report it");
});

test("macInstallScript: a failed copy leaves no half-copied app behind", { skip: posixOnly }, () => {
  const fx = macFixture();
  fx.tools.ditto = writeTool(path.dirname(fx.tools.ditto), "ditto-fail", 'mkdir -p "$2"; exit 1');
  const run = runScript(installer.macInstallScript({ pid: exitedPid(), ...fx }));
  assert.equal(run.status, 1);
  assert.deepEqual(readResult(fx.resultPath), { ok: false, stage: "copy" });
  assert.equal(fs.readFileSync(path.join(fx.appPath, "Contents", "version"), "utf8"), "old");
  assert.deepEqual(fs.readdirSync(path.dirname(fx.appPath)), ["SciStudio.app"]);
});

test("macInstallScript: waits for the app to exit before touching it", { skip: posixOnly }, async () => {
  const fx = macFixture();
  // Both children are spawned asynchronously: a synchronous run would block
  // this event loop, the sleeper would never be reaped, and the helper's
  // `kill -0` would see its zombie forever.
  const sleeper = spawn(process.execPath, ["-e", "setTimeout(() => {}, 1500)"]);
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-installer-script-")), "install.sh");
  fs.writeFileSync(file, installer.macInstallScript({ pid: sleeper.pid, ...fx }), { mode: 0o700 });
  let appExited = false;
  sleeper.on("exit", () => {
    appExited = true;
  });
  const started = Date.now();
  const status = await new Promise((resolve) => {
    const helper = spawn("/bin/sh", [file], { stdio: "ignore" });
    // While the app is still running, the old copy must be untouched.
    setTimeout(() => {
      if (!appExited) {
        assert.equal(fs.readFileSync(path.join(fx.appPath, "Contents", "version"), "utf8"), "old");
      }
    }, 500);
    helper.on("exit", resolve);
  });
  assert.equal(status, 0);
  assert.ok(Date.now() - started >= 1000, "the swap ran before the app had exited");
  assert.equal(fs.readFileSync(path.join(fx.appPath, "Contents", "version"), "utf8"), "new");
});

function linuxFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-installer-linux-"));
  const appImagePath = path.join(root, "SciStudio-0.3.4-alpha-build0030.AppImage");
  fs.writeFileSync(appImagePath, "old", { mode: 0o755 });
  const sourcePath = path.join(root, "download.AppImage");
  fs.writeFileSync(sourcePath, "new");
  const launched = path.join(root, "launched");
  const launch = writeTool(root, "launch", `printf '%s\\n' "$1" >> ${installer.shQuote(launched)}`);
  return {
    root,
    appImagePath,
    sourcePath,
    launched,
    resultPath: path.join(root, "result.json"),
    logPath: path.join(root, "install.log"),
    tools: { launch }
  };
}

test("linuxInstallScript: replaces the AppImage in place, executable, and starts it", { skip: posixOnly }, () => {
  const fx = linuxFixture();
  const run = runScript(installer.linuxInstallScript({ pid: exitedPid(), ...fx }));
  assert.equal(run.status, 0, fs.existsSync(fx.logPath) ? fs.readFileSync(fx.logPath, "utf8") : run.stderr);
  assert.equal(fs.readFileSync(fx.appImagePath, "utf8"), "new");
  assert.ok(fs.statSync(fx.appImagePath).mode & 0o100, "the new AppImage must be executable");
  assert.equal(fs.existsSync(fx.sourcePath), false);
  assert.deepEqual(readResult(fx.resultPath), { ok: true, stage: "done" });
  assert.equal(fs.readFileSync(fx.launched, "utf8").trim(), fx.appImagePath);
});

test("linuxInstallScript: a missing download keeps the old AppImage and starts it", { skip: posixOnly }, () => {
  const fx = linuxFixture();
  fs.rmSync(fx.sourcePath);
  const run = runScript(installer.linuxInstallScript({ pid: exitedPid(), ...fx }));
  assert.equal(run.status, 1);
  assert.equal(fs.readFileSync(fx.appImagePath, "utf8"), "old");
  assert.deepEqual(readResult(fx.resultPath), { ok: false, stage: "copy" });
  assert.equal(fs.readFileSync(fx.launched, "utf8").trim(), fx.appImagePath);
  assert.deepEqual(fs.readdirSync(fx.root).filter((name) => name.includes("scistudio-update")), []);
});

test("windowsInstallScript: silent NSIS into the install dir, relaunch, BOM-free result", () => {
  const script = installer.windowsInstallScript({
    pid: 4242,
    exePath: "C:\\Users\\o'brien\\AppData\\Roaming\\SciStudio\\installer\\SciStudio-Setup.exe",
    installDir: "C:\\Users\\o'brien\\AppData\\Local\\Programs\\SciStudio",
    appExe: "C:\\Users\\o'brien\\AppData\\Local\\Programs\\SciStudio\\SciStudio.exe",
    resultPath: "C:\\r.json",
    logPath: "C:\\l.log"
  });
  assert.match(script, /\$waitPid = 4242/);
  assert.match(script, /\$installDir = 'C:\\Users\\o''brien\\AppData\\Local\\Programs\\SciStudio'/);
  assert.match(script, /@\('\/S', '--updated', '--force-run', \('\/D=' \+ \$installDir\)\)/);
  assert.match(script, /WaitForExit\(180000\)/);
  assert.match(script, /\[System\.IO\.File\]::WriteAllText/);
  assert.match(script, /Start-Process -FilePath \$appExe/);
  // $pid is a read-only automatic variable in PowerShell; assigning it fails.
  assert.doesNotMatch(script, /\$pid\s*=/i);
});

// --------------------------------------------------------------------------- //
// describeInstallOutcome
// --------------------------------------------------------------------------- //
const PENDING = { version: "0.3.5-beta-build0035", releasePage: INSTALLER.release_page, startedAt: 1000 };

test("describeInstallOutcome: nothing pending is nothing to report", () => {
  assert.deepEqual(installer.describeInstallOutcome({ pending: null, result: null, baseline: BASELINE_034, now: 0 }), {
    kind: "none"
  });
});

test("describeInstallOutcome: running the target version is success, whatever the helper said", () => {
  const baseline = { base: "0.3.5", channel: "beta", build: 35 };
  assert.equal(installer.describeInstallOutcome({ pending: PENDING, result: null, baseline, now: 2000 }).kind, "installed");
  assert.equal(
    installer.describeInstallOutcome({ pending: PENDING, result: { ok: false, stage: "copy" }, baseline, now: 2000 }).kind,
    "installed"
  );
});

test("describeInstallOutcome: a failed helper reports its stage and the release page", () => {
  assert.deepEqual(
    installer.describeInstallOutcome({ pending: PENDING, result: { ok: false, stage: "mount" }, baseline: BASELINE_034, now: 2000 }),
    { kind: "failed", stage: "mount", version: PENDING.version, releasePage: PENDING.releasePage }
  );
});

test("describeInstallOutcome: ok from the helper on the old version is still a failure", () => {
  assert.equal(
    installer.describeInstallOutcome({ pending: PENDING, result: { ok: true, stage: "done" }, baseline: BASELINE_034, now: 2000 }).stage,
    "verify"
  );
});

test("describeInstallOutcome: no result yet is left alone for the grace period, then failed", () => {
  const within = installer.describeInstallOutcome({ pending: PENDING, result: null, baseline: BASELINE_034, now: 1000 + 60000 });
  assert.equal(within.kind, "none");
  const after = installer.describeInstallOutcome({
    pending: PENDING,
    result: null,
    baseline: BASELINE_034,
    now: 1000 + installer.PENDING_GRACE_MS + 1
  });
  assert.deepEqual(after, { kind: "failed", stage: "unknown", version: PENDING.version, releasePage: PENDING.releasePage });
});
