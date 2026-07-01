"use strict";

// #1895: Guard the Linux AppImage packaging chain so a future edit to
// package.json or a rename of the runtime script cannot silently break the
// Linux build without a test failing. Run with: npm --prefix desktop test.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.join(__dirname, "..");
const pkg = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));

test("package.json declares a Linux AppImage electron-builder target", () => {
  const linux = pkg.build && pkg.build.linux;
  assert.ok(linux, "build.linux must be defined");
  assert.deepEqual(linux.target, ["AppImage"]);
  assert.equal(linux.icon, "icon.png", "Linux icon must reference the bundled PNG");
});

test("package.json exposes the Linux build + dist npm scripts", () => {
  assert.equal(
    pkg.scripts["build:python:linux"],
    "bash ./scripts/build-python-runtime-linux.sh"
  );
  assert.equal(pkg.scripts["dist:linux"], "electron-builder --linux AppImage");
});

test("Linux Python runtime uses python-build-standalone linux-gnu triples", () => {
  const scriptPath = path.join(desktopRoot, "scripts", "build-python-runtime-linux.sh");
  assert.ok(fs.existsSync(scriptPath), "build-python-runtime-linux.sh must exist");
  const body = fs.readFileSync(scriptPath, "utf8");
  assert.match(body, /python-build-standalone/);
  assert.match(body, /x86_64-unknown-linux-gnu/);
  assert.match(body, /aarch64-unknown-linux-gnu/);
  // `pty` is stdlib on Linux; the verification line imports it, not winpty.
  assert.match(body, /import scistudio, fastapi, uvicorn, pty/);
  // scistudio must load from source/OTA, not a redundant bundled copy (#1775).
  assert.match(body, /pip uninstall -y scistudio/);
});

test("the AppImage icon asset is present and a valid PNG", () => {
  // electron-builder needs a >=512px source icon for Linux; the shared asset is
  // 1024x1024. Assert presence and a PNG header rather than decoding the image.
  const iconPath = path.join(desktopRoot, "assets", "icon.png");
  assert.ok(fs.existsSync(iconPath), "assets/icon.png must exist");
  const header = fs.readFileSync(iconPath).subarray(0, 8);
  assert.deepEqual(
    Array.from(header),
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
    "icon.png must be a valid PNG"
  );
});
