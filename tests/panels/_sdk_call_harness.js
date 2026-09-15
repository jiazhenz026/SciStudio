// Host-side harness for the panel SDK's ``call`` (ADR-054 MiniApp FR-016).
// The standalone sample path never reaches the host, so this drives the real
// one: it delivers the ``init`` message with a fake MessagePort, calls
// ``scistudio.call``, answers with the reply the host would post, and prints
// whether the page's promise resolved or rejected.
// Usage: node _sdk_call_harness.js <sdk-path> <error|result|error-like>
"use strict";
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const mode = process.argv[3];

const listeners = {};
global.window = global;
window.parent = { host: true };
window.location = { href: "http://panel.test/" };
window.addEventListener = function (type, fn) {
  (listeners[type] = listeners[type] || []).push(fn);
};
window.removeEventListener = function (type, fn) {
  const list = listeners[type] || [];
  const index = list.indexOf(fn);
  if (index >= 0) list.splice(index, 1);
};
global.document = { documentElement: { style: { setProperty() {} }, dataset: {} } };
global.Blob = class {};

eval(src);

const outbound = [];
const port = {
  postMessage(message) {
    outbound.push(message);
  },
  onmessage: null,
  start() {},
  close() {},
};

(listeners.message || []).slice().forEach(function (fn) {
  fn({
    data: {
      v: 1,
      type: "init",
      payload: {
        context: "miniapp",
        input: { ref: "data-a", type: "Text" },
        operations: ["read", "call"],
        services: ["save"],
        apiVersion: "1.0",
        basePath: "",
        theme: { mode: "light", tokens: {} },
      },
    },
    source: window.parent,
    ports: [port],
  });
});

const payloads = {
  // A raising panel.py function: HTTP 200 with an error body.
  error: { error: { type: "ValueError", message: "nope", traceback: "Traceback..." } },
  // An ordinary result.
  result: { total: 42 },
  // A result that merely mentions an error: still a result.
  "error-like": { error: { type: "ValueError", message: "nope" }, rows: 3 },
};

const promise = window.scistudio.call("compute", { x: 1 });
const sent = outbound.filter((message) => message.type === "call").pop();
port.onmessage({ data: { v: 1, id: sent.id, type: "result", payload: payloads[mode] } });

promise.then(
  function (value) {
    process.stdout.write(JSON.stringify({ outcome: "resolved", value: value, sent: sent.payload }));
  },
  function (error) {
    process.stdout.write(
      JSON.stringify({
        outcome: "rejected",
        code: error.code,
        message: error.message,
        traceback: error.traceback,
        sent: sent.payload,
      })
    );
  }
);
