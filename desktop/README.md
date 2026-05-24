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
npm --prefix desktop run stage
npm --prefix desktop run dist:dir
```
