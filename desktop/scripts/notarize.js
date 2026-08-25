"use strict";

/**
 * electron-builder `afterSign` hook: notarize the signed .app, visibly (#2176).
 *
 * electron-builder can notarize on its own, and did until this hook existed.
 * The problem was never that it failed -- it was that it was silent, and that
 * it handed an unbounded wait to a third party.
 *
 * `@electron/notarize` runs:
 *
 *     xcrun notarytool submit <zip> --key ... --wait --output-format json
 *
 * Two separate defects come out of that one line.
 *
 * `--output-format json` suppresses every progress line: notarytool emits one
 * JSON object when it finishes and nothing before it. So a submission queued
 * behind Apple and a submission that is wedged produce byte-identical logs --
 * empty ones. Two 0.3.4 builds were cancelled at 118 and 79 minutes on the
 * strength of that silence, neither ever allowed to finish, leaving it unknown
 * whether notarization worked at all. #2174 tried to fix this with
 * `DEBUG: electron-notarize*`, which surfaces @electron/notarize's own phase
 * logging and stops at the moment notarytool is spawned: enough to prove
 * signing takes ~2 min and `ditto` 26 s, blind to the only phase that mattered.
 *
 * `--wait` is the second defect, and the reason this hook polls instead of
 * asking for a bounded wait. There are reports of `submit --wait` sitting for
 * hours after Apple has already finished processing -- the wait loop itself
 * wedging, not the queue. Anything built on `--wait` inherits that, including
 * `--wait --timeout`, which still depends on the same loop noticing. So we
 * submit without waiting, take the submission ID, and drive the polling here:
 * each `notarytool info` is a fresh short-lived process that cannot wedge, and
 * every poll writes a line, so elapsed time is legible in the build log while
 * it is happening rather than only in hindsight.
 *
 * The hook keeps the semantics electron-builder had -- the ticket is stapled to
 * the .app *before* the dmg is built around it, because `afterSign` fires
 * between signing and target assembly. It differs in one deliberate way: a
 * notarization error fails the build. electron-builder fails soft here (#2096),
 * which is the reason the workflow needs a separate `Verify signature...` step
 * to assert the outcome rather than trust the build log.
 *
 * On timeout the build fails with the submission ID, because the submission is
 * still live at Apple and stays queryable with `notarytool history`/`log`.
 * That ID is the thing every earlier cancelled build failed to produce.
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
 * second is the unbounded wait this hook replaces with its own polling.
 */
function submitArgs({ zipPath, ...creds }) {
  return ["notarytool", "submit", zipPath, ...authArgs(creds)];
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

function log(message) {
  process.stdout.write(`[notarize] ${message}\n`);
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

async function zipApp(appPath) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scistudio-notarize-"));
  const zipPath = path.join(dir, "app.zip");
  log(`compressing ${path.basename(appPath)} for submission`);
  const { code } = await run(
    "ditto",
    ["-c", "-k", "--sequesterRsrc", "--keepParent", appPath, zipPath],
    { label: "ditto" },
  );
  if (code !== 0) {
    throw new Error(`ditto failed with exit code ${code}`);
  }
  const { size } = fs.statSync(zipPath);
  log(`submission archive is ${(size / 1024 / 1024).toFixed(0)} MB`);
  return { zipPath, dir };
}

/** Poll Apple until the submission reaches a terminal status or we give up. */
async function waitForVerdict(submissionId, creds, deadline) {
  let polls = 0;
  for (;;) {
    const { transcript } = await run("xcrun", infoArgs({ submissionId, ...creds }), {
      label: "notarytool info",
      quiet: true,
    });
    polls += 1;
    const status = parseStatus(transcript) || "unknown";
    const elapsed = Math.round((Date.now() - deadline.started) / 60_000);
    log(`poll ${polls} at ${elapsed} min: ${status}`);
    if (isTerminal(status)) {
      return status;
    }
    if (Date.now() >= deadline.at) {
      return null;
    }
    await sleep(POLL_INTERVAL_MS);
  }
}

async function notarizeApp(appPath, creds, env) {
  const { zipPath, dir } = await zipApp(appPath);
  const started = Date.now();
  const minutes = timeoutMinutes(env);
  try {
    log("uploading to Apple");
    const submit = await run("xcrun", submitArgs({ zipPath, ...creds }), {
      label: "notarytool submit",
    });
    const submissionId = parseSubmissionId(submit.transcript);
    if (submit.code !== 0 || !submissionId) {
      throw new Error(`notarytool submit failed with exit code ${submit.code}`);
    }
    log(`submission ${submissionId}; polling every 60s, giving up after ${minutes} min`);
    log(`check independently with: xcrun notarytool history --key ... --key-id ... --issuer ...`);

    const status = await waitForVerdict(submissionId, creds, {
      started,
      at: started + minutes * 60_000,
    });

    if (status === null) {
      throw new Error(
        `notarization did not finish within ${minutes} min. The submission is still live at ` +
          `Apple: ${submissionId}. Query it with \`xcrun notarytool info ${submissionId}\` rather ` +
          `than resubmitting.`,
      );
    }
    if (status !== "Accepted") {
      // The status says *that* Apple refused; only the log says why.
      log("fetching Apple's rejection detail");
      await run("xcrun", logArgs({ submissionId, ...creds }), { label: "notarytool log" });
      throw new Error(`Apple returned ${status} for submission ${submissionId}`);
    }

    log("accepted; stapling the ticket");
    const stapled = await run("xcrun", ["stapler", "staple", appPath], { label: "stapler" });
    if (stapled.code !== 0) {
      throw new Error(`stapler failed with exit code ${stapled.code}`);
    }
    log(`notarized and stapled in ${((Date.now() - started) / 60_000).toFixed(1)} min`);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** The electron-builder hook itself. */
async function afterSign(context) {
  if (context.electronPlatformName !== "darwin") {
    return;
  }
  const creds = credentials(process.env);
  if (!creds) {
    log("no App Store Connect credentials in the environment; skipping notarization");
    return;
  }
  const appName = context.packager.appInfo.productFilename;
  const appPath = path.join(context.appOutDir, `${appName}.app`);
  if (!fs.existsSync(appPath)) {
    throw new Error(`expected a signed app at ${appPath}`);
  }
  await notarizeApp(appPath, creds, process.env);
}

module.exports = afterSign;
module.exports.default = afterSign;
module.exports.credentials = credentials;
module.exports.submitArgs = submitArgs;
module.exports.infoArgs = infoArgs;
module.exports.logArgs = logArgs;
module.exports.parseSubmissionId = parseSubmissionId;
module.exports.parseStatus = parseStatus;
module.exports.isTerminal = isTerminal;
module.exports.timeoutMinutes = timeoutMinutes;
