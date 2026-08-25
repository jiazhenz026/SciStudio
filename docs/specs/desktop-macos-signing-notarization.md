---
spec_id: desktop-macos-signing-notarization
title: "Signed And Notarized macOS Desktop Build"
status: Draft
feature_branch: guided/2096-macos-signing-notarization
created: 2026-08-21
input: "Issue #2096 — the unsigned macOS dmg forces every user through a Gatekeeper override before the app will launch. Owner joined the Apple Developer Program. Owner-directed guided session 2026-08-21."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - desktop-ota-hot-update
  - desktop-package-ota-hot-update
scope:
  in:
    - Developer ID signing, hardened runtime, notarization and stapling for the macOS dmg.
    - An explicit entitlements file used for both the app and its nested binaries.
    - Pruning files that break the codesign pass from the bundled interpreter and the staged backend tree.
    - A build-configuration test suite that runs on any platform, wired into CI.
    - CI-side signing, notarization, and a hard post-build verification step.
    - The release credential procedure.
  out:
    - Windows code signing (a separate certificate; the Apple Developer Program does not cover it).
    - electron-updater integration (deferred; see section 8).
    - Electron shell hot-update (issue #2097).
    - Mac App Store (mas) distribution.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/desktop-macos-signing-notarization.md
    - desktop/package.json
    - desktop/assets/entitlements.mac.plist
    - desktop/scripts/build-python-runtime-macos.sh
    - desktop/scripts/stage-resources.sh
    - desktop/scripts/stage-resources.ps1
    - .github/workflows/desktop-macos-dmg.yml
    - .github/workflows/ci.yml
  excludes: []
tests:
  - desktop/test/macos-signing.test.js
  - tests/qa/test_workflow_expressions.py
acceptance_source: issue
language_source: en
---

# Signed And Notarized macOS Desktop Build

## 1. Change Summary

From issue #2096. The macOS build shipped unsigned: `hardenedRuntime: false`, no
entitlements, no notarization. Every user who downloaded the dmg was stopped by
Gatekeeper — "SciStudio can't be opened because Apple cannot check it for
malicious software" — and had to right-click then Open, or approve the app under
System Settings, Privacy and Security.

With a Developer ID Application certificate now available, the build signs,
hardens, notarizes and staples, so a clean machine launches the app by
double-clicking it.

The change is mostly build configuration. The one part with runtime consequences
is the entitlements file, because the hardened runtime constrains what the
bundled interpreter is allowed to load — which is exactly what package OTA
(#1784) depends on. Section 3 covers that.

## 2. What removing the Gatekeeper prompt actually requires

All four steps are necessary. Signing alone does not remove the prompt.

| Step | Setting | Why |
|---|---|---|
| Developer ID signature | `mac.identity` (auto-detected from the keychain) | Must be a **Developer ID Application** certificate — not "Apple Development", not a Mac App Store certificate |
| Hardened runtime | `mac.hardenedRuntime: true` | Apple refuses to notarize without it |
| Notarization | the `Desktop macOS DMG` workflow submits; `mac.notarize` is deliberately `false` | electron-builder's native path waits on Apple inside the build, which has no upper bound; see section 6.5 |
| Stapling | the `Desktop macOS Staple` workflow, once Apple returns a verdict | Without a stapled ticket the **first launch needs network access** to reach Apple, so an offline first run still prompts |

`mac.gatekeeperAssess` stays `false`. It controls a local `spctl` assessment
electron-builder runs on the build machine; it does not affect what ships, and
leaving it off avoids build-machine flakiness.

## 3. Entitlements

`desktop/assets/entitlements.mac.plist` is used for **both** `mac.entitlements`
and `mac.entitlementsInherit`.

| Key | Why |
|---|---|
| `com.apple.security.cs.allow-jit` | V8 needs writable-executable memory; Electron crashes on launch without it under the hardened runtime |
| `com.apple.security.cs.allow-unsigned-executable-memory` | Same |
| `com.apple.security.cs.disable-library-validation` | Load-bearing for package OTA — see below |

### 3.1 Why disable-library-validation is load-bearing

Under the hardened runtime, library validation refuses to load any dylib not
signed by the same Team ID as the loading process.

Package OTA ([desktop-package-ota-hot-update](desktop-package-ota-hot-update.md))
downloads packages into `userData` **after** the bundle was signed and lets the
bundled interpreter import them. Any package carrying a compiled extension
(`.so`) will therefore be loading code that can never bear our signature.

Removing this key does not fail the build and does not fail notarization. It
breaks package OTA at runtime, and the failure surfaces as a Python
`ImportError` rather than a code-signing error, which makes it expensive to
diagnose. This is a deliberate, recorded weakening of the hardened runtime, not
an oversight: the app's whole plugin model is loading third-party code the user
chose to install.

### 3.2 Why entitlementsInherit matters as much as entitlements

The bundled interpreter is spawned as a **separate process**
(`desktop/main.js` `spawnRuntimeCandidate`), so it is that process's own
signature and entitlements — not the Electron app's — that govern whether its
`dlopen` calls are allowed.

In `app-builder-lib`'s `macPackager.getOptionsForFile`, only the root app path
receives `mac.entitlements`; every nested binary, the bundled `python3`
included, receives `mac.entitlementsInherit`. Pointing both at the same file is
what actually puts `disable-library-validation` on the process that performs the
`dlopen`. `desktop/test/macos-signing.test.js` asserts the two do not drift
apart.

### 3.3 Not inherited from the vendor default

electron-builder's bundled fallback template happens to contain the same three
keys today. This spec pins them in-repo anyway: a security-relevant property
that package OTA depends on should not be an implicit vendor default that a
dependency bump can change silently.

## 4. Signing surface and the prune

`@electron/osx-sign` walks `Contents/` — which includes `Contents/Resources/`,
where `extraResources` places the bundled interpreter and the staged backend
tree — and hands `codesign` every file its `isBinaryFile` check flags.

That is mostly good news: the hundreds of `.so` files in the interpreter's
`site-packages` are signed automatically rather than by hand.

But `isbinaryfile` sniffs for null bytes; it does not parse Mach-O headers. So
it also flags files that `codesign` cannot sign, and one failure fails the
build. Two categories are removed before staging:

| Removed | Where | Safe because |
|---|---|---|
| `__pycache__` / `.pyc` | bundled interpreter, staged backend tree | pure cache; CPython runs without it. `scripts/ota_publish.py` already excludes them from the OTA snapshot, so this also makes the installer consistent with the patch payload |
| stdlib `lib/python*/test` | bundled interpreter | nothing SciStudio ships imports the stdlib `test` package; it carries binary fixtures (pickles, archives) purely for CPython's own test suite |

The dependency verification in `build-python-runtime-macos.sh` runs **after** the
prune, so a mistake fails that build rather than the signing run.

If a signing run still fails on an unsignable file, the next lever is a
`signIgnore` entry for the specific path. Prefer that over broadening the prune.

Signing several hundred files is slow; budget 10 to 30 minutes per build.

## 5. Electron fuses stay unset

`build.electronFuses` must remain absent.

Verified in `app-builder-lib/out/platformPackager.js` (`doAddElectronFuses`):
fuses are entirely opt-in — with no configuration, none are flipped. **Signing
and notarization do not enable them.**

This matters because enabling `onlyLoadAppFromAsar` or
`enableEmbeddedAsarIntegrityValidation` would prevent the shell hot-update
loader (#2097) from `require`-ing shell code staged under `userData`, and the
resulting failure is obscure. `desktop/test/macos-signing.test.js` asserts the
key is absent so the constraint fails loudly instead of at runtime.

## 6. Release path and credentials

Release dmgs are built by `.github/workflows/desktop-macos-dmg.yml`, which
already stamps the release version and selects the OTA channel. Signing is wired
into that job rather than performed by hand, so a release keeps a single
reproducible path (owner decision, 2026-08-21).

### 6.1 Repository secrets

| Secret | Contents |
|---|---|
| `MACOS_CSC_LINK` | The Developer ID Application certificate exported as a `.p12` and base64-encoded |
| `MACOS_CSC_KEY_PASSWORD` | The password protecting that `.p12` |
| `APPLE_API_KEY_P8` | The contents of the App Store Connect `AuthKey_<KEYID>.p8` |
| `APPLE_API_KEY_ID` | The API key ID |
| `APPLE_API_ISSUER` | The issuer UUID |

The App Store Connect API-key form is used rather than
`APPLE_ID` + app-specific password; electron-builder recommends it (electron-builder
issue 7859). electron-builder reads `APPLE_API_KEY` as a **file path**, so the
workflow writes the secret to `$RUNNER_TEMP/private_keys/AuthKey.p8` with mode
600, passes it through `env` rather than interpolating it into a script line,
and removes it in an `if: always()` step.

### 6.2 Builds without credentials still work

`CSC_IDENTITY_AUTO_DISCOVERY` is derived from whether `MACOS_CSC_LINK` is set.
With no certificate configured — a fork, or a contributor running the workflow —
identity discovery stays off and the job produces the same unsigned dev artifact
it produced before this change.

**Secret presence is tested through job-level `env` flags, never in an `if:`
directly.** GitHub does not expose the `secrets` context to any `if:` condition,
and the failure is not a skipped step: it rejects the whole workflow file with
`Unrecognized named-value: 'secrets'`, so the run never starts and the dmg build
that previously worked stops working. `secrets` *is* available in
`jobs.<id>.env`, and `env` *is* available in `steps.<id>.if`, so the job defines
`HAS_MACOS_SIGNING` and `HAS_NOTARY_KEY` and the conditional steps compare those
against the string `'true'`. Note the mirror-image trap when tempted to hoist
such a condition: `env` is **not** available in a *job-level* `if:`.

`tests/qa/test_workflow_expressions.py` guards both directions across every
workflow file. It exists because nothing else here validates workflows — there
is no actionlint hook, no CI job parses them, and a `workflow_dispatch`-only
workflow is never exercised by a pull request, so this class of defect passes a
fully green PR.

### 6.3 Notarization fails soft, so the build asserts the outcome

`macPackager.notarizeIfProvided()` logs `skipped macOS notarization` and returns
when its options cannot be generated. A missing or mistyped credential therefore
yielded a **green build and a dmg that still shows the Gatekeeper prompt**.

The #2176 hook hard-fails instead, so that specific hole is closed at the
source. The verification step still runs, because it is the only check that
survives the hook being unwired, mis-pathed, or skipped because signing did not
occur — and it asserts the shipped artifact rather than the build's account of
itself.

The workflow closes that hole with a verification step that runs whenever
signing was expected:

- `codesign --verify --deep --strict`
- `codesign --display` must report the `runtime` flag, proving
  `hardenedRuntime` actually applied
- `spctl -a -vvv -t exec` — Gatekeeper's own verdict, the same assessment a user
  double-clicking the app triggers
- `xcrun stapler validate` — a stapled ticket is the only proof notarization ran

Any of these failing fails the build.

### 6.4 Local build

For a one-off local build on macOS, the same credentials work as environment
variables:

```sh
export APPLE_API_KEY=/path/to/AuthKey_XXXXXXXX.p8
export APPLE_API_KEY_ID=... APPLE_API_ISSUER=...
export SCISTUDIO_OTA_CHANNEL=alpha
npm --prefix desktop run build:python:mac
npm --prefix desktop run stage:sh
npm --prefix desktop run dist:dmg:arm64   # or dist:dmg:x64 for an Intel build
```

The Developer ID Application certificate must be in the local keychain;
electron-builder selects it automatically. `dist:dmg:<arch>` produces the
runtime and shell for the arch of the machine it runs on, so an Intel dmg is
built on an Intel Mac (or under Rosetta) and an arm64 dmg on Apple Silicon.
`dist:dmg` remains an alias for `dist:dmg:arm64`.

### 6.5 Notarization is submitted by the build and finished separately (#2176)

`mac.notarize` is `false` and there is no `afterSign` hook. electron-builder
signs; `desktop/scripts/notarize.js` does everything else, in two phases that
run in different jobs.

**Why it left electron-builder.** `@electron/notarize` runs

```
xcrun notarytool submit <zip> --key ... --wait --output-format json
```

and both flags are load-bearing mistakes for us. `--output-format json`
suppresses every progress line — notarytool emits one object at the end and
nothing before it — so a submission queued behind Apple and one that is wedged
produce byte-identical logs: empty ones. Two 0.3.4 builds were cancelled at 118
and 79 minutes reading that silence as a hang. `DEBUG: electron-notarize*`
(#2174) did not fix it: that surfaces the package's own phase logging, which
stops where notarytool is spawned. `--wait` is separately untrustworthy — it has
been reported outliving Apple's own verdict — so the script polls
`notarytool info` instead, one fresh short-lived process per minute, each
writing a line.

**Why it is split across two jobs.** Measured on 2026-08-25 with that
instrumentation: signing 2 min 36 s, `ditto` 20 s, upload 17 s — and then
**61 consecutive polls, every one `In Progress`**. Apple held the submission for
over an hour without a verdict.

That is not a failure anything here can fix. What *was* fixable is the cost:
waiting inside the build discarded the signed dmg together with the queue
position, so each attempt began another hour from zero. So:

| Job | Does |
|---|---|
| `Desktop macOS DMG` | sign, build the dmg, submit it, upload it, print the submission ID — then stop |
| `Desktop macOS Staple` | wait for the verdict, staple the ticket to that dmg, assert the result |

A slow queue now costs a delay rather than a rebuild. Re-running the staple
workflow is free; **resubmitting is not** — the ticket is bound to the signed
artifact's cdhash, so a rebuilt dmg needs a fresh submission and a fresh wait,
and the old one was never invalid.

**What is submitted.** The dmg, not the `.app`. Stapling has to attach to
something that outlives the build, and the dmg is what ships. The `.app` inside
is therefore not itself stapled: Gatekeeper resolves it online, which every
download-from-GitHub user is. Only a first launch with no network would notice,
and that is the trade the split buys.

**Where the assertions live.** The build job can only assert what exists at
build time — the signature and the hardened runtime. `spctl` and
`xcrun stapler validate` both require a ticket, so they run in the staple job,
against the shipped dmg and the app mounted from it. That is also the more
faithful check: it asks Gatekeeper about the app a user will actually launch.

**Where the trace lives.** The script mirrors every line to
`$RUNNER_TEMP/notarize.log`, and both workflows print it in an `if: always()`
step. GitHub drops the tail of an in-progress step's log when a job is cancelled
or times out — exactly when the trace is wanted. A cancelled build lost twelve
minutes of output that way, leaving the runner's own
`Terminate orphan process (notarytool)` as the only evidence anything had run.

**Failure behaviour.** A rejection fails the job: notarytool exits 0 for a
submission Apple *refused* — it completed, the verdict was `Invalid` — so the
status line decides, not the exit status, and `notarytool log <id>` runs first
because the status says only *that* Apple refused. A timeout fails carrying the
submission ID, which keeps the submission queryable instead of forcing a blind
resubmit. Missing credentials skip; partial credentials fail, because a
half-configured set is always a misconfiguration.

### 6.6 Both architectures are built by CI (#2165)

The dmg job is a matrix over architecture, one leg per runner whose native arch
matches the artifact — arm64 on `macos-15`, x64 on `macos-15-intel`.
`build:python:mac` keys off `uname -m`, so each runner bundles the matching
CPython automatically and no Rosetta cross-build is involved.

The Intel leg was originally written against `macos-13`. GitHub retired that
image — it keeps only the latest two macOS versions — so a leg pinned to it
fails on an unknown runner label rather than building anything, a failure with
no useful diagnostic. `macos-15-intel` is the current x64 image.

`macos-15-intel` is also a *larger* runner, and larger runners are billed even
for public repositories where the arm64 leg is not, so building both
architectures on every dispatch has a cost the arm64-only workflow did not.

Each leg is a separate submission with its own artifact
(`scistudio-macos-dmg-<arch>`), so each needs its own `Desktop macOS Staple`
run (section 6.5). `dist:dmg:${{ matrix.arch }}` passes the electron-builder arch flag,
and `build.dmg.artifactName` (`${productName}-${version}-${arch}.dmg`) gives the
two dmgs distinct, arch-suffixed names so both can be attached to one release
without colliding.

Before this, only arm64 had a CI path and the Intel dmg was built by hand
(#2165). The signing, notarization and verification steps above are shared by
both legs, so the Intel dmg is signed, notarized and stapled on exactly the same
terms as the Apple Silicon one.

`dist:dmg` signs but does not notarize (section 6.5), so a local dmg still
meets Gatekeeper until the two remaining phases are run by hand:

```sh
node desktop/scripts/notarize.js submit desktop/dist/SciStudio-*.dmg   # prints the id
node desktop/scripts/notarize.js wait <submission-id>
node desktop/scripts/notarize.js staple desktop/dist/SciStudio-*.dmg
```

`wait` is safe to re-run and safe to interrupt. Re-submitting is not: the ticket
is bound to that dmg's cdhash, so a second submission buys a second queue wait
and invalidates nothing.

## 7. Verification

Automated, any platform — `desktop/test/macos-signing.test.js`:

- `hardenedRuntime` is on, `mac.notarize` is `false`, and there is no
  `build.afterSign` — notarization is driven by the workflows, not by
  electron-builder (#2176).
- `entitlements` and `entitlementsInherit` are set and identical (section 3.2).
- The configured entitlements path exists. electron-builder returns an
  explicitly configured entitlements path verbatim rather than resolving it
  against `directories.buildResources` (which is `assets` here), so a path typo
  would otherwise only surface during a signing run on a mac.
- The entitlements file carries all three required keys.
- `build.electronFuses` is unset (section 5).

Owner-executed on macOS — **not yet run**; this is why the spec status is
`Draft` rather than `Implemented`:

- A machine that has never had SciStudio installed launches the notarized dmg
  with no security prompt of any kind.
- `spctl -a -vvv -t install <app>` reports `accepted` and `Developer ID`.
- `xcrun stapler validate <dmg>` passes.
- Package OTA installs and loads a package with a compiled extension under the
  notarized build (this is the check that proves section 3.1).

## 8. Deferred

- **Windows code signing.** The Apple Developer Program does not cover it;
  SmartScreen will keep warning until a separate OV/EV certificate or Azure
  Trusted Signing is in place. Out of scope per issue #2096 scope.out.
  Followup: open a dedicated issue when a Windows certificate is acquired.
- **electron-updater.** Signing is what makes Squirrel.Mac viable, so background
  auto-update of the Electron binary and the interpreter becomes possible for
  the first time. It is deliberately not part of this change: Squirrel.Mac has
  no delta mechanism and would download the full app each time. Revisit after
  #2097, which removes the common reasons to ship a new installer at all.

## 9. Assumptions

- A Developer ID Application certificate is available in the build machine's
  keychain (source: owner, 2026-08-21).
- Notarization runs on macOS; the agent authoring this change works on Windows,
  so section 7's owner-executed checks are the acceptance gate (source: owner
  session constraint).
- The bundled interpreter is python-build-standalone as built by
  `desktop/scripts/build-python-runtime-macos.sh` (source: repository).
