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

## Developer / CI escape hatch

The gate runs for **packaged builds** and is skipped in dev (running from a
source checkout) so a checkout is never locked out. Override either way with:

```bash
SCISTUDIO_ALPHA_GATE=0   # force the gate off (e.g. a packaged build under test)
SCISTUDIO_ALPHA_GATE=1   # force the gate on (e.g. exercise it in dev)
SCISTUDIO_ALPHA_PUBKEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
                         # supply the public key inline without a rebuild
```

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
- [ ] Delete this document.
