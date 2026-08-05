"use strict";

// #1986: runtime port selection for the packaged desktop app.
//
// The backend used to bind a fresh ephemeral port on every launch, so the
// renderer loaded `http://127.0.0.1:<random>` each time. `localStorage` is
// origin-scoped, so a new port meant a new origin meant an empty store: the
// zustand `scistudio-studio-ui` snapshot (tutorial prompt state, panel sizes,
// open file tabs, terminal tabs, active bottom tab) was silently discarded at
// every start. Remembering the bound port keeps the origin stable, which keeps
// the preferences.
//
// The decision logic lives here as pure functions so it can be unit tested
// without Electron; `main.js` gathers the on-disk and network facts and acts on
// the verdict, mirroring how `ota.js` is used.

// A remembered port must be non-privileged: ephemeral ports always are, and
// refusing the privileged range means a corrupt or hand-edited file can never
// send the backend at a port it has no business binding.
const MIN_REMEMBERED_PORT = 1024;
const MAX_PORT = 65535;

/**
 * Normalize `SCISTUDIO_DESKTOP_RUNTIME_PORT`.
 *
 * `0` stays meaningful here — it is how an operator asks for the historical
 * "always pick a fresh ephemeral port" behavior. Returns null when the value is
 * absent or unusable, which the caller reports and then ignores.
 */
function normalizeEnvPort(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > MAX_PORT) {
    return null;
  }
  return parsed;
}

/**
 * Normalize a port read back from (or about to be written to) the remembered
 * port file. Unlike the env override, `0` is not a valid remembered port: it is
 * a request for an ephemeral port, never the result of one.
 */
function normalizeRememberedPort(value) {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return null;
  }
  if (value < MIN_REMEMBERED_PORT || value > MAX_PORT) {
    return null;
  }
  return value;
}

/**
 * Extract the remembered port from a parsed `runtime-port.json` record.
 * Anything unrecognized reads as "nothing remembered".
 */
function parseRememberedPort(record) {
  if (!record || typeof record !== "object") {
    return null;
  }
  return normalizeRememberedPort(record.port);
}

/**
 * Decide which `--port` value to hand the backend.
 *
 * An explicit env override always wins and is never second-guessed. Otherwise
 * the remembered port is used when it is still free, and "0" (ephemeral) is the
 * fallback.
 */
function selectRuntimePort({ envPort = null, rememberedPort = null, rememberedPortFree = false }) {
  if (envPort !== null) {
    return String(envPort);
  }
  if (rememberedPort !== null && rememberedPortFree) {
    return String(rememberedPort);
  }
  return "0";
}

/**
 * Decide whether the port the backend actually bound should be written back.
 *
 * An env override is the operator's business, not state to remember, and
 * rewriting an unchanged value would churn the file on every launch.
 */
function shouldRememberPort({ envPort = null, boundPort = null, rememberedPort = null }) {
  if (envPort !== null) {
    return false;
  }
  const normalized = normalizeRememberedPort(boundPort);
  if (normalized === null) {
    return false;
  }
  return normalized !== rememberedPort;
}

/**
 * Read the bound port out of a `scistudio.ready` message. The backend reports
 * it as a field; the URL is the fallback for a message that predates or omits
 * it.
 */
function boundPortFromReady(ready) {
  if (!ready || typeof ready !== "object") {
    return null;
  }
  const direct = normalizeRememberedPort(ready.port);
  if (direct !== null) {
    return direct;
  }
  if (typeof ready.url !== "string") {
    return null;
  }
  try {
    return normalizeRememberedPort(Number.parseInt(new URL(ready.url).port, 10));
  } catch {
    return null;
  }
}

// uvicorn's own bind-failure wording, plus the raw errno name, so the check
// holds on both POSIX ("[Errno 48] ... address already in use") and Windows
// ("[Errno 10048] ... only one usage of each socket address"), and does not
// depend on the localized tail of the message.
const PORT_UNAVAILABLE_MARKERS = [
  "error while attempting to bind on address",
  "eaddrinuse",
  "address already in use"
];

/**
 * Did the runtime fail because it could not take the port we asked for?
 *
 * Only such a failure justifies retrying on an ephemeral port. Retrying a
 * broken interpreter or a missing dependency would just spend the startup
 * timeout twice before showing the same error.
 */
function isPortUnavailableFailure(text) {
  if (typeof text !== "string") {
    return false;
  }
  const haystack = text.toLowerCase();
  return PORT_UNAVAILABLE_MARKERS.some((marker) => haystack.includes(marker));
}

module.exports = {
  isPortUnavailableFailure,
  MIN_REMEMBERED_PORT,
  MAX_PORT,
  normalizeEnvPort,
  normalizeRememberedPort,
  parseRememberedPort,
  selectRuntimePort,
  shouldRememberPort,
  boundPortFromReady
};
