"use strict";

// #2280 (AU1 P2-4): stand-in for `python -m scistudio.cli.main gui --port N
// --bundled`, used by desktop/test/harness/run-scenario.js. Node only, because
// the Desktop CI job has neither Python nor an Electron download.
//
// It binds 127.0.0.1 on the requested port (0 = ephemeral), prints the same
// `scistudio.ready` line the real CLI prints, serves a page with a painted
// #root, and appends its PID to $HARNESS_PID_FILE so the harness can check
// process lifetimes.
//
//   HARNESS_BACKEND_PLAN   comma-separated behaviour per launch, the last entry
//                          repeating: "serve" (default) or "exit-after-ready"
//                          (print the ready line, then exit without serving)
//   HARNESS_IGNORE_SIGTERM "1" = ignore SIGTERM, like a backend stuck in
//                          shutdown (POSIX; on Windows the harness emulates it)

const fs = require("fs");
const http = require("http");

const args = process.argv.slice(2);

// main.js probes a Windows candidate for pywinpty with `-c <code>` first.
if (args[0] === "-c") {
  process.exit(0);
}

const pidFile = process.env.HARNESS_PID_FILE;
let launchIndex = 0;
try {
  launchIndex = fs.readFileSync(pidFile, "utf8").split(/\s+/).filter(Boolean).length;
} catch {
  launchIndex = 0;
}
const plan = (process.env.HARNESS_BACKEND_PLAN || "serve").split(",");
const mode = plan[Math.min(launchIndex, plan.length - 1)];
fs.appendFileSync(pidFile, `${process.pid}\n`);

// #2327: a graceful stop, standing in for the real backend's lifespan
// shutdown. SIGTERM asks for it on POSIX; on Windows the shell closes stdin
// instead (SCISTUDIO_STOP_ON_STDIN_EOF=1). HARNESS_GRACEFUL_STOP_MS delays the
// exit the way shutdown_workflow_runs does, HARNESS_STOP_LOG records how the
// stop was asked for, and HARNESS_IGNORE_STOP_REQUEST ignores a closed stdin.
let stopping = false;
function gracefulStop(how) {
  if (stopping) {
    return;
  }
  stopping = true;
  if (process.env.HARNESS_STOP_LOG) {
    fs.appendFileSync(process.env.HARNESS_STOP_LOG, `${process.pid} ${how}\n`);
  }
  setTimeout(() => process.exit(0), Number(process.env.HARNESS_GRACEFUL_STOP_MS || 0));
}

if (process.env.HARNESS_IGNORE_SIGTERM === "1") {
  process.on("SIGTERM", () => {});
} else {
  process.on("SIGTERM", () => gracefulStop("sigterm"));
}
if (process.env.SCISTUDIO_STOP_ON_STDIN_EOF === "1" && process.env.HARNESS_IGNORE_STOP_REQUEST !== "1") {
  process.stdin.on("end", () => gracefulStop("stdin-eof"));
  process.stdin.resume();
}

// Never outlive the harness: on POSIX an orphan is reparented, so exit when
// the parent changes (Windows already kills a non-detached child with it).
const parentPid = process.ppid;
setInterval(() => {
  if (process.ppid !== parentPid || process.ppid === 1) {
    process.exit(0);
  }
}, 500).unref();

const portAt = args.indexOf("--port");
const port = portAt >= 0 ? Number(args[portAt + 1]) : 0;

const server = http.createServer((_req, res) => {
  res.writeHead(200, { "content-type": "text/html" });
  res.end("<html><body><div id='root'><p>ok</p></div></body></html>");
});

server.listen(port, "127.0.0.1", () => {
  const bound = server.address().port;
  const line = `${JSON.stringify({ event: "scistudio.ready", url: `http://127.0.0.1:${bound}/`, port: bound })}\n`;
  if (mode === "exit-after-ready") {
    process.stdout.write(line, () => process.exit(3));
    return;
  }
  process.stdout.write(line);
});
