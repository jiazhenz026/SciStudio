---
spec_id: desktop-package-ota-hot-update
title: "Per-Package OTA Hot-Update via In-App Package Manager"
status: Implemented
feature_branch: guided/1784-package-ota-hotupdate
created: 2026-06-26
input: "Issue #1784 — extend desktop OTA (#1775) to individual plugin packages, driven by an in-app Package Manager rather than a startup dialog. Owner-directed guided session 2026-06-26."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - desktop-ota-hot-update
  - alpha-version-management
scope:
  in:
    - Self-declared per-package OTA source via PackageInfo.ota (manifest_url + channel).
    - A pure Python decision module (package_ota.py) mirroring desktop/ota.js, semver-based.
    - A Package Manager service (package_manager.py) — check updates, download + sha256 verify + stage, rollback, delete, list installed.
    - Backend API — GET /api/packages/installed, GET /api/packages/updates, POST /{name}/update, POST /{name}/rollback, DELETE /{name}.
    - An in-app Package Manager modal (install / update / rollback / delete) opened from a toolbar Packages button that replaces the WS/Logs status pills.
    - A startup update check with a non-blocking toolbar badge.
    - A scistudio:relaunch Electron IPC so applying an update restarts into a fresh interpreter.
    - A non-scanned per-package rollback backup root (plugins/package-backups).
  out:
    - SRS package (deferred; only spectroscopy, imaging, lcms adopt the template first).
    - Live (no-relaunch) registry refresh for applying new package code.
    - Cryptographic signing (sha256 + HTTPS only; packages are public repos).
    - Core/Electron/interpreter OTA (covered by desktop-ota-hot-update).
    - The per-package publish tooling and template wiring (lives in the package repos / scistudio-package-template).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/desktop-package-ota-hot-update.md
    - src/scistudio/blocks/base/package_info.py
    - src/scistudio/desktop/package_ota.py
    - src/scistudio/desktop/package_manager.py
    - src/scistudio/desktop/paths.py
    - src/scistudio/api/routes/packages.py
    - desktop/main.js
    - desktop/preload.js
    - frontend/src/components/PackageManagerDialog.tsx
    - frontend/src/components/Toolbar.tsx
    - frontend/src/hooks/usePackageUpdates.ts
    - frontend/src/lib/api/packages.ts
  excludes: []
tests:
  - tests/desktop/test_package_ota.py
  - tests/desktop/test_package_manager.py
  - tests/api/test_packages.py
  - frontend/src/components/PackageManagerDialog.test.tsx
acceptance_source: issue
language_source: en
---

# Per-Package OTA Hot-Update via In-App Package Manager

## 1. Change Summary

The desktop OTA mechanism ([desktop-ota-hot-update](desktop-ota-hot-update.md))
hot-patches the **core** backend+frontend snapshot at launch. This spec extends
the same idea to **individual plugin packages**, which now live in standalone
public repos discovered via Python entry points.

Each package self-declares its update source. The user manages packages from an
in-app **Package Manager** (install / update / rollback / delete) opened from a
toolbar **Packages** button. A background check at startup surfaces available
updates as a non-blocking badge. Applying an update relaunches the app so a
fresh interpreter imports the new package code.

## 2. Why this differs from core OTA

| Concern | Core OTA (#1775) | Package OTA (#1784) |
|---|---|---|
| Unit | Whole backend source snapshot | One package's install dir |
| Versioning | Monotonic `build` over an installer baseline | Plain **semver** (full replace, no baseline) |
| Overlay | userData patch shadows bundled src via PYTHONPATH | Active version in the already-scanned `installed_packages_dir()` shadows any bundled copy |
| Trigger | Launch-time native dialog | In-app Package Manager + startup badge |
| Apply IO | Electron `main.js` | Python backend (download/verify/stage); Electron only relaunches |
| Rollback | Boot-failure auto-revert | User-driven; prior version kept in non-scanned `package-backups/` |

## 3. Self-declared source

A package declares its update source through the new optional
`PackageInfo.ota` field (`PackageOtaSource(manifest_url, channel)`), returned by
its `scistudio.blocks` entry point. Core keeps no package list: the update check
iterates the *loaded* registry packages (`registry.packages()`) and reads each
one's `ota`.

## 4. Manifest

Each package publishes a `manifest.json` to its own public, rolling
`ota-<channel>` GitHub pre-release alongside a `<pkg>-<version>.tar.gz`
snapshot:

```json
{
  "package": "scistudio-blocks-spectroscopy",
  "version": "1.2.0",
  "requires": { "min_core_base": "0.2.1" },
  "url": "https://github.com/<owner>/<repo>/releases/download/ota-alpha/scistudio-blocks-spectroscopy-1.2.0.tar.gz",
  "sha256": "…",
  "size": 1234567,
  "notes": "…",
  "published_at": "2026-06-26T00:00:00Z"
}
```

`package_ota.evaluate_update` returns `update` only when the manifest version is
newer by semver **and** the running core base satisfies `min_core_base`;
otherwise `none` / `incompatible` / `invalid`.

## 5. Apply model and rollback

`package_manager.update_package` fetches the manifest, downloads the snapshot,
verifies sha256, installs it into `installed_packages_dir()` (which is on the
block scan path and shadows any bundled copy), then moves the prior active
version into `plugins/package-backups/<name>/`. Exactly one active version stays
on the scan path — this also fixes a latent bug where a version bump left the old
install dir discoverable.

Because Python does not re-import an already-loaded module in-process, applying
new code requires a fresh interpreter. The Package Manager prompts a restart and
calls the `scistudio:relaunch` IPC (`app.relaunch(); app.exit(0)`). Rollback
restores the backup and discards the current version; delete removes both.

## 6. API and UI

- `GET /api/packages/installed` — on-disk install records.
- `GET /api/packages/updates` — per-package update status (network).
- `POST /api/packages/{name}/update` · `POST /{name}/rollback` · `DELETE /{name}`.

All are gated to bundled desktop runs. The frontend Package Manager
(`PackageManagerDialog`) is an app-modal following the "open project" pattern,
opened from a toolbar **Packages** button that replaces the former WS/Logs
connection pills. `usePackageUpdates` runs the startup check and drives the
badge; it degrades silently to "no updates" in non-bundled or offline runs.

## 7. Security

Packages are public repos: HTTPS + sha256 only (no auth, no signing), matching
the core OTA threat model. Manifest URLs must be `http(s)`; snapshot downloads
must be `https`. Archive extraction reuses `package_installer`'s path-traversal
and symlink guards.

## 8. Verification

- `tests/desktop/test_package_ota.py` — semver parse/compare + `evaluate_update`.
- `tests/desktop/test_package_manager.py` — check, download+verify+stage+backup,
  rollback, delete, checksum-mismatch rejection.
- `tests/api/test_packages.py` — the five Package Manager routes + bundled gate.
- `frontend/src/components/PackageManagerDialog.test.tsx` — list, update→relaunch
  prompt, rollback/delete, empty state.

## 9. Assumptions

- Package install dirs are named `<name>-<version>` with a
  `scistudio-local-package.json` record (existing installer contract).
- The package-side publish tooling and `PackageInfo.ota` declarations live in
  `scistudio-package-template` and the per-package repos; this spec governs the
  core consumer side only.
