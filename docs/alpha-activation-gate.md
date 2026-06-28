# Alpha Activation Gate (#1848)

**Status:** Alpha-only, temporary. Remove entirely in beta (see the removal
checklist below and issue #1848).

## Purpose

Stop alpha testers from redistributing the build to people who were not
authorized. The dmg/installer itself never expires and may be reused or
reinstalled freely. The gate is a **per-machine activation token**: without a
valid token, the app does not open.

## How it works (offline, zero-server)

This is an offline signed-token scheme — there is no activation server.

- The developer holds an **Ed25519 private signing key** (kept outside the repo,
  in `~/.scistudio/alpha-signing.key`).
- The matching **public key ships in the build** at
  `desktop/resources/alpha-public-key.pem`.
- A **token** binds to exactly one **machine fingerprint** (a sha256 of a stable
  per-machine id: `IOPlatformUUID` on macOS, registry `MachineGuid` on Windows)
  and is signed with the private key.
- On launch the app verifies the token's signature with the embedded public key
  **and** checks that the bound fingerprint equals this machine's fingerprint. A
  token forwarded to a different machine fails the fingerprint check, so a
  redistributed copy cannot be opened.

Because verification is local, this stops casual redistribution (no token = no
app; a tester's token only works on the tester's machine). It does not provide
remote revocation — that would need a server and is deliberately out of scope
for the alpha (see issue #1848).

## One-time developer setup

Generate the signing keypair once, then rebuild so the public key ships:

```bash
node scripts/alpha-token.js keygen
# Private key -> ~/.scistudio/alpha-signing.key  (keep secret, never commit, back it up)
# Public key  -> desktop/resources/alpha-public-key.pem  (commit it)
```

Commit `desktop/resources/alpha-public-key.pem` and build the alpha dmg/installer
as usual. If the public key is missing from a packaged build, the gate fails
closed (the window shows "Activation is not configured").

> Losing the private key invalidates every issued token. Back it up.

## Per-tester activation flow

1. The tester installs and launches the app. The gate window shows their
   **machine fingerprint** with a **Copy** button.
2. The tester sends you that fingerprint.
3. You mint a token bound to it, either with the GUI or the CLI.

   **GUI (recommended):**

   ```bash
   node scripts/alpha-token-gui.js
   ```

   This opens a small local page in your browser. It auto-uses the signing key
   in `~/.scistudio/alpha-signing.key` (no key handling needed) — paste the
   fingerprint, optionally a name, click **Sign token**, and copy the result. It
   also shows a running count of how many tokens you have issued.

   To avoid the terminal, double-click `scripts/alpha-token-issuer.command` in
   Finder: it launches the same GUI (Ctrl+C in its Terminal window stops it).

   For a desktop app you can double-click (no Electron, no terminal window),
   build a self-contained `.app`:

   ```bash
   bash scripts/build-issuer-app.sh        # writes "Alpha Token Issuer.app" to ~/Desktop
   ```

   The app bundles the issuer scripts and reads the signing key from
   `~/.scistudio/alpha-signing.key`; use the GUI's **Quit issuer** button to stop
   it. It requires Node.js on the machine and is a build artifact (not committed).

   **CLI:**

   ```bash
   node scripts/alpha-token.js sign --fingerprint <fingerprint> --name "Tester Name"
   # check it:  node scripts/alpha-token.js verify --token <t> --fingerprint <fp>
   ```
4. You send the token back. The tester pastes it and clicks **Activate**.
5. The app stores the token at `<userData>/alpha-activation.json` and launches.
   Every subsequent launch re-verifies it silently. There is no expiry.

## Developer escape hatch (dev builds only)

A **packaged build always requires activation** — there is no env switch to turn
the gate off in a real dmg/installer, and the public key is read only from the
shipped `alpha-public-key.pem`. Otherwise a redistributed copy could be bypassed
with an env var (set `SCISTUDIO_ALPHA_GATE=0`, or point `SCISTUDIO_ALPHA_PUBKEY`
at an attacker's key and self-mint a token).

The env vars therefore apply **only in dev** (running from a source checkout),
where the gate is off by default so a checkout is never locked out:

```bash
SCISTUDIO_ALPHA_GATE=1   # dev only: exercise the gate from a source checkout
SCISTUDIO_ALPHA_PUBKEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
                         # dev only: use a public key inline without a rebuild
```

## Alpha tester check-in (#1855)

The gate binds a token to a machine but, being offline/zero-server, cannot tell
you how many machines are actually running the build (the issuance ledger only
counts tokens you *minted*). A lightweight launch check-in fills that gap.

How it works:

- On every launch the **Python backend** (`scistudio.api.app` lifespan) fires a
  best-effort, fire-and-forget POST to a Slack incoming webhook. It runs on a
  daemon thread, never blocks startup, and swallows all errors.
- It lives in the backend on purpose: a user who bypasses the Electron gate by
  running the bundled backend directly still flows through `create_app`, so the
  count includes them.
- The payload is a single Slack `{"text": ...}` line:
  `alpha_launch fp=<fingerprint> build=<n> <os>/<arch> name=<tester>`. The
  fingerprint matches the gate's exactly, so you can de-duplicate by machine and
  spot a shared token (one token id reporting from many fingerprints means the
  per-machine binding was spoofed).

Setup (per build, the URL is **never committed**):

```bash
# Create the gitignored config so the desktop app knows where to report.
cat > desktop/resources/alpha-checkin.json <<'JSON'
{ "url": "https://hooks.slack.com/services/XXX/YYY/ZZZ" }
JSON
```

`desktop/main.js` reads that file and forwards the URL plus the already-computed
fingerprint to the backend as `SCISTUDIO_ALPHA_CHECKIN_URL` /
`SCISTUDIO_ALPHA_FP`. With no config file the check-in is a no-op (source
checkouts and CI stay silent). The webhook URL is intentionally gitignored: in
an open-source build it would otherwise let anyone spam the channel. If that
happens, rotate the webhook.

A short privacy notice on the activation screen tells testers that usage and log
information may be collected during the alpha.

> The check-in narrows casual bypass tracking, not determined bypass: a
> professional can strip it from the open source. That is accepted — the goal is
> a tester count, not DRM.

## Beta removal checklist

The gate is intentionally isolated so it can be deleted in one pass:

- [ ] Delete `desktop/activation.js`, `desktop/preload-gate.js`,
      `desktop/resources/alpha-gate.html`, `desktop/resources/alpha-public-key.pem`.
- [ ] Delete `desktop/test/activation.test.js`.
- [ ] Delete `scripts/alpha-token.js`, `scripts/alpha-token-gui.js`,
      `scripts/alpha-token-issuer.command`, and `scripts/build-issuer-app.sh`
      (plus any "Alpha Token Issuer.app" you built).
- [ ] (Local only) the issuance ledger `~/.scistudio/alpha-issued-tokens.csv` and
      the signing key `~/.scistudio/alpha-signing.key` are never committed; remove
      them from your machine when you retire the alpha.
- [ ] In `desktop/main.js`: remove the `./activation` require, the
      `runActivationGate` / `ensureAlphaActivation` functions, the
      `ensureAlphaActivation()` call in `app.whenReady`, and the `clipboard`
      import if unused elsewhere.
- [ ] In `desktop/package.json`: remove `activation.js` and `preload-gate.js`
      from `build.files`.
- [ ] (#1855 check-in) Delete `src/scistudio/telemetry/` and
      `tests/telemetry/test_checkin.py`; remove the `fire_and_forget()` block
      from the `scistudio.api.app` lifespan; remove `alphaCheckinEnv()` and its
      spread in `runtimeEnv()` from `desktop/main.js`; remove the privacy notice
      from `desktop/resources/alpha-gate.html`; drop the `alpha-checkin.json`
      entry from `desktop/resources/.gitignore`.
- [ ] (Local only) remove `desktop/resources/alpha-checkin.json` from your
      machine; the Slack webhook is never committed.
- [ ] Delete this document.
