"use strict";

// Frozen-loader invariants for the hot-updatable shell (issue #2097).
// See docs/specs/desktop-shell-ota-hot-update.md.
//
// The loader's *decisions* are pure and tested directly in ota.test.js
// (resolveShellSource, shellBootRefused). What is left here cannot be exercised
// by requiring the modules: main.js and bootstrap.js both `require("electron")`,
// which only resolves inside a real Electron process. These are therefore
// source- and configuration-level assertions, and they are deliberately aimed at
// the mistakes that would be silent in production rather than at coverage.
//
// Run with: npm --prefix desktop test   (uses the Node built-in test runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.join(__dirname, "..");
const pkg = require("../package.json");
const read = (name) => fs.readFileSync(path.join(desktopRoot, name), "utf8");

test("the asar entry point is the loader, not the shell", () => {
  assert.equal(pkg.main, "bootstrap.js");
});

test("the asar carries the loader and a complete baseline shell", () => {
  // The baseline shell is the copy inside the asar: signed, read-only, and
  // impossible for a patch to corrupt. Dropping any of these from `files` would
  // leave the loader with nothing to fall back to when a patch is refused, and
  // the failure would only appear on a user's machine after a bad patch.
  for (const file of [
    "bootstrap.js",
    "main.js",
    "ota.js",
    "runtime-port.js",
    "background-mode.js",
    "preload.js",
    "connection-preload.js",
    "splash.html",
    "connection.html",
    "package.json",
    "assets/tray.png",
    "assets/tray@2x.png",
    "assets/trayTemplate.png",
    "assets/trayTemplate@2x.png"
  ]) {
    assert.ok(pkg.build.files.includes(file), `build.files must include ${file}`);
  }
});

test("every file the shell loads from next to itself ships in the asar (#2280)", () => {
  // A relative require, or a path.join(__dirname, ...) file, that is missing
  // from build.files crashes the installed app on launch; the same file missing
  // from SHELL_FILES crashes every patched launch (tests/scripts/
  // test_ota_publish.py pins the two lists together).
  for (const name of ["main.js", "menu.js"]) {
    const source = read(name);
    for (const match of source.matchAll(/require\(["']\.\/([^"']+)["']\)/g)) {
      const file = match[1].endsWith(".js") || match[1].endsWith(".json") ? match[1] : `${match[1]}.js`;
      assert.ok(pkg.build.files.includes(file), `${name} requires ./${match[1]}, which build.files lacks`);
    }
  }
  const main = read("main.js");
  const dirnameFiles = [...main.matchAll(/path\.join\(__dirname,((?:\s*"[^"]+",?)+)\)/g)].map((m) =>
    [...m[1].matchAll(/"([^"]+)"/g)].map((part) => part[1]).join("/")
  );
  assert.ok(dirnameFiles.length >= 6, `expected the shell-relative files, found ${dirnameFiles}`);
  for (const file of dirnameFiles) {
    assert.ok(pkg.build.files.includes(file), `main.js loads ${file} next to itself, which build.files lacks`);
  }
  // Electron picks the @2x tray images up by itself, so no code names them.
  for (const file of ["assets/tray@2x.png", "assets/trayTemplate@2x.png"]) {
    assert.ok(pkg.build.files.includes(file), `build.files must include ${file}`);
    assert.ok(fs.existsSync(path.join(desktopRoot, file)), `${file} must exist`);
  }
});

test("the connection window, its preload, and the tray images stay __dirname-relative (#2280)", () => {
  // Like splash.html, these travel with the shell: a patched shell must load
  // its own copies, never depend on an older installed bundle having them.
  const main = read("main.js");
  assert.match(main, /path\.join\(__dirname, "connection\.html"\)/);
  assert.match(main, /path\.join\(__dirname, "connection-preload\.js"\)/);
  assert.match(main, /path\.join\(__dirname, "assets", "trayTemplate\.png"\)/);
  assert.match(main, /path\.join\(__dirname, "assets", "tray\.png"\)/);
});

test("every relaunch stops the backend and carries the launch mode (#2280)", () => {
  // Owner decision 5: OTA stop-then-relaunch includes the background instance,
  // and the relaunch honours the mode. All three relaunch sites (package update,
  // mandatory OTA, optional OTA) must go through the one helper that does both.
  const main = read("main.js");
  const helperAt = main.indexOf("async function stopRuntimeAndRelaunch()");
  assert.ok(helperAt > 0, "main.js must define stopRuntimeAndRelaunch");
  const helper = main.slice(helperAt, main.indexOf("\n}\n", helperAt));
  assert.match(helper, /isQuitting = true/);
  assert.match(helper, /stopRuntimeAndWait\(/);
  assert.match(helper, /backgroundMode\.relaunchArgs\(process\.argv, launchMode\)/);

  const relaunchCalls = [...main.matchAll(/app\.relaunch\(/g)].map((m) => m.index);
  assert.ok(relaunchCalls.length > 0);
  for (const at of relaunchCalls) {
    assert.ok(
      at > helperAt && at < helperAt + helper.length,
      "app.relaunch() may only be called from stopRuntimeAndRelaunch"
    );
  }
  assert.ok(
    (main.match(/await stopRuntimeAndRelaunch\(\)/g) || []).length >= 3,
    "the package-update and both OTA paths must use stopRuntimeAndRelaunch"
  );
});

test("the tray is held by a module-level reference (#2280)", () => {
  // A Tray that is garbage-collected disappears from the menu bar (owner
  // decision 2 calls this out for macOS).
  const main = read("main.js");
  assert.match(main, /^let tray = null;$/m);
  assert.match(main, /\n {4}tray = new Tray\(trayImage\(\)\);/);
  assert.match(main, /image\.setTemplateImage\(true\)/);
});

test("external-AI mode vouches for the shell without a main window (#2280)", () => {
  // Desktop mode records known-good once the main window paints (#2179).
  // External-AI mode has no main window; without its own vouching path a
  // working patched shell would be quarantined on the next launch.
  const main = read("main.js");
  const start = main.indexOf("function maybeVouchForShellInBackground()");
  assert.ok(start > 0, "main.js must define maybeVouchForShellInBackground");
  const fn = main.slice(start, main.indexOf("\n}\n", start));
  assert.match(fn, /launchMode !== backgroundMode\.MODES\.EXTERNAL_AI/);
  assert.match(fn, /connectionBridgeReady/);
  assert.match(fn, /SERVICE_STATUS\.RUNNING/);
  assert.match(fn, /recordKnownGood\(effectiveBuild\(\)\)/);
});

test("window-all-closed follows the launch mode instead of always quitting (#2280)", () => {
  const main = read("main.js");
  const handler = main.slice(main.indexOf('app.on("window-all-closed"'), main.indexOf('app.on("activate"'));
  assert.match(handler, /backgroundMode\.windowAllClosedAction\(/);
  assert.match(handler, /if \(action === "quit"\)/);
});

test("the shell exposes start() for the loader to call", () => {
  assert.match(read("main.js"), /module\.exports\s*=\s*\{\s*start\s*\}/);
});

test("the shell takes its baseline version from the host, never from ./package.json", () => {
  // THE central trap of #2097. Once main.js runs from a patch directory,
  // `require("./package.json")` is the *patch's* manifest, so the patch would be
  // compared against itself and ota.resolveActivePatch would never call it
  // stale. A leftover patch would then shadow a freshly installed build forever,
  // and nothing would fail loudly.
  const main = read("main.js");
  assert.doesNotMatch(
    main,
    /require\(["']\.\/package\.json["']\)/,
    "main.js must not read its own package.json; the loader supplies baselineVersion"
  );
  assert.match(main, /return host\(\)\.baselineVersion/);
});

test("the shell resolves bundle-relative paths through the host, not __dirname", () => {
  // resourcesDir / repoRoot / appIconPath all pointed at __dirname, which stops
  // meaning "the app bundle" the moment the shell is loaded from userData.
  const main = read("main.js");
  assert.match(main, /return host\(\)\.resourcesPath/);
  assert.match(main, /return host\(\)\.repoRoot/);
  assert.match(main, /path\.join\(host\(\)\.appRoot, "assets", "icon\.png"\)/);
});

test("splash.html and preload.js stay __dirname-relative", () => {
  // These two travel *with* the shell, so they must keep resolving next to
  // main.js rather than against the bundle root.
  const main = read("main.js");
  assert.match(main, /path\.join\(__dirname, "splash\.html"\)/);
  assert.match(main, /path\.join\(__dirname, "preload\.js"\)/);
});

test("the loader takes its update logic from the asar, not from a shell", () => {
  // The loader decides which shell is trustworthy, so it must not execute code
  // from a shell to make that decision. Only a plain relative require is
  // acceptable here.
  const bootstrap = read("bootstrap.js");
  const requires = [...bootstrap.matchAll(/require\((["'])([^"']+)\1\)/g)].map((m) => m[2]);
  assert.deepEqual(requires.sort(), ["./ota", "./package.json", "electron", "fs", "os", "path"].sort());
});

test("the loader records the boot attempt before requiring the shell", () => {
  // Ordering is the whole guard: a shell that kills the main process leaves no
  // chance to write anything afterwards.
  // Compare call sites inside boot(), not the earlier function definitions.
  const bootstrap = read("bootstrap.js");
  const body = bootstrap.slice(bootstrap.indexOf("function boot() {"));
  const recordAt = body.indexOf("recordBootAttempt(candidate.build)");
  const startAt = body.indexOf("startShell(shell);");
  assert.ok(recordAt > 0, "boot() must record the attempt");
  assert.ok(startAt > 0, "boot() must start the shell");
  assert.ok(recordAt < startAt, "recordBootAttempt must precede startShell");
});

test("the shell clears the boot marker only from the known-good path", () => {
  // Clearing it anywhere else would make the marker mean "we tried" rather than
  // "we succeeded", and a crash-looping shell would never be refused.
  // #2179 moved *when* that path runs -- it now waits for the renderer to paint
  // rather than for the backend to answer -- but the marker must still be
  // cleared from recordKnownGood and nowhere else.
  const main = read("main.js");
  const clearAt = main.indexOf("host().clearBootAttempt()");
  assert.ok(clearAt > 0, "main.js must clear the marker");
  const declAt = main.lastIndexOf("function recordKnownGood", clearAt);
  assert.ok(declAt > 0 && declAt < clearAt, "the marker must be cleared from recordKnownGood");
  assert.equal(
    main.slice(declAt, clearAt).indexOf("\nfunction "),
    -1,
    "another function declaration sits between recordKnownGood and the clear"
  );
});

test("the loader never clears the marker on the refusal or load-failure paths", () => {
  // A quarantine must survive both a refusal and a failed require, because
  // active.json still points at the broken build. Clearing it on either path is
  // what produced the alternating crash loop Codex found on PR #2139.
  const body = read("bootstrap.js");
  const boot = body.slice(body.indexOf("function boot() {"));
  const keepBranch = boot.slice(boot.indexOf('if (action === "keep")'), boot.indexOf('} else if (action === "record")'));
  assert.doesNotMatch(keepBranch, /clearBootAttempt\(\)/, "the keep branch must not clear the marker");

  const failurePath = boot.slice(boot.indexOf('if (shell.source === "patch") {', boot.indexOf("catch")));
  assert.doesNotMatch(failurePath, /clearBootAttempt\(\)/, "the load-failure fallback must not clear the marker");
});

test("the host's clearBootAttempt is guarded by mayClearShellMarker", () => {
  // The shell calls this from recordKnownGood whenever the runtime comes up,
  // including when the baseline is up *because* a patch was quarantined.
  const body = read("bootstrap.js");
  assert.match(body, /clearBootAttempt:\s*\(\)\s*=>\s*\{[\s\S]*?ota\.mayClearShellMarker\(shell\)/);
});

test("the loader persists its diagnostics instead of only writing stdout", () => {
  // A packaged app is a GUI-subsystem process with detached stdout, so a
  // stdout-only log vanishes exactly when a shell fails to load. main.js
  // persists its own log for this reason (#1741); the loader runs before
  // main.js exists and must do the same for itself. Verified by observation:
  // a packaged Windows build produced no loader output at all on the console.
  const bootstrap = read("bootstrap.js");
  assert.match(bootstrap, /appendFileSync\(\s*path\.join\(dir, "scistudio-desktop\.log"\)/);
  assert.match(bootstrap, /require\("os"\)/);
  // The write must be non-fatal: logging is never a reason not to start.
  const logFn = bootstrap.slice(bootstrap.indexOf("function log(message)"), bootstrap.indexOf("// The installed baseline"));
  assert.equal((logFn.match(/catch/g) || []).length, 2, "both the stdout and file writes must be guarded");
});

// --------------------------------------------------------------------------- //
// #2097: About reports the build that is RUNNING, not the one installed.
// --------------------------------------------------------------------------- //

test("the app installs its own menu instead of inheriting Electron's default", () => {
  // The default menu is why macOS showed a stale version and Windows had no
  // About item at all. #2159 moved the template into the pure, unit-testable
  // desktop/menu.js; main.js only has to install it.
  const main = read("main.js");
  assert.match(main, /require\("\.\/menu"\)/);
  assert.match(main, /Menu\.setApplicationMenu\(Menu\.buildFromTemplate\(template\)\)/);
});

test("About reports the effective build, never app.getVersion()", () => {
  // app.getVersion() is the packaged package.json version, i.e. the installer
  // baseline. Once a patch is applied that is not what is running, so reporting
  // it would be wrong by construction for an app whose whole premise is that
  // the two can differ.
  const main = read("main.js");
  const about = main.slice(main.indexOf("function aboutText()"), main.indexOf("async function showAbout()"));
  assert.match(about, /effectiveBuild\(\)/);
  assert.doesNotMatch(about, /app\.getVersion\(\)/);
  // and it names the installed baseline whenever the two diverge
  assert.match(about, /effective !== baseline\.build/);
});

test("About carries the licence and copyright, pinned to the repository", () => {
  // The strings are duplicated into the shell out of necessity -- a native
  // dialog cannot read LICENSE at runtime from inside an asar patch -- so pin
  // them to their sources instead of trusting them to stay in step.
  const main = read("main.js");
  const license = /const LICENSE_NAME = "(.+)";/.exec(main);
  const copyright = /const COPYRIGHT = "(.+)";/.exec(main);
  assert.ok(license && copyright, "both constants must exist");

  const repoRoot = path.join(desktopRoot, "..");
  const licenseFile = fs.readFileSync(path.join(repoRoot, "LICENSE"), "utf8");
  assert.ok(
    licenseFile.includes(copyright[1]),
    `LICENSE does not contain ${copyright[1]}`
  );
  assert.ok(licenseFile.includes("Apache License"), "LICENSE is not the Apache License");

  const pyproject = fs.readFileSync(path.join(repoRoot, "pyproject.toml"), "utf8");
  assert.match(pyproject, /license = \{text = "Apache-2\.0"\}/);

  const about = main.slice(main.indexOf("function aboutText()"), main.indexOf("async function showAbout()"));
  assert.match(about, /lines\.push\(LICENSE_NAME\)/);
  assert.match(about, /lines\.push\(COPYRIGHT\)/);
});

test("every platform can reach About", () => {
  // macOS gets it in the application menu, Windows and Linux in File -- which
  // previously held nothing but Quit. The template lives in menu.js (#2159);
  // unlike main.js it is pure, so assert on the built template directly.
  const { buildMenuTemplate } = require("../menu");
  const deps = {
    appName: "SciStudio",
    sendMenuAction: () => {},
    checkForUpdates: () => {},
    showAbout: () => {},
  };
  const hasAbout = (submenu) => submenu.some((item) => item.label === "About SciStudio");

  const mac = buildMenuTemplate({ ...deps, platform: "darwin" });
  assert.ok(hasAbout(mac[0].submenu), "macOS app menu must carry About");

  const win = buildMenuTemplate({ ...deps, platform: "win32" });
  const file = win.find((item) => item.label === "File");
  assert.ok(hasAbout(file.submenu), "File menu must carry About on Windows/Linux");
});

test("replacing the default menu keeps the standard roles", () => {
  // Without these, copy/paste and the developer tools lose their accelerators.
  const { buildMenuTemplate } = require("../menu");
  const template = buildMenuTemplate({
    platform: "win32",
    appName: "SciStudio",
    sendMenuAction: () => {},
    checkForUpdates: () => {},
    showAbout: () => {},
  });
  const roles = template.map((item) => item.role);
  for (const role of ["editMenu", "viewMenu", "windowMenu"]) {
    assert.ok(roles.includes(role), `missing role ${role}`);
  }
});
