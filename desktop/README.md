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

The macOS DMG build runs on macOS:

```bash
npm --prefix desktop run build:python:mac
npm --prefix desktop run stage:sh
npm --prefix desktop run dist:dmg
```

The GitHub Actions build chain for packaged artifacts is intentionally manual
because the installer jobs are slow. Run `.github/workflows/desktop-windows-installer.yml`
to upload `scistudio-windows-installer`, and run
`.github/workflows/desktop-macos-dmg.yml` to upload `scistudio-macos-dmg`.

The packaged app uses the SciStudio icon assets in `desktop/assets`: `icon.svg`
is the source, `icon.png` is the runtime window icon, and `icon.ico`/`icon.icns`
are the Windows and macOS packaging icons.

## Runtime Python

The ADR-037 MVP is expected to ship with a staged Python under
`resources/python/python.exe`. Build it with:

```powershell
npm --prefix desktop run build:python
```

On Windows, that portable runtime includes `pywinpty`/`winpty` because embedded
agent terminals are PTY-backed. System Python is only a developer fallback; an
end-user desktop build should include `resources/python` so a user can launch
SciStudio without installing Python first.

On macOS, `build:python:mac` stages a standalone Python under
`resources/python/bin/python3` before `dist:dmg` builds the DMG.

## Local Package Installer

The desktop app exposes a local package installer from the toolbar. Use it to
select a local wheel, source archive, or source directory that contains a
`scistudio_blocks_*` Python package. The installer copies or extracts the
package into the user-scoped plugin directory:

```text
<user data dir>/SciStudio/plugins/packages/
```

After installation the backend refreshes the block registry, so package blocks
appear in the palette without a remote package index. This path is strictly
local: it does not download dependencies or query PyPI. The install endpoint is
enabled only when the backend is running in bundled desktop mode.
