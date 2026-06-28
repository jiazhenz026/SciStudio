#!/usr/bin/env node
// #1848: minimal local GUI for issuing alpha activation tokens.
//
// Run:  node scripts/alpha-token-gui.js
// It starts a tiny local web app (127.0.0.1 only) and opens it in your browser.
// Paste a tester's machine fingerprint, click Sign, copy the token. It reuses the
// signing key in ~/.scistudio/alpha-signing.key via scripts/alpha-token.js.
//
// ALPHA-ONLY developer tool; delete in beta with the rest of the gate (#1848).

const http = require("http");
const { execFile } = require("child_process");

const tokens = require("./alpha-token");

const HOST = "127.0.0.1";
const PORT = Number(process.env.SCISTUDIO_ALPHA_GUI_PORT || 7848);

const PAGE = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>SciStudio Alpha — Token Issuer</title>
    <style>
      * { box-sizing: border-box; }
      body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif; background: #f7f8fb; color: #1f2533; margin: 0; padding: 28px 32px; font-size: 14px; }
      h1 { font-size: 18px; margin: 0 0 4px; }
      p.sub { margin: 0 0 18px; color: #6b7280; }
      .status { font-size: 13px; padding: 8px 12px; border-radius: 8px; margin-bottom: 18px; }
      .status.ok { background: #e7f4ec; color: #1e8e4e; }
      .status.warn { background: #fdecea; color: #c0392b; }
      label { display: block; font-weight: 600; margin: 0 0 6px; }
      .field { margin-bottom: 16px; }
      input, textarea { width: 100%; font-size: 13px; padding: 9px 10px; border: 1px solid #d7dbe3; border-radius: 8px; background: #fff; font-family: ui-monospace, "SF Mono", Consolas, monospace; }
      textarea { resize: vertical; min-height: 72px; }
      button { font-size: 14px; font-weight: 600; padding: 9px 16px; border-radius: 8px; border: 1px solid #2f6df6; background: #2f6df6; color: #fff; cursor: pointer; }
      button.secondary { background: #fff; color: #1f2533; border-color: #d7dbe3; }
      button:disabled { opacity: 0.5; cursor: default; }
      .row { display: flex; gap: 8px; align-items: flex-start; }
      .result { margin-top: 18px; }
      .hint { color: #6b7280; font-size: 12px; margin-top: 6px; }
    </style>
  </head>
  <body>
    <h1>Alpha Token Issuer</h1>
    <p class="sub">Sign a per-machine activation token for an alpha tester (#1848).</p>

    <div id="status" class="status">Checking signing key…</div>

    <div id="keygen" style="display:none" class="field">
      <button id="keygenBtn" class="secondary" type="button">Generate signing keys</button>
      <div class="hint">No signing key found. This creates ~/.scistudio/alpha-signing.key and writes the public key into the build. Commit the public key and rebuild.</div>
    </div>

    <div class="field">
      <label for="fp">Tester machine fingerprint</label>
      <textarea id="fp" placeholder="Paste the fingerprint the tester copied from the activation window"></textarea>
    </div>

    <div class="field">
      <label for="name">Tester name (optional)</label>
      <input id="name" type="text" placeholder="e.g. Alice" />
    </div>

    <button id="signBtn" type="button">Sign token</button>

    <div id="result" class="result" style="display:none">
      <label for="token">Activation token — send this to the tester</label>
      <div class="row">
        <textarea id="token" readonly></textarea>
        <button id="copyBtn" class="secondary" type="button">Copy</button>
      </div>
    </div>

    <div class="result">
      <label>Issued so far</label>
      <div id="issued" class="hint">…</div>
    </div>

    <script>
      const statusEl = document.getElementById("status");
      const keygenEl = document.getElementById("keygen");
      const signBtn = document.getElementById("signBtn");
      const resultEl = document.getElementById("result");
      const tokenEl = document.getElementById("token");

      function setStatus(text, kind) { statusEl.textContent = text; statusEl.className = "status " + kind; }

      async function refresh() {
        const s = await (await fetch("/api/status")).json();
        if (s.hasPrivate) {
          setStatus("Signing key ready: " + s.keyPath + (s.hasPublic ? "" : "  (public key missing — generate or rebuild)"), s.hasPublic ? "ok" : "warn");
          keygenEl.style.display = s.hasPublic ? "none" : "block";
          signBtn.disabled = false;
        } else {
          setStatus("No signing key found.", "warn");
          keygenEl.style.display = "block";
          signBtn.disabled = true;
        }
      }

      document.getElementById("keygenBtn").addEventListener("click", async () => {
        setStatus("Generating keys…", "ok");
        const res = await fetch("/api/keygen", { method: "POST" });
        if (res.ok) { await refresh(); } else { setStatus("Key generation failed.", "warn"); }
      });

      signBtn.addEventListener("click", async () => {
        const fingerprint = document.getElementById("fp").value.trim();
        const name = document.getElementById("name").value.trim();
        if (!fingerprint) { setStatus("Paste a fingerprint first.", "warn"); return; }
        signBtn.disabled = true;
        const res = await fetch("/api/sign", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ fingerprint, name })
        });
        signBtn.disabled = false;
        const data = await res.json();
        if (res.ok && data.token) {
          tokenEl.value = data.token;
          resultEl.style.display = "block";
          setStatus("Token signed. Copy it and send it to the tester.", "ok");
          refreshIssued();
        } else {
          setStatus("Signing failed: " + (data.error || "unknown error"), "warn");
        }
      });

      async function refreshIssued() {
        try {
          const d = await (await fetch("/api/issued")).json();
          const lines = (d.recent || []).map(function (r) {
            return (r.issued_at || "").slice(0, 19).replace("T", " ") + "  " + (r.name || "-") + "  " + (r.fingerprint || "").slice(0, 12) + "…";
          });
          document.getElementById("issued").textContent =
            d.count + " token(s), " + d.machines + " machine(s)" + (lines.length ? "\\n" + lines.join("\\n") : "");
          document.getElementById("issued").style.whiteSpace = "pre-line";
        } catch (e) { /* ignore */ }
      }

      document.getElementById("copyBtn").addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(tokenEl.value); } catch { tokenEl.select(); document.execCommand("copy"); }
        const btn = document.getElementById("copyBtn");
        const original = btn.textContent; btn.textContent = "Copied"; setTimeout(() => { btn.textContent = original; }, 1200);
      });

      refresh();
      refreshIssued();
    </script>
  </body>
</html>`;

function readJsonBody(req) {
  return new Promise((resolve) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) {
        req.destroy();
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        resolve({});
      }
    });
  });
}

function sendJson(res, status, value) {
  const payload = JSON.stringify(value);
  res.writeHead(status, { "content-type": "application/json" });
  res.end(payload);
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/") {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      res.end(PAGE);
      return;
    }
    if (req.method === "GET" && req.url === "/api/status") {
      sendJson(res, 200, tokens.keyStatus());
      return;
    }
    if (req.method === "POST" && req.url === "/api/keygen") {
      const result = tokens.generateKeypair();
      sendJson(res, 200, { ok: true, ...result });
      return;
    }
    if (req.method === "POST" && req.url === "/api/sign") {
      const body = await readJsonBody(req);
      if (!body.fingerprint) {
        sendJson(res, 400, { error: "fingerprint is required" });
        return;
      }
      const name = body.name || null;
      const token = tokens.mintToken({ fingerprint: body.fingerprint, name });
      // #1848: record every issuance to the local CSV ledger.
      tokens.recordIssuance({ fingerprint: String(body.fingerprint).trim(), name, token });
      sendJson(res, 200, { token });
      return;
    }
    if (req.method === "GET" && req.url === "/api/issued") {
      const rows = tokens.readIssuance();
      const unique = new Set(rows.map((row) => row.fingerprint));
      sendJson(res, 200, {
        count: rows.length,
        machines: unique.size,
        ledgerPath: tokens.defaultLedgerPath(),
        recent: rows.slice(-8).reverse()
      });
      return;
    }
    res.writeHead(404);
    res.end("not found");
  } catch (error) {
    sendJson(res, 500, { error: error.message });
  }
});

function openBrowser(url) {
  const opener =
    process.platform === "darwin" ? "open" : process.platform === "win32" ? "explorer" : "xdg-open";
  execFile(opener, [url], () => {});
}

server.listen(PORT, HOST, () => {
  const url = `http://${HOST}:${PORT}/`;
  process.stdout.write(`Alpha token issuer running at ${url}\n`);
  process.stdout.write("Press Ctrl+C to stop.\n");
  openBrowser(url);
});
