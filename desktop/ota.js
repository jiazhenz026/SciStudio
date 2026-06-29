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

// #1805: a user-facing version string for the update dialogs — "0.3.1.0008"
// (base + zero-padded build) instead of the engineering-flavored "build 8".
// The build is zero-padded to 4 digits to match the display/SemVer form
// (a.b.c-channel-buildNNNN) used elsewhere.
function displayBuildVersion(base, build) {
  const padded = String(Math.max(0, Number(build) || 0)).padStart(4, "0");
  return `${base}.${padded}`;
}

// #1868: is the offered update mandatory for this client? A manifest may carry
// `requires.min_build: N`; when the local effective build is below it the update
// must be taken. Guard on `manifest.build >= min_build` so applying the offered
// build actually clears the requirement (a misconfigured min_build above the
// offered build is treated as non-mandatory rather than an unsatisfiable block).
function isMandatoryUpdate(manifest, effectiveBuild) {
  const minBuild =
    manifest && manifest.requires && typeof manifest.requires.min_build === "number"
      ? manifest.requires.min_build
      : 0;
  return effectiveBuild < minBuild && manifest.build >= minBuild;
}

// Decide what to do with a fetched manifest given local state.
//
// Returns one of:
//   { kind: "none", reason }          - nothing to do
//   { kind: "invalid", reason }       - manifest is malformed; ignore it
//   { kind: "incompatible", build, minBase, mandatory } - newer, needs a new installer
//   { kind: "patch", build, mandatory } - newer and hot-patchable
//
// #1868: `mandatory` is true when the manifest's `requires.min_build` is newer
// than the local build; main.js blocks startup on a mandatory update.
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
  const mandatory = isMandatoryUpdate(manifest, effectiveBuild);
  const minBase = (manifest.requires && manifest.requires.min_base) || manifest.base;
  if (minBase && baseline && compareBase(baseline.base, minBase) < 0) {
    return { kind: "incompatible", build: manifest.build, minBase, mandatory };
  }
  return { kind: "patch", build: manifest.build, mandatory };
}

// #1787: decide how to treat the persisted active-patch pointer given the
// installed baseline build and whether the patch source tree still exists.
//
// Returns one of:
//   { kind: "none" }            - no valid pointer; serve the bundled baseline
//   { kind: "stale", build }    - patch build <= baseline; a reinstall (or a
//                                 newer bundle) superseded it. The caller must
//                                 discard it so the stale patch source can never
//                                 shadow the newer bundled source on PYTHONPATH.
//   { kind: "missing", build }  - pointer set, newer than baseline, but the
//                                 patch src tree is gone; serve the baseline
//   { kind: "active", build }   - honor the patch; it is newer than the baseline
//
// Staleness is checked before src existence so a superseded pointer is always
// cleaned up, even if its directory was already partially removed.
function resolveActivePatch(pointer, baselineBuild, srcExists) {
  if (!pointer || typeof pointer.build !== "number") {
    return { kind: "none" };
  }
  if (baselineBuild >= pointer.build) {
    return { kind: "stale", build: pointer.build };
  }
  if (!srcExists) {
    return { kind: "missing", build: pointer.build };
  }
  return { kind: "active", build: pointer.build };
}

// Resolve the ordered PYTHONPATH entries for the bundled Python runtime.
//
// Packaged (installed app): an applied OTA patch (if any) shadows the staged
// bundle, which shadows the checkout src — the #1775 layered model, unchanged.
//
// Dev (unpackaged, launched from a source checkout via `npm run dev`): the
// worktree `src` is the single source of truth. A leftover userData OTA patch
// or a stale staged `resources/backend/src` copy must NEVER shadow it. This is
// not covered by resolveActivePatch's #1787 stale check, because a dev build's
// baseline build is 0, so any applied patch (build > 0) always compares as
// "newer" and would win. isPackaged is the correct discriminator: an installed
// app is packaged; a source-checkout dev run is not.
//
// Falsy entries are dropped so callers can pass a null patchSrc.
function pythonPathFor({ isPackaged, patchSrc, stagedSrc, checkoutSrc }) {
  if (!isPackaged) {
    return [checkoutSrc].filter(Boolean);
  }
  return [patchSrc, stagedSrc, checkoutSrc].filter(Boolean);
}

module.exports = {
  VERSION_RE,
  parseVersion,
  compareBase,
  patchDirName,
  isMandatoryUpdate,
  evaluateUpdate,
  resolveActivePatch,
  pythonPathFor,
  displayBuildVersion
};
