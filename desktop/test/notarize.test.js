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
  const args = notarize.submitArgs({ zipPath: "/tmp/app.zip", ...CREDS });
  assert.ok(!args.includes("--output-format"), `--output-format present: ${args.join(" ")}`);
  assert.ok(!args.includes("json"), `json output requested: ${args.join(" ")}`);
});

test("the submit argv does not wait; polling is this hook's job", () => {
  // `--wait` hands an unbounded wait to a process that has been observed
  // wedging after Apple already returned a verdict. Submitting and polling
  // separately means every check is a fresh, short-lived process.
  const args = notarize.submitArgs({ zipPath: "/tmp/app.zip", ...CREDS });
  assert.ok(!args.includes("--wait"), `--wait present: ${args.join(" ")}`);
  assert.deepEqual(args.slice(0, 3), ["notarytool", "submit", "/tmp/app.zip"]);
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
// Wiring. A correct hook nobody calls is worth nothing.
// --------------------------------------------------------------------------

test("the hook is wired as afterSign and points at a file that exists", () => {
  assert.equal(pkg.build.afterSign, "scripts/notarize.js");
  assert.ok(fs.existsSync(path.join(__dirname, "..", pkg.build.afterSign)));
  assert.equal(typeof notarize, "function");
});

test("electron-builder's own notarization is off, so Apple is asked once", () => {
  // Leaving `notarize: true` alongside the hook submits the same app twice --
  // once blind, once visible -- and doubles an already unbounded wait.
  assert.equal(pkg.build.mac.notarize, false);
});

test("the hardened runtime stays on", () => {
  // Apple refuses to notarize without it, so a regression here would surface as
  // a notarization rejection rather than as a config error.
  assert.equal(pkg.build.mac.hardenedRuntime, true);
});

test("the hook is a build tool and does not ship inside the app", () => {
  // `files` is the asar allowlist. Shipping build scripts would put the
  // notarization argv, and the shape of our credentials handling, in every
  // user's install for no reason.
  assert.ok(!pkg.build.files.some((f) => String(f).includes("scripts/")));
});
