#!/usr/bin/env node
"use strict";

/**
 * Apple notarization, driven by us instead of by electron-builder (#2176).
 *
 * Three subcommands, deliberately separable so Apple's queue is not on the
 * release critical path:
 *
 *     node scripts/notarize.js submit <artifact>   # upload, print the id, exit
 *     node scripts/notarize.js wait <submissionId> # poll until a verdict
 *     node scripts/notarize.js staple <artifact>   # attach the ticket
 *
 * ## Why not electron-builder's own notarization
 *
 * `@electron/notarize` runs:
 *
 *     xcrun notarytool submit <zip> --key ... --wait --output-format json
 *
 * `--output-format json` suppresses every progress line -- notarytool emits one
 * object when it finishes and nothing before it -- so a submission queued behind
 * Apple and one that is wedged produce byte-identical logs: empty ones. Two
 * 0.3.4 builds were cancelled at 118 and 79 minutes reading that silence as a
 * hang. `DEBUG: electron-notarize*` (#2174) did not help: it surfaces that
 * package's phase logging, which stops where notarytool is spawned.
 *
 * `--wait` is separately untrustworthy -- it has been reported outliving Apple's
 * own verdict -- so this polls `notarytool info` instead. Every poll is a fresh
 * short-lived process that cannot wedge, and every poll writes a line.
 *
 * ## Why submit and wait are separate commands
 *
 * Measured on 2026-08-25: signing 2 min 36 s, `ditto` 20 s, upload 17 s, and
 * then **61 consecutive polls, every one `In Progress`** -- Apple held the
 * submission for over an hour without a verdict and the build timed out. That
 * is not a failure anything here can fix, and waiting inside the build job
 * throws away the queue position along with the signed artifact.
 *
 * So the build submits and stops. A later job waits and staples the artifact
 * the build kept. A slow queue then costs a delay instead of a rebuild, and the
 * ticket Apple eventually issues still matches the artifact we have -- it is
 * bound to the signed code's cdhash, so a rebuilt artifact would need a fresh
 * submission and a fresh hour.
 *
 * ## What gets submitted
 *
 * The dmg, not the `.app`. Stapling has to attach to something that outlives
 * the build, and the dmg is the artifact that ships. The `.app` inside is
 * therefore not itself stapled: Gatekeeper resolves it online, which every
 * download-from-GitHub user is. Only a first launch with no network would
 * notice. A `.app` (or any bundle directory) is still accepted here and gets
 * zipped first, because notarytool takes an archive rather than a directory.
 */

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// notarytool prints the id on its own indented line under "Submission ID
// received". The UUID shape keeps this from matching some future unrelated
// `id:` field; the same id is echoed again later, so first-match is correct.
const SUBMISSION_ID_RE = /\bid:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/i;

const STATUS_RE = /status:\s*([A-Za-z ]+?)\s*$/gim;

const TERMINAL = new Set(["Accepted", "Invalid", "Rejected"]);

const POLL_INTERVAL_MS = 60_000;
const DEFAULT_TIMEOUT_MIN = 90;

/**
 * Resolve App Store Connect API credentials from the environment.
 *
 * Deliberately the same three variables electron-builder's own
 * `getNotarizeOptions()` reads, so the workflow's env block did not have to
 * change when notarization moved in here.
 *
 * Returns null when none are set -- a local `dist:dmg` with no credentials
 * still produces an unsigned-and-unnotarized build rather than an error, which
 * is the behaviour developers already had. A *partial* set is an error, because
 * it is always a misconfiguration and silently skipping it is how an
 * unnotarized dmg reaches a release.
 */
function credentials(env) {
  const keyPath = env.APPLE_API_KEY || "";
  const keyId = env.APPLE_API_KEY_ID || "";
  const issuer = env.APPLE_API_ISSUER || "";
  if (!keyPath && !keyId && !issuer) {
    return null;
  }
  const missing = [
    !keyPath && "APPLE_API_KEY",
    !keyId && "APPLE_API_KEY_ID",
    !issuer && "APPLE_API_ISSUER",
  ].filter(Boolean);
  if (missing.length > 0) {
    throw new Error(`notarization credentials are incomplete; missing ${missing.join(", ")}`);
  }
  return { keyPath, keyId, issuer };
}

function authArgs({ keyPath, keyId, issuer }) {
  return ["--key", keyPath, "--key-id", keyId, "--issuer", issuer];
}

/**
 * Build the notarytool submit argv.
 *
 * Neither `--output-format json` nor `--wait` may appear here; both are tested
 * for. The first is what made a stall indistinguishable from progress, and the
 * second both wedges and would put Apple's queue back inside the build.
 */
function submitArgs({ artifactPath, ...creds }) {
  return ["notarytool", "submit", artifactPath, ...authArgs(creds)];
}

function infoArgs({ submissionId, ...creds }) {
  return ["notarytool", "info", submissionId, ...authArgs(creds)];
}

function logArgs({ submissionId, ...creds }) {
  return ["notarytool", "log", submissionId, ...authArgs(creds)];
}

function parseSubmissionId(text) {
  const match = SUBMISSION_ID_RE.exec(String(text || ""));
  return match ? match[1] : null;
}

/**
 * Read the last `status:` value out of a notarytool transcript.
 *
 * Returns the raw word, including the non-terminal "In Progress", so the poll
 * loop can tell "Apple is still working" from "nothing parsed" -- treating
 * those two alike is how a poll loop either spins forever or declares success
 * on garbage.
 */
function parseStatus(text) {
  const source = String(text || "");
  STATUS_RE.lastIndex = 0;
  let last = null;
  let match;
  while ((match = STATUS_RE.exec(source)) !== null) {
    last = match[1].trim();
  }
  return last;
}

function isTerminal(status) {
  return TERMINAL.has(String(status));
}

function timeoutMinutes(env) {
  const raw = Number.parseInt(env.SCISTUDIO_NOTARIZE_TIMEOUT_MIN || "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_TIMEOUT_MIN;
}

/**
 * Write a progress line to the build log *and* to a file.
 *
 * The file is the load-bearing half. GitHub drops the tail of an in-progress
 * step's log when a job is cancelled or times out -- which is exactly when the
 * trace is wanted. A cancelled 0.3.4 build lost twelve minutes of output that
 * way, leaving the runner's own `Terminate orphan process (notarytool)` as the
 * only evidence anything had run. The workflow cats this file in an
 * `if: always()` step, so the trace survives however the job ends.
 */
function logPath(env) {
  return env.SCISTUDIO_NOTARIZE_LOG || path.join(env.RUNNER_TEMP || os.tmpdir(), "notarize.log");
}

function log(message) {
  const line = `[notarize] ${message}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(logPath(process.env), `${new Date().toISOString()} ${line}`);
  } catch {
    // A build must never fail because its own progress log is unwritable.
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Spawn a command, streaming output to the build log as it arrives while also
 * accumulating the transcript for parsing.
 */
function run(command, args, { label = command, quiet = false } = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let transcript = "";
    const consume = (chunk) => {
      const text = chunk.toString();
      transcript += text;
      if (!quiet) {
        process.stdout.write(text);
      }
    };
    child.stdout.on("data", consume);
    child.stderr.on("data", consume);
    child.on("error", (error) => resolve({ code: -1, transcript: `${transcript}${error.message}` }));
    child.on("close", (code) => {
      if (code !== 0) {
        log(`${label} exited ${code}`);
      }
      resolve({ code, transcript });
    });
  });
}

/**
 * notarytool takes a file, not a bundle directory. A dmg is already a file; a
 * `.app` has to be zipped, with `ditto --sequesterRsrc --keepParent` so the
 * signature survives the round trip.
 */
async function archiveFor(artifactPath) {
  if (fs.statSync(artifactPath).isFile()) {
    return { uploadPath: artifactPath, cleanup: null };
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-notarize-"));
  const zipPath = path.join(dir, "upload.zip");
  log(`compressing ${path.basename(artifactPath)} for submission`);
  const { code } = await run(
    "ditto",
    ["-c", "-k", "--sequesterRsrc", "--keepParent", artifactPath, zipPath],
    { label: "ditto" },
  );
  if (code !== 0) {
    throw new Error(`ditto failed with exit code ${code}`);
  }
  return { uploadPath: zipPath, cleanup: dir };
}

/** `submit` -- upload and return the submission id without waiting. */
async function commandSubmit(artifactPath, creds) {
  const { uploadPath, cleanup } = await archiveFor(artifactPath);
  try {
    const { size } = fs.statSync(uploadPath);
    log(`submission archive is ${(size / 1024 / 1024).toFixed(0)} MB`);
    log("uploading to Apple");
    const result = await run("xcrun", submitArgs({ artifactPath: uploadPath, ...creds }), {
      label: "notarytool submit",
    });
    const submissionId = parseSubmissionId(result.transcript);
    if (result.code !== 0 || !submissionId) {
      throw new Error(`notarytool submit failed with exit code ${result.code}`);
    }
    log(`submission ${submissionId}`);
    log("Apple is now queueing this; the build does not wait for it");
    return submissionId;
  } finally {
    if (cleanup) {
      fs.rmSync(cleanup, { recursive: true, force: true });
    }
  }
}

/** `wait` -- poll until Apple returns a verdict, or give up with the id intact. */
async function commandWait(submissionId, creds, env) {
  const started = Date.now();
  const minutes = timeoutMinutes(env);
  const deadline = started + minutes * 60_000;
  log(`waiting on ${submissionId}; polling every 60s, giving up after ${minutes} min`);

  let polls = 0;
  for (;;) {
    const { transcript } = await run("xcrun", infoArgs({ submissionId, ...creds }), {
      label: "notarytool info",
      quiet: true,
    });
    polls += 1;
    const status = parseStatus(transcript) || "unknown";
    log(`poll ${polls} at ${Math.round((Date.now() - started) / 60_000)} min: ${status}`);

    if (isTerminal(status)) {
      if (status === "Accepted") {
        return;
      }
      // The status says *that* Apple refused; only the log says why.
      log("fetching Apple's rejection detail");
      await run("xcrun", logArgs({ submissionId, ...creds }), { label: "notarytool log" });
      throw new Error(`Apple returned ${status} for submission ${submissionId}`);
    }
    if (Date.now() >= deadline) {
      throw new Error(
        `no verdict within ${minutes} min. The submission is still live at Apple: ` +
          `${submissionId}. Re-run this wait rather than resubmitting -- a new submission ` +
          `starts a new queue wait, and the ticket is bound to the artifact already uploaded.`,
      );
    }
    await sleep(POLL_INTERVAL_MS);
  }
}

/** `staple` -- attach the issued ticket to the artifact we kept. */
async function commandStaple(artifactPath) {
  log(`stapling ${path.basename(artifactPath)}`);
  const { code } = await run("xcrun", ["stapler", "staple", artifactPath], { label: "stapler" });
  if (code !== 0) {
    throw new Error(`stapler failed with exit code ${code}`);
  }
  log("stapled");
}

/**
 * Publish a value to the GitHub step output, when running in Actions.
 *
 * The submission id has to reach the stapling job somehow, and a step output is
 * the channel that does not require the artifact to be re-read.
 */
function emitOutput(name, value) {
  const file = process.env.GITHUB_OUTPUT;
  if (!file) {
    return;
  }
  try {
    fs.appendFileSync(file, `${name}=${value}\n`);
  } catch (error) {
    log(`could not write ${name} to GITHUB_OUTPUT: ${error.message}`);
  }
}

async function main(argv) {
  const [command, target] = argv;
  if (!command || !target) {
    process.stderr.write("usage: notarize.js <submit|wait|staple> <artifact|submissionId>\n");
    return 2;
  }

  const creds = credentials(process.env);
  if (!creds) {
    // Matches the pre-#2176 behaviour: a developer with no App Store Connect
    // key gets an unsigned local build rather than a failure.
    log("no App Store Connect credentials in the environment; skipping notarization");
    return 0;
  }

  if (command === "submit") {
    const id = await commandSubmit(target, creds);
    emitOutput("submission-id", id);
    return 0;
  }
  if (command === "wait") {
    await commandWait(target, creds, process.env);
    return 0;
  }
  if (command === "staple") {
    await commandStaple(target);
    return 0;
  }
  process.stderr.write(`unknown command: ${command}\n`);
  return 2;
}

if (require.main === module) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (error) => {
      log(`FAILED: ${error.message}`);
      process.exit(1);
    },
  );
}

module.exports = {
  credentials,
  submitArgs,
  infoArgs,
  logArgs,
  parseSubmissionId,
  parseStatus,
  isTerminal,
  timeoutMinutes,
  logPath,
  main,
};
