---
session_id: "2026-08-23-shell-ota-hot-update-lifecycle"
title: "Shell + backend + frontend hot-update, rollback, poisoned patch, and the mandatory-reinstall prompt"
created: "2026-08-23"
owner: "@jiazhenz026"
trigger:
  kind: "pr-readiness"
  ref: "PR #2139 (issue #2097), depends on PR #2128 (issue #2096)"
related_adrs: []
status: "draft"
language_source: en
---

# E2E Session — Shell OTA Hot-Update Lifecycle

> Run this on **macOS** against an **installed** build. Most of it cannot be
> exercised from a source checkout: the loader treats an unpackaged run as
> "never patched" (#1801), so `npm run dev` deliberately bypasses everything
> under test here.

## 1. Goal And Out-Of-Scope

- **Goal**: prove that one published snapshot updates the Electron shell, the
  backend and the frontend together without an installer; that a shell that
  cannot boot is rolled back and **stays** rolled back; and that an
  incompatible mandatory manifest blocks startup with a reinstall prompt.
- **Out of scope**:
  - macOS signing and notarization (separate scenario; PR #2128).
  - Package OTA (#1784) — different mechanism, different unit.
  - Any client on the `alpha` channel. Nothing here may reach a real user.

## 2. Preconditions

- **Repo state**: PR #2139 head, with PR #2128 merged or merged-in.
- **Working tree**: clean apart from the two identity lines in Section 2.1,
  which must **never be committed**.
- **Backend port**: whatever the packaged client picks; do not pin.
- **Frontend mode**: prebuilt SPA inside the snapshot. Not Vite.
- **Required tooling**: `gh` authenticated with write access to the repo,
  Xcode command line tools, Node, a macOS machine.

### 2.1 Isolation — read this before building

Channel isolation protects *other* users. It does **not** protect your own
install, and skipping this step is how a test patch reaches your real client.

`evaluateUpdate` filters on `manifest.channel`, but that only governs whether a
manifest is *fetched and offered*. `getActivePatch()` and the bootstrap loader
read `userData/patches/active.json` with **no channel check at all** — they
simply honour whatever pointer is on disk. `userData` is derived from
`productName`, which both builds share.

So a test build installed beside the real one writes its patches into the very
directory the real client reads on next launch.

Before building the test client, edit `desktop/package.json`:

```json
"appId": "org.scistudio.desktop.test",
"productName": "SciStudio Test",
```

`productName` moves `userData` to `~/Library/Application Support/SciStudio Test/`;
`appId` stops the installer replacing `/Applications/SciStudio.app`. Revert both
after the session.

A separate machine, VM, or macOS user account achieves the same isolation and is
preferable if available.

## 3. Launch Plan

- **Build the test client** (once):
  ```sh
  export SCISTUDIO_OTA_CHANNEL=test
  npm --prefix desktop run build:python:mac
  npm --prefix desktop run stage:sh
  npm --prefix desktop run dist:dmg
  ```
  Install the resulting dmg. Confirm the app is named **SciStudio Test**.

- **Publish a patch** (repeated per step). `stage:sh` is mandatory whenever the
  backend or frontend changed: the snapshot takes `src/` from
  `desktop/resources/backend/src` (staged) but `shell/` straight from the
  repository's `desktop/` directory.
  ```sh
  npm --prefix desktop run stage:sh
  python scripts/ota_publish.py --channel test --notes "<what changed>" --yes
  ```

- **Reset to the bundled baseline** between steps:
  ```sh
  rm -rf ~/Library/Application\ Support/SciStudio\ Test/patches
  ```

- **Cleanup** (end of session, even on failure):
  ```sh
  gh release delete ota-test --yes --cleanup-tag
  rm -rf ~/Library/Application\ Support/SciStudio\ Test
  git checkout desktop/package.json
  ```

## 4. Affordances Under Test

- Launch-time OTA dialog (optional patch) and its apply + relaunch path.
- Bootstrap loader shell selection: baseline vs patch.
- Loader fallback when a patch shell throws at `require`.
- Sticky quarantine when a patch shell loads but never reaches readiness.
- Backend rollback when a patch's `src/` cannot start.
- Pre-window mandatory gate: incompatible manifest, reinstall prompt, quit.
- `/version` reporting the effective (post-patch) build.

## 5. Steps

### Step 1 — Three layers update from one snapshot

- **Action**: make one visible change per layer, then stage and publish.
  - Shell: change the visible text in `desktop/splash.html`.
  - Backend: change a user-visible string served by `src/scistudio/`.
  - Frontend: change a visible string in the SPA.

  Launch the test client, accept the update dialog, let it relaunch.
- **Expected**: after relaunch, **all three** markers are the new ones. The
  splash marker proves the shell swapped, because the splash is drawn before
  the runtime exists. `/version` reports the new build number.
- **Capture**: screenshot of the splash and of the changed UI; `/version` body.
- **On failure**: halt.

### Step 2 — Reset to baseline

- **Action**: quit, `rm -rf .../SciStudio Test/patches`, relaunch.
- **Expected**: all three markers are back to the installed values; `/version`
  reports the installer baseline build.
- **Capture**: `/version` body.
- **On failure**: halt.

> **Note on "rolling back" deliberately.** There is no client-side downgrade:
> `evaluateUpdate` requires `manifest.build > effectiveBuild`, so returning to
> older code means republishing it under a *higher* build number. Deleting
> `patches/` is the only direct route back to the bundled baseline.

### Step 3 — Poisoned backend, Electron survives

- **Action**: add `raise RuntimeError("boom")` at the top of
  `src/scistudio/__init__.py`. Stage, publish, apply, relaunch.
- **Expected**: the runtime never reaches readiness; the client reverts to the
  last known-good build (or the baseline) and retries **once**, then comes up.
  The window appears. Electron never dies.
- **Capture**: desktop log lines showing the rollback.
- **On failure**: halt. Remove the `raise` before continuing.

### Step 4 — Poisoned shell that throws at load

- **Action**: add `throw new Error("boom");` at the top of `desktop/main.js`.
  Publish (no `stage:sh` needed — the shell is taken from the repo). Apply,
  relaunch.
- **Expected**: the app still starts, on the **baseline** shell. stdout carries
  `[scistudio][bootstrap] shell failed to load:`.
- **Capture**: bootstrap log lines.
- **On failure**: halt. Remove the `throw` before continuing.

### Step 5 — Poisoned shell that loads but never reaches readiness

This is the regression Codex found on PR #2139. **Launch three times** — the
third launch is the actual assertion.

- **Action**: instead of a top-level throw, make the failure late so the marker
  is already on disk when the process dies:
  ```js
  app.whenReady().then(() => { throw new Error("late boom"); });
  ```
  Publish, apply, then launch three times.
- **Expected**:

  | Launch | Expected |
  |---|---|
  | 1 | patch shell loads, then the process dies |
  | 2 | patch refused, baseline shell, app comes up |
  | 3 | **still the baseline** — the patch is not retried |

  Before the fix, launch 3 loaded the broken shell again and the app alternated
  between crashing and working forever. A second crash at launch 3 is a
  regression, not a flake.
- **Capture**: bootstrap log for each of the three launches;
  `userData/SciStudio Test/shell-boot-attempt.json` after launch 2 (it must
  still exist and still name the broken build).
- **On failure**: halt.

### Step 6 — A newer patch is still tried after a quarantine

- **Action**: with the Step 5 quarantine still in place, remove the `throw`,
  publish a healthy higher build, relaunch.
- **Expected**: the new patch **is** offered and applied. The quarantine must
  not have become a permanent refusal of all future updates.
- **Capture**: `/version` body showing the new build.
- **On failure**: halt.

### Step 7 — Mandatory reinstall prompt

Run this **last**: it leaves the client blocked at every launch until the
`ota-test` manifest is removed.

- **Action**: `ota_publish.py` cannot produce this (`base` comes from the
  version and has no override), so hand-write `manifest.json` and upload it:
  ```json
  {
    "channel": "test",
    "base": "0.4.0",
    "build": 999,
    "requires": {
      "min_base": "0.4.0\n\nDownload: https://github.com/jiazhenz026/SciStudio/releases",
      "min_build": 999
    },
    "url": "https://github.com/jiazhenz026/SciStudio/releases/download/ota-test/backend-build999.tar.gz",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "size": 1,
    "notes": "reinstall prompt test",
    "published_at": "2026-08-23T00:00:00Z"
  }
  ```
  ```sh
  gh release upload ota-test manifest.json --clobber
  ```
  Launch the client.
- **Expected**: **before** the window or runtime start, a warning dialog titled
  "Update required" appears with a single **Quit** button; choosing it exits.
  The `url` and `sha256` are never used — the incompatible path does not
  download.

  The `min_base` string also renders verbatim, so the download URL smuggled into
  it is visible to the user. This is the exact text a 0.3.3 client would see, so
  judge the wording here before shipping it: `compareBase` only `parseInt`s the
  first three dot-separated segments, which is why the trailing text does not
  break the version comparison.
- **Capture**: screenshot of the dialog.
- **On failure**: halt.

### Step 8 — Confirm the real channel was never touched

- **Action**:
  ```sh
  gh release view ota-alpha --json assets --jq '.assets[].name'
  gh release download ota-alpha --pattern manifest.json --output -
  ```
- **Expected**: the alpha manifest's `build`, `sha256` and `published_at` are
  unchanged from before the session, and no `ota-test` artefact appears there.
- **Capture**: the alpha manifest body.
- **On failure**: halt and treat as an incident — a real user may have been
  offered a test build.

## 6. Regression Sentinels

- **Native dialogs**: no dialog fires except the ones Steps 1 and 7 expect.
- **Process health**: outside Steps 3–5, the Electron main process never exits
  unexpectedly and the backend reaches readiness on every launch.
- **Isolation**: `~/Library/Application Support/SciStudio/` (the real client's
  directory, no "Test") is never created or modified during the session. Check
  its mtime before and after.
- **Channel**: the `ota-alpha` release is never written to. Any
  `ota_publish.py` invocation without `--channel test` is a session failure.

## 7. Results (skill fills in)
