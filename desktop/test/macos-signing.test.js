"use strict";

// Build-configuration tests for the signed + notarized macOS build (issue #2096).
// See docs/specs/desktop-macos-signing-notarization.md.
//
// These assert the electron-builder configuration and the entitlements file that
// governs it. They run on any platform: the signing itself needs macOS, but a
// misconfiguration that would silently ship an unsigned or under-entitled build
// is catchable here.
//
// Run with: npm --prefix desktop test   (uses the Node built-in test runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.join(__dirname, "..");
const pkg = require("../package.json");
const mac = pkg.build.mac;

test("mac: hardened runtime is on (a precondition for notarization)", () => {
  assert.equal(mac.hardenedRuntime, true);
});

test("mac: notarization is enabled", () => {
  assert.equal(mac.notarize, true);
});

test("mac: entitlements and entitlementsInherit point at the same file", () => {
  // The bundled interpreter is spawned as a nested process and receives the
  // *inherit* entitlements, not the app's. It is the process that dlopen()s
  // unsigned package-OTA extensions, so the two must not drift apart.
  assert.ok(mac.entitlements, "mac.entitlements must be set explicitly");
  assert.equal(mac.entitlements, mac.entitlementsInherit);
});

test("mac: the configured entitlements file exists", () => {
  // electron-builder returns an explicitly configured entitlements path
  // verbatim (app-builder-lib macPackager getOptionsForFile) rather than
  // resolving it against directories.buildResources, which is "assets" here.
  // A path typo would therefore not fail the build config, only the signing
  // run on a mac. Catch it on every platform instead.
  const resolved = path.join(desktopRoot, mac.entitlements);
  assert.ok(fs.existsSync(resolved), `missing entitlements file: ${resolved}`);
});

test("mac: entitlements carry the keys the runtime depends on", () => {
  const plist = fs.readFileSync(path.join(desktopRoot, mac.entitlements), "utf8");
  for (const key of [
    // Electron/V8 crash on launch under the hardened runtime without these.
    "com.apple.security.cs.allow-jit",
    "com.apple.security.cs.allow-unsigned-executable-memory",
    // #1784 package OTA installs packages into userData after this bundle was
    // signed; their compiled extensions can never carry our Team ID. Dropping
    // this key breaks package OTA at runtime, not at build time.
    "com.apple.security.cs.disable-library-validation"
  ]) {
    assert.ok(plist.includes(key), `entitlements are missing ${key}`);
  }
});

test("build: electron fuses stay unset", () => {
  // Verified in app-builder-lib platformPackager.doAddElectronFuses: fuses are
  // entirely opt-in, so signing and notarization do not flip them. Enabling
  // onlyLoadAppFromAsar or enableEmbeddedAsarIntegrityValidation would block
  // the shell hot-update loader (#2097) from requiring shell code staged under
  // userData, and the failure mode is obscure. Fail loudly here instead.
  assert.equal(pkg.build.electronFuses, undefined);
});
