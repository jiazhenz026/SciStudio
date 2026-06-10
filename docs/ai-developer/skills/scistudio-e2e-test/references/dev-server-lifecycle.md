# Dev Server Lifecycle

Backend (`scistudio gui` / `scistudio serve`) and frontend (`vite`) lifecycle
rules for e2e sessions. The single most common failure mode is a stale
process from a prior session serving outdated code — verify before you
debug.

## 1. Process Audit At Session Start

Before launching anything, sweep for stale processes. They survive agent
exit because the Claude Code harness does not kill background processes
when a sub-agent terminates.

```powershell
# Vite processes — usually point at .claude/worktrees/agent-* when stale
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like '*vite*' } |
  Select-Object ProcessId, CommandLine

# SciStudio backend processes
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*scistudio gui*' -or $_.CommandLine -like '*scistudio serve*' } |
  Select-Object ProcessId, CommandLine
```

For any process pointing at a `.claude/worktrees/agent-*` path that is
not the current session's, kill it:

```powershell
Stop-Process -Id <PID> -Force
```

For processes pointing at the user's main checkout, **ask first** — that
might be the user's own dev server.

## 2. Port Selection

- Default backend: `8000`. Default Vite: `5173`.

- If the user is likely running their own dev session, use a non-default
  port for the e2e run to avoid collision:
  - Backend: `--port 50338` (or anything 50000+ that is free)
  - Vite: `npm run dev -- --port 5180`

- The scenario file's Section 2 specifies the port. Honor it.

- Verify the port is free before launching:

  ```powershell
  $port = 8000
  $inUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($inUse) { throw "Port $port already in use by PID $($inUse.OwningProcess)" }
  ```

## 3. Frontend Mode Choice

Two valid modes — pick based on what the scenario is testing:

**Prebuilt SPA via `scistudio gui`** (most scenarios):

```powershell
scistudio gui --port 8000 --no-browser
```

The wheel ships the prebuilt React SPA. This is the production path. Use
this when the scenario tests user-facing behavior, not frontend dev
ergonomics.

**Vite dev server + `scistudio serve`** (frontend-dev scenarios only):

```powershell
# Backend headless
Start-Process -NoNewWindow scistudio -ArgumentList 'serve', '--port', '8000'

# Vite dev server, proxies /api to backend
Start-Process -NoNewWindow npm -ArgumentList 'run', 'dev', '--', '--port', '5180' -WorkingDirectory frontend
```

Use this only when the scenario explicitly tests HMR, in-development
frontend changes, or Vite-specific behavior. Pure feature scenarios
should use the prebuilt SPA — it matches what users see after
`pip install scistudio`.

## 4. Readiness Probe

A 60-second ceiling, polling every 500ms. Time it out hard — do not
extend or retry blindly.

```powershell
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
do {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-WebRequest http://localhost:8000/api/health -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ready = $true }
  } catch {}
} while (-not $ready -and (Get-Date) -lt $deadline)
if (-not $ready) { throw "Backend did not become ready within 60s" }
```

If the probe times out: ABORT the session. Capture backend stderr (from
the background job output) into the Artifacts list. Do not start Chrome.

## 5. Cleanup On Exit

Always run cleanup, even on session failure. Stale processes are the
gift that keeps on giving.

```powershell
# Backend
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*scistudio gui*' -or $_.CommandLine -like '*scistudio serve*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Vite (if frontend dev mode was used)
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like '*vite*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Confirm shutdown:

```powershell
Start-Sleep 1
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue  # expect empty
```

## 6. Editable-Install Contamination Check

If running from a worktree, verify which `scistudio` is actually getting
imported:

```powershell
python -c "import scistudio; print(scistudio.__file__)"
```

If the path is not under the current worktree's `src/scistudio/`, a prior
`pip install -e .` from another worktree has contaminated the global
environment. Resolve by clearing the stale editable install or switching to a
clean per-worktree virtual environment, then launch with
`PYTHONPATH=src python -m scistudio.cli.main gui ...`.

This is more common than it should be in multi-worktree workflows.

## 7. Long-Running Background Job Hygiene

Both backend and frontend should be started as background processes
inside the e2e session, not as detached daemons:

- Prefer `Bash(run_in_background: true)` — the harness tracks the PID
  and you can read its output via `Monitor` or `BashOutput`.
- Avoid `Start-Process` for processes you might need to kill mid-run;
  it harder to track the PID.
- Always tag the process for cleanup — when you start it, capture the
  PID immediately:

  ```powershell
  $proc = Start-Process scistudio -ArgumentList '...' -PassThru
  $proc.Id  # save for cleanup
  ```

## Related

- `chrome-mcp-recipes.md` §8 — backend restart for editable-install
- `screenshot-recipes.md` — capture after launch
