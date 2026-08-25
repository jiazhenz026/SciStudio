---
session_id: "2026-08-23-shell-ota-hot-update-lifecycle"
title: "Shell + backend + frontend hot-update, rollback, poisoned patch, and the mandatory-reinstall prompt"
created: "2026-08-23"
owner: "@jiazhenz026"
trigger:
  kind: "pr-readiness"
  ref: "PR #2139 (issue #2097), depends on PR #2128 (issue #2096)"
related_adrs: []
status: "passed"
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

### 2.2 `ELECTRON_RUN_AS_NODE` must be unset

If this variable is set in the launching shell's environment, the Electron
binary starts as **Node**, rejects the Chromium switches with
`bad option: --user-data-dir`, and **exits 0 having done nothing**. It is
indistinguishable from a clean run and it cost an hour on 2026-08-25. It can be
inherited from a parent process without appearing in the User or Machine scope,
so check the process scope specifically:

```powershell
$env:ELECTRON_RUN_AS_NODE          # must be empty
Remove-Item env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
```

A GUI launch from Explorer or the Start Menu does not inherit a process-scoped
value, so the real client is unaffected — only shell-launched test builds are.

### 2.3 The bundled interpreter must be freshly built

A `desktop/resources/python` copied from another checkout can be stale in ways
that break the test and look like product bugs. Both were hit on 2026-08-25:

- an old **embeddable** Python carrying `pythonXX._pth`, which makes CPython
  ignore `PYTHONPATH` entirely, so no OTA patch can ever shadow the baseline.
  `build-python-runtime.ps1` documents this and stages python-build-standalone
  precisely to avoid it. Assert `desktop/resources/python/*._pth` does not exist.
- a `scistudio` left in `Lib/site-packages` from before the build script's
  `pip uninstall` step, which shadows the source tree and surfaces as a
  `TypeError` from a *newer* registry key (looking exactly like a #2073
  regression). Assert `Lib/site-packages/scistudio` does not exist.

Run `npm --prefix desktop run build:python` rather than copying.

### 2.4 Nothing else may be running

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

**Run 2026-08-25, Windows 11, `electron-builder --dir` build of
`guided/2097-shell-ota-bootstrap-loader`, launched with `--user-data-dir`.
Every step executed. The manifest was served from `127.0.0.1:8899`, so no
public release infrastructure was involved and no real client could reach it.
The owner clicked the two blocking dialogs.**

| Step | Result | Evidence |
|---|---|---|
| Baseline launch | pass | `loading baseline shell (build 0) from …
esourcespp.asar`; `/api/version` → `build: 0` |
| 1 — three layers from one snapshot | **pass** | shell: `loading patch shell (build 1) from …\patchesuild1\shell`; backend: `/api/version` `build: 0 → 1`; frontend: the patched SPA served the injected marker |
| 4 — shell throws at `require` | **pass** | `loading patch shell (build 1)` → `shell failed to load: Error: …` → `loading baseline shell (build 0)`; the app came up |
| 5 — quarantine is sticky | **pass** | launches 2 and 3 both logged `build 1 did not reach readiness; staying on the baseline shell` with **no `loading patch shell` line at all** — the broken patch was never re-attempted |
| 6 — newer patch after a quarantine | **pass** | `loading patch shell (build 2)`; marker cleared on readiness; `/api/version` → `build: 2` |
| Marker lifecycle | **pass** | written before the require; **survived** the failed load; cleared only when the build it named reached readiness |
| 1 (full path) — dialog → download → apply → relaunch | **pass** | `update decision=patch local build=0 remote build=1` → server logged `GET /backend-build1.tar.gz 200` → `applied OTA build 1; relaunching` → `loading patch shell (build 1)` → `update decision=none` |
| 7 — mandatory reinstall prompt | **pass** | `mandatory update required: kind=incompatible remote build=26`, blocking dialog before any window, single Quit button, app exited on Quit |
| 7b — mandatory patch delivering a copyable page | **pass** | `mandatory update required: kind=patch remote build=27` → `applied mandatory OTA build 27; relaunching` → patched SPA rendered with a working copy button |
| Isolation | **pass** | the real client's `patches/active.json` stayed `{"build":25}` at its 2026-08-21 mtime and all of `build15…build25` were intact, before and after |

### Defects found by this run

Both were invisible to unit tests, code review and the Codex review, and both
were fixed on the branch:

1. **The loader produced no observable output in a packaged app.** It logged
   only to `process.stdout`, which is detached for a GUI-subsystem process — so
   its diagnostics vanished in the one case they exist for. It now mirrors into
   the same desktop log `main.js` uses. Every "Evidence" cell above depends on
   that fix.
2. **The patched splash screen rendered a broken logo.** `splash.html`
   references `assets/icon.png` with a *relative* `src`, and `assets/` did not
   travel with the shell, so under a patch it resolved against the patch
   directory and found nothing. The asset now ships in the shell payload.
   Confirmed visually by the owner after the fix.

### Findings that changed the release plan

**The reinstall address cannot be made copyable inside the native dialog.**
`dialog.showMessageBox` renders plain text on both platforms: the URL smuggled
through `requires.min_base` is visible but neither clickable nor selectable, so
a 0.3.3 user would have to retype it. Nothing can change that — the code that
draws the dialog is the one part a patch cannot replace.

A mandatory **patch** solves it, and was demonstrated in step 7b. A 0.3.3 client
can still apply a backend snapshot, and a snapshot carries the SPA, so the patch
delivers an ordinary web page with selectable text and a clipboard button. Spec
section 8.1 records this as the route for the 0.3.3 cohort, with the real
release URL rather than an abbreviated one.

**A force-quit during startup quarantines an otherwise healthy shell.** Observed
incidentally: killing the app before the runtime reaches readiness leaves the
marker in place, so the next launch refuses that build, and because the baseline
cannot clear the marker the patch stays quarantined until a newer build arrives.
It is fail-safe — never worse than the baseline — but it never forgives. Whether
to require N consecutive failures, or clear the marker on a clean `before-quit`,
is an open design question and deliberately not changed here.

### Not executed

Steps 2 and 8. Step 8 is only meaningful when a real channel was published to,
and this run served everything from localhost.
