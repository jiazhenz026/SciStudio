---
spec_id: desktop-in-app-installer
title: "In-App Download and Install of the Next Desktop Installer"
status: Draft
feature_branch: feat/2396-in-app-installer
created: 2026-09-15
input: "Issue #2396 — a client that cannot be hot-updated any further has no way to reach the next installer from inside the app. Owner decisions 2026-09-15."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - desktop-ota-hot-update
  - desktop-shell-ota-hot-update
  - desktop-macos-signing-notarization
scope:
  in:
    - An optional `installer` field in the OTA manifest naming the next installer per platform.
    - Downloading, verifying and installing that installer from inside the app on macOS (arm64, x64), Windows (x64 NSIS) and Linux (x64 AppImage).
    - The reinstall-notice page offering the install when the shell supports it.
    - The incompatible branch of both update checks offering the install.
    - Reporting the outcome on the next launch.
    - Filling the field from a GitHub release in scripts/ota_publish.py.
  out:
    - electron-updater, Squirrel.Mac or Squirrel.Windows.
    - Installing without the user asking (no silent background install).
    - The wording of a particular release's notice page (decided at release time).
    - Publishing the 0.3.5 release or its migration patch (release actions).
    - Clients whose shell predates this spec, which cannot run any of it (section 8).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/desktop-in-app-installer.md
    - desktop/installer.js
    - desktop/main.js
    - desktop/preload.js
    - desktop/package.json
    - scripts/ota_publish.py
    - scripts/templates/reinstall-notice.html
  excludes: []
tests:
  - desktop/test/installer.test.js
  - desktop/test/bootstrap.test.js
  - desktop/test/main-orchestration.test.js
  - tests/scripts/test_ota_publish.py
acceptance_source: issue
language_source: en
---

# In-App Download and Install of the Next Desktop Installer

## 1. Change Summary

From issue #2396. [desktop-shell-ota-hot-update](desktop-shell-ota-hot-update.md)
made the Electron shell hot-updatable, which shrank "needs a reinstall" to the
Electron binary, the bundled interpreter, native dependencies and the loader.
Crossing that line still meant the user leaving the app: the native
`incompatible` dialog (text that cannot be copied) or a reinstall-notice patch
whose page asks the user to copy an address into a browser, download, and
install by hand.

Because a patched shell is ordinary JavaScript, a client that already runs the
bootstrap loader can receive a shell that downloads and installs the next
installer itself. This spec defines that shell behaviour, the manifest field it
reads, and how a release names the installer.

## 2. Owner decisions (2026-09-15)

| Decision | Choice |
|---|---|
| Platforms | macOS arm64 and x64, Windows x64, Linux x64, together |
| Consent | The download starts only when the user clicks; installing asks again in a native dialog |
| Rosetta | An x64 build running under Rosetta on Apple Silicon is moved to the arm64 installer |
| Notice copy | Only the page structure and button ship here; a release writes its own wording |
| Mechanism | Built into the shell with Node built-ins and system tools, no new npm dependency |

The mechanism follows from what can be patched: `desktop/package.json`
`dependencies` is empty and `node_modules` never rides a patch, so a library
would reach only users of a new installer. Code in `SHELL_FILES` reaches every
loader-era client and can itself be fixed by a later patch.

## 3. Manifest field

`installer` is optional. Clients that do not know it ignore it, because
`evaluateUpdate` reads only the fields it names.

```json
"installer": {
  "version": "0.3.5-beta-build0035",
  "release_page": "https://github.com/jiazhenz026/SciStudio/releases/tag/v0.3.5-beta",
  "assets": {
    "darwin-arm64": { "url": "https://…-arm64.dmg", "sha256": "<64 hex>", "size": 241623724 },
    "darwin-x64":   { "url": "https://…-x64.dmg",   "sha256": "<64 hex>", "size": 252122487 },
    "win32-x64":    { "url": "https://…Setup-….exe", "sha256": "<64 hex>", "size": 237318433 },
    "linux-x64":    { "url": "https://….AppImage",  "sha256": "<64 hex>", "size": 338845750 }
  }
}
```

`installer.evaluateInstallerOffer` offers it when all of these hold:

- `version` parses as a SciStudio version;
- it is newer than what runs: a higher base, or the same base above the effective build;
- this machine has a platform key (section 4) and the field names an asset for it;
- the asset URL is `https`, its `sha256` is 64 hex digits, and its `size` is a positive integer.

The channel is not compared, since moving a user from alpha to beta is one of
the things an installer is for. A `release_page` that is not `https` is dropped
and the offer is kept.

## 4. Platform key

| Running build | Key |
|---|---|
| macOS arm64 | `darwin-arm64` |
| macOS x64 | `darwin-x64` |
| macOS x64 under Rosetta (`app.runningUnderARM64Translation`) | `darwin-arm64` |
| Windows x64, including under ARM64 emulation | `win32-x64` |
| Linux x64 | `linux-x64` |
| anything else | none, so no offer |

## 5. Flow

1. **Offer.** `resolveInstallerOffer` fetches the manifest from the channel's
   manifest URL and evaluates the offer. It then resolves the install target
   (section 6) and decides `canInstall`. A dev (unpackaged) run, an unsupported
   target, or a folder the user cannot write to all give `canInstall: false`
   with a reason. In those cases the user is sent to the release page instead.
2. **Download.** Only after a click. The file goes to
   `userData/installer/<asset name>.partial` and is streamed with progress
   reports. Its size and sha256 are checked against the manifest before it is
   renamed into place. A file already there that passes the check is reused.
   Concurrent requests for the same installer share one download.
3. **Confirm.** The install request uses the offer whose file was downloaded
   and verified in this run. It does not read the manifest again, so an install
   still works offline after the download, and a manifest that changed in the
   meantime cannot swap in a different asset. A native dialog says the app will quit, install and open again,
   and that projects and settings are kept. Cancel keeps the download.
4. **Hand over.** Main writes `userData/installer/pending.json`
   (`{version, releasePage, startedAt}`) and the platform helper script. It
   starts the helper detached and calls `app.quit()`. The ordinary quit path
   (#2327) then stops the backend gracefully.
5. **Install.** The helper waits up to 180 s for the app's process to exit,
   installs, writes `userData/installer/result.json` (`{ok, stage}`), and opens
   the app: the new one on success, the old one on failure.
6. **Report.** On the next launch `reportInstallOutcome` reads both files. It
   runs right after the launch mode is settled and **before** the mandatory
   update check. A failed migration reopens the old app on the same mandatory
   manifest, and enforcing that first would send the user straight back into
   the installer prompt without saying why the last attempt failed.
   Success is judged by the version now running. A helper that reported `ok` on
   an app still at the old version counts as a failure at stage `verify`. A
   failure shows a dialog naming the stage, with "Open download page". A pending
   install with no result is left alone for 10 minutes, because the helper may
   still be running.

The two files are a contract across versions. On success the reader is the
**new** installer's shell, so their shape must not change incompatibly.

## 6. Install targets and helpers

`installer.resolveInstallTarget` judges the target from `process.execPath`, and
`desktop/installer.js` writes each helper as a string. The macOS and Linux
helpers run for real in the tests against fake tools.

### 6.1 macOS: replace the `.app`

The target is the `.app` that contains the executable. Three cases are refused:

- a path under `/Volumes/`, meaning the app is running from the disk image;
- a path under `/AppTranslocation/`, meaning Gatekeeper translocation, where replacing would not touch the user's copy;
- a bare binary.

The helper runs these steps:

1. Mount the dmg read-only and without Finder (`hdiutil attach -nobrowse -readonly -noautoopen`).
2. `ditto` the new app to a hidden sibling of the installed one, then detach.
3. Swap with two renames: installed to backup, then new to installed. If the second rename fails, the backup is put back.
4. Delete the backup and the dmg, then `open` the app.

Renames within one folder are atomic, so at every moment one complete app sits
at the installed path. `ditto` keeps the signature and stapled ticket. A file
downloaded by Node carries no quarantine attribute, so Gatekeeper does not
re-prompt.

### 6.2 Windows: run NSIS silently

The target folder is the executable's folder. The helper is PowerShell. It
waits for the pid, then runs
`installer.exe /S --updated --force-run /D=<install dir>`:

- `/S` makes the install silent;
- `--updated` and `--force-run` are electron-builder's update flags, and `--force-run` starts the app afterwards;
- `/D=` must be the last argument, and it takes the rest of the line verbatim.

The installer is per-user (`nsis.perMachine: false`), so no elevation is
needed. A non-zero exit code is a failure, and the helper then starts the old
executable. The result file is written with `WriteAllText`, which adds no byte
order mark, because `JSON.parse` rejects one.

### 6.3 Linux: replace the AppImage

The target is `$APPIMAGE`. When it is unset, the app is not running from an
AppImage and the target is refused. The helper runs these steps:

1. Copy the download next to the target.
2. `chmod 755` the copy.
3. `mv -f` it over the target path, then start it.

The path keeps its old file name, so desktop entries and launchers keep working.
Because of that, the name can mention the older version.

## 7. Surfaces

- **Reinstall notice** (`scripts/templates/reinstall-notice.html`): the page
  feature-detects `window.scistudioDesktop.installer`.
  - When the bridge is there and `canInstall` is true, the page shows
    "Download and install SciStudio X (N MB)" with a progress bar and hides the
    copy-address flow.
  - When `canInstall` is false, it shows "Open download page" and the copy flow.
  - When the bridge is missing, which is any shell older than this spec, the page is
    unchanged.
- **Incompatible branch** of `maybeEnforceMandatoryUpdate` (pre-window, where the
  splash shows the progress) and of `maybeCheckForUpdate` (post-window, where the
  taskbar or dock progress bar shows it). When an installer is on offer, the
  native dialog offers "Download and install", "Open download page", and
  "Quit" (mandatory) or "Later" (optional). Without an offer the existing dialog
  is unchanged.
- **Preload bridge** `scistudioDesktop.installer`: `getOffer`, `download`,
  `install`, `openReleasePage`, `onProgress`. The page only asks. Main owns the
  manifest, the file, the dialog and the spawn. A page cannot choose a URL, a
  path or a script, and it cannot install without the native confirmation.

## 8. Rollout: which clients can use it

| Client | Shell | What it gets |
|---|---|---|
| 0.3.3 | frozen `main.js`, no loader | reinstall notice with copy-address only |
| 0.3.4 and later | loader; runs the patch's shell | the notice's Download and install button, and the incompatible dialog's offer, once a patch carrying this shell is applied |

A migration therefore works in two steps. The mandatory notice patch, published
with `--min-base` at or below the oldest client base, carries this shell. The
0.3.4 client applies it and relaunches into the new shell, and the notice page
it serves then offers the install. The same patch shows 0.3.3 clients the
copy-address page.

Publish the patch with `--installer-release <tag>` so the manifest names the
installer (section 9). The release runbook's ordering rule applies unchanged:
the installer assets must be public and downloadable before the manifest that
names them is published.

## 9. Publishing

`scripts/ota_publish.py --installer-release <tag>` reads
`gh api repos/<repo>/releases/tags/<tag>` and builds the field with
`installer_from_release`. Assets are matched by the file names the build
workflows publish:

| Key | Asset name |
|---|---|
| `darwin-arm64` | `SciStudio-<version>-arm64.dmg` |
| `darwin-x64` | `SciStudio-<version>-x64.dmg` |
| `win32-x64` | `SciStudio-Setup-<version>.exe` (also `SciStudio Setup <version>.exe` and `SciStudio.Setup.<version>.exe`) |
| `linux-x64` | `SciStudio-<version>.AppImage` (also with `-x86_64`) |

electron-builder's default NSIS name is `${productName} Setup ${version}.exe`.
GitHub turns the spaces into dots on upload. Past releases were renamed by hand.
`desktop/package.json` now pins `nsis.artifactName` to the hyphenated form, and
the publisher still accepts both older spellings. A test expands the
`artifactName` patterns in `desktop/package.json` and checks that each one lands
on its own key.

The URL, the size and GitHub's `sha256:` asset digest go into the field, so
nothing is downloaded while publishing. The publish stops when any of these
holds:

- the release is a draft;
- a platform has no asset or has more than one;
- an asset has no digest;
- the assets disagree on the version.

A test pins the key set to `PLATFORM_KEYS` in `desktop/installer.js`.

`installer.js` is listed in `SHELL_FILES` and in `build.files`. The existing
tests keep those two lists and the relative requires in step.

## 10. Verification

Automated:

- `desktop/test/installer.test.js` covers these cases:
  - every platform key, including Rosetta;
  - every offer and refusal reason;
  - every install-target kind and refusal;
  - quoting of paths with spaces and quotes;
  - the macOS helper run for real against a fake `hdiutil`, `ditto` and `open`: a successful swap, a dmg with no app, a failed copy that leaves no half-copied app, and waiting for a live process;
  - the Linux helper run for real: replace, and a missing download;
  - the Windows script's arguments, quoting and BOM-free result;
  - every outcome branch.
- `tests/scripts/test_ota_publish.py` covers `installer_from_release`: the
  mapping, draft, missing platform, missing digest and version disagreement. It
  also checks the key-set pin, the field in `build_manifest`, and `main()`
  wiring, including an incomplete release stopping the publish before any
  upload.

Manual, owner-executed before the migration patch is published (not yet run):

- On a packaged macOS arm64 build, with a local manifest naming a newer dmg:
  - download, confirm, quit, swap and reopen into the new version;
  - a dmg with a bad digest is refused before the dialog.
- The same flow on an x64 build under Rosetta, which lands on arm64.
- A packaged Windows build installs silently into its current folder and reopens.
- A Linux AppImage replaces itself and reopens.
- A failure (for example a read-only folder) shows the stage dialog on the next launch.

## 11. Assumptions

- electron-builder's NSIS installer accepts `/S`, `--updated`, `--force-run`
  and a final `/D=`. It closes nothing that is still running, which is why the
  helper waits for the pid first. Source: electron-builder's NSIS templates, as
  used by its own `NsisUpdater`; to be confirmed by the manual Windows run.
- A detached child spawned by Node on Windows is not placed in the kill-on-close
  job object that non-detached children get, so the helper outlives the app.
  Source: libuv `uv_spawn`; to be confirmed by the manual Windows run.
- GitHub's asset `digest` is the sha256 of the served bytes. Source: GitHub
  REST API release asset schema.
