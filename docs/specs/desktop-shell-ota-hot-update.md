---
spec_id: desktop-shell-ota-hot-update
title: "Electron Shell Hot-Update via a Frozen Bootstrap Loader"
status: Draft
feature_branch: guided/2097-shell-ota-bootstrap-loader
created: 2026-08-23
input: "Issue #2097 — every change to the Electron shell JS requires a full installer download. Owner-directed guided session 2026-08-22/23."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - desktop-ota-hot-update
  - desktop-package-ota-hot-update
  - desktop-macos-signing-notarization
scope:
  in:
    - A frozen bootstrap loader that chooses between the bundled shell and a patched one.
    - Carrying the Electron shell inside the existing core OTA snapshot, under shell/.
    - Host facts injected into the shell to replace what __dirname can no longer answer.
    - An on-disk crash-loop guard, because a bad shell kills the main process.
    - Publishing the shell from scripts/ota_publish.py.
  out:
    - Any change to the manifest schema, the channel model, or the build numbering.
    - Any change to the eight existing pure decision functions in desktop/ota.js.
    - electron-updater integration.
    - Hot-update of the Electron binary, the bundled interpreter, native dependencies, or the loader itself.
    - The 0.3.4 version bump (a release action; see section 8).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/desktop-shell-ota-hot-update.md
    - desktop/bootstrap.js
    - desktop/main.js
    - desktop/ota.js
    - desktop/package.json
    - scripts/ota_publish.py
    - scripts/templates/reinstall-notice.html
  excludes: []
tests:
  - desktop/test/bootstrap.test.js
  - desktop/test/ota.test.js
  - tests/scripts/test_ota_publish.py
acceptance_source: issue
language_source: en
---

# Electron Shell Hot-Update via a Frozen Bootstrap Loader

## 1. Change Summary

From issue #2097. [desktop-ota-hot-update](desktop-ota-hot-update.md) excluded
"OTA of the Electron JS shell" from scope, so every change to `main.js`,
`preload.js`, `ota.js`, `runtime-port.js` or `splash.html` required a full
installer download. The CHANGELOG entry for #1805 records the cost plainly: a
one-line dialog wording fix was "Shell-only — reaches users via a new installer,
not OTA."

The shell is ordinary JavaScript executed by the Electron binary, and is as
hot-updatable as the backend source tree already is. This spec makes it so.

| Layer | Hot-updatable? | Mechanism |
|---|---|---|
| Backend source (`src/`) | Yes | OTA snapshot (unchanged) |
| Frontend SPA (inside the backend tree) | Yes | rides in the same snapshot (unchanged) |
| **Electron shell JS (`shell/`)** | **Yes** | **rides in the same snapshot (this spec)** |
| Electron/Chromium binary, Python interpreter, native deps, **the loader** | No | new installer |

"Requires a reinstall" shrinks from *any JS change* to *Electron, interpreter,
native dependency, or loader changes only*.

## 2. One snapshot, not a second manifest

The shell is packed into the **existing** core snapshot as a `shell/` directory
beside `src/`, sharing one manifest, one build number and one publish path.

Splitting them would create a shell-42-plus-backend-39 compatibility matrix to
reason about at every launch. Coupling them makes a build mean, atomically, *all
of this app's interpreted code*. Shell and backend are released together anyway.

The accepted cost: shipping a shell-only fix republishes the backend snapshot
too.

Nothing in the manifest schema, the channel model, the build numbering, or the
eight pure decision functions in `desktop/ota.js` changes. Four new pure
functions are added (sections 3 and 5).

## 3. The loader is the frozen part

`desktop/bootstrap.js` becomes the asar entry point (`package.json` `main`). It
is the one piece that still needs an installer to change, so it stays small and
dependency-light, and its contract is fixed at first release.

```
resolve which shell to run  (ota.resolveShellSource)
  -> refuse a patch whose marker says it never booted  (ota.shellBootRefused)
  -> record the boot attempt          BEFORE requiring anything
  -> require(<shell>/main.js).start(hostFacts)
  -> on throw: fall back to the baseline shell, then quit if that fails too
```

Two deliberate constraints:

**The baseline shell is the copy already inside the asar.** Nothing extra is
staged. It is signed, read-only, and impossible for a patch to corrupt, and it
means the staging scripts need no changes at all. In a source checkout the same
rule reads as "next to `bootstrap.js`", so a `npm run dev` run always uses the
worktree — the #1801 source-of-truth rule, extended to the shell.

**The loader requires `./ota` from the asar, never from the shell.** The loader
decides *which* shell is trustworthy, so it must not execute code from a shell
to make that decision. A patch carries its own `ota.js` for its own use and the
two may diverge; the asar copy is the frozen one that governs load decisions.

## 4. Host facts — what `__dirname` stopped answering

Once `main.js` runs from a patch directory, `__dirname` no longer points into
the app bundle. Four resolvers had to move onto facts the loader supplies:

| `desktop/main.js` | Was | Now |
|---|---|---|
| `baselineVersion()` | `require("./package.json").version` | `host().baselineVersion` |
| `resourcesDir()` | `path.join(__dirname, "resources")` | `host().resourcesPath` |
| `repoRoot()` | `path.resolve(__dirname, "..")` | `host().repoRoot` |
| `appIconPath()` | `__dirname/assets/icon.png` | `host().appRoot/assets/icon.png` |

`splash.html` and `preload.js` keep resolving against `__dirname`: they travel
*with* the shell. `webPreferences.preload` accepts any absolute path, including
one under `userData`.

### 4.1 Why `baselineVersion` is the dangerous one

`ota.resolveActivePatch(pointer, baselineBuild, srcExists)` decides staleness by
comparing the **installed baseline** against the **patch** build. If
`baselineVersion()` read `./package.json` from inside a patch, the patch would
be compared against itself, `resolveActivePatch` would never return `stale`, and
the #1787 protection would stop working silently — a leftover patch would shadow
a freshly installed build forever, with nothing failing loudly.

`desktop/test/bootstrap.test.js` asserts `main.js` contains no
`require("./package.json")`.

### 4.2 `start()` rather than a restructure

`main.js` keeps its module-scope work (the single-instance lock, the pipe
guards, the `process.on("exit")` reaper) — none of it needs host facts. Only the
lifecycle registrations do, so they moved into an exported `start(host)` that the
loader calls immediately after `require`. The `whenReady` handler still checks
the single-instance lock exactly as before.

## 5. Crash-loop guard

The backend's rollback works because Electron survives a bad backend patch and
can still show a dialog. **A bad shell patch kills the main process**, so nothing
is left running to recover, and the guard has to be on disk.

`userData/shell-boot-attempt.json` names the shell build the loader is about to
require. It is written **before** the `require` and cleared only when the runtime
reaches HTTP readiness — from `recordKnownGood()`, which already marks the
backend patch good at exactly that point. A marker still naming the candidate
means the previous attempt at that build died before readiness, so it is refused
in favour of the baseline.

Only a patch is ever refused. The baseline is the fallback itself; refusing it
would turn one bad patch into an unstartable app.

**The refusal is sticky, and that is the whole point.** `active.json` still
points at the broken build after the fallback, so a loader that deleted the
marker on its way to the baseline would re-select the same shell on the next
launch: the app would alternate between crashing and working forever instead of
settling. The marker therefore survives both the refusal and a failed `require`,
and it is cleared only when

- the patch the marker names reaches readiness (it was fine after all), or
- a **different** build becomes the candidate — a newer patch overwrites the
  marker, and a baseline that supersedes the patch (#1787) clears it outright,
  so a reinstall is a fresh start and the quarantine never becomes a permanent
  refusal of all future updates.

The second door matters as much as the first: the baseline reaches readiness too
and calls `recordKnownGood()`, so the host's `clearBootAttempt` is guarded by
`mayClearShellMarker` and does nothing unless the shell that came up *is* the
patch the marker names.

Four new pure functions in `desktop/ota.js` carry these decisions, matching the
module's existing "no Electron, no filesystem, unit tested directly" contract:

- `resolveShellSource({isPackaged, pointer, baselineBuild, patchShellExists})`
- `shellBootRefused(marker, candidate)`
- `shellMarkerAction(marker, candidate)` — record / keep / clear
- `mayClearShellMarker(shell)`

## 6. Snapshot layout and publishing

`scripts/ota_publish.py` packs `shell/` alongside `src/` from the repository's
`desktop/` directory:

```
backend-build<N>.tar.gz
  src/scistudio/...        backend + embedded SPA   (unchanged)
  shell/main.js
  shell/ota.js
  shell/runtime-port.js
  shell/preload.js
  shell/splash.html
```

`bootstrap.js` is **never** published: it is the loader, it lives in the asar,
and a patch able to replace it could disable its own rollback. `package.json` is
never published either — the loader supplies the baseline version, and a manifest
inside the patch would be the patch describing itself (section 4.1).

`shell_sources()` fails the publish when a listed file is missing, because a
`shell/` without `main.js` fails the client's existence check and silently falls
back to the baseline for every user. A test also asserts the published list and
the asar's `build.files` cannot drift apart.

## 7. Mixed states are expected

A snapshot published **before** this change has `src/` but no `shell/`. The
client applies it, serves the backend from the patch, finds no patch shell, and
runs the baseline shell. That combination is supported, not an error — it is what
every already-published build looks like to a 0.3.4 client.

## 8. Release requirement for 0.3.4

`desktop/package.json` is `0.3.3-alpha-build0000`, which `VERSION_RE` parses to
baseline build **0**, and `resolveActivePatch` only discards a patch when
`baselineBuild >= pointer.build`.

If 0.3.4 ships as `0.3.4-alpha-build0000`, an existing user's applied build-42
patch stays **active** after installing 0.3.4 — shadowing the new backend with
old code, and carrying no `shell/` at all.

**The 0.3.4 installer must therefore be stamped `0.3.4-alpha-buildNNNN` with
NNNN at least the highest build published on the channel.** The live alpha
manifest was build 25 on 2026-08-21; re-check `gh release view ota-alpha` at
release time. The release workflow already stamps this from its `build_number`
input, so this is a release-procedure requirement, not a code change — which is
why the version bump is out of scope here.

The rollout order is equally load-bearing: publish the 0.3.4 installer and
confirm it downloads *before* publishing a mandatory manifest. Reversed, every
0.3.3 client is blocked with no way forward, because the incompatible branch
offers only a "Quit" button.

### 8.1 How the 0.3.3 cohort is told to reinstall

0.3.3 clients need one manual download, because the bootstrap loader ships in
the asar. The obvious route — a mandatory **incompatible** manifest — produces
the frozen 0.3.3 dialog, and a native `dialog.showMessageBox` renders plain
text: the download address is neither clickable nor **selectable**, so the user
has to retype it. Verified on 2026-08-25; there is no way to change that dialog,
since the code that draws it is the one part a patch cannot replace.

Use a mandatory **patch** instead (owner decision, 2026-08-25). A 0.3.3 client
can still apply a backend snapshot, and a snapshot carries the SPA, so the patch
can deliver an ordinary web page — where text selects, a link clicks, and a
button can call `navigator.clipboard.writeText()`. The native dialog then only
has to say "click Update now", which it already does through `manifest.notes`.

For this the manifest must satisfy `min_base <= 0.3.3` so the decision is
`patch` rather than `incompatible`, with `min_build` set to make it mandatory.

Because the address is copyable, it does not need to be short: use the real
0.3.4 release URL rather than an abbreviation.

This composes with the build-number rule above: once the user installs 0.3.4,
its baseline build is at least that of the notice patch, so `resolveActivePatch`
discards it (#1787) and the dead-end page cannot outlive the migration.

Verified end to end on 2026-08-25 — `mandatory update required: kind=patch`,
`applied mandatory OTA build 27; relaunching`, then the patched page rendered
with a working copy button.

## 8.2 About reports the build that is running

Electron's default menu shows `app.getVersion()` — the version compiled into
the packaged `package.json`, i.e. the **installer baseline** — and offers no
About item at all on Windows or Linux. For an app whose premise is that the
running build can differ from the installed one, reporting the baseline is
wrong by construction.

`desktop/main.js` therefore installs its own menu. About reports the **effective
build**, and names the installed baseline separately whenever the two differ:

```
Version 0.3.4.0026
Installed 0.3.4.0000, updated without reinstalling
```

That second line is the pair a support conversation actually needs — "which
build are you on" and "which one did you install" are different questions once
patches exist.

Replacing the default menu means the standard roles (`editMenu`, `viewMenu`,
`windowMenu`) must be restored explicitly, or copy/paste and the developer tools
lose their accelerators. A test asserts they are present.

The licence and copyright shown there are duplicated into the shell out of
necessity: a native dialog cannot read `LICENSE` at runtime from inside a
patched asar. A test pins the two constants to the repository `LICENSE` and
`pyproject.toml` so they cannot drift silently — About is not a surface anyone
checks.

## 9. Verification

Automated, any platform:

- `desktop/test/ota.test.js` — every `resolveShellSource` branch (dev checkout,
  no pointer, newer patch, a patch with no `shell/`, a patch at or below the
  baseline) and every `shellBootRefused` branch, including that the baseline can
  never be refused.
- `desktop/test/bootstrap.test.js` — the loader is the asar entry point; the
  asar carries a complete baseline shell; `main.js` exports `start`; `main.js`
  never reads `./package.json`; the bundle-relative resolvers go through the
  host while `splash.html`/`preload.js` stay `__dirname`-relative; the loader
  requires nothing from a shell; the boot marker is written before the require
  and cleared only from `recordKnownGood`.
- `tests/scripts/test_ota_publish.py` — the snapshot carries `shell/`, never the
  loader, never a shell manifest; an incomplete shell fails the publish; the
  published list and the asar's `build.files` cannot drift.

Executed 2026-08-25 on a packaged Windows build, recorded in
[docs/ai-developer/e2e/2026-08-23-shell-ota-hot-update-lifecycle.md](../ai-developer/e2e/2026-08-23-shell-ota-hot-update-lifecycle.md).
All of the following passed except the two dialog-driven steps, which block on a
human click and remain owner-executed:

- A shell-only change published as a build is applied by an installed client and
  takes effect after relaunch, with no installer download.
- A deliberately broken shell patch is rolled back to the baseline on the next
  launch rather than producing a crash loop.
- A patch tarball with no `shell/` runs the baseline shell while its `src/`
  still serves the backend (section 7).
- Installing a build over an older applied patch discards that patch, for both
  `src/` and `shell/`.
- `npm run dev` from a source checkout still resolves to the worktree.

## 10. Assumptions

- Electron fuses stay unset, so the main process may `require` shell code from
  outside the asar. Enabling `onlyLoadAppFromAsar` or
  `enableEmbeddedAsarIntegrityValidation` would break this design; that
  constraint is recorded and tested in
  [desktop-macos-signing-notarization](desktop-macos-signing-notarization.md)
  (source: verified in `app-builder-lib`).
- Code signing does not restrict loading interpreted JavaScript from `userData`;
  only Mach-O loading is subject to library validation (source: inferred, and
  the reason that spec carries `disable-library-validation`).
- The loader contract is fixed once released: changing it requires a new
  installer (source: design consequence).
