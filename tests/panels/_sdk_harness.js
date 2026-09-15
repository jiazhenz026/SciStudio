// Minimal host-free harness for the dependency-free panel SDK (ADR-054).
// Drives the SDK's standalone "sample" path for one context and prints which
// capabilities it exposes, so a Python test can assert that ``call`` exists only
// in the miniapp context. Usage: node _sdk_harness.js <sdk-path> <context>
"use strict";
const fs = require("fs");
const path = process.argv[2];
const context = process.argv[3];
const src = fs.readFileSync(path, "utf8");

global.window = global;
window.parent = window;
window.location = { href: "http://panel.test/" };
window.addEventListener = function () {};
window.removeEventListener = function () {};
global.document = { documentElement: { style: { setProperty() {} }, dataset: {} } };
global.Blob = class {};
global.fetch = function () {
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ context: context, input: { ref: "data-a", type: "Text" } }) });
};

eval(src);

setTimeout(function () {
  const s = window.scistudio || {};
  process.stdout.write(
    JSON.stringify({
      call: typeof s.call,
      read: typeof s.read,
      open: typeof s.open,
      writeBack: typeof s.writeBack,
      save: typeof s.save,
    })
  );
}, 20);
