"use strict";

// How to spawn npm as a child process, per platform (issue #2093).
//
// Two Node behaviours collide on Windows, and a launcher has to satisfy both:
//
//   1. The `npm` on PATH is `npm.cmd`, a batch shim. Node hardened
//      `child_process.spawn` against Windows batch-file argument injection
//      (CVE-2024-27980, shipped in 18.20.1 / 20.12.1 / 21.7.2): spawning a
//      `.cmd` without `shell: true` now fails with `EINVAL` instead of running
//      it. So Windows needs the shell.
//   2. Passing an *args array* together with `shell: true` is deprecated
//      (DEP0190) precisely because the runtime concatenates those arguments
//      instead of escaping them. So the shell must be handed one finished
//      command line, not a command plus an array.
//
// Joining tokens into a command line is only safe when no token needs quoting,
// and correct cmd.exe quoting is genuinely hard to get right: cmd.exe's own
// parsing and CommandLineToArgvW disagree about backslash-before-quote runs.
// Rather than ship a quoting routine that is subtly wrong, this module refuses
// to build a command line out of anything outside a conservative safe set.
// Every token the launcher actually passes -- `--prefix`, `frontend`, `run`,
// `dev`, `--`, `--host`, `127.0.0.1`, `--port`, `5173`, `desktop`, `start` --
// is inside that set, so a future edit that introduces, say, a path with a
// space fails loudly here instead of mis-quoting silently at launch time.
//
// Kept as pure functions in their own module -- no side effects on require --
// so the decision is unit-testable without starting Vite or Electron. Same
// shape as `desktop/runtime-port.js` (#1986).

// Letters, digits, and the punctuation that shows up in flags, versions,
// hosts, ports, and path separators. Deliberately excludes whitespace, quotes,
// and every cmd.exe metacharacter.
const SHELL_SAFE_TOKEN = /^[A-Za-z0-9._:/\\@=+-]+$/;

/**
 * Return the command name and shell flag to spawn npm with.
 *
 * @param {string} platform A `process.platform` value.
 * @returns {{command: string, shell: boolean}}
 */
function npmSpawnSpec(platform) {
  if (platform === "win32") {
    return { command: "npm.cmd", shell: true };
  }
  return { command: "npm", shell: false };
}

/**
 * Report whether *token* can be concatenated into a shell command line as-is.
 *
 * @param {string} token
 * @returns {boolean}
 */
function isShellSafeToken(token) {
  return SHELL_SAFE_TOKEN.test(String(token));
}

/**
 * Return spawn arguments for running npm with *args* on *platform*.
 *
 * On Windows this collapses the command and its arguments into a single shell
 * command line (see DEP0190 above); elsewhere it returns the command and the
 * argument array unchanged, with the shell off.
 *
 * @param {string} platform A `process.platform` value.
 * @param {string[]} args Arguments to pass to npm.
 * @returns {{command: string, args: string[], shell: boolean}}
 * @throws {Error} On the shell path, when a token would need quoting.
 */
function npmSpawnArgs(platform, args) {
  const spec = npmSpawnSpec(platform);
  const argv = Array.isArray(args) ? args.map(String) : [];
  if (!spec.shell) {
    return { command: spec.command, args: argv, shell: false };
  }
  const unsafe = argv.filter((token) => !isShellSafeToken(token));
  if (unsafe.length > 0) {
    throw new Error(
      `npm launch argument needs shell quoting, which this launcher does not do: ${JSON.stringify(unsafe)}. ` +
        "Windows requires shell:true to reach npm.cmd, and DEP0190 forbids an args array there, " +
        "so every token must be shell-safe. Pass the value through the environment instead.",
    );
  }
  return { command: [spec.command, ...argv].join(" "), args: [], shell: true };
}

module.exports = { npmSpawnSpec, npmSpawnArgs, isShellSafeToken };
