#!/usr/bin/env node
// #1848: developer-side CLI for the alpha activation gate (offline, zero-server).
//
// The private signing key never lives in the repo. `keygen` writes it to
// ~/.scistudio/alpha-signing.key and writes the matching public key into
// desktop/resources/alpha-public-key.pem (safe to commit + ship). `sign` mints a
// token bound to one machine fingerprint that the desktop app verifies offline.
//
// This whole tool is ALPHA-ONLY; delete it in beta together with the gate (see
// issue #1848).
//
// Token format (shared with desktop/activation.js):
//   token        = base64url(payloadJson) + "." + base64url(ed25519Signature)
//   signed bytes = utf8 bytes of the base64url(payloadJson) string
//   payloadJson  = {"v":1,"fp":"<sha256-hex>","name":<string|null>,"iat":<unix>}
//
// Usage:
//   node scripts/alpha-token.js keygen [--out <pubkey.pem>] [--key <private.key>]
//   node scripts/alpha-token.js sign --fingerprint <fp> [--name <tester>] [--key <private.key>]
//   node scripts/alpha-token.js verify --token <t> --fingerprint <fp> [--pubkey <pubkey.pem>]

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}

function defaultKeyPath() {
  return path.join(os.homedir(), ".scistudio", "alpha-signing.key");
}

function defaultPubPath() {
  return path.join(__dirname, "..", "desktop", "resources", "alpha-public-key.pem");
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const key = token.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("--")) {
        args[key] = true;
      } else {
        args[key] = next;
        i += 1;
      }
    }
  }
  return args;
}

function keygen(args) {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("ed25519");
  const privPem = privateKey.export({ type: "pkcs8", format: "pem" });
  const pubPem = publicKey.export({ type: "spki", format: "pem" });

  const keyPath = args.key || defaultKeyPath();
  fs.mkdirSync(path.dirname(keyPath), { recursive: true });
  fs.writeFileSync(keyPath, privPem, { mode: 0o600 });

  const pubPath = args.out || defaultPubPath();
  fs.mkdirSync(path.dirname(pubPath), { recursive: true });
  fs.writeFileSync(pubPath, pubPem);

  process.stdout.write(`Private signing key: ${keyPath}\n`);
  process.stdout.write("  -> keep secret, never commit. Back it up; losing it invalidates every token.\n");
  process.stdout.write(`Public key:          ${pubPath}\n`);
  process.stdout.write("  -> commit it and rebuild the app so the gate can verify tokens.\n");
}

function sign(args) {
  if (!args.fingerprint || args.fingerprint === true) {
    throw new Error("sign requires --fingerprint <machine-fingerprint>");
  }
  const keyPath = args.key || defaultKeyPath();
  const privPem = fs.readFileSync(keyPath, "utf8");
  const keyObject = crypto.createPrivateKey(privPem);

  const payload = {
    v: 1,
    fp: String(args.fingerprint),
    name: args.name && args.name !== true ? String(args.name) : null,
    iat: Math.floor(Date.now() / 1000)
  };
  const payloadB64 = b64url(Buffer.from(JSON.stringify(payload), "utf8"));
  const signature = crypto.sign(null, Buffer.from(payloadB64, "utf8"), keyObject);
  const token = `${payloadB64}.${b64url(signature)}`;
  process.stdout.write(`${token}\n`);
}

function verify(args) {
  if (!args.token || args.token === true) {
    throw new Error("verify requires --token <token>");
  }
  if (!args.fingerprint || args.fingerprint === true) {
    throw new Error("verify requires --fingerprint <machine-fingerprint>");
  }
  const pubPath = args.pubkey || defaultPubPath();
  const pubPem = fs.readFileSync(pubPath, "utf8");
  const parts = String(args.token).trim().split(".");
  if (parts.length !== 2) {
    process.stdout.write("INVALID (malformed)\n");
    process.exitCode = 1;
    return;
  }
  const keyObject = crypto.createPublicKey(pubPem);
  const ok = crypto.verify(
    null,
    Buffer.from(parts[0], "utf8"),
    keyObject,
    Buffer.from(parts[1], "base64url")
  );
  if (!ok) {
    process.stdout.write("INVALID (bad signature)\n");
    process.exitCode = 1;
    return;
  }
  const payload = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  if (payload.fp !== String(args.fingerprint)) {
    process.stdout.write("INVALID (wrong machine)\n");
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`VALID (name=${payload.name || "-"}, iat=${payload.iat})\n`);
}

function usage() {
  process.stdout.write(
    [
      "Alpha activation token tool (#1848)",
      "",
      "  node scripts/alpha-token.js keygen [--out <pubkey.pem>] [--key <private.key>]",
      "  node scripts/alpha-token.js sign --fingerprint <fp> [--name <tester>] [--key <private.key>]",
      "  node scripts/alpha-token.js verify --token <t> --fingerprint <fp> [--pubkey <pubkey.pem>]",
      ""
    ].join("\n")
  );
}

function main() {
  const [command, ...rest] = process.argv.slice(2);
  const args = parseArgs(rest);
  try {
    switch (command) {
      case "keygen":
        keygen(args);
        break;
      case "sign":
        sign(args);
        break;
      case "verify":
        verify(args);
        break;
      default:
        usage();
        process.exitCode = command ? 1 : 0;
    }
  } catch (error) {
    process.stderr.write(`error: ${error.message}\n`);
    process.exitCode = 1;
  }
}

main();
