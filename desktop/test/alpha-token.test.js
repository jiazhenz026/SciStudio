"use strict";

// Unit tests for the developer-side token tooling (scripts/alpha-token.js,
// issue #1848): mint/inspect round-trip and the CSV issuance ledger. Run with:
// npm --prefix desktop test (Node built-in test runner). Alpha-only.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const tokens = require("../../scripts/alpha-token");

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-tok-"));
}

test("mintToken + inspectToken round-trip", () => {
  const dir = tmpDir();
  try {
    const keyPath = path.join(dir, "priv.key");
    const pubPath = path.join(dir, "pub.pem");
    tokens.generateKeypair({ keyPath, pubPath });
    const fp = "ab".repeat(32);
    const token = tokens.mintToken({ fingerprint: fp, name: "alice", keyPath });
    const result = tokens.inspectToken({ token, fingerprint: fp, pubPath });
    assert.equal(result.valid, true);
    assert.equal(result.payload.name, "alice");
    // A different fingerprint is rejected.
    assert.equal(tokens.inspectToken({ token, fingerprint: "cd".repeat(32), pubPath }).reason, "wrong-machine");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("issuance ledger: append, read, count, CSV escaping", () => {
  const dir = tmpDir();
  const ledgerPath = path.join(dir, "issued.csv");
  try {
    assert.deepEqual(tokens.readIssuance({ ledgerPath }), []);
    tokens.recordIssuance({ fingerprint: "f".repeat(64), name: "Bob", token: "tok-1", ledgerPath });
    // A name containing a comma and a quote must survive the CSV round-trip.
    tokens.recordIssuance({ fingerprint: "e".repeat(64), name: 'Eve, "the tester"', token: "tok-2", ledgerPath });
    const rows = tokens.readIssuance({ ledgerPath });
    assert.equal(rows.length, 2);
    assert.equal(rows[0].name, "Bob");
    assert.equal(rows[0].token, "tok-1");
    assert.equal(rows[1].name, 'Eve, "the tester"');
    assert.equal(rows[1].fingerprint, "e".repeat(64));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
