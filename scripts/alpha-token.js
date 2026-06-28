#!/usr/bin/env node
// #1848: developer-side tooling for the alpha activation gate (offline, zero-server).
//
// The private signing key never lives in the repo. `keygen` writes it to
// ~/.scistudio/alpha-signing.key and writes the matching public key into
// desktop/resources/alpha-public-key.pem (safe to commit + ship). `sign` mints a
// token bound to one machine fingerprint that the desktop app verifies offline.
//
// This module exposes its core functions for reuse (scripts/alpha-token-gui.js);
// the CLI only runs when invoked directly. ALPHA-ONLY; delete in beta with the
// rest of the gate (see issue #1848).
//
// Token format (shared with desktop/activation.js):
//   token        = base64url(payloadJson) + "." + base64url(ed25519Signature)
//   signed bytes = utf8 bytes of the base64url(payloadJson) string
//   payloadJson  = {"v":1,"fp":"<sha256-hex>","name":<string|null>,"iat":<unix>}
//
// CLI usage:
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

// --------------------------------------------------------------------------- //
// Core functions (return values; no I/O to stdout). Reused by the GUI.
// --------------------------------------------------------------------------- //

function generateKeypair({ keyPath = defaultKeyPath(), pubPath = defaultPubPath() } = {}) {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("ed25519");
  const privPem = privateKey.export({ type: "pkcs8", format: "pem" });
  const pubPem = publicKey.export({ type: "spki", format: "pem" });

  fs.mkdirSync(path.dirname(keyPath), { recursive: true });
  fs.writeFileSync(keyPath, privPem, { mode: 0o600 });

  fs.mkdirSync(path.dirname(pubPath), { recursive: true });
  fs.writeFileSync(pubPath, pubPem);

  return { keyPath, pubPath };
}

function mintToken({ fingerprint, name = null, keyPath = defaultKeyPath() }) {
  if (!fingerprint) {
    throw new Error("fingerprint is required");
  }
  const privPem = fs.readFileSync(keyPath, "utf8");
  const keyObject = crypto.createPrivateKey(privPem);
  const payload = {
    v: 1,
    fp: String(fingerprint).trim(),
    name: name ? String(name) : null,
    iat: Math.floor(Date.now() / 1000)
  };
  const payloadB64 = b64url(Buffer.from(JSON.stringify(payload), "utf8"));
  const signature = crypto.sign(null, Buffer.from(payloadB64, "utf8"), keyObject);
  return `${payloadB64}.${b64url(signature)}`;
}

function inspectToken({ token, fingerprint, pubPath = defaultPubPath() }) {
  const pubPem = fs.readFileSync(pubPath, "utf8");
  const parts = String(token).trim().split(".");
  if (parts.length !== 2) {
    return { valid: false, reason: "malformed" };
  }
  const keyObject = crypto.createPublicKey(pubPem);
  const ok = crypto.verify(
    null,
    Buffer.from(parts[0], "utf8"),
    keyObject,
    Buffer.from(parts[1], "base64url")
  );
  if (!ok) {
    return { valid: false, reason: "bad-signature" };
  }
  const payload = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  if (fingerprint && payload.fp !== String(fingerprint).trim()) {
    return { valid: false, reason: "wrong-machine", payload };
  }
  return { valid: true, reason: "ok", payload };
}

function keyStatus({ keyPath = defaultKeyPath(), pubPath = defaultPubPath() } = {}) {
  return {
    keyPath,
    pubPath,
    hasPrivate: fs.existsSync(keyPath),
    hasPublic: fs.existsSync(pubPath)
  };
}

// --------------------------------------------------------------------------- //
// Issuance ledger (#1848): an append-only CSV of every token signed, so the
// developer can see how many tokens were issued and to which machines. Lives
// outside the repo (next to the signing key) and is never committed.
// --------------------------------------------------------------------------- //

const LEDGER_HEADER = "issued_at,name,fingerprint,token";

function defaultLedgerPath() {
  return path.join(os.homedir(), ".scistudio", "alpha-issued-tokens.csv");
}

function csvField(value) {
  return `"${String(value == null ? "" : value).replace(/"/g, '""')}"`;
}

function parseCsvLine(line) {
  const fields = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      fields.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  fields.push(current);
  return fields;
}

// Append one issuance to the CSV ledger (creating it with a header if needed).
function recordIssuance({ fingerprint, name = null, token, ledgerPath = defaultLedgerPath() }) {
  fs.mkdirSync(path.dirname(ledgerPath), { recursive: true });
  if (!fs.existsSync(ledgerPath)) {
    fs.writeFileSync(ledgerPath, `${LEDGER_HEADER}\n`);
  }
  const row = [
    csvField(new Date().toISOString()),
    csvField(name),
    csvField(fingerprint),
    csvField(token)
  ].join(",");
  fs.appendFileSync(ledgerPath, `${row}\n`);
  return ledgerPath;
}

// Read the ledger back into rows. Returns [] when it does not exist yet.
function readIssuance({ ledgerPath = defaultLedgerPath() } = {}) {
  if (!fs.existsSync(ledgerPath)) {
    return [];
  }
  const lines = fs.readFileSync(ledgerPath, "utf8").split("\n").filter((line) => line.length > 0);
  if (lines.length <= 1) {
    return [];
  }
  return lines.slice(1).map((line) => {
    const [issued_at, name, fingerprint, token] = parseCsvLine(line);
    return { issued_at, name, fingerprint, token };
  });
}

// --------------------------------------------------------------------------- //
// CLI.
// --------------------------------------------------------------------------- //

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

function cliKeygen(args) {
  const result = generateKeypair({
    keyPath: args.key && args.key !== true ? args.key : undefined,
    pubPath: args.out && args.out !== true ? args.out : undefined
  });
  process.stdout.write(`Private signing key: ${result.keyPath}\n`);
  process.stdout.write("  -> keep secret, never commit. Back it up; losing it invalidates every token.\n");
  process.stdout.write(`Public key:          ${result.pubPath}\n`);
  process.stdout.write("  -> commit it and rebuild the app so the gate can verify tokens.\n");
}

function cliSign(args) {
  if (!args.fingerprint || args.fingerprint === true) {
    throw new Error("sign requires --fingerprint <machine-fingerprint>");
  }
  const name = args.name && args.name !== true ? args.name : null;
  const token = mintToken({
    fingerprint: args.fingerprint,
    name,
    keyPath: args.key && args.key !== true ? args.key : undefined
  });
  recordIssuance({ fingerprint: String(args.fingerprint).trim(), name, token });
  process.stdout.write(`${token}\n`);
}

function cliList() {
  const rows = readIssuance();
  const unique = new Set(rows.map((row) => row.fingerprint));
  process.stdout.write(`Issued tokens: ${rows.length} (${unique.size} unique machines)\n`);
  process.stdout.write(`Ledger: ${defaultLedgerPath()}\n`);
  for (const row of rows) {
    process.stdout.write(`  ${row.issued_at}  ${row.name || "-"}  ${row.fingerprint.slice(0, 12)}…\n`);
  }
}

function cliVerify(args) {
  if (!args.token || args.token === true) {
    throw new Error("verify requires --token <token>");
  }
  if (!args.fingerprint || args.fingerprint === true) {
    throw new Error("verify requires --fingerprint <machine-fingerprint>");
  }
  const result = inspectToken({
    token: args.token,
    fingerprint: args.fingerprint,
    pubPath: args.pubkey && args.pubkey !== true ? args.pubkey : undefined
  });
  if (!result.valid) {
    process.stdout.write(`INVALID (${result.reason})\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`VALID (name=${result.payload.name || "-"}, iat=${result.payload.iat})\n`);
}

function usage() {
  process.stdout.write(
    [
      "Alpha activation token tool (#1848)",
      "",
      "  node scripts/alpha-token.js keygen [--out <pubkey.pem>] [--key <private.key>]",
      "  node scripts/alpha-token.js sign --fingerprint <fp> [--name <tester>] [--key <private.key>]",
      "  node scripts/alpha-token.js verify --token <t> --fingerprint <fp> [--pubkey <pubkey.pem>]",
      "  node scripts/alpha-token.js list",
      "",
      "Or run the GUI:  node scripts/alpha-token-gui.js",
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
        cliKeygen(args);
        break;
      case "sign":
        cliSign(args);
        break;
      case "verify":
        cliVerify(args);
        break;
      case "list":
        cliList();
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

if (require.main === module) {
  main();
}

module.exports = {
  defaultKeyPath,
  defaultPubPath,
  defaultLedgerPath,
  generateKeypair,
  mintToken,
  inspectToken,
  keyStatus,
  recordIssuance,
  readIssuance
};
