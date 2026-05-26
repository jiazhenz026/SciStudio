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

The macOS DMG build runs on macOS:

```bash
npm --prefix desktop run build:python:mac
npm --prefix desktop run stage:sh
npm --prefix desktop run dist:dmg
```

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
