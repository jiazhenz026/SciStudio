---
title: "Desktop Release Runbook"
status: Approved
owners:
  - "@jiazhenz026"
related_specs:
  - desktop-ota-hot-update
  - desktop-shell-ota-hot-update
  - desktop-macos-signing-notarization
  - alpha-version-management
language_source: en
---

# Desktop Release Runbook

How to ship a desktop release and then update installed clients. This is the
procedure; the *reasoning* lives in the specs listed above and is not repeated
here.

## 1. Two rules that brick users when broken

Read these before anything else. Neither is visible in the code, and neither
produces a symptom when it goes wrong.

### 1.1 The installer must exist and download **before** any mandatory manifest

A mandatory manifest blocks startup. If it is published before the installer it
tells people to fetch, every older client is stopped at launch with nowhere to
go — the incompatible dialog carries a single **Quit** button, and there is no
"remind me later".

Publish the installers, download one yourself, *then* publish the manifest.

### 1.2 The installer must carry a build number ≥ the highest published patch

`resolveActivePatch` discards a patch only when
`baselineBuild >= pointer.build`. The committed version is
`a.b.c-alpha-build0000` by design, and the build number is stamped at build time
from the workflow's `build_number` input.

Ship an installer stamped `build0000` and every user's applied patch stays
**active**: they install the new version, keep running the old code, and nothing
fails loudly. If that patch predates shell OTA it also carries no `shell/`, so
the new loader silently falls back to the bundled shell.

Check the current channel high-water mark first:

```bash
gh release download ota-alpha --pattern manifest.json --output - | python -c "import json,sys; print(json.load(sys.stdin)['build'])"
```

Then stamp above it, with headroom for the migration patch.

## 2. Version bump

`src/scistudio/_version.py` is the single source of truth.

```bash
# edit BASE_VERSION, then
python scripts/version.py sync
python scripts/version.py show
```

The API reference carries the version in its header and is generated — do not
edit the line:

```bash
python scripts/docs/build_reference.py
```

Land this as its own PR before building anything.

## 3. Build the installers

Three `workflow_dispatch` workflows, one per platform. Give each the **same**
`build_number` (section 1.2) and the OTA channel.

| Platform | Workflow |
|---|---|
| macOS | `Desktop macOS DMG` |
| Windows | `Desktop Windows Installer` |
| Linux | `Desktop Linux AppImage` |

```bash
gh workflow run desktop-macos-dmg.yml --ref main -f build_number=30 -f ota_channel=alpha
```

Leaving `ota_channel` empty produces a build with OTA **disabled** — correct for
a local test artifact, wrong for a release.

### 3.1 macOS signing is secret-driven

Signing turns on when `MACOS_CSC_LINK` is configured; without it the dmg builds
unsigned and users still meet Gatekeeper. The five secrets are `MACOS_CSC_LINK`,
`MACOS_CSC_KEY_PASSWORD`, `APPLE_API_KEY_P8`, `APPLE_API_KEY_ID`,
`APPLE_API_ISSUER`.

electron-builder's notarization **fails soft** — a missing or mistyped
credential logs `skipped macOS notarization` and returns, leaving a green build
and a dmg that still prompts. The workflow's `Verify signature, hardened runtime
and notarization` step exists to turn that into a red build. If it is skipped,
the artifact is not signed no matter what the rest of the log says.

### 3.2 macOS Intel (x64) is not built by CI

`dist:dmg` is hardcoded to `--arm64`, and the workflow's own comment rules out
running it on an Intel runner: `build:python:mac` keys off `uname -m`, so an
Intel runner would bundle x64 Python inside an arm64 shell. Yet
`v0.3.3-alpha` shipped an `-x64.dmg`.

That artefact is produced **locally**, and the procedure is not written down
anywhere — the only trace is a line in the body of a closed issue.

<!-- TODO(#2165): document the macOS Intel (x64) build.
     The procedure exists only as tacit knowledge; this section cannot be
     completed without it. Followup:
     https://github.com/jiazhenz026/SciStudio/issues/2165 -->

Two things to carry over from section 3.1 when building it by hand:

* the same `APPLE_API_KEY` / `APPLE_API_KEY_ID` / `APPLE_API_ISSUER` must be
  exported, or the dmg is unsigned;
* `dist:dmg` does **not** run the workflow's verification step, and
  electron-builder's notarization fails soft, so run the four checks manually:

```sh
APP=$(find dist -maxdepth 2 -name '*.app' -print -quit)
codesign --verify --deep --strict --verbose=2 "$APP"
codesign --display --verbose=2 "$APP"   # must report flags=...runtime
spctl -a -vvv -t exec "$APP"
xcrun stapler validate "$APP"
```

## 4. Publish the release and **verify the download**

Attach the installers to a GitHub Release for the tag -- three from CI plus the
macOS x64 dmg from section 3.2.

Then actually download one and install it. This is the gate for section 1.1, not
a formality: everything after this point assumes the artifact is reachable.

For macOS, confirm on a machine that has never had the app installed that it
opens without any security prompt.

## 5. Publish the OTA update

From a **clean detached worktree at `origin/main`**, with the backend staged:

```bash
npm --prefix desktop run stage:sh     # or `stage` on Windows
python scripts/ota_publish.py --channel alpha --notes "<what changed>"
```

The snapshot carries `src/` **and** `shell/`, sharing one build number.
`bootstrap.js` and `package.json` are never published — the loader must not be
replaceable by the thing it decides whether to trust.

`--dry-run` always reports build 1; its `build` and `url` are meaningless, while
`sha256`, `size`, `notes` and `requires` are real.

### 5.1 Clients that must reinstall

When the base version moved, older clients cannot reach the new build by OTA.
Do **not** migrate them with a mandatory *incompatible* manifest: that renders in
a native dialog, whose text is neither clickable nor selectable, so the address
has to be retyped — and it cannot be improved, because that dialog is drawn by
the one part a patch cannot replace.

Publish a mandatory **patch** instead:

```bash
python scripts/ota_publish.py --channel alpha --min-build N \
  --min-base <the OLD base, e.g. 0.3.3> \
  --reinstall-notice "https://github.com/jiazhenz026/SciStudio/releases/tag/vX.Y.Z"
```

It swaps the snapshot's SPA for an ordinary web page with selectable text and a
clipboard button. Because the address is copyable it does not need to be
short — use the real release URL.

**`--min-base` is not optional here (#2169).** Without it the value derives
from the build's own base, which after a bump is the *new* one — so every
client on the old base evaluates to `incompatible` instead of `patch`, and
that branch never downloads anything. The notice page would be built,
uploaded, and never fetched, leaving the user at the plain native dialog the
notice exists to avoid.

Check the decision before publishing rather than reasoning about it:

```bash
cd desktop && node -e "
const ota = require('./ota.js');
console.log(JSON.stringify(ota.evaluateUpdate(
  {enabled:true, channel:'alpha'},
  require('/path/to/manifest.json'),
  {base:'0.3.3', channel:'alpha', build:0},   // a client you are migrating
  25                                          // its effective build
)));   // must read kind:'patch', mandatory:true
"
```

### 5.2 Making an update mandatory

`--min-build N` writes `requires.min_build` and makes startup blocking. Say the
consequences out loud before publishing, because each one is "the user cannot
open the app": declining quits, a failed download or sha mismatch quits, and a
client below `requires.min_base` gets the reinstall path. Offline is
**fail-open** — an unreachable manifest lets the app start.

## 6. Verify the published patch

A sha mismatch locks out every client, so check the live artifacts rather than
the publish script's own output:

```bash
gh release download ota-alpha -p manifest.json -p backend-buildNN.tar.gz -D <dir> --clobber
sha256sum <dir>/backend-buildNN.tar.gz          # must equal manifest.sha256
tar -tzf <dir>/backend-buildNN.tar.gz | head    # src/scistudio/... and shell/...
```

Then feed the live manifest through the real decision module rather than
reasoning about it. `desktop/ota.js` is dependency-free:

```bash
cd desktop && node -e "
const ota = require('./ota.js'); const m = require('C:/.../manifest.json');
const cfg = {enabled:true, channel:'alpha'}, base = {base:'0.3.4', channel:'alpha', build:30};
for (const eff of [25,29,30]) console.log(eff, JSON.stringify(ota.evaluateUpdate(cfg, m, base, eff)));
"
```

## 7. Testing a release without touching real users

Channel isolation protects other people; it does not protect this machine.
`evaluateUpdate` filters on `manifest.channel`, but `getActivePatch` and the
bootstrap loader read `userData/patches/active.json` with **no channel check at
all**.

- Isolate with Electron's `--user-data-dir`. Changing `build.productName` does
  **not** work: `app.getName()` reads the packaged `package.json`'s top-level
  `name`, so a renamed build still shares the real client's userData.
- Serve the manifest from `127.0.0.1` via `SCISTUDIO_OTA_MANIFEST_URL`;
  `otaHttpGet` selects the `http` module for `http:` URLs, so no public release
  is involved.
- Nothing else may be running. The single-instance lock (#1867) makes a second
  launch `app.quit()` immediately with **exit code 0** — indistinguishable from a
  clean run.
- `ELECTRON_RUN_AS_NODE` inherited from the launching shell starts the binary as
  Node, rejects `--user-data-dir`, and exits 0 having done nothing.

The full scenario, with expected log lines, is
`docs/ai-developer/e2e/2026-08-23-shell-ota-hot-update-lifecycle.md`.
