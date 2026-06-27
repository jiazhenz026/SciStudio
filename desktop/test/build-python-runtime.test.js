"use strict";

// Regression guard for issue #1807: the Windows portable Python runtime must be
// staged from astral-sh/python-build-standalone (a full CPython, no `._pth`),
// NOT the python.org embeddable zip.
//
// The embeddable distribution ships a `pythonXX._pth` file, and when a `._pth`
// file is present CPython ignores the PYTHONPATH environment variable. The
// bundled app loads scistudio from resources/backend/src (and OTA patches from
// a userData dir) purely through PYTHONPATH (desktop/main.js runtimeEnv), so an
// embeddable runtime could never import scistudio on Windows ("No module named
// 'scistudio'") and OTA patches could never shadow the baseline. macOS already
// uses python-build-standalone; this keeps Windows on the same footing.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SCRIPT = fs.readFileSync(
  path.join(__dirname, "..", "scripts", "build-python-runtime.ps1"),
  "utf8"
);

test("windows runtime uses python-build-standalone (msvc install_only)", () => {
  assert.match(SCRIPT, /python-build-standalone/);
  assert.match(SCRIPT, /x86_64-pc-windows-msvc/);
  assert.match(SCRIPT, /install_only/);
});

test("windows runtime does NOT use the embeddable zip", () => {
  // The embeddable distribution is the root cause of #1807; it must not return.
  assert.doesNotMatch(SCRIPT, /embed-amd64/);
  assert.doesNotMatch(SCRIPT, /www\.python\.org\/ftp\/python/);
});

test("windows runtime does NOT manipulate a _pth file", () => {
  // A `._pth` file is what makes the interpreter ignore PYTHONPATH. A full
  // standalone CPython has none, and the script must not reintroduce one.
  // Ignore comment lines (which legitimately explain why `._pth` is avoided);
  // assert only executable code never touches a `_pth` path.
  const code = SCRIPT.split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join("\n");
  assert.doesNotMatch(code, /_pth/);
});

test("windows runtime still removes the redundant bundled scistudio", () => {
  // scistudio must load from resources/backend/src / OTA, not from a second
  // copy installed into the interpreter (#1775).
  assert.match(SCRIPT, /pip uninstall -y scistudio/);
});
