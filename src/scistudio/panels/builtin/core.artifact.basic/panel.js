/* core.artifact.basic — artifact metadata + safe inline display (parity: ArtifactViewer).
 * Reads artifact.info for name/mime/size, then artifact.file for a token-scoped
 * (blob) URL. Images render inline; other types offer a download of the same
 * URL. Bytes are only ever fetched through the guarded artifact.file grant. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");

  function humanBytes(n) {
    if (typeof n !== "number" || !isFinite(n)) return "?";
    var units = ["B", "KiB", "MiB", "GiB"];
    var i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + " " + units[i];
  }
  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function render(info, file) {
    var name = info.name || "artifact";
    var mime = info.mime_type || "application/octet-stream";
    var size = info.size;
    var url = file && file.url;
    var kids = [
      el("div", { class: "name", "data-testid": "artifact-name", text: name }),
      el("div", { class: "field", "data-testid": "artifact-mime", text: mime }),
      el("div", { class: "field", "data-testid": "artifact-size", text: humanBytes(size) + (typeof size === "number" ? " (" + size + " bytes)" : "") }),
    ];
    if (url && mime.indexOf("image/") === 0) {
      kids.push(el("img", { src: url, alt: name, "data-testid": "artifact-image" }));
    } else if (url) {
      kids.push(el("a", { class: "download", href: url, download: name, "data-testid": "artifact-download", text: "Download " + name }));
    }
    root.textContent = "";
    root.appendChild(el("div", { class: "card", "data-testid": "artifact-card" }, kids));
  }

  function fail(err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read artifact: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  }

  api.ready().then(function () {
    return api.read("artifact.info", {}).then(function (info) {
      return api.read("artifact.file", {}).then(function (file) { render(info, file); },
        function () { render(info, null); });
    });
  }).catch(fail);

  window.__panel = { humanBytes: humanBytes, render: render };
})();
