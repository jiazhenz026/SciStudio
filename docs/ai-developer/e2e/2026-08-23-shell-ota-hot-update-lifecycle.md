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

> Run this against a **packaged** build on any of the three platforms. OTA is
> cross-platform; only signing (#2096) is macOS-only. It cannot be exercised
> from a source checkout: the loader treats an unpackaged run as "never
> patched" (#1801), so `npm run dev` deliberately bypasses everything under
> test here. `electron-builder --dir` is enough — a full installer is not
> required, because `app.isPackaged` is already true for an unpacked build.

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
- **Working tree**: clean. Isolation needs no file edits — see Section 2.1.
- **Backend port**: whatever the packaged client picks; do not pin.
- **Frontend mode**: prebuilt SPA inside the snapshot. Not Vite.
- **Required tooling**: Node, and either a local static file server or `gh`
  with write access. Prefer the local server: `otaHttpGet` selects the `http`
  module for `http:` URLs, so pointing `SCISTUDIO_OTA_MANIFEST_URL` at
  `http://127.0.0.1:<port>/manifest.json` keeps the whole session off the public
  release infrastructure, where no real client can reach it even by accident.

### 2.1 Isolation — read this before launching anything

Channel isolation protects *other* users. It does **not** protect this machine,
and getting it wrong is how a test patch reaches the real client.

`evaluateUpdate` filters on `manifest.channel`, but that only governs whether a
manifest is *fetched and offered*. `getActivePatch()` and the bootstrap loader
read `userData/patches/active.json` with **no channel check at all** — they
honour whatever pointer is on disk.

**Use Electron's `--user-data-dir`.** It is the only lever that actually works,
and it changes no file:

```sh
"<app>" --user-data-dir="$HOME/scistudio-otatest-userdata"
```

> **Do not try to isolate via `build.productName`.** Verified on 2026-08-23 and
> it does **not** work: Electron derives `userData` from `app.getName()`, which
> reads the **top-level** `name`/`productName` of the packaged `package.json`.
> `build.productName` is electron-builder configuration and only renames the
> executable and installer. A build with `build.productName` set to something
> else still shares `%APPDATA%\scistudio-desktop` (and the macOS/Linux
> equivalents) with the real client **and with every `npm run dev` session in
> every worktree**.

### 2.2 Nothing else may be running

The shell holds a single-instance lock (#1867). If any other SciStudio has it —
the installed client, or an `npm run dev` session in any worktree — the test
build calls `app.quit()` immediately and **exits with code 0**, writing nothing.
That looks exactly like a clean successful run and is the easiest way to spend
an afternoon testing nothing.

Before each launch:

```sh
# macOS/Linux
pgrep -fl "electron|SciStudio" || echo "clear"
```
```powershell
# Windows
Get-CimInstance Win32_Process -Filter "Name='electron.exe' OR Name LIKE 'SciStudio%'" |
  Select-Object ProcessId, CommandLine
```

Note the command line, not just the name: on a machine running several agent
worktrees the owner of a stray process is not guessable from its PID.

A concurrent `npm run dev` also rewrites the shared `known-good.json` to
`{"build": 0}`, because an unpackaged run reports baseline build 0 (#1801). That
is pre-existing behaviour, not a fault of this session, but it will confuse the
rollback steps if a dev session is live.

## 3. Launch Plan

- **Build the test client** (once):
  ```sh
  export SCISTUDIO_OTA_CHANNEL=test
  export SCISTUDIO_OTA_MANIFEST_URL=http://127.0.0.1:8899/manifest.json
  npm --prefix desktop run build:python      # :mac / :linux on those platforms
  npm --prefix desktop run stage             # stage:sh on macOS/Linux
  npx electron-builder --dir
  ```
  On Windows add `-c.win.signAndEditExecutable=false` (or set it in the config):
  without it electron-builder tries to unpack its winCodeSign bundle and fails
  on symlink creation unless the shell is elevated.

- **Publish a patch** (repeated per step). `stage:sh` is mandatory whenever the
  backend or frontend changed: the snapshot takes `src/` from
  `desktop/resources/backend/src` (staged) but `shell/` straight from the
  repository's `desktop/` directory.
  ```sh
  npm --prefix desktop run stage:sh
  python scripts/ota_publish.py --channel test --src src --dry-run --notes "<what changed>"
  # serve the printed artifact directory on 127.0.0.1:8899, or drop --dry-run to
  # publish to the ota-test release instead
  ```

- **Reset to the bundled baseline** between steps:
  ```sh
  rm -rf "$USER_DATA_DIR/patches"
  ```

- **Cleanup** (end of session, even on failure):
  ```sh
  gh release delete ota-test --yes --cleanup-tag   # only if a release was used
  rm -rf "$USER_DATA_DIR"
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
- **Expected**: the app still starts, on the **baseline** shell.
  `$USER_DATA_DIR/logs/scistudio-desktop.log` carries
  `[scistudio][bootstrap] shell failed to load:`. Read the log file, not the
  console: a packaged app is a GUI-subsystem process with detached stdout.
- **Capture**: the bootstrap lines from the desktop log.
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
- **Capture**: `$USER_DATA_DIR/logs/scistudio-desktop.log` after each of the
  three launches, and `$USER_DATA_DIR/shell-boot-attempt.json` after launch 2
  (it must still exist and still name the broken build).
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
- **Isolation**: the real client's userData (`%APPDATA%/scistudio-desktop` on
  Windows, `~/Library/Application Support/scistudio-desktop` on macOS) is never
  modified. Record the mtimes of `patches/active.json`, `patches/known-good.json`
  and every `patches/build*/` before the session and diff them after.
- **Channel**: the `ota-alpha` release is never written to. Any
  `ota_publish.py` invocation without `--channel test` is a session failure.

## 7. Results (skill fills in)
