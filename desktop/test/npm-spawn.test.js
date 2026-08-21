"use strict";

// Unit tests for the pure npm spawn decision (desktop/scripts/npm-spawn.js,
// issue #2093). Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const { npmSpawnSpec, npmSpawnArgs, isShellSafeToken } = require("../scripts/npm-spawn");

test("npmSpawnSpec: Windows asks for a shell, because npm is a .cmd shim", () => {
  // The regression this guards: Node >=18.20.1/20.12.1/21.7.2 raises EINVAL
  // when spawning a .cmd without a shell (CVE-2024-27980), which killed
  // `npm --prefix desktop run dev` outright.
  assert.deepEqual(npmSpawnSpec("win32"), { command: "npm.cmd", shell: true });
});

test("npmSpawnSpec: POSIX platforms spawn npm directly, no shell", () => {
  assert.deepEqual(npmSpawnSpec("darwin"), { command: "npm", shell: false });
  assert.deepEqual(npmSpawnSpec("linux"), { command: "npm", shell: false });
});

test("npmSpawnSpec: an unknown platform falls back to the POSIX form", () => {
  assert.deepEqual(npmSpawnSpec("freebsd"), { command: "npm", shell: false });
  assert.deepEqual(npmSpawnSpec(undefined), { command: "npm", shell: false });
});

test("npmSpawnArgs: POSIX passes the argument array through untouched", () => {
  assert.deepEqual(npmSpawnArgs("linux", ["--prefix", "frontend", "run", "dev"]), {
    command: "npm",
    args: ["--prefix", "frontend", "run", "dev"],
    shell: false,
  });
});

test("npmSpawnArgs: Windows hands the shell one command line and no array", () => {
  // DEP0190: an args array combined with shell:true is concatenated rather
  // than escaped, so the array must be empty on the shell path.
  const spawned = npmSpawnArgs("win32", [
    "--prefix",
    "frontend",
    "run",
    "dev",
    "--",
    "--host",
    "127.0.0.1",
    "--port",
    "5173",
  ]);
  assert.equal(spawned.shell, true);
  assert.deepEqual(spawned.args, []);
  assert.equal(spawned.command, "npm.cmd --prefix frontend run dev -- --host 127.0.0.1 --port 5173");
});

test("npmSpawnArgs: both real launch argument vectors survive the round trip", () => {
  // Spelled out so an edit to either call site in start-dev.js has to come
  // past this test.
  assert.equal(
    npmSpawnArgs("win32", ["--prefix", "desktop", "run", "start"]).command,
    "npm.cmd --prefix desktop run start",
  );
  assert.deepEqual(npmSpawnArgs("darwin", ["--prefix", "desktop", "run", "start"]).args, [
    "--prefix",
    "desktop",
    "run",
    "start",
  ]);
});

test("npmSpawnArgs: tolerates a missing or non-array argument list", () => {
  assert.equal(npmSpawnArgs("win32", undefined).command, "npm.cmd");
  assert.deepEqual(npmSpawnArgs("linux", undefined).args, []);
});

test("npmSpawnArgs: refuses to concatenate a token that would need quoting", () => {
  // The launcher does not quote. Failing loudly here is the contract: silent
  // mis-quoting would produce a command line that runs the wrong thing.
  assert.throws(
    () => npmSpawnArgs("win32", ["--prefix", "C:/Program Files/app"]),
    /needs shell quoting/,
  );
  assert.throws(() => npmSpawnArgs("win32", ["a&b"]), /needs shell quoting/);
  assert.throws(() => npmSpawnArgs("win32", ['say "hi"']), /needs shell quoting/);
});

test("npmSpawnArgs: an unquotable token is fine on POSIX, which keeps the array", () => {
  // No shell there, so no concatenation and nothing to refuse.
  assert.deepEqual(npmSpawnArgs("linux", ["C:/Program Files/app"]).args, ["C:/Program Files/app"]);
});

test("isShellSafeToken: accepts the punctuation real launch arguments carry", () => {
  for (const token of ["--prefix", "frontend", "127.0.0.1", "5173", "--", "a/b", "a\\b", "x=1"]) {
    assert.equal(isShellSafeToken(token), true, token);
  }
});

test("isShellSafeToken: rejects whitespace, quotes, and cmd.exe metacharacters", () => {
  for (const token of ["a b", 'a"b', "a&b", "a|b", "a>b", "a<b", "a^b", "a(b", ""]) {
    assert.equal(isShellSafeToken(token), false, JSON.stringify(token));
  }
});
