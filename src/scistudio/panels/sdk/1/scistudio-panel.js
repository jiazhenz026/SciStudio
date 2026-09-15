/* SciStudio Panel SDK 1.0 — dependency-free, ADR-054. */
/**
 * @overview
 * The panel SDK is one dependency-free script that defines `window.scistudio`,
 * the only way a panel page talks to SciStudio. Load it from the SDK major the
 * panel's `api_version` names, before the page's own code:
 *
 * ```html
 * <script src="../../sdk/1/scistudio-panel.js"></script>
 * ```
 *
 * Await `scistudio.ready()` first. Every operation returns a promise. Which
 * operations exist depends on the context the host opened the page in (see
 * the context table below): an operation the context does not provide is
 * absent from `window.scistudio`, so test for it rather than calling it.
 *
 * Opened directly (not inside a SciStudio frame), the SDK runs in sample
 * mode: it reads `panel.sample.json` beside the page and answers from it, so a
 * page can be checked without a running host.
 */
(function () {
  "use strict";
  var port = null;
  var disposed = false;
  var nextId = 0;
  var pending = new Map();
  var themeCallbacks = new Set();
  var disposeCallbacks = new Set();
  var sample = null;
  var artifactUrls = new Map();
  var errorBeforeInit = null;
  var initializedResolve;
  var initializedReject;
  var initialized = new Promise(function (resolve, reject) {
    initializedResolve = resolve;
    initializedReject = reject;
  });
  // A page need not call ready if it crashes during startup.
  initialized.catch(function () {});
  /**
   * @errors
   * A rejected promise carries an `Error` whose `code` names the failure. The
   * host adds its own codes for refused requests (for example
   * `invalid_request`, `unsupported`, `unauthorized_ref`, `read_budget`); a
   * failed `call` uses the Python exception's type name as its code.
   *
   * @error disposed The host disposed the panel; pending operations reject with this.
   * @error not_ready An operation was attempted before the host initialised the frame.
   * @error timeout The host did not answer within 60 seconds.
   * @error not_found Sample mode has no `reads` or `calls` entry for the request.
   * @error unsupported Sample mode cannot perform the request (no host `save` or `open`), or the sample's `context` is not a panel context.
   * @error already_used `writeBack` was already called once for this decision.
   * @error invalid_request `call` was given no function name.
   * @error sample_missing Sample mode could not load `panel.sample.json`.
   */
  function failure(code, message) {
    var error = new Error(message);
    error.code = code;
    return error;
  }
  function request(type, payload, transfers) {
    if (disposed) return Promise.reject(failure("disposed", "Panel has been disposed"));
    if (!port) return Promise.reject(failure("not_ready", "Await scistudio.ready() first"));
    return new Promise(function (resolve, reject) {
      var id = String(++nextId);
      var timer = setTimeout(function () {
        pending.delete(id);
        reject(failure("timeout", "Panel operation timed out"));
      }, 60000);
      pending.set(id, { resolve: resolve, reject: reject, timer: timer });
      try { port.postMessage({ v: 1, id: id, type: type, payload: payload }, transfers || []); }
      catch (error) { clearTimeout(timer); pending.delete(id); reject(error); }
    });
  }
  /**
   * @member theme
   * @group View state and theme
   * @type {object}
   * The current theme, `{mode: "light" | "dark", tokens: {"--ss-*": value}}`.
   * Kept current by the SDK; use `onTheme` to be told when it changes.
   */
  function applyTheme(theme) {
    if (!theme || typeof theme !== "object") return;
    var tokens = theme.tokens || {};
    Object.keys(tokens).forEach(function (name) {
      if (name.indexOf("--ss-") === 0 && typeof tokens[name] === "string") {
        document.documentElement.style.setProperty(name, tokens[name]);
      }
    });
    document.documentElement.dataset.theme = theme.mode === "dark" ? "dark" : "light";
    api.theme = theme;
    themeCallbacks.forEach(function (callback) { callback(theme); });
  }
  /*
   * Tutorial pointing (ADR-054). The host measures a step's target by walking
   * its own document for `[data-tutorial-target]`, which cannot reach inside
   * this frame. When a step points at something here the host says so, and this
   * measures that element and reports its box back; the host adds the frame's
   * own position to get viewport coordinates.
   *
   * The loop runs only while a step is pointing into this panel, and reports
   * only when the box actually changes, so a panel nobody is pointing at does
   * no work and a still target sends nothing.
   */
  var highlightWanted = null;
  var highlightFrame = 0;
  var highlightLast = null;
  function highlightElement(request) {
    if (!request || typeof request.target !== "string") return null;
    var selector = '[data-tutorial-target="' + (window.CSS && CSS.escape ? CSS.escape(request.target) : request.target) + '"]';
    if (request.key !== null && request.key !== undefined) {
      selector += '[data-tutorial-target-key="' + (window.CSS && CSS.escape ? CSS.escape(String(request.key)) : request.key) + '"]';
    }
    return document.querySelector(selector);
  }
  function highlightBox(element) {
    if (!element || typeof element.getBoundingClientRect !== "function") return null;
    var box = element.getBoundingClientRect();
    // A zero-sized box is an element that is in the document but not laid out.
    // Reporting it would ring nothing; the host treats null as "not here".
    if (box.width <= 0 || box.height <= 0) return null;
    return { top: box.top, left: box.left, width: box.width, height: box.height };
  }
  function sameBox(a, b) {
    if (!a || !b) return a === b;
    return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
  }
  function highlightTick() {
    var next = highlightBox(highlightElement(highlightWanted));
    if (!sameBox(highlightLast, next)) {
      highlightLast = next;
      request("highlightRect", { target: highlightWanted.target, key: highlightWanted.key, rect: next }).catch(function () {});
    }
    highlightFrame = window.requestAnimationFrame(highlightTick);
  }
  function setHighlight(request_) {
    if (highlightFrame) { window.cancelAnimationFrame(highlightFrame); highlightFrame = 0; }
    highlightWanted = request_ && typeof request_.target === "string" ? request_ : null;
    highlightLast = null;
    if (!highlightWanted || typeof window.requestAnimationFrame !== "function") return;
    highlightTick();
  }

  /*
   * Report this document's height so the window around an interactive frame can
   * size itself to the panel. Measured from the document rather than from any
   * element, so a panel that lays itself out however it likes is still measured
   * correctly, and reported only when it changes.
   */
  var heightObserver = null;
  var lastHeight = 0;
  /*
   * The content's height, measured on the body and never on the root element:
   * a root element's scrollHeight and offsetHeight are at least the viewport's,
   * so measuring there reports the frame's current height back to the host as
   * though it were the content's and the frame never moves off its own
   * fallback size.
   */
  function documentHeight() {
    var body = document.body;
    if (!body) return 0;
    var box = typeof body.getBoundingClientRect === "function" ? body.getBoundingClientRect().height : 0;
    return Math.ceil(Math.max(box, body.scrollHeight || 0));
  }
  function reportHeight() {
    if (disposed) return;
    var height = documentHeight();
    if (!height || height === lastHeight) return;
    // Remembered only once the host has taken it: the first measurement happens
    // before the panel has called ready(), which the host refuses, and treating
    // a refused report as delivered would suppress the next identical one.
    request("resize", { height: height }).then(function () { lastHeight = height; }, function () {});
  }
  function startReportingHeight() {
    reportHeight();
    if (typeof ResizeObserver !== "function" || !document.documentElement) return;
    heightObserver = new ResizeObserver(reportHeight);
    heightObserver.observe(document.documentElement);
    if (document.body) heightObserver.observe(document.body);
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    if (highlightFrame) { window.cancelAnimationFrame(highlightFrame); highlightFrame = 0; }
    if (heightObserver) { heightObserver.disconnect(); heightObserver = null; }
    pending.forEach(function (item) {
      clearTimeout(item.timer);
      item.reject(failure("disposed", "Panel has been disposed"));
    });
    pending.clear();
    artifactUrls.forEach(function (url) { URL.revokeObjectURL(url); });
    artifactUrls.clear();
    disposeCallbacks.forEach(function (callback) { callback(); });
    if (port) { port.onmessage = null; port.close(); }
  }
  function configure(payload) {
    /**
     * @member context
     * @group Context properties
     * @type {"preview" | "interactive" | "miniapp"}
     * The context the host opened this page in. Also published on the root
     * element as `data-panel-context`, so a stylesheet can tell a preview frame
     * (whose height the host sets) from an interactive window (which sizes
     * itself to the panel).
     */
    api.context = payload.context;
    /*
     * Which way the height flows, published to the stylesheet. A preview frame
     * is given its height by the host and the panel fills it; an interactive
     * frame opens a window that sizes itself to the panel, so the document must
     * be free to be as tall as its content.
     */
    if (document.documentElement) document.documentElement.dataset.panelContext = payload.context;
    /**
     * @member input
     * @group Context properties
     * @type {object}
     * What the host opened the context with. In `preview` and `miniapp` it
     * carries `ref`, the target that `read` uses when no `params.ref` is given.
     */
    api.input = payload.input;
    /**
     * @member viewState
     * @group Context properties
     * @type {any}
     * The view state last stored with `setViewState` for this view, or
     * `undefined` when none was stored.
     */
    api.viewState = payload.viewState;
    /**
     * @member apiVersion
     * @group Context properties
     * @type {string}
     * The `MAJOR.MINOR` panel API version the host serves.
     */
    api.apiVersion = payload.apiVersion;
    /**
     * @member basePath
     * @group Context properties
     * @type {string}
     * The host's URL base path; empty in sample mode.
     */
    api.basePath = payload.basePath;
    /**
     * @member libBaseUrl
     * @group Context properties
     * @type {string}
     * Base URL of the pinned shared libraries (see the library table below).
     * Pass it to components that load a library on demand, such as `PlotView`
     * for PDF figures.
     */
    api.libBaseUrl = payload.libBaseUrl;
    var operations = payload.operations || [];
    var services = payload.services || [];
    if ((api.context === "preview" || api.context === "miniapp") && operations.indexOf("read") >= 0) {
      /**
       * @member read
       * @group Data
       * @context preview, miniapp
       * @param {string} op One of the read operations listed below.
       * @param {object} [params] The operation's parameters. `params.ref` reads a different authorised target than `input.ref`, such as a collection item or composite slot.
       * @returns {Promise<object>} The operation's result.
       * Read a bounded part of a target. The host checks that the target is
       * reachable from this context before reading.
       *
       * An `artifact.file` result whose bytes the host transferred gains a
       * `url` (a `blob:` URL) that the SDK revokes on dispose or on the next
       * `artifact.file` read of the same target.
       *
       * In sample mode the answer comes from the sample's `reads` map: first
       * the key `JSON.stringify({ref, op, params})`, then the key `op`.
       */
      api.read = function (op, params) {
        params = params || {};
        var ref = params.ref || api.input.ref;
        var readParams = Object.assign({}, params);
        delete readParams.ref;
        if (sample) {
          var reads = sample.reads || {};
          var key = JSON.stringify({ ref: ref, op: op, params: readParams });
          if (Object.prototype.hasOwnProperty.call(reads, key)) return Promise.resolve(reads[key]);
          if (Object.prototype.hasOwnProperty.call(reads, op)) return Promise.resolve(reads[op]);
          return Promise.reject(failure("not_found", "No sample read for " + op));
        }
        return request("read", { ref: ref, op: op, params: readParams }).then(function (result) {
          if (op !== "artifact.file" || !result || !(result.data instanceof ArrayBuffer)) return result;
          if (disposed) throw failure("disposed", "Panel has been disposed");
          if (artifactUrls.has(ref)) URL.revokeObjectURL(artifactUrls.get(ref));
          var url = URL.createObjectURL(new Blob([result.data], { type: result.mime_type || "application/octet-stream" }));
          artifactUrls.set(ref, url);
          return Object.assign({}, result, { url: url });
        });
      };
    }
    if (api.context === "preview" && services.indexOf("open") >= 0) {
      /**
       * @member open
       * @group Data
       * @context preview
       * @param {string} ref A child of the previewed target: a collection item or composite slot `ref` returned by a read.
       * @returns {Promise<any>}
       * Open a child target in the host's own preview of it. The host checks
       * that the child belongs to the previewed target. Not available in sample
       * mode.
       */
      api.open = function (ref) {
        return sample ? Promise.reject(failure("unsupported", "Sample mode has no child router")) : request("open", { ref: ref });
      };
    }
    if (api.context === "interactive" && operations.indexOf("writeBack") >= 0) {
      var used = false;
      /**
       * @member writeBack
       * @group Decisions
       * @context interactive
       * @param {object} value The decision, a JSON-safe object in the shape the block expects.
       * @returns {Promise<any>}
       * Submit the decision the interactive block is waiting for. A decision is
       * submitted once; a second call rejects with `already_used`. In sample
       * mode it resolves with `value`.
       */
      api.writeBack = function (value) {
        if (used) return Promise.reject(failure("already_used", "Decision already submitted"));
        used = true;
        return sample ? Promise.resolve(value) : request("writeBack", value);
      };
      /**
       * @member cancel
       * @group Decisions
       * @context interactive
       * @returns {Promise<null>}
       * Withdraw without deciding. The window around the frame already offers
       * Cancel, so a panel does not draw its own; call this to withdraw from
       * code. Pressing Escape inside the frame calls it.
       */
      /*
       * Leaving without deciding. The window around this frame already offers
       * Cancel, and it is outside the frame precisely so that a panel cannot
       * fail to provide a way out — so do not draw your own; call this if you
       * need to withdraw from code.
       *
       * Escape is forwarded from in here because a key pressed inside a frame
       * does not reach the document around it: the host listens on its own
       * window, which only sees the key while focus is outside the panel.
       */
      api.cancel = function () {
        return sample ? Promise.resolve(null) : request("cancel", null);
      };
      window.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !disposed) api.cancel().catch(function () {});
      });
      /*
       * An interactive panel opens in a window that sizes itself to what it
       * holds, so the frame has to say how tall the panel is — otherwise the
       * window settles on the frame's fallback height and the panel occupies
       * part of it with empty space below.
       *
       * The opposite of a preview panel, where the host owns the height and the
       * panel fills it, which is why this is reported only from here.
       */
      if (!sample) startReportingHeight();
    }
    // ADR-054 MiniApp FR-016: call is defined only in the miniapp context, which
    // is the only one whose host and backend accept it; it is deliberately
    // absent in preview and interactive.
    if (api.context === "miniapp" && operations.indexOf("call") >= 0) {
      /**
       * @member call
       * @group Python
       * @context miniapp
       * @param {string} fn Name of a function defined in the panel's `panel.py`.
       * @param {object} [args] Keyword arguments, a JSON-safe object.
       * @returns {Promise<any>} The function's JSON-safe return value.
       * Call a function in the MiniApp's Python process. Present only when the
       * panel directory has a `panel.py`. A function that raised rejects with an
       * `Error` whose `code` is the exception type and whose `traceback` is the
       * Python traceback.
       *
       * In sample mode the answer comes from the sample's `calls` map: first
       * the key `JSON.stringify({fn, args})`, then the key `fn`.
       */
      api.call = function (fn, args) {
        if (typeof fn !== "string" || !fn) return Promise.reject(failure("invalid_request", "call needs a function name"));
        if (sample) {
          var calls = (sample.calls || {});
          var key = JSON.stringify({ fn: fn, args: args || {} });
          if (Object.prototype.hasOwnProperty.call(calls, key)) return Promise.resolve(calls[key]);
          if (Object.prototype.hasOwnProperty.call(calls, fn)) return Promise.resolve(calls[fn]);
          return Promise.reject(failure("not_found", "No sample call for " + fn));
        }
        return request("call", { fn: fn, args: args || {} }).then(function (value) {
          /*
           * A panel.py function that raised answers HTTP 200 with a body of
           * {error: {type, message, traceback}}: the call reached the process
           * and the process is still alive, so it is not a transport failure.
           * The page still asked a question that has no answer, so the promise
           * rejects rather than resolving with the error as though it were the
           * result. Matched on the exact shape the backend sends — the only key
           * is ``error`` and it names a type and a message — so a function that
           * legitimately returns something with an ``error`` field still
           * resolves.
           */
          if (value && typeof value === "object" && !Array.isArray(value)) {
            var keys = Object.keys(value);
            var failed = value.error;
            if (keys.length === 1 && keys[0] === "error" && failed && typeof failed === "object" &&
                typeof failed.type === "string" && typeof failed.message === "string") {
              var error = failure(failed.type, failed.message);
              error.traceback = typeof failed.traceback === "string" ? failed.traceback : "";
              throw error;
            }
          }
          return value;
        });
      };
    }
    // sync is deliberately absent in every context in this SDK major.
    applyTheme(payload.theme);
    initializedResolve(api);
  }
  var api = {
    /**
     * @member ready
     * @group Lifecycle
     * @returns {Promise<object>} `window.scistudio`, with its context properties set.
     * Wait for the host to initialise the frame and tell it the page is
     * ready. Call it before anything else; other operations reject with
     * `not_ready` until it resolves. In sample mode it resolves once
     * `panel.sample.json` has loaded.
     */
    ready: function () {
      return initialized.then(function () {
        return sample ? api : request("ready", null).then(function () { return api; });
      });
    },
    /**
     * @member save
     * @group Services
     * @param {object} value `{name, mime, data}`: a file name, a MIME type, and the content as a string, `ArrayBuffer`, or typed array.
     * @returns {Promise<object>} The host's report of where the file went.
     * Save a file for the user through the host. An `ArrayBuffer` in
     * `value.data` is transferred, not copied. Not available in sample mode.
     */
    save: function (value) {
      if (sample) return Promise.reject(failure("unsupported", "Sample mode has no host save service"));
      var transfers = value && value.data instanceof ArrayBuffer ? [value.data] : [];
      return request("save", value, transfers);
    },
    /**
     * @member setViewState
     * @group View state and theme
     * @param {any} state JSON-safe state to keep for this view.
     * @returns {Promise<null>}
     * Store view state (a zoom level, a selected tab) that the host passes
     * back as `viewState` the next time this view opens. Updates
     * `scistudio.viewState` immediately.
     */
    setViewState: function (state) {
      api.viewState = state;
      return sample ? Promise.resolve(null) : request("viewState", state);
    },
    /**
     * @member onTheme
     * @group View state and theme
     * @param {function} callback Receives the theme `{mode, tokens}`.
     * @returns {function} Call it to unsubscribe.
     * Follow the application's theme. The callback runs at once when a theme
     * is known and again on every change. The SDK has already applied the
     * `--ss-*` tokens to the root element and set its `data-theme` attribute
     * to `light` or `dark`, so a page styled with `panel.css` needs no
     * callback.
     */
    onTheme: function (callback) {
      themeCallbacks.add(callback);
      if (api.theme) callback(api.theme);
      return function () { themeCallbacks.delete(callback); };
    },
    /**
     * @member onDispose
     * @group Lifecycle
     * @param {function} callback Runs once when the host disposes the panel.
     * @returns {function} Call it to unsubscribe.
     * Release what the page holds when the host closes it. By then pending
     * operations have rejected with `disposed` and artifact URLs are revoked.
     */
    onDispose: function (callback) {
      disposeCallbacks.add(callback);
      return function () { disposeCallbacks.delete(callback); };
    },
    /**
     * @member reportError
     * @group Lifecycle
     * @param {string} message What went wrong.
     * @returns {Promise<null>}
     * Show an error in the host's panel diagnostics. Uncaught errors and
     * unhandled rejections are reported automatically. A message reported
     * before the host initialises the frame is sent once it does.
     */
    reportError: function (message) {
      if (!port) { errorBeforeInit = String(message); return Promise.resolve(null); }
      return request("reportError", String(message));
    }
  };
  window.scistudio = api;
  function initialize(event) {
    var message = event.data;
    if (port || window.parent === window || event.source !== window.parent || !message || message.v !== 1 || message.type !== "init" || !message.payload || event.ports.length !== 1) return;
    port = event.ports[0];
    window.removeEventListener("message", initialize);
    port.onmessage = function (incoming) {
      var data = incoming.data;
      if (!data || data.v !== 1 || typeof data.type !== "string" || disposed) return;
      if (data.type === "theme") { applyTheme(data.payload); return; }
      if (data.type === "highlight") { setHighlight(data.payload); return; }
      if (data.type === "dispose") { dispose(); return; }
      if (data.type !== "result" && data.type !== "error") return;
      var item = pending.get(data.id);
      if (!item) return;
      pending.delete(data.id); clearTimeout(item.timer);
      if (data.type === "error") item.reject(failure(data.payload.code, data.payload.message));
      else item.resolve(data.payload);
    };
    port.start();
    configure(message.payload);
    if (errorBeforeInit) api.reportError(errorBeforeInit).catch(function () {});
  }
  window.addEventListener("message", initialize);
  window.addEventListener("error", function (event) { api.reportError(event.message || "Panel error").catch(function () {}); });
  window.addEventListener("unhandledrejection", function (event) { api.reportError(String(event.reason)).catch(function () {}); });
  /**
   * @sample
   * `panel.sample.json` sits beside the panel page and stands in for the host
   * when the page is opened directly. The SDK gives the sample context the
   * operations and services of a real context of that kind, with `call`
   * always present for `miniapp`; without a host, `open` and `save` reject
   * with `unsupported`.
   *
   * @property {"preview" | "interactive" | "miniapp"} context Required. The context to simulate.
   * @property {object} [input] Becomes `scistudio.input`; give `ref` for `preview` and `miniapp`. Defaults to `{}`.
   * @property {any} [viewState] Becomes `scistudio.viewState`.
   * @property {object} [theme] Becomes `scistudio.theme`. Defaults to `{mode: "light", tokens: {}}`.
   * @property {object} [reads] Answers for `read`, keyed by `JSON.stringify({ref, op, params})` or by the operation name.
   * @property {object} [calls] Answers for `call`, keyed by `JSON.stringify({fn, args})` or by the function name.
   */
  if (window.parent === window) {
    fetch(new URL("panel.sample.json", window.location.href)).then(function (response) {
      if (!response.ok) throw failure("sample_missing", "Could not load panel.sample.json");
      return response.json();
    }).then(function (loaded) {
      sample = loaded;
      var kind = loaded.context;
      var ops = { preview: ["read"], interactive: ["writeBack"], miniapp: ["read", "call"] };
      var svc = { preview: ["open", "save"], interactive: ["save"], miniapp: ["save"] };
      if (!ops[kind]) throw failure("unsupported", "Sample context must be preview, interactive or miniapp");
      configure({ context: kind, input: loaded.input || {}, viewState: loaded.viewState,
        operations: ops[kind], services: svc[kind],
        apiVersion: "1.0", basePath: "", theme: loaded.theme || { mode: "light", tokens: {} } });
    }).catch(initializedReject);
  }
}());
