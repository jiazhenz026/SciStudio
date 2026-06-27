---
spec_id: desktop-ota-hot-update
title: "Desktop OTA Hot-Update: Full-Snapshot Backend+Frontend Patches"
status: Implemented
feature_branch: guided/ota-hot-update-20260625
created: 2026-06-25
input: "Issue #1775 — internal alpha testers should receive backend + frontend fixes without re-downloading the full installer. Owner-directed guided session 2026-06-25."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - alpha-version-management
scope:
  in:
    - Launch-time OTA update check in the Electron desktop client.
    - Full-snapshot patches of the staged backend source tree (which embeds the frontend SPA at scistudio/api/static).
    - A per-channel rolling GitHub pre-release as the manifest + asset host.
    - A publish CLI (scripts/ota_publish.py) that packs, hashes, numbers, and uploads a patch.
    - userData-staged patches with PYTHONPATH redirection, atomic apply, and boot-failure rollback.
    - A build-time dev marker (ota-config.json) that disables OTA for local/dev builds.
    - Removal of the duplicate bundled-interpreter scistudio copy left by the runtime build.
  out:
    - OTA of the Electron JS shell, the Electron/Chromium binary, the Python interpreter, or native dependencies (these require a new installer; the client only prompts).
    - Cryptographic signing of patches (sha256 + HTTPS only for now; Ed25519 deferred to release).
    - A manual "check for updates" UI entry and background polling (launch-time check only).
    - CI auto-publish on merge (manual publish for now).
    - An ADR (owner decision; this spec is the design record).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/desktop-ota-hot-update.md
    - desktop/main.js
    - desktop/ota.js
    - desktop/scripts/stage-resources.sh
    - desktop/scripts/stage-resources.ps1
    - desktop/scripts/build-python-runtime-macos.sh
    - desktop/scripts/build-python-runtime.ps1
    - scripts/ota_publish.py
  excludes: []
tests:
  - tests/scripts/test_ota_publish.py
  - desktop/test/ota.test.js
acceptance_source: issue
language_source: en
---

# Desktop OTA Hot-Update: Full-Snapshot Backend+Frontend Patches

## 1. Change Summary

From issue #1775. The desktop app ships a bundled Python interpreter plus the
backend **source tree** on `PYTHONPATH` (`resources/backend/src`), and that tree
embeds the built frontend SPA at `scistudio/api/static`, which the bundled
backend serves over HTTP. Because the runtime executes source (not compiled
artifacts), the backend **and** frontend can be updated by swapping one
directory — without re-running the installer.

This spec adds an OTA mechanism that does exactly that: at launch the client
checks a per-channel manifest, and if a newer compatible **build** exists it
downloads a full-snapshot tarball, verifies it, stages it under `userData`, and
restarts the runtime pointed at the new source. The Electron shell, the Python
interpreter, and native dependencies are **not** hot-updatable; a patch that
needs a newer baseline asks the user to reinstall.

It also removes a pre-existing redundancy: the runtime build `pip install`s
scistudio into the bundled interpreter in addition to staging the source tree,
shipping two plaintext copies. Only the `PYTHONPATH` copy is used; the installed
one is removed (dependencies are kept).

## 2. Layered update model

| Layer | Hot-updatable? | Mechanism |
|---|---|---|
| Backend source (`backend/src`) | Yes | OTA full-snapshot swap |
| Frontend SPA (`scistudio/api/static`, inside the backend tree) | Yes | rides in the same snapshot |
| Electron JS, Electron/Chromium binary, Python interpreter, native deps | No | new installer (client prompts only) |

## 3. Versioning (extends [alpha-version-management](alpha-version-management.md))

Two independently-moving parts:

- **`base`** (`a.b.c`, from `desktop/package.json`) — the installer baseline:
  Electron + interpreter + native deps.
- **`build`** (integer) — the patch sequence for the hot-updatable source layer.
  Source of truth is the published manifest, not the local counter.

The client's **effective build** is `max(baseline build, applied patch build)`
and is reported to the backend via the existing `SCISTUDIO_BUILD_NUMBER`
override so `/version` reflects the applied patch.

Update decision (pure logic in `desktop/ota.js`, `evaluateUpdate`):

1. `manifest.channel == config.channel` (else ignore).
2. `manifest.build > effective build` (else up-to-date).
3. `base >= manifest.requires.min_base` → **patch**; otherwise **incompatible**
   (prompt to reinstall). The client always targets the latest build; a client
   several builds behind jumps straight to it in one snapshot download.

## 4. Distribution

- Host: a public-repo, per-channel rolling GitHub **pre-release** tagged
  `ota-<channel>`, with assets `manifest.json` and `backend-build<N>.tar.gz`.
  Anonymous download (repo is public); pre-release is visible but not "latest".
- `manifest.json`:
  `{channel, base, build, requires:{min_base}, url, sha256, size, notes, published_at}`.
- Publish: `scripts/ota_publish.py` packs `desktop/resources/backend/src` into a
  gzip tarball rooted at `src/` (excluding `__pycache__`/`.pyc`/`egg-info`),
  computes sha256, sets `build = max(latest_published, baseline) + 1`, and
  uploads with `gh release upload --clobber`. `--dry-run` builds locally only.

## 5. Client behavior (`desktop/main.js`)

- **Launch-time only**, after the window is shown (never blocks startup); offline
  failures are logged and ignored.
- Reads `resources/ota-config.json`. `{enabled:false, channel:"dev"}` (the
  default for local builds) disables OTA entirely.
- On a `patch` decision: native dialog → download → sha256 verify → `tar -xzf`
  into a temp dir → atomic rename to `userData/patches/build<N>/` → write
  `active.json` pointer → `app.relaunch()`.
- `runtimeEnv()` prepends `userData/patches/build<N>/src` to `PYTHONPATH`; the
  app bundle is never modified (works under a read-only/signed bundle and avoids
  Windows `Program Files` permission issues). The ordered entries are resolved by
  the pure `ota.pythonPathFor({isPackaged, patchSrc, stagedSrc, checkoutSrc})`.
- **Supersession (#1787)**: an active patch shadows the bundled baseline only
  while it is strictly newer. `getActivePatch()` consults
  `ota.resolveActivePatch(pointer, baselineBuild, srcExists)`; when the installed
  `baseline build >= active patch build` (e.g. a newer or equal bundle was
  reinstalled over an older patch), the patch is treated as **stale**: it is
  ignored and its `userData/patches/build<N>/` directory plus the `active.json`
  pointer are discarded, so a fresh install always wins instead of being silently
  shadowed by leftover patch source on `PYTHONPATH`.
- **Rollback**: if the runtime fails to reach ready with an active patch, the
  client reverts to the last known-good patch (or the bundled baseline) and
  retries once, so a bad patch cannot brick the install. A patch is recorded
  known-good only after the runtime reaches HTTP readiness.

## 6. Local/dev isolation

Local builds (`npm run dist:dmg`) leave `SCISTUDIO_OTA_CHANNEL` unset; the stage
step writes `ota-config.json` with `enabled:false`, so a developer testing a
local build is never disturbed or overwritten. A release build sets
`SCISTUDIO_OTA_CHANNEL` (and optionally `SCISTUDIO_OTA_MANIFEST_URL`) to enable
checks. Publishing is a separate explicit step; run it from the same checkout
that was built and tested.

**Dev source-of-truth (#1801).** Disabling the OTA *check* (`enabled:false`) is
not enough on its own: a developer who previously ran a packaged build may have a
leftover applied patch under `userData/patches/`, and the staged
`desktop/resources/backend/src` copy may also exist in the checkout. Both sit
ahead of the worktree `src` on `PYTHONPATH`, and the #1787 stale check cannot
catch them because a dev build's baseline build is `0`, so any applied patch
(build > 0) always compares as newer. Therefore, when the app is **not packaged**
(`!app.isPackaged` — a `npm run dev` source-checkout run, never an installed
app), `getActivePatch()` returns `null` (non-destructively — the user's
`active.json` is left intact) and `pythonPathFor` resolves `PYTHONPATH` to the
worktree `src` alone. Edits to the worktree always take effect in dev; the
packaged client's layered patch/staged/checkout order is unchanged.

## 7. Security

Internal alpha threat model: HTTPS + sha256 integrity (detects corruption, not
MITM). Patches are open-source code on a public repo. Ed25519 signing is
deferred to a release-grade channel.

## 8. Verification

- `tests/scripts/test_ota_publish.py`: version parse, monotonic build numbering,
  manifest shape, naming/URLs, sha256, snapshot packing + exclusions.
- `desktop/test/ota.test.js`: `parseVersion`, numeric `compareBase`, and every
  `evaluateUpdate` branch (disabled, invalid, channel-mismatch, up-to-date,
  patch, incompatible, effective-build comparison).
- Manual: `python scripts/ota_publish.py --channel alpha --dry-run`; build a
  dev DMG and confirm OTA is skipped; build with `SCISTUDIO_OTA_CHANNEL=alpha`
  and confirm the launch-time dialog, apply, relaunch, and `/version` update.

## 9. Assumptions

- Repo `jiazhenz026/SciStudio` is public; OTA assets are anonymously downloadable
  (source: owner).
- Single combined PR; no ADR; this spec is the design record (source: owner).
- `gh` is available and authenticated when publishing (source: inferred).
- System `tar` (bsdtar) is present on macOS and Windows 10+ for extraction
  (source: inferred).
