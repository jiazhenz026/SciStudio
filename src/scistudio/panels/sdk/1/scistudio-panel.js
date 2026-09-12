/* SciStudio Panel SDK 1.0 — dependency-free, ADR-054. */
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
  function documentHeight() {
    var body = document.body;
    var root = document.documentElement;
    return Math.ceil(Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      root ? root.scrollHeight : 0,
      root ? root.offsetHeight : 0
    ));
  }
  function reportHeight() {
    if (disposed) return;
    var height = documentHeight();
    if (!height || height === lastHeight) return;
    lastHeight = height;
    request("resize", { height: height }).catch(function () {});
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
    api.context = payload.context;
    /*
     * Which way the height flows, published to the stylesheet. A preview frame
     * is given its height by the host and the panel fills it; an interactive
     * frame opens a window that sizes itself to the panel, so the document must
     * be free to be as tall as its content.
     */
    if (document.documentElement) document.documentElement.dataset.panelContext = payload.context;
    api.input = payload.input;
    api.viewState = payload.viewState;
    api.apiVersion = payload.apiVersion;
    api.basePath = payload.basePath;
    api.libBaseUrl = payload.libBaseUrl;
    var operations = payload.operations || [];
    var services = payload.services || [];
    if (api.context === "preview" && operations.indexOf("read") >= 0) {
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
      api.open = function (ref) {
        return sample ? Promise.reject(failure("unsupported", "Sample mode has no child router")) : request("open", { ref: ref });
      };
    }
    if (api.context === "interactive" && operations.indexOf("writeBack") >= 0) {
      var used = false;
      api.writeBack = function (value) {
        if (used) return Promise.reject(failure("already_used", "Decision already submitted"));
        used = true;
        return sample ? Promise.resolve(value) : request("writeBack", value);
      };
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
    // call and sync are deliberately absent in preview/interactive contexts.
    applyTheme(payload.theme);
    initializedResolve(api);
  }
  var api = {
    ready: function () {
      return initialized.then(function () {
        return sample ? api : request("ready", null).then(function () { return api; });
      });
    },
    save: function (value) {
      if (sample) return Promise.reject(failure("unsupported", "Sample mode has no host save service"));
      var transfers = value && value.data instanceof ArrayBuffer ? [value.data] : [];
      return request("save", value, transfers);
    },
    setViewState: function (state) {
      api.viewState = state;
      return sample ? Promise.resolve(null) : request("viewState", state);
    },
    onTheme: function (callback) {
      themeCallbacks.add(callback);
      if (api.theme) callback(api.theme);
      return function () { themeCallbacks.delete(callback); };
    },
    onDispose: function (callback) {
      disposeCallbacks.add(callback);
      return function () { disposeCallbacks.delete(callback); };
    },
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
  if (window.parent === window) {
    fetch(new URL("panel.sample.json", window.location.href)).then(function (response) {
      if (!response.ok) throw failure("sample_missing", "Could not load panel.sample.json");
      return response.json();
    }).then(function (value) {
      sample = value;
      var kind = value.context;
      if (kind !== "preview" && kind !== "interactive") throw failure("unsupported", "Sample context must be preview or interactive");
      configure({ context: kind, input: value.input || {}, viewState: value.viewState,
        operations: kind === "preview" ? ["read"] : ["writeBack"], services: kind === "preview" ? ["open", "save"] : ["save"],
        apiVersion: "1.0", basePath: "", theme: value.theme || { mode: "light", tokens: {} } });
    }).catch(initializedReject);
  }
}());
