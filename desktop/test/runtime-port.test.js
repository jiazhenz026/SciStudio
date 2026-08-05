"use strict";

// Unit tests for the pure runtime-port decision logic (desktop/runtime-port.js,
// issue #1986). Run with: npm --prefix desktop test   (Node built-in runner).

const test = require("node:test");
const assert = require("node:assert/strict");
const runtimePort = require("../runtime-port");

test("normalizeEnvPort: accepts 0 as an explicit ephemeral request", () => {
  assert.equal(runtimePort.normalizeEnvPort("0"), 0);
  assert.equal(runtimePort.normalizeEnvPort("8000"), 8000);
  assert.equal(runtimePort.normalizeEnvPort(65535), 65535);
});

test("normalizeEnvPort: rejects absent and out-of-range values", () => {
  assert.equal(runtimePort.normalizeEnvPort(undefined), null);
  assert.equal(runtimePort.normalizeEnvPort(null), null);
  assert.equal(runtimePort.normalizeEnvPort(""), null);
  assert.equal(runtimePort.normalizeEnvPort("nope"), null);
  assert.equal(runtimePort.normalizeEnvPort("-1"), null);
  assert.equal(runtimePort.normalizeEnvPort("65536"), null);
});

test("normalizeRememberedPort: rejects 0 and the privileged range", () => {
  assert.equal(runtimePort.normalizeRememberedPort(0), null);
  assert.equal(runtimePort.normalizeRememberedPort(1023), null);
  assert.equal(runtimePort.normalizeRememberedPort(1024), 1024);
  assert.equal(runtimePort.normalizeRememberedPort(50123), 50123);
  assert.equal(runtimePort.normalizeRememberedPort(65536), null);
});

test("normalizeRememberedPort: rejects non-integer values", () => {
  assert.equal(runtimePort.normalizeRememberedPort("50123"), null);
  assert.equal(runtimePort.normalizeRememberedPort(50123.5), null);
  assert.equal(runtimePort.normalizeRememberedPort(null), null);
});

test("parseRememberedPort: reads the port field, tolerates junk records", () => {
  assert.equal(runtimePort.parseRememberedPort({ port: 50123 }), 50123);
  assert.equal(runtimePort.parseRememberedPort({ port: "50123" }), null);
  assert.equal(runtimePort.parseRememberedPort({}), null);
  assert.equal(runtimePort.parseRememberedPort(null), null);
  assert.equal(runtimePort.parseRememberedPort("50123"), null);
});

test("selectRuntimePort: env override wins over a free remembered port", () => {
  assert.equal(
    runtimePort.selectRuntimePort({
      envPort: 8000,
      rememberedPort: 50123,
      rememberedPortFree: true
    }),
    "8000"
  );
});

test("selectRuntimePort: env 0 forces an ephemeral port", () => {
  assert.equal(
    runtimePort.selectRuntimePort({
      envPort: 0,
      rememberedPort: 50123,
      rememberedPortFree: true
    }),
    "0"
  );
});

test("selectRuntimePort: reuses a remembered port that is still free", () => {
  assert.equal(
    runtimePort.selectRuntimePort({ rememberedPort: 50123, rememberedPortFree: true }),
    "50123"
  );
});

test("selectRuntimePort: falls back to ephemeral when the remembered port is taken", () => {
  assert.equal(
    runtimePort.selectRuntimePort({ rememberedPort: 50123, rememberedPortFree: false }),
    "0"
  );
});

test("selectRuntimePort: first launch has nothing remembered", () => {
  assert.equal(runtimePort.selectRuntimePort({}), "0");
});

test("shouldRememberPort: records a newly bound ephemeral port", () => {
  assert.equal(
    runtimePort.shouldRememberPort({ boundPort: 50123, rememberedPort: null }),
    true
  );
});

test("shouldRememberPort: rewrites when the bound port moved", () => {
  assert.equal(
    runtimePort.shouldRememberPort({ boundPort: 50124, rememberedPort: 50123 }),
    true
  );
});

test("shouldRememberPort: no churn when the port is unchanged", () => {
  assert.equal(
    runtimePort.shouldRememberPort({ boundPort: 50123, rememberedPort: 50123 }),
    false
  );
});

test("shouldRememberPort: an env override is never remembered", () => {
  assert.equal(
    runtimePort.shouldRememberPort({ envPort: 8000, boundPort: 8000, rememberedPort: 50123 }),
    false
  );
  assert.equal(
    runtimePort.shouldRememberPort({ envPort: 0, boundPort: 50124, rememberedPort: 50123 }),
    false
  );
});

test("shouldRememberPort: an unusable bound port is not written back", () => {
  assert.equal(runtimePort.shouldRememberPort({ boundPort: null, rememberedPort: 50123 }), false);
  assert.equal(runtimePort.shouldRememberPort({ boundPort: 0, rememberedPort: null }), false);
});

test("boundPortFromReady: prefers the port field", () => {
  assert.equal(
    runtimePort.boundPortFromReady({ port: 50123, url: "http://127.0.0.1:50123" }),
    50123
  );
});

test("boundPortFromReady: falls back to the url", () => {
  assert.equal(runtimePort.boundPortFromReady({ url: "http://127.0.0.1:50123" }), 50123);
});

test("isPortUnavailableFailure: recognizes uvicorn's POSIX bind failure", () => {
  assert.equal(
    runtimePort.isPortUnavailableFailure(
      "[Errno 48] error while attempting to bind on address ('127.0.0.1', 50123): address already in use"
    ),
    true
  );
});

test("isPortUnavailableFailure: recognizes the Windows bind failure", () => {
  assert.equal(
    runtimePort.isPortUnavailableFailure(
      "[Errno 10048] error while attempting to bind on address ('127.0.0.1', 50123): only one usage of each socket address is normally permitted"
    ),
    true
  );
});

test("isPortUnavailableFailure: recognizes a raw EADDRINUSE", () => {
  assert.equal(runtimePort.isPortUnavailableFailure("listen EADDRINUSE 127.0.0.1:50123"), true);
});

test("isPortUnavailableFailure: an unrelated failure is not retried", () => {
  assert.equal(
    runtimePort.isPortUnavailableFailure("ModuleNotFoundError: No module named 'scistudio'"),
    false
  );
  assert.equal(runtimePort.isPortUnavailableFailure(""), false);
  assert.equal(runtimePort.isPortUnavailableFailure(null), false);
  assert.equal(runtimePort.isPortUnavailableFailure(undefined), false);
});

test("boundPortFromReady: rejects unusable messages", () => {
  assert.equal(runtimePort.boundPortFromReady(null), null);
  assert.equal(runtimePort.boundPortFromReady({}), null);
  assert.equal(runtimePort.boundPortFromReady({ url: "not-a-url" }), null);
  assert.equal(runtimePort.boundPortFromReady({ url: "http://127.0.0.1" }), null);
});
