// #1848: Alpha activation gate (offline, zero-server, per-machine token).
//
// Goal: stop alpha testers from redistributing the build to unauthorized
// people. The installer/dmg itself never expires and may be reused; the gate is
// a per-machine activation token. Without a valid token the app does not open.
//
// Trust model (Option C — offline signed token):
//   - The developer holds an Ed25519 private signing key (outside the repo).
//   - The matching public key ships in the build (resources/alpha-public-key.pem).
//   - A token binds to one machine fingerprint and is signed with the private
//     key. The app verifies the signature and that the bound fingerprint equals
//     this machine's fingerprint. A forwarded copy fails on a different machine.
//
// This whole module is ALPHA-ONLY and is removed in beta. See issue #1848 for
// the removal checklist.
//
// Token format (shared with scripts/alpha-token.js):
//   token       = base64url(payloadJson) + "." + base64url(ed25519Signature)
//   signed bytes = utf8 bytes of the base64url(payloadJson) string
//   payloadJson = {"v":1,"fp":"<sha256-hex>","name":<string|null>,"iat":<unix>}

const crypto = require("crypto");
const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

// --------------------------------------------------------------------------- //
// Machine fingerprint (stable, cross-platform: macOS + Windows).
// --------------------------------------------------------------------------- //

// Best-effort stable per-machine identifier. macOS uses the IOPlatformUUID;
// Windows uses the registry MachineGuid. Both survive app reinstalls. Falls back
// to the hostname when the platform probe is unavailable so the gate still has
// *some* binding rather than crashing.
function rawMachineId() {
  try {
    if (process.platform === "darwin") {
      const out = execFileSync("ioreg", ["-rd1", "-c", "IOPlatformExpertDevice"], {
        encoding: "utf8",
        timeout: 5000
      });
      const match = out.match(/"IOPlatformUUID"\s*=\s*"([^"]+)"/);
      if (match && match[1]) {
        return `mac:${match[1]}`;
      }
    } else if (process.platform === "win32") {
      const out = execFileSync(
        "reg",
        ["query", "HKLM\\SOFTWARE\\Microsoft\\Cryptography", "/v", "MachineGuid"],
        { encoding: "utf8", timeout: 5000 }
      );
      const match = out.match(/MachineGuid\s+REG_SZ\s+([A-Za-z0-9-]+)/i);
      if (match && match[1]) {
        return `win:${match[1]}`;
      }
    }
  } catch {
    // Fall through to the hostname-based fallback below.
  }
  return `host:${os.hostname()}`;
}

// Public fingerprint: a sha256 hex digest the tester copies and sends to the
// developer. Hashing hides the raw machine id and yields a fixed-width string.
function machineFingerprint() {
  return crypto.createHash("sha256").update(`scistudio-alpha-v1:${rawMachineId()}`).digest("hex");
}

// --------------------------------------------------------------------------- //
// Token verification.
// --------------------------------------------------------------------------- //

// Verify a token against a machine fingerprint using the shipped public key.
// Returns { ok, reason, payload }. `reason` is a short machine-readable tag the
// gate UI maps to human text. Never throws.
function verifyToken(token, fingerprint, publicKeyPem) {
  if (!token || typeof token !== "string") {
    return { ok: false, reason: "empty" };
  }
  if (!publicKeyPem) {
    return { ok: false, reason: "not-configured" };
  }
  const parts = token.trim().split(".");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return { ok: false, reason: "malformed" };
  }

  let keyObject;
  try {
    keyObject = crypto.createPublicKey(publicKeyPem);
  } catch {
    return { ok: false, reason: "bad-key" };
  }

  const message = Buffer.from(parts[0], "utf8");
  const signature = Buffer.from(parts[1], "base64url");

  let signatureValid = false;
  try {
    // Ed25519: algorithm is null; the key carries the curve.
    signatureValid = crypto.verify(null, message, keyObject, signature);
  } catch {
    return { ok: false, reason: "verify-error" };
  }
  if (!signatureValid) {
    return { ok: false, reason: "bad-signature" };
  }

  let payload;
  try {
    payload = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (!payload || typeof payload !== "object" || payload.fp !== fingerprint) {
    return { ok: false, reason: "wrong-machine", payload };
  }
  return { ok: true, reason: "ok", payload };
}

// --------------------------------------------------------------------------- //
// Public key + stored activation.
// --------------------------------------------------------------------------- //

// Resolve the shipped Ed25519 public key. An env override (SCISTUDIO_ALPHA_PUBKEY,
// with literal "\n" allowed for one-line values) wins so a packaged build can be
// tested without a rebuild. Returns the PEM string or null when not configured.
function loadPublicKeyPem(resourcesDir) {
  const inline = (process.env.SCISTUDIO_ALPHA_PUBKEY || "").trim();
  if (inline) {
    return inline.replace(/\\n/g, "\n");
  }
  try {
    return fs.readFileSync(path.join(resourcesDir, "alpha-public-key.pem"), "utf8");
  } catch {
    return null;
  }
}

function activationFilePath(userDataDir) {
  return path.join(userDataDir, "alpha-activation.json");
}

function readStoredToken(userDataDir) {
  try {
    const data = JSON.parse(fs.readFileSync(activationFilePath(userDataDir), "utf8"));
    return typeof data.token === "string" ? data.token : null;
  } catch {
    return null;
  }
}

function writeStoredToken(userDataDir, token, payload) {
  const file = activationFilePath(userDataDir);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(
    tmp,
    JSON.stringify(
      {
        token,
        name: (payload && payload.name) || null,
        activated_at: new Date().toISOString()
      },
      null,
      2
    )
  );
  fs.renameSync(tmp, file);
}

// Is this machine already activated? Re-verifies the stored token every launch
// so a token copied to another machine (different fingerprint) is rejected.
function checkActivation({ userDataDir, fingerprint, publicKeyPem }) {
  const token = readStoredToken(userDataDir);
  if (!token) {
    return { activated: false, reason: "no-token" };
  }
  const result = verifyToken(token, fingerprint, publicKeyPem);
  return { activated: result.ok, reason: result.reason, payload: result.payload };
}

// --------------------------------------------------------------------------- //
// Gate flag.
// --------------------------------------------------------------------------- //

// Whether the activation gate is active. SCISTUDIO_ALPHA_GATE forces it on/off;
// otherwise it gates packaged builds (real dmg/installer) and is skipped in dev
// so a source checkout is never locked out.
function gateEnabled(isPackaged) {
  const raw = (process.env.SCISTUDIO_ALPHA_GATE || "").trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "on") {
    return true;
  }
  if (raw === "0" || raw === "false" || raw === "off") {
    return false;
  }
  return Boolean(isPackaged);
}

module.exports = {
  machineFingerprint,
  verifyToken,
  loadPublicKeyPem,
  activationFilePath,
  readStoredToken,
  writeStoredToken,
  checkActivation,
  gateEnabled
};
