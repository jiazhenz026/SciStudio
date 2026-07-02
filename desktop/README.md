# SciStudio Desktop MVP

## Development Loop

Use the desktop dev runner when changing frontend or backend code:

```powershell
npm --prefix desktop run dev
```

This starts Vite at `http://127.0.0.1:5173`, starts the SciStudio backend on
port `8000`, and opens Electron against the Vite URL. Frontend edits hot-reload
through Vite. Backend edits are picked up by restarting this command; no
`stage` or `dist:dir` rebuild is needed for normal testing.

The packaged desktop build still uses staged static assets:

```powershell
npm --prefix desktop run build:python
npm --prefix desktop run stage
npm --prefix desktop run dist:dir
```

The Windows installer uses the same staged resources and emits an unsigned NSIS
installer under `desktop/dist`:

```powershell
npm --prefix desktop run build:python
npm --prefix desktop run stage
npm --prefix desktop run dist:win
```

The macOS DMG build runs on macOS and targets **arm64** (Apple Silicon):

```bash
npm --prefix desktop run build:python:mac
npm --prefix desktop run stage:sh
npm --prefix desktop run dist:dmg
```

`build:python:mac` stages a Python runtime for the host architecture (`uname -m`)
and `dist:dmg` builds `--arm64`, so run these on an Apple Silicon Mac to keep the
bundled Python and the Electron shell the same architecture. `stage:sh` refreshes
the packaged SPA (`scistudio/api/static`) from the fresh `frontend/dist` on every
build; a bundled app serves only that embedded SPA, never a `frontend/dist` found
on the host (#1747).

The Linux AppImage build runs on Linux and emits an unsigned AppImage under
`desktop/dist` (ADR-037 §3.6 D21 selects AppImage as the primary Linux format):

```bash
npm --prefix desktop run build:python:linux
npm --prefix desktop run stage:sh
npm --prefix desktop run dist:linux
```

`build:python:linux` stages a standalone glibc-based Python under
`resources/python/bin/python3` for the host architecture
(`x86_64-unknown-linux-gnu` or `aarch64-unknown-linux-gnu`) before `dist:linux`
builds the AppImage. Build on the oldest distro you intend to support: the
bundled interpreter and the numpy/pyarrow/zarr manylinux wheels are glibc-based,
so an AppImage built against a newer glibc will not launch on older distros. CI
pins `ubuntu-22.04` as the compatibility baseline. On systems without FUSE
(minimal containers, some hardened distros), launch with
`./SciStudio-*.AppImage --appimage-extract-and-run`.

The GitHub Actions build chain for packaged artifacts is intentionally manual
because the installer jobs are slow. Run `.github/workflows/desktop-windows-installer.yml`
to upload `scistudio-windows-installer`, run
`.github/workflows/desktop-macos-dmg.yml` to upload `scistudio-macos-dmg`, and run
`.github/workflows/desktop-linux-appimage.yml` to upload `scistudio-linux-appimage`.

By default the Linux workflow produces a dev `build0000`, OTA-disabled AppImage.
For a **release** build that joins the `ota-alpha` release alongside the mac/win
installers, dispatch it with the `build_number` and `ota_channel` inputs: e.g.
`build_number=11 ota_channel=alpha` stamps the SSOT version
(`python scripts/version.py sync`) so electron-builder names the artifact
`SciStudio-0.3.2-alpha-build0011-*.AppImage` and enables launch-time OTA against
the channel manifest. Leave both inputs empty for a plain dev build.

The packaged app uses the SciStudio icon assets in `desktop/assets`: `icon.svg`
is the source, `icon.png` is the runtime window icon (and the Linux AppImage
icon), and `icon.ico`/`icon.icns` are the Windows and macOS packaging icons.

## Runtime Python

The ADR-037 MVP is expected to ship with a staged Python under
`resources/python/python.exe`. Build it with:

```powershell
npm --prefix desktop run build:python
```

On Windows, that portable runtime is staged from
[python-build-standalone](https://github.com/astral-sh/python-build-standalone)
(`x86_64-pc-windows-msvc-install_only`) — a full CPython, the same source macOS
uses. It deliberately does **not** use the python.org *embeddable* zip: the
embeddable distribution ships a `pythonXX._pth` file that makes CPython ignore
`PYTHONPATH`, and the bundled app loads `scistudio` from `resources/backend/src`
(and OTA patches from a userData dir) purely through `PYTHONPATH`
(`main.js` `runtimeEnv`). An embeddable runtime therefore could not import
`scistudio` and broke OTA on Windows (#1807). The runtime includes
`pywinpty`/`winpty` because embedded agent terminals are PTY-backed. System
Python is only a developer fallback; an end-user desktop build should include
`resources/python` so a user can launch SciStudio without installing Python
first.

On macOS, `build:python:mac` stages a standalone Python under
`resources/python/bin/python3` before `dist:dmg` builds the DMG.

On Linux, `build:python:linux` stages the same standalone `python-build-standalone`
layout under `resources/python/bin/python3` before `dist:linux` builds the
AppImage. Linux agent terminals are backed by the stdlib `pty` module, so no
extra PTY backend is bundled.

## Local Package Installer

The desktop app exposes a local package installer from the toolbar. Use it to
select a local wheel, source archive, or source directory that contains a
`scistudio_blocks_*` Python package. The installer copies or extracts the
package into the user-scoped plugin directory:

```text
<user data dir>/SciStudio/plugins/packages/
```

After installation the backend refreshes the block registry, so package blocks
appear in the palette without a remote package browser. The installer uses the
bundled Python interpreter to install the selected package's Python runtime
dependencies into that package's user-scoped plugin directory. It does not rely
on a user-installed Python and does not mutate the application bundle. The
install endpoint is enabled only when the backend is running in bundled desktop
mode.

## User Python Terminal

The AI chat panel also exposes a desktop terminal tab for manual dependency
installation. It opens in the current project and puts SciStudio's user Python
wrappers first on `PATH`, so `python` and `pip` use the bundled Python while
manual installs land in the user-scoped dependency runtime:

```text
<user data dir>/SciStudio/plugins/python/site-packages/
```

That runtime is added to `PYTHONPATH` for trusted custom-block discovery and
worker subprocesses. It does not mutate the application bundle or require a
system Python install.
