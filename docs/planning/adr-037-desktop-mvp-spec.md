---
title: "ADR-037 Desktop MVP Implementation Spec"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: [17, 19, 24, 25, 31, 34, 35, 36, 37, 38, 39, 40, 42, 43, 45, 47]
language_source: en
---

# ADR-037 Desktop MVP Implementation Spec

## 1. Purpose

This spec translates ADR-037 into an implementable MVP desktop distribution
track. The owner-authorized MVP deliberately stops before the full ADR-037
plugin system:

- ship an Electron desktop shell that launches the existing SciStudio runtime;
- keep `scistudio gui` as the developer path;
- bundle or stage frontend/runtime resources under `desktop/resources/`;
- support a software-directory `packages/` folder for hard-installed plugin
  source packages;
- defer PyPI plugin browser, per-plugin venvs, permission UI, auto-update,
  signing, telemetry, and uninstaller polish.

The MVP is a product spike that should be runnable by a reviewer from the
desktop branch. It is not a stable public release.

## 2. Branch, Issue, And Evidence

- Issue: #1502
- Protected integration branch: `desktop`
- Manager branch/worktree:
  - branch: `adr-037-desktop-mvp-manager`
  - worktree: `C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-mvp`
- Gate record:
  `.workflow/records/1502-adr-037-desktop-mvp-manager.json`
- Final target for this overnight run: push commits to remote `desktop`.
- No PR to `main` is opened for the MVP unless the owner later requests it.

## 3. Later ADR Impact Review

ADR-037 was written before ADR-038 through ADR-047 settled several contracts.
The MVP must obey the later accepted/proposed contracts below.

| ADR | Status | Impact on ADR-037 MVP |
|---|---|---|
| ADR-038 | Accepted | Project lineage is `<project>/.scistudio/lineage.db`; desktop paths must not move it to user config. Block versions are load-bearing. Hard-installed packages must resolve a real version or use the existing monorepo/dev fallback. |
| ADR-039 | Accepted | Desktop bundle must reserve `desktop/resources/git/` and use the bundled git locator. MVP must not require system git for packaged users. Existing `fetch-git-portable` scripts are part of the desktop resource flow. |
| ADR-040 | Accepted in implementation history | Skills and MCP resources must be package-resource friendly. Desktop resource staging must include `src/scistudio/_skills/**` through the normal Python package/wheel path, not a root-only `skills/` assumption. |
| ADR-041 | Accepted | CodeBlock script-as-AppBlock and IO capability validation rely on the current registry/capability APIs. Desktop plugin discovery must not reintroduce legacy IO finder behavior. |
| ADR-042 | Accepted | Gate record, checklist, committed evidence, issue linkage, and CI/readiness truth are mandatory. MVP gaps must be visible in repo TODOs or checklist deferrals. |
| ADR-043 | Accepted | Plugin-provided IO loaders/savers must register `FormatCapability` records; the MVP package scanner must go through `BlockRegistry.scan()` and existing validation, not import blocks ad hoc. |
| ADR-044 | Accepted | SubWorkflowBlock is authoring-only and flattened at load; desktop launch must preserve current project file semantics and watcher behavior. |
| ADR-045 | Accepted | Desktop wrapper must not swallow websocket/file watcher events. It only hosts the browser window around localhost; version-vector state remains server-authoritative. |
| ADR-046 | Proposed | Scheduler package shape may change; MVP must avoid touching scheduler internals. |
| ADR-047 | Proposed/partially landed | BlockRegistry is already a sub-package. MVP registry changes belong in `__init__.py` and `_scan.py`, preserving the Path D split and no class definitions in helper modules. |

Conclusion: the owner-requested hard-installed `packages/` MVP is compatible
with later ADRs if it is treated as a development/source-package discovery
layer, not as the final ADR-037 PyPI plugin system.

## 4. MVP User Story

As a non-terminal user, I can launch a SciStudio desktop app from the desktop
branch artifact. The app opens the existing SciStudio UI in an Electron window,
starts the bundled/current Python runtime on an ephemeral localhost port, and
shuts that runtime down when the window closes.

As an advanced tester, I can place source plugin packages under:

```text
desktop/packages/
  scistudio-blocks-imaging/
    pyproject.toml
    src/scistudio_blocks_imaging/...
```

or in an installed app layout:

```text
<app resources>/packages/
  scistudio-blocks-imaging/
    pyproject.toml
    src/scistudio_blocks_imaging/...
```

When the backend starts in bundled mode, it activates desktop package import
roots for registry and worker subprocesses, then asks
`BlockRegistry.scan(include_monorepo=True)` to discover `scistudio_blocks_*`
packages via the existing package protocol. For user selected local packages,
the installer may use the bundled Python interpreter to resolve that package's
Python dependencies from the configured package index into a user-scoped plugin
runtime. It must not rely on a user-installed system Python and must not install
dependencies into the application bundle.

As an advanced desktop user writing local custom blocks, I can open a SciStudio
desktop terminal from the GUI. The terminal starts in the current project and
routes `python`/`pip` commands through the bundled Python while installing
manual dependencies into a shared user-scoped dependency runtime.

## 5. In Scope

### 5.1 Desktop Shell

- New `desktop/package.json` with scripts for:
  - `npm run build:frontend`
  - `npm run stage`
  - `npm run start`
  - `npm run dist:dir`
- New Electron main process:
  - locates a Python executable from `SCISTUDIO_DESKTOP_PYTHON`, staged
    `desktop/resources/python/python(.exe)`, or `python`/`py` fallback for
    developer MVP;
  - launches `python -m scistudio.cli.main gui --port 0 --bundled`;
  - sets `PYTHONPATH` to include `desktop/resources/app/src` or repo `src`;
  - sets `SCISTUDIO_BUNDLED=1`;
  - sets `SCISTUDIO_DESKTOP_RESOURCES=<resources dir>`;
  - opens `BrowserWindow` only after a JSON ready line is read;
  - terminates the child process on app quit.

### 5.2 CLI Runtime Adaptation

- Extend `scistudio gui`:
  - `--port 0` means bind an ephemeral port;
  - `--bundled` suppresses browser open;
  - emits one machine-readable JSON line:
    `{"event":"scistudio.ready","host":"127.0.0.1","port":12345,"url":"http://127.0.0.1:12345"}`;
  - preserves current developer behavior for default `scistudio gui`.

### 5.3 Path Resolver

- Add `src/scistudio/desktop/paths.py`:
  - `config_dir()`, `cache_dir()`, `logs_dir()`, `plugins_dir()`,
    `shared_model_cache()`, `desktop_resources_dir()`, `bundled_resource()`,
    `bundled_packages_dir()`, and the user Python dependency runtime helpers;
  - use `platformdirs` when available;
  - keep a conservative stdlib fallback so tests can run before dependency
    installation;
  - never relocate project-owned `.scistudio/lineage.db` or `.git/`.

### 5.4 Hard-Installed Source Packages

- Add `BlockRegistry.add_package_src_dir(directory)` and a Tier 3 scan path.
- On startup/scan, include:
  - paths from `SCISTUDIO_PLUGIN_PACKAGE_DIRS` split by `os.pathsep`;
  - `<desktop resources>/packages`;
  - `desktop/packages` in source checkout.
- For each `packages/*/src`, temporarily prepend to `sys.path`, import
  `scistudio_blocks_*`, and use existing `get_block_package()` or
  `get_blocks()` protocol.
- This is source-package hard install plus per-package dependency resolution
  using the bundled Python interpreter. Dependency installs are scoped to the
  selected package's user plugin directory; they must not mutate the bundled
  application runtime or the user's system Python.

### 5.5 Desktop User Terminal

- Add a desktop terminal provider on the existing PTY WebSocket route.
- The terminal starts a user shell in the current project directory.
- `PATH`, `PYTHONPATH`, and pip-related environment are set so `python` and
  `pip` use the bundled Python and shared user-scoped dependency runtime.
- The shared user dependency import root is visible to trusted project drop-in
  block scans and worker subprocesses without globally leaking package source
  roots into the server process.

### 5.6 Staging Scripts

- Add cross-platform staging scripts:
  - build frontend to `frontend/dist`;
  - copy frontend into `desktop/resources/frontend`;
  - copy Python source into `desktop/resources/app/src`;
  - ensure `desktop/resources/packages/.gitkeep`;
  - preserve existing `desktop/scripts/fetch-git-portable.{ps1,sh}`.

## 6. Out Of Scope For MVP

The following are ADR-037-compliant deferrals and must remain visible:

- PyPI plugin search/browser.
- Per-plugin venvs and bundled `uv` installation.
- Heavy dependency prebundling in the DMG or download from GitHub Releases.
- Plugin permission confirmation UI.
- Plugin hot-upgrade quiescence and deletion.
- First-run claude/codex/git-bash installer UI.
- Auto-update, signing, notarization, airgapped variant, telemetry, and
  uninstaller data prompts.
- Public stable release matrix.

## 7. Acceptance Criteria

- `desktop/` contains a runnable Electron MVP.
- `npm --prefix desktop install` succeeds.
- `npm --prefix desktop run stage` succeeds.
- `npm --prefix desktop start` launches Electron and reaches the existing UI
  when run from the manager worktree on Windows.
- `PYTHONPATH=src python -m pytest tests/cli/test_cli.py tests/blocks/test_desktop_package_discovery.py --timeout=60`
  passes or any failure is recorded with a concrete blocker.
- `npm --prefix frontend run build` passes.
- The branch `desktop` contains committed spec, checklist, prompts, code,
  tests, and gate record evidence.

## 8. Agent Plan

Maximum five agents:

1. Desktop shell/staging worker.
2. CLI/path worker.
3. Hard-installed packages/registry worker.
4. Tests/validation worker.
5. Documentation/audit worker.

All agents work in dedicated branches/worktrees off `desktop`, with disjoint
write sets. The manager integrates into `adr-037-desktop-mvp-manager` and then
pushes to remote `desktop`.
