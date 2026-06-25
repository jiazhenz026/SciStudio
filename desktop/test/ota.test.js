"use strict";

// Unit tests for the pure OTA decision logic (desktop/ota.js, issue #1775).
// Run with: npm --prefix desktop test   (uses the Node built-in test runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const ota = require("../ota");

test("parseVersion: prerelease form", () => {
  assert.deepEqual(ota.parseVersion("0.2.1-alpha-build0006"), {
    base: "0.2.1",
    channel: "alpha",
    build: 6
  });
});

test("parseVersion: stable form", () => {
  assert.deepEqual(ota.parseVersion("1.4.0"), { base: "1.4.0", channel: "stable", build: 0 });
});

test("parseVersion: invalid returns null", () => {
  assert.equal(ota.parseVersion("nope"), null);
  assert.equal(ota.parseVersion(null), null);
});

test("compareBase: numeric, not lexical", () => {
  assert.equal(ota.compareBase("0.2.1", "0.2.1"), 0);
  assert.equal(ota.compareBase("0.2.1", "0.2.2"), -1);
  assert.equal(ota.compareBase("0.10.0", "0.9.9"), 1); // lexical would be wrong
});

test("patchDirName", () => {
  assert.equal(ota.patchDirName(7), "build7");
});

const CONFIG = { enabled: true, channel: "alpha", manifestUrl: "https://x/m.json" };
const BASELINE = { base: "0.2.1", channel: "alpha", build: 6 };

test("evaluateUpdate: disabled config short-circuits", () => {
  const d = ota.evaluateUpdate({ enabled: false }, { build: 99 }, BASELINE, 6);
  assert.equal(d.kind, "none");
  assert.equal(d.reason, "ota-disabled");
});

test("evaluateUpdate: malformed manifest is invalid", () => {
  assert.equal(ota.evaluateUpdate(CONFIG, {}, BASELINE, 6).kind, "invalid");
  assert.equal(ota.evaluateUpdate(CONFIG, null, BASELINE, 6).kind, "invalid");
});

test("evaluateUpdate: channel mismatch is ignored", () => {
  const m = { build: 99, channel: "beta", base: "0.2.1" };
  assert.equal(ota.evaluateUpdate(CONFIG, m, BASELINE, 6).reason, "channel-mismatch");
});

test("evaluateUpdate: same or lower build is up-to-date", () => {
  const m = { build: 6, channel: "alpha", base: "0.2.1" };
  assert.equal(ota.evaluateUpdate(CONFIG, m, BASELINE, 6).reason, "up-to-date");
  const older = { build: 5, channel: "alpha", base: "0.2.1" };
  assert.equal(ota.evaluateUpdate(CONFIG, older, BASELINE, 6).reason, "up-to-date");
});

test("evaluateUpdate: newer, compatible base => patch", () => {
  const m = { build: 7, channel: "alpha", base: "0.2.1", requires: { min_base: "0.2.1" } };
  const d = ota.evaluateUpdate(CONFIG, m, BASELINE, 6);
  assert.equal(d.kind, "patch");
  assert.equal(d.build, 7);
});

test("evaluateUpdate: newer but base too old => incompatible", () => {
  const m = { build: 8, channel: "alpha", base: "0.3.0", requires: { min_base: "0.3.0" } };
  const d = ota.evaluateUpdate(CONFIG, m, BASELINE, 6);
  assert.equal(d.kind, "incompatible");
  assert.equal(d.minBase, "0.3.0");
});

test("evaluateUpdate: compares against effective build, not baseline", () => {
  // Installed baseline build 6, but an applied patch made effective build 9.
  const m = { build: 8, channel: "alpha", base: "0.2.1", requires: { min_base: "0.2.1" } };
  assert.equal(ota.evaluateUpdate(CONFIG, m, BASELINE, 9).reason, "up-to-date");
});
