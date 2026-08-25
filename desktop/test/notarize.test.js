"use strict";

// Notarization visibility invariants (issue #2176).
//
// The bug these guard against is not a crash -- it is silence, and a wait with
// no upper bound. When notarytool runs with `--output-format json` it prints
// nothing until it finishes, so a build queued behind Apple and a build that is
// wedged produce the same empty log; and `submit --wait` has been reported to
// sit for hours after Apple has already finished, so the wait itself is not
// trustworthy either. Two 0.3.4 macOS builds were cancelled at 118 and 79
// minutes on that evidence, neither ever finishing.
//
// Nothing here talks to Apple. The pure argv/parsing helpers are tested
// directly; the wiring that decides whether the hook runs at all is asserted
// against package.json, because a hook that is present but unreferenced fails
// exactly as quietly as the problem it replaces.
//
// Run with: npm --prefix desktop test   (uses the Node built-in test runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const notarize = require("../scripts/notarize.js");
const pkg = require("../package.json");

const CREDS = { keyPath: "/tmp/AuthKey.p8", keyId: "264X72XYKB", issuer: "abc-123" };

// `notarytool submit` in its real shape: the id arrives, the process exits.
const SUBMITTED = `Conducting pre-submission checks for app.zip and initiating connection to the Apple notary service...
Submission ID received
  id: 2efe2717-52ef-43a5-96dc-0797e4ca1041
Upload progress: 100.00% (312 MB of 312 MB)
Successfully uploaded file
  id: 2efe2717-52ef-43a5-96dc-0797e4ca1041
  path: /tmp/app.zip
`;

const info = (status) => `Successfully received submission info
  createdDate: 2026-08-25T20:49:30.000Z
  id: 2efe2717-52ef-43a5-96dc-0797e4ca1041
  name: app.zip
  status: ${status}
`;

// --------------------------------------------------------------------------
// The argv. This is the whole point of the change.
// --------------------------------------------------------------------------

test("the submit argv never asks for JSON output", () => {
  // Reintroducing `--output-format json` -- by hand, or by letting
  // electron-builder notarize again -- restores the exact blindness that cost
  // two cancelled builds. It is the one flag that must never come back.
  const args = notarize.submitArgs({ artifactPath: "/tmp/SciStudio.dmg", ...CREDS });
  assert.ok(!args.includes("--output-format"), `--output-format present: ${args.join(" ")}`);
  assert.ok(!args.includes("json"), `json output requested: ${args.join(" ")}`);
});

test("the submit argv does not wait; polling is this hook's job", () => {
  // `--wait` hands an unbounded wait to a process that has been observed
  // wedging after Apple already returned a verdict. Submitting and polling
  // separately means every check is a fresh, short-lived process.
  const args = notarize.submitArgs({ artifactPath: "/tmp/SciStudio.dmg", ...CREDS });
  assert.ok(!args.includes("--wait"), `--wait present: ${args.join(" ")}`);
  assert.deepEqual(args.slice(0, 3), ["notarytool", "submit", "/tmp/SciStudio.dmg"]);
  assert.equal(args[args.indexOf("--key") + 1], CREDS.keyPath);
  assert.equal(args[args.indexOf("--key-id") + 1], CREDS.keyId);
  assert.equal(args[args.indexOf("--issuer") + 1], CREDS.issuer);
});

test("info and log target one submission with the same credentials", () => {
  const id = "2efe2717-52ef-43a5-96dc-0797e4ca1041";
  assert.deepEqual(
    notarize.infoArgs({ submissionId: id, ...CREDS }).slice(0, 3),
    ["notarytool", "info", id],
  );
  assert.deepEqual(
    notarize.logArgs({ submissionId: id, ...CREDS }).slice(0, 3),
    ["notarytool", "log", id],
  );
  for (const args of [
    notarize.infoArgs({ submissionId: id, ...CREDS }),
    notarize.logArgs({ submissionId: id, ...CREDS }),
  ]) {
    assert.equal(args[args.indexOf("--issuer") + 1], CREDS.issuer);
  }
});

// --------------------------------------------------------------------------
// Reading the transcript.
// --------------------------------------------------------------------------

test("the submission id is recovered from the submit transcript", () => {
  // This id is what makes a timed-out or failed build investigable afterwards
  // via `notarytool info/log <id>` -- the capability #2174 claimed to add and
  // did not. Every build cancelled so far failed to produce one.
  assert.equal(notarize.parseSubmissionId(SUBMITTED), "2efe2717-52ef-43a5-96dc-0797e4ca1041");
});

test("a transcript with no id yields null rather than a bad id", () => {
  assert.equal(notarize.parseSubmissionId("Conducting pre-submission checks...\n"), null);
  assert.equal(notarize.parseSubmissionId(""), null);
  assert.equal(notarize.parseSubmissionId(undefined), null);
});

test("an in-progress poll is reported as in progress, not as unparseable", () => {
  // The poll loop has to tell "Apple is still working" from "nothing parsed".
  // Collapsing those either spins forever or declares success on garbage.
  assert.equal(notarize.parseStatus(info("In Progress")), "In Progress");
  assert.equal(notarize.isTerminal("In Progress"), false);
});

test("terminal verdicts are recognised", () => {
  for (const status of ["Accepted", "Invalid", "Rejected"]) {
    assert.equal(notarize.parseStatus(info(status)), status);
    assert.equal(notarize.isTerminal(status), true);
  }
});

test("an absent verdict is not mistaken for success", () => {
  // notarytool exits 0 for a submission Apple rejected, so a missing status
  // must never read as Accepted.
  assert.equal(notarize.parseStatus("Waiting for processing to complete.\n"), null);
  assert.equal(notarize.parseStatus(""), null);
  assert.equal(notarize.isTerminal(null), false);
  assert.equal(notarize.isTerminal("unknown"), false);
});

test("the last status wins when a transcript carries several", () => {
  const transcript = `${info("In Progress")}${info("Accepted")}`;
  assert.equal(notarize.parseStatus(transcript), "Accepted");
});

// --------------------------------------------------------------------------
// The bound. A wait with no deadline is the thing being removed.
// --------------------------------------------------------------------------

test("polling is bounded by default and overridable", () => {
  assert.equal(notarize.timeoutMinutes({}), 90);
  assert.equal(notarize.timeoutMinutes({ SCISTUDIO_NOTARIZE_TIMEOUT_MIN: "20" }), 20);
});

test("a nonsensical timeout falls back to the default rather than to zero", () => {
  // A zero or negative bound would abandon every submission on the first poll,
  // and an unparseable one must not silently mean "no timeout" either.
  for (const value of ["", "0", "-5", "abc", "  "]) {
    assert.equal(notarize.timeoutMinutes({ SCISTUDIO_NOTARIZE_TIMEOUT_MIN: value }), 90, value);
  }
});

// --------------------------------------------------------------------------
// Where the trace survives. The build log is not enough.
// --------------------------------------------------------------------------

test("the trace is mirrored to a file, defaulting under the runner temp dir", () => {
  // GitHub drops the tail of an in-progress step's log when a job is cancelled
  // or times out -- exactly when the trace is wanted. The first cancelled run
  // of this hook lost twelve minutes of output that way, leaving the runner's
  // own "Terminate orphan process (notarytool)" as the only evidence it had
  // run. The workflow cats this file in an `if: always()` step.
  assert.equal(notarize.logPath({ RUNNER_TEMP: "/tmp/runner" }), path.join("/tmp/runner", "notarize.log"));
  assert.equal(notarize.logPath({ SCISTUDIO_NOTARIZE_LOG: "/x/y.log" }), "/x/y.log");
  // No RUNNER_TEMP off-CI: still a real path, never undefined.
  assert.ok(notarize.logPath({}).endsWith("notarize.log"));
});

test("the notarization bound sits below the staple job's own timeout", () => {
  // Two equal bounds race, and the job wins: it is killed before the script can
  // say which submission was left in flight -- the one thing a timed-out wait
  // needs to report, since re-waiting is free and resubmitting costs an hour.
  const wf = fs.readFileSync(
    path.join(__dirname, "..", "..", ".github", "workflows", "desktop-macos-staple.yml"),
    "utf8",
  );
  const job = Number(/timeout-minutes:\s*(\d+)/.exec(wf)?.[1]);
  const bound = Number(/SCISTUDIO_NOTARIZE_TIMEOUT_MIN:\s*"?(\d+)"?/.exec(wf)?.[1]);
  assert.ok(Number.isFinite(job), "the staple job has no timeout-minutes");
  assert.ok(Number.isFinite(bound), "the staple job does not bound the wait");
  assert.ok(bound + 15 <= job, `wait bound ${bound} leaves no headroom under job timeout ${job}`);
});

test("the workflow prints the trace however the job ends", () => {
  // A trace written to a file nobody reads is no better than one that was lost.
  const wf = fs.readFileSync(
    path.join(__dirname, "..", "..", ".github", "workflows", "desktop-macos-dmg.yml"),
    "utf8",
  );
  const step = wf.slice(wf.indexOf("- name: Notarization trace"));
  assert.ok(step.length > 0, "the workflow has no step printing the notarization trace");
  assert.match(step.slice(0, 200), /if:\s*always\(\)/);
  assert.match(step.slice(0, 300), /notarize\.log/);
});

// --------------------------------------------------------------------------
// Credentials.
// --------------------------------------------------------------------------

test("an empty environment skips notarization instead of failing", () => {
  // A developer running `dist:dmg` locally has no App Store Connect key. That
  // has always produced an unsigned build, not an error, and must keep doing so.
  assert.equal(notarize.credentials({}), null);
  assert.equal(notarize.credentials({ APPLE_API_KEY: "", APPLE_API_KEY_ID: "" }), null);
});

test("a partial credential set is an error, never a silent skip", () => {
  // Half-configured secrets are always a mistake, and skipping quietly is how
  // an unnotarized dmg reaches a release (#2096). electron-builder threw here
  // too; the behaviour is preserved deliberately.
  assert.throws(
    () => notarize.credentials({ APPLE_API_KEY_ID: "X", APPLE_API_ISSUER: "Y" }),
    /APPLE_API_KEY\b/,
  );
  assert.throws(() => notarize.credentials({ APPLE_API_KEY: "/tmp/k.p8" }), /APPLE_API_KEY_ID/);
});

test("a complete credential set is accepted", () => {
  assert.deepEqual(
    notarize.credentials({
      APPLE_API_KEY: "/tmp/k.p8",
      APPLE_API_KEY_ID: "264X72XYKB",
      APPLE_API_ISSUER: "abc-123",
    }),
    { keyPath: "/tmp/k.p8", keyId: "264X72XYKB", issuer: "abc-123" },
  );
});

// --------------------------------------------------------------------------
// The split. Apple's queue must not be able to fail a build.
// --------------------------------------------------------------------------

const workflow = (name) =>
  fs.readFileSync(path.join(__dirname, "..", "..", ".github", "workflows", name), "utf8");

test("electron-builder does not notarize, and no hook re-adds it", () => {
  // `notarize: true` would put a blind `--wait --output-format json` submission
  // back inside the build -- the exact thing measured holding a build for 61
  // minutes. An `afterSign` hook would do the same at a different seam.
  assert.equal(pkg.build.mac.notarize, false);
  assert.equal(pkg.build.afterSign, undefined);
});

test("the build submits and does not wait", () => {
  // Waiting here discards the signed dmg *and* the queue position when Apple is
  // slow, so the next attempt starts another hour from zero.
  const wf = workflow("desktop-macos-dmg.yml");
  assert.match(wf, /notarize\.js submit/);
  assert.ok(!/notarize\.js wait/.test(wf), "the build workflow waits on Apple");
  assert.ok(!/notarize\.js staple/.test(wf), "the build workflow staples before a ticket exists");
});

test("the build keeps the dmg, because the ticket is bound to it", () => {
  // Apple issues the ticket against this artifact's cdhash. A rebuild to staple
  // would invalidate it and need a fresh submission.
  const wf = workflow("desktop-macos-dmg.yml");
  assert.match(wf, /upload-artifact/);
  assert.match(wf, /desktop\/dist\/\*\.dmg/);
});

test("the build cannot assert a ticket it has not been issued", () => {
  // `spctl` and `stapler validate` both check for a notarization ticket. Run in
  // the build they would fail every time now that submission does not wait.
  const wf = workflow("desktop-macos-dmg.yml");
  const verify = wf
    .slice(wf.indexOf("Verify signature"), wf.indexOf("Verify DMG artifact"))
    .split("\n")
    .filter((line) => !line.trim().startsWith("#"))
    .join("\n");
  assert.ok(!/stapler validate/.test(verify), "the build validates a ticket that cannot exist yet");
  assert.ok(!/spctl/.test(verify), "the build runs spctl before notarization completes");
});

test("the staple workflow waits, staples, and asserts the ticket", () => {
  const wf = workflow("desktop-macos-staple.yml");
  assert.match(wf, /notarize\.js wait/);
  assert.match(wf, /notarize\.js staple/);
  assert.match(wf, /stapler validate/);
  assert.match(wf, /spctl/);
  // Resubmitting is the one thing that must not happen on a retry: it buys a
  // fresh queue wait and invalidates nothing.
  assert.ok(!/notarize\.js submit/.test(wf), "the staple workflow resubmits instead of waiting");
});

test("the staple workflow can read another run's artifact", () => {
  // Downloading across runs needs `actions: read`; `contents` alone fails with a
  // 403 that reads like a bad run id.
  const wf = workflow("desktop-macos-staple.yml");
  assert.match(wf, /actions:\s*read/);
  assert.match(wf, /run-id:/);
});

test("the hardened runtime stays on", () => {
  // Apple refuses to notarize without it, so a regression would surface as a
  // rejection an hour later rather than as a config error.
  assert.equal(pkg.build.mac.hardenedRuntime, true);
});

test("the notarization script is a build tool and does not ship inside the app", () => {
  // `files` is the asar allowlist. Shipping build scripts would put the
  // notarization argv, and the shape of our credentials handling, in every
  // user's install for no reason.
  assert.ok(!pkg.build.files.some((f) => String(f).includes("scripts/")));
});
