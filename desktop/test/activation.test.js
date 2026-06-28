"use strict";

// Unit tests for the alpha activation gate's pure logic (desktop/activation.js,
// issue #1848). Run with: npm --prefix desktop test (Node built-in test runner).
//
// Alpha-only; removed in beta together with the gate.

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const activation = require("../activation");

// Mint a token the way scripts/alpha-token.js does, so the test exercises the
// real verify path against an independently generated keypair.
function makeKeypair() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("ed25519");
  return {
    privatePem: privateKey.export({ type: "pkcs8", format: "pem" }),
    publicPem: publicKey.export({ type: "spki", format: "pem" })
  };
}

function signToken(privatePem, payload) {
  const payloadB64 = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  const sig = crypto.sign(null, Buffer.from(payloadB64, "utf8"), crypto.createPrivateKey(privatePem));
  return `${payloadB64}.${sig.toString("base64url")}`;
}

test("machineFingerprint: stable 64-char hex digest", () => {
  const fp = activation.machineFingerprint();
  assert.match(fp, /^[0-9a-f]{64}$/);
  assert.equal(fp, activation.machineFingerprint());
});

test("verifyToken: valid token for this machine", () => {
  const { privatePem, publicPem } = makeKeypair();
  const fp = "a".repeat(64);
  const token = signToken(privatePem, { v: 1, fp, name: "tester", iat: 1 });
  const result = activation.verifyToken(token, fp, publicPem);
  assert.equal(result.ok, true);
  assert.equal(result.payload.name, "tester");
});

test("verifyToken: rejects a token bound to a different machine", () => {
  const { privatePem, publicPem } = makeKeypair();
  const token = signToken(privatePem, { v: 1, fp: "a".repeat(64), name: null, iat: 1 });
  const result = activation.verifyToken(token, "b".repeat(64), publicPem);
  assert.equal(result.ok, false);
  assert.equal(result.reason, "wrong-machine");
});

test("verifyToken: rejects a token signed by a different key", () => {
  const signer = makeKeypair();
  const other = makeKeypair();
  const fp = "c".repeat(64);
  const token = signToken(signer.privatePem, { v: 1, fp, name: null, iat: 1 });
  const result = activation.verifyToken(token, fp, other.publicPem);
  assert.equal(result.ok, false);
  assert.equal(result.reason, "bad-signature");
});

test("verifyToken: rejects a tampered payload", () => {
  const { privatePem, publicPem } = makeKeypair();
  const fp = "d".repeat(64);
  const token = signToken(privatePem, { v: 1, fp, name: null, iat: 1 });
  const [, sig] = token.split(".");
  const forged = Buffer.from(JSON.stringify({ v: 1, fp, name: "x", iat: 9 }), "utf8").toString("base64url");
  const result = activation.verifyToken(`${forged}.${sig}`, fp, publicPem);
  assert.equal(result.ok, false);
  assert.equal(result.reason, "bad-signature");
});

test("verifyToken: empty / malformed / unconfigured", () => {
  const { publicPem } = makeKeypair();
  assert.equal(activation.verifyToken("", "x", publicPem).reason, "empty");
  assert.equal(activation.verifyToken("nodot", "x", publicPem).reason, "malformed");
  assert.equal(activation.verifyToken("a.b", "x", null).reason, "not-configured");
});

test("gateEnabled: env override beats packaged default", () => {
  const prev = process.env.SCISTUDIO_ALPHA_GATE;
  try {
    delete process.env.SCISTUDIO_ALPHA_GATE;
    assert.equal(activation.gateEnabled(true), true);
    assert.equal(activation.gateEnabled(false), false);
    process.env.SCISTUDIO_ALPHA_GATE = "0";
    assert.equal(activation.gateEnabled(true), false);
    process.env.SCISTUDIO_ALPHA_GATE = "1";
    assert.equal(activation.gateEnabled(false), true);
  } finally {
    if (prev === undefined) {
      delete process.env.SCISTUDIO_ALPHA_GATE;
    } else {
      process.env.SCISTUDIO_ALPHA_GATE = prev;
    }
  }
});

test("checkActivation + storage round-trip", () => {
  const { privatePem, publicPem } = makeKeypair();
  const fp = "e".repeat(64);
  const token = signToken(privatePem, { v: 1, fp, name: "round-trip", iat: 1 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-alpha-"));
  try {
    assert.equal(activation.checkActivation({ userDataDir: dir, fingerprint: fp, publicKeyPem: publicPem }).activated, false);
    activation.writeStoredToken(dir, token, { name: "round-trip" });
    const status = activation.checkActivation({ userDataDir: dir, fingerprint: fp, publicKeyPem: publicPem });
    assert.equal(status.activated, true);
    // A stored token does not activate a different machine.
    const other = activation.checkActivation({ userDataDir: dir, fingerprint: "f".repeat(64), publicKeyPem: publicPem });
    assert.equal(other.activated, false);
    assert.equal(other.reason, "wrong-machine");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
