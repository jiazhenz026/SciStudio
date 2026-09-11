/* core.plot.basic — plot artifact viewer (parity: PlotViewer).
 * PNG/JPEG/GIF/WEBP/SVG render as an <img> (scripts never run); PDF renders with
 * the local PDF.js from the library set (the browser PDF viewer will not run in a
 * sandboxed frame); zoom controls and Save via the host save service. Bytes come
 * only through the guarded artifact.file grant. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var PDFJS_VERSION = "5.4.149";
  var state = { zoom: 1 };
  var info = null;
  var file = null;

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "onclick") node.onclick = props[k];
      else if (k === "onchange") node.onchange = props[k];
      else if (k === "style") node.setAttribute("style", props[k]);
      else if (k === "disabled") { if (props[k]) node.setAttribute("disabled", ""); }
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function formatOf(mime, name) {
    var m = (mime || "").toLowerCase();
    if (m.indexOf("pdf") >= 0) return "pdf";
    if (m.indexOf("svg") >= 0) return "svg";
    if (m.indexOf("png") >= 0) return "png";
    if (m.indexOf("jpeg") >= 0 || m.indexOf("jpg") >= 0) return "jpeg";
    if (m.indexOf("gif") >= 0) return "gif";
    if (m.indexOf("webp") >= 0) return "webp";
    return ((name || "").split(".").pop() || "").toLowerCase();
  }
  var IMAGE = { png: 1, jpeg: 1, jpg: 1, gif: 1, webp: 1, svg: 1 };

  function applyZoom(next) {
    state.zoom = Math.min(4, Math.max(0.5, Math.round(next * 4) / 4));
    var layer = document.querySelector(".zoom");
    if (layer) layer.setAttribute("style", "transform:scale(" + state.zoom + ")");
    var lvl = document.querySelector("[data-testid=plot-zoom-level]");
    if (lvl) lvl.textContent = Math.round(state.zoom * 100) + "%";
  }

  function controls(fmt) {
    function zbtn(label, aria, fn) { return el("button", { text: label, "aria-label": aria, onclick: fn }); }
    var save = el("button", {
      text: "Save", "data-testid": "plot-export-button", "aria-label": "Save plot",
      disabled: !(file && file.data),
      onclick: function () {
        if (!file || !file.data || !api.save) return;
        api.save({ name: (info && info.name) || "plot." + fmt, mime: (info && info.mime_type) || "application/octet-stream", data: file.data.slice(0) })
          .catch(function (err) { api.reportError(String(err && err.message || err)); });
      },
    });
    return el("div", { class: "bar" }, [
      el("span", { class: "fmt", text: fmt || ((info && info.mime_type) || "") }),
      el("div", { "data-testid": "plot-zoom-controls" }, [
        zbtn("−", "Zoom out", function () { applyZoom(state.zoom - 0.25); }),
        el("span", { "data-testid": "plot-zoom-level", style: "min-width:3em;display:inline-block;text-align:center", text: Math.round(state.zoom * 100) + "%" }),
        zbtn("+", "Zoom in", function () { applyZoom(state.zoom + 0.25); }),
        zbtn("Reset", "Reset zoom", function () { applyZoom(1); }),
      ]),
      el("span", { class: "spacer" }),
      save,
    ]);
  }

  function renderImage(fmt) {
    root.textContent = "";
    var img = el("img", { src: file.url, alt: "Plot " + fmt, "data-testid": "plot-image" });
    var layer = el("div", { class: "zoom", style: "transform:scale(1)" }, [img]);
    root.appendChild(el("div", { class: "surface", "data-testid": "plot-surface" }, [layer]));
    root.appendChild(controls(fmt));
  }

  function renderPdf() {
    root.textContent = "";
    var canvas = el("canvas", { "data-testid": "plot-pdf-canvas" });
    var layer = el("div", { class: "zoom", style: "transform:scale(1)" }, [canvas]);
    root.appendChild(el("div", { class: "surface", "data-testid": "plot-surface" }, [layer]));
    root.appendChild(controls("pdf"));
    var libBase = api.libBaseUrl;
    if (!libBase) { pdfFallback("The PDF renderer is unavailable in this context."); return; }
    var moduleUrl = libBase + "pdfjs@" + PDFJS_VERSION + "/build/pdf.min.mjs";
    import(moduleUrl).then(function (pdfjs) {
      pdfjs.GlobalWorkerOptions.workerSrc = libBase + "pdfjs@" + PDFJS_VERSION + "/build/pdf.worker.min.mjs";
      return pdfjs.getDocument({ data: new Uint8Array(file.data.slice(0)) }).promise;
    }).then(function (doc) {
      return doc.getPage(1);
    }).then(function (page) {
      var viewport = page.getViewport({ scale: 1.5 });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      return page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
    }).catch(function (err) {
      pdfFallback("Could not render the PDF: " + (err && err.message || err));
    });
  }
  function pdfFallback(message) {
    root.textContent = "";
    var kids = [el("div", { class: "note", text: message })];
    if (file && file.url) kids.push(el("a", { href: file.url, download: (info && info.name) || "plot.pdf", "data-testid": "plot-pdf-download", text: "Download PDF" }));
    root.appendChild(el("div", { class: "surface" }, kids));
    root.appendChild(controls("pdf"));
  }

  function fail(err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read plot: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  }

  api.ready().then(function () {
    return api.read("artifact.info", {}).then(function (i) {
      info = i;
      return api.read("artifact.file", {}).then(function (f) {
        file = f;
        var fmt = formatOf((f && f.mime_type) || (i && i.mime_type), (i && i.name));
        if (fmt === "pdf") renderPdf();
        else if (IMAGE[fmt] && file.url) renderImage(fmt);
        else { root.textContent = ""; root.appendChild(el("div", { class: "note", "data-testid": "plot-unrenderable", text: "No renderable plot artifact (" + fmt + ")." })); root.appendChild(controls(fmt)); }
      });
    });
  }).catch(fail);

  window.__panel = { formatOf: formatOf, applyZoom: applyZoom };
})();
