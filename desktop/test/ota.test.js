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

// #1868: mandatory updates (requires.min_build).
test("isMandatoryUpdate: below min_build is mandatory; at/above is not", () => {
  assert.equal(ota.isMandatoryUpdate({ build: 8, requires: { min_build: 8 } }, 6), true);
  assert.equal(ota.isMandatoryUpdate({ build: 8, requires: { min_build: 8 } }, 8), false);
  assert.equal(ota.isMandatoryUpdate({ build: 8, requires: { min_build: 8 } }, 9), false);
});

test("isMandatoryUpdate: no min_build (or non-numeric) is never mandatory", () => {
  assert.equal(ota.isMandatoryUpdate({ build: 8 }, 0), false);
  assert.equal(ota.isMandatoryUpdate({ build: 8, requires: {} }, 0), false);
  assert.equal(ota.isMandatoryUpdate({ build: 8, requires: { min_build: "8" } }, 0), false);
});

test("isMandatoryUpdate: min_build above the offered build is not enforceable", () => {
  // Applying build 7 would not reach min_build 9, so it must not block.
  assert.equal(ota.isMandatoryUpdate({ build: 7, requires: { min_build: 9 } }, 6), false);
});

test("evaluateUpdate: patch carries mandatory flag from min_build", () => {
  const required = { build: 8, channel: "alpha", base: "0.2.1", requires: { min_base: "0.2.1", min_build: 8 } };
  const d = ota.evaluateUpdate(CONFIG, required, BASELINE, 6);
  assert.equal(d.kind, "patch");
  assert.equal(d.mandatory, true);

  const optional = { build: 8, channel: "alpha", base: "0.2.1", requires: { min_base: "0.2.1" } };
  assert.equal(ota.evaluateUpdate(CONFIG, optional, BASELINE, 6).mandatory, false);
});

test("evaluateUpdate: incompatible can also be mandatory", () => {
  const m = { build: 8, channel: "alpha", base: "0.3.0", requires: { min_base: "0.3.0", min_build: 8 } };
  const d = ota.evaluateUpdate(CONFIG, m, BASELINE, 6);
  assert.equal(d.kind, "incompatible");
  assert.equal(d.mandatory, true);
});

// #1787: an active patch must shadow the bundled baseline only when it is
// strictly newer. A freshly installed bundle whose build is >= the patch build
// supersedes it; otherwise a stale patch would silently shadow the new bundle.
test("resolveActivePatch: no pointer => none", () => {
  assert.deepEqual(ota.resolveActivePatch(null, 6, false), { kind: "none" });
  assert.deepEqual(ota.resolveActivePatch({}, 6, true), { kind: "none" });
  assert.deepEqual(ota.resolveActivePatch({ build: "9" }, 6, true), { kind: "none" });
});

test("resolveActivePatch: patch newer than baseline with src => active", () => {
  assert.deepEqual(ota.resolveActivePatch({ build: 9 }, 6, true), { kind: "active", build: 9 });
});

test("resolveActivePatch: patch newer than baseline but src gone => missing", () => {
  assert.deepEqual(ota.resolveActivePatch({ build: 9 }, 6, false), { kind: "missing", build: 9 });
});

test("resolveActivePatch: baseline >= patch build => stale (the #1787 bug)", () => {
  // Newer bundle reinstalled over an old patch: baseline 12 supersedes patch 9.
  assert.deepEqual(ota.resolveActivePatch({ build: 9 }, 12, true), { kind: "stale", build: 9 });
  // Equal builds (reinstall of the same build) also supersede the patch.
  assert.deepEqual(ota.resolveActivePatch({ build: 9 }, 9, true), { kind: "stale", build: 9 });
  // Stale verdict wins even when the src tree is already gone, so the pointer
  // still gets cleaned up.
  assert.deepEqual(ota.resolveActivePatch({ build: 9 }, 9, false), { kind: "stale", build: 9 });
});

// #1801: PYTHONPATH resolution. Packaged keeps the #1775 layered order; dev
// (unpackaged, run from a source checkout) uses the worktree src alone so a
// leftover OTA patch or a stale staged copy can never shadow it.
test("pythonPathFor: packaged with a patch keeps patch > staged > checkout", () => {
  assert.deepEqual(
    ota.pythonPathFor({
      isPackaged: true,
      patchSrc: "/u/patches/build9/src",
      stagedSrc: "/app/backend/src",
      checkoutSrc: "/repo/src"
    }),
    ["/u/patches/build9/src", "/app/backend/src", "/repo/src"]
  );
});

test("pythonPathFor: packaged without a patch drops the null patch entry", () => {
  assert.deepEqual(
    ota.pythonPathFor({
      isPackaged: true,
      patchSrc: null,
      stagedSrc: "/app/backend/src",
      checkoutSrc: "/repo/src"
    }),
    ["/app/backend/src", "/repo/src"]
  );
});

// #1805: user-facing version string for the update dialogs.
test("displayBuildVersion: base + zero-padded 4-digit build", () => {
  assert.equal(ota.displayBuildVersion("0.3.1", 8), "0.3.1.0008");
  assert.equal(ota.displayBuildVersion("0.3.1", 7), "0.3.1.0007");
  assert.equal(ota.displayBuildVersion("0.3.0", 1234), "0.3.0.1234");
  assert.equal(ota.displayBuildVersion("0.3.1", 0), "0.3.1.0000");
});

test("pythonPathFor: dev uses only the worktree checkout src", () => {
  // Even when a patch and a staged copy are present, dev must ignore both so
  // edits to the worktree src take effect (the #1801 dev-shadow bug).
  assert.deepEqual(
    ota.pythonPathFor({
      isPackaged: false,
      patchSrc: "/u/patches/build9/src",
      stagedSrc: "/repo/desktop/resources/backend/src",
      checkoutSrc: "/repo/src"
    }),
    ["/repo/src"]
  );
});

// #2068: the HTTP cache was cleared on every launch, so each start threw away
// the frontend bundle and paid a full re-download and re-parse. It only has to
// be dropped when the served assets change, which is a build change.
test("shouldClearCache: only when the effective build changed", () => {
  assert.equal(ota.shouldClearCache({ build: 22 }, 22), false);
  assert.equal(ota.shouldClearCache({ build: 21 }, 22), true);
  assert.equal(ota.shouldClearCache({ build: 22 }, 0), true);
});

test("shouldClearCache: a missing or unusable record clears", () => {
  // First launch after this lands, and any corrupted pointer, must still start
  // from a known-clean cache rather than trusting an unreadable record.
  assert.equal(ota.shouldClearCache(null, 22), true);
  assert.equal(ota.shouldClearCache(undefined, 22), true);
  assert.equal(ota.shouldClearCache({}, 22), true);
  assert.equal(ota.shouldClearCache({ build: "22" }, 22), true);
});

// --------------------------------------------------------------------------- //
// #2097: which shell copy the frozen bootstrap loader runs.
// --------------------------------------------------------------------------- //

test("resolveShellSource: a dev source-checkout run is never patched", () => {
  // #1801 applies to the shell exactly as it does to the backend tree: an edit
  // to the worktree must always take effect, even with a patch pointer left
  // behind by a packaged build.
  assert.deepEqual(
    ota.resolveShellSource({
      isPackaged: false,
      pointer: { build: 42 },
      baselineBuild: 0,
      patchShellExists: true
    }),
    { source: "checkout", build: 0 }
  );
});

test("resolveShellSource: no pointer serves the baseline shell", () => {
  assert.deepEqual(
    ota.resolveShellSource({
      isPackaged: true,
      pointer: null,
      baselineBuild: 25,
      patchShellExists: false
    }),
    { source: "baseline", build: 25 }
  );
});

test("resolveShellSource: a newer patch carrying a shell wins", () => {
  assert.deepEqual(
    ota.resolveShellSource({
      isPackaged: true,
      pointer: { build: 42 },
      baselineBuild: 25,
      patchShellExists: true
    }),
    { source: "patch", build: 42 }
  );
});

test("resolveShellSource: a pre-shell-OTA patch falls back to the baseline shell", () => {
  // A snapshot published before #2097 has src/ but no shell/. Its backend still
  // serves from the patch; only the shell falls back. Supported mixed state.
  assert.deepEqual(
    ota.resolveShellSource({
      isPackaged: true,
      pointer: { build: 42 },
      baselineBuild: 25,
      patchShellExists: false
    }),
    { source: "baseline", build: 25 }
  );
});

test("resolveShellSource: a patch at or below the baseline is stale, not active", () => {
  // #1787 for the shell: installing a build over an older applied patch must not
  // leave that patch's shell shadowing the freshly installed one. This is the
  // case the 0.3.4 release depends on, which is why the installer version must
  // carry a build number at least as high as the newest published build.
  for (const patchBuild of [25, 24]) {
    assert.deepEqual(
      ota.resolveShellSource({
        isPackaged: true,
        pointer: { build: patchBuild },
        baselineBuild: 25,
        patchShellExists: true
      }),
      { source: "baseline", build: 25 },
      `patch build ${patchBuild} against baseline 25 must not win`
    );
  }
});

test("shellBootRefused: a marker naming this patch build refuses it", () => {
  assert.equal(ota.shellBootRefused({ build: 42 }, { source: "patch", build: 42 }), true);
});

test("shellBootRefused: a marker from a different build does not refuse", () => {
  assert.equal(ota.shellBootRefused({ build: 41 }, { source: "patch", build: 42 }), false);
});

test("shellBootRefused: no marker never refuses", () => {
  assert.equal(ota.shellBootRefused(null, { source: "patch", build: 42 }), false);
});

test("shellBootRefused: the baseline is the fallback and can never be refused", () => {
  // Refusing the baseline would leave nothing to run, turning one bad patch into
  // an unstartable app.
  assert.equal(ota.shellBootRefused({ build: 25 }, { source: "baseline", build: 25 }), false);
  assert.equal(ota.shellBootRefused({ build: 0 }, { source: "checkout", build: 0 }), false);
});

test("shellMarkerAction: a fresh patch is recorded, a quarantined one is kept", () => {
  assert.equal(ota.shellMarkerAction(null, { source: "patch", build: 42 }), "record");
  assert.equal(ota.shellMarkerAction({ build: 41 }, { source: "patch", build: 42 }), "record");
  assert.equal(ota.shellMarkerAction({ build: 42 }, { source: "patch", build: 42 }), "keep");
  assert.equal(ota.shellMarkerAction({ build: 42 }, { source: "baseline", build: 25 }), "clear");
  assert.equal(ota.shellMarkerAction(null, { source: "checkout", build: 0 }), "clear");
});

test("mayClearShellMarker: only the patch the marker names may clear it", () => {
  assert.equal(ota.mayClearShellMarker({ source: "patch", build: 42 }), true);
  assert.equal(ota.mayClearShellMarker({ source: "baseline", build: 25 }), false);
  assert.equal(ota.mayClearShellMarker({ source: "checkout", build: 0 }), false);
});

test("a shell that never reaches readiness is refused for good, not every other launch", () => {
  // Regression for the alternating crash loop: active.json keeps pointing at the
  // broken build, so clearing the marker on fallback would re-select it next
  // launch and the app would flip between crashing and working forever.
  //
  // Simulated launch loop. `reachesReadiness` models a patch shell that always
  // dies before HTTP readiness; the baseline always comes up.
  let marker = null;
  const pointer = { build: 42 };
  const baselineBuild = 25;
  const ran = [];

  for (let launch = 0; launch < 5; launch += 1) {
    const candidate = ota.resolveShellSource({
      isPackaged: true,
      pointer,
      baselineBuild,
      patchShellExists: true
    });
    const action = ota.shellMarkerAction(marker, candidate);
    let shell = candidate;
    if (action === "keep") {
      shell = { source: "baseline", build: baselineBuild };
    } else if (action === "record") {
      marker = { build: candidate.build };
    } else {
      marker = null;
    }

    ran.push(shell.source);
    const reachesReadiness = shell.source !== "patch";
    if (reachesReadiness && ota.mayClearShellMarker(shell)) {
      marker = null;
    }
  }

  // One attempt, then the baseline forever — never a second crash.
  assert.deepEqual(ran, ["patch", "baseline", "baseline", "baseline", "baseline"]);
  assert.deepEqual(marker, { build: 42 }, "the quarantine must survive a healthy baseline launch");
});

test("a newer patch is still tried after an older one was quarantined", () => {
  // The quarantine must not become a permanent refusal of all future updates.
  const marker = { build: 42 };
  const candidate = ota.resolveShellSource({
    isPackaged: true,
    pointer: { build: 43 },
    baselineBuild: 25,
    patchShellExists: true
  });
  assert.deepEqual(candidate, { source: "patch", build: 43 });
  assert.equal(ota.shellMarkerAction(marker, candidate), "record");
});

test("reinstalling over a quarantined patch clears the marker", () => {
  // A baseline that supersedes the patch (#1787) is a fresh start, so the stale
  // quarantine must not outlive it.
  const candidate = ota.resolveShellSource({
    isPackaged: true,
    pointer: { build: 42 },
    baselineBuild: 42,
    patchShellExists: true
  });
  assert.deepEqual(candidate, { source: "baseline", build: 42 });
  assert.equal(ota.shellMarkerAction({ build: 42 }, candidate), "clear");
});
