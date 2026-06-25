"use strict";

// Pure OTA decision logic for the SciStudio desktop client (issue #1775).
//
// This module has no Electron or filesystem dependencies so it can be unit
// tested directly (see test/ota.test.js). main.js owns all IO: fetching the
// manifest, downloading/verifying/extracting the snapshot, and restarting the
// runtime. The rules here decide *whether* an update applies.

// Matches the #1742 version display/SemVer form: "a.b.c-<channel>-build<NNNN>"
// for prereleases, or a bare "a.b.c" for stable.
const VERSION_RE = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)-build(\d+))?$/;

function parseVersion(version) {
  const match = VERSION_RE.exec(String(version == null ? "" : version).trim());
  if (!match) {
    return null;
  }
  return {
    base: `${match[1]}.${match[2]}.${match[3]}`,
    channel: match[4] || "stable",
    build: match[5] ? parseInt(match[5], 10) : 0
  };
}

// Numeric compare of two "a.b.c" base strings. Returns -1, 0, or 1.
function compareBase(a, b) {
  const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
  const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < 3; i += 1) {
    const diff = (pa[i] || 0) - (pb[i] || 0);
    if (diff !== 0) {
      return diff < 0 ? -1 : 1;
    }
  }
  return 0;
}

function patchDirName(build) {
  return `build${build}`;
}

// Decide what to do with a fetched manifest given local state.
//
// Returns one of:
//   { kind: "none", reason }          - nothing to do
//   { kind: "invalid", reason }       - manifest is malformed; ignore it
//   { kind: "incompatible", build, minBase } - newer, but needs a new installer
//   { kind: "patch", build }          - newer and hot-patchable
function evaluateUpdate(config, manifest, baseline, effectiveBuild) {
  if (!config || !config.enabled) {
    return { kind: "none", reason: "ota-disabled" };
  }
  if (!manifest || typeof manifest.build !== "number") {
    return { kind: "invalid", reason: "bad-manifest" };
  }
  if (manifest.channel && config.channel && manifest.channel !== config.channel) {
    return { kind: "none", reason: "channel-mismatch" };
  }
  if (manifest.build <= effectiveBuild) {
    return { kind: "none", reason: "up-to-date" };
  }
  const minBase = (manifest.requires && manifest.requires.min_base) || manifest.base;
  if (minBase && baseline && compareBase(baseline.base, minBase) < 0) {
    return { kind: "incompatible", build: manifest.build, minBase };
  }
  return { kind: "patch", build: manifest.build };
}

module.exports = {
  VERSION_RE,
  parseVersion,
  compareBase,
  patchDirName,
  evaluateUpdate
};
