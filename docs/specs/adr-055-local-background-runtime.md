---
spec_id: adr-055-local-background-runtime
title: "ADR-055 Spec 3 — Local Startup Modes And The Background Runtime"
status: Draft
feature_branch: feat/2280-local-background-runtime
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 3 covers ADR-055 section 7. Owner decisions recorded: the installed launcher offers desktop use and external AI use at startup; the external AI mode runs the bundled backend without requiring a full desktop window, with the Electron main process staying resident as the process owner (the piggyback route — spawn, readiness, port memory, stop, and OTA chains already live there); all three platforms (Windows, macOS, Linux) ship. Amended 2026-09-10 by the owner decisions recorded in issue #2280: the mode choice is offered at every launch with a don't-ask-again option; the tray icon exists in external-AI mode only; the backend stops with Electron (no watchdog opt-out, no instance adoption, no runtime-port.js discovery changes); one backend per machine through second-instance routing; OTA stop-then-relaunch includes the background instance and honours the mode. Amended 2026-09-11 by the audit fixes on PR #2284 and the owner decision that external-AI mode quits when its service stops, crashes, or fails while no window is open. Amended 2026-09-11 by #2327 after the PR #2334 audits: stopRuntime requests a graceful backend stop (SIGTERM on macOS and Linux, a closed stdin on Windows) and force-kills only 25 s later; quitting waits for the backend; a stop signal first ends the backend's long-lived streams; section 4.6 records how workflow runs end when the backend stops."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 34
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
  - desktop-shell-ota-hot-update
scope:
  in:
    - "A launch-mode choice on the splash at every launch (desktop use or external AI use) with a don't-ask-again option, and a remembered choice that stays changeable from the application menu, the tray, and the connection window."
    - "External AI mode: the Electron main process starts the bundled backend through the existing chain without creating the main desktop window, waits for real service readiness, and presents a copyable address."
    - "A connection window that can be closed without stopping the service and reopened to see the address, service status, and explicit stop and restart controls."
    - "A tray icon in external AI mode only, with a monochrome template image on macOS."
    - "One backend per machine: a second launch reaches the running instance through second-instance and reveals the connection window or attaches a desktop window."
    - "Explicit shutdown through stopRuntime, a graceful stop request followed by a tree-kill after a bound, with visible effect; crash surfacing with a restart action."
    - "Workflow runs across a backend stop: every run reaches a terminal lineage status (section 4.6, #2327)."
    - "Per-mode window-closed semantics on all three platforms."
    - "OTA interplay: every relaunch stops the background instance first and comes back in the running mode; a patched shell is recorded as known-good in external AI mode too."
    - All three desktop platforms (Windows, macOS, Linux).
  out:
    - OS-level autostart/login-item registration (not required by ADR-055 section 7; the launcher manages its own backend).
    - Hub accounts, Docker, branded domains, or DNS (excluded by ADR-055 sections 7 and 10).
    - The loopback session token mechanics (defined in adr-055-webmcp-bridge); the backend injects the token into the page it serves, so the connection window only presents the address.
    - "A backend that outlives Electron: the POSIX parent-watchdog opt-out, instance adoption and re-adoption, and runtime-port.js discovery changes (dropped by owner decision 3 on #2280)."
    - "Worker and grandchild process cleanup when the backend stops or dies (#2281)."
    - Lab deployment (adr-055-enterprise-support).
    - The AI-host presentation (deferred by owner).
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-055-local-background-runtime.md
    - desktop/background-mode.js
    - desktop/main.js
    - desktop/menu.js
    - desktop/splash.html
    - desktop/connection.html
    - desktop/connection-preload.js
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - desktop/test/background-mode.test.js
  - desktop/test/main-orchestration.test.js
  - desktop/test/menu.test.js
  - desktop/test/bootstrap.test.js
  - desktop/test/shell-known-good.test.js
  - tests/scripts/test_ota_publish.py
  - tests/api/test_runtime_run_lifetime.py
  - tests/api/test_runtime_stop_request.py
acceptance_source: adr
language_source: en
---

# ADR-055 Spec 3 — Local Startup Modes And The Background Runtime

## 1. Change Summary

This spec comes from ADR-055 (section 7) and umbrella issue #2263. The owner
decisions recorded in issue #2280 amend it, and the text below reflects them.

A local user choosing external AI use should not have to keep a full desktop
window open, understand ports, or supervise processes. The installed app now
asks on its splash, at every launch, whether to open the desktop app or run for
an external AI tool. A "don't ask again" box remembers the answer, and the
remembered choice stays changeable afterwards. Desktop use is today's flow.
External AI use starts the bundled backend without creating the main desktop
window, waits for real readiness, and shows a copyable address in a small
connection window. The window can be closed and reopened, and the service keeps
running until it is explicitly stopped or the app quits.

The process-ownership decision (owner-directed): **the Electron main process
stays resident and owns the backend; no daemon, supervisor, or OS service is
introduced, and the backend never outlives Electron.** The spawn, readiness,
port-memory, stop, logging, crash-capture, and OTA-rollback chains already live
in `desktop/main.js`, so "no main window" is the delta, not a new process model.
The CLI already has the matching headless server mode (`scistudio gui
--bundled` binds `127.0.0.1`, opens no browser, and prints a ready line), so
nothing changes on the backend side.

Because the backend stops with Electron, the earlier draft's three
backend-lifetime changes are gone: the POSIX parent watchdog stays exactly as
it is, there is no `--no-parent-watchdog` opt-out, and there is no adoption of
an orphaned backend or discovery change in `runtime-port.js`. What remains
platform-specific is small: `window-all-closed` depends on the mode, the tray
uses a template image on macOS, a Linux desktop without a tray host reaches the
running instance by launching the app again, and on Windows the backend's
death with Electron was verified (section 4.4).

## 2. User Scenarios & Testing

### User Story 1 - External AI mode starts a ready backend and shows the address (Priority: P1)

A scientist opens SciStudio, picks External AI on the splash, and shortly sees
a copyable address once the service is actually ready. No full desktop window
appears and no developer tools are needed.

**Why this priority**: This is the mode's core promise (ADR-055 section 7:
"waits for actual service readiness, and presents a copyable localhost:port
address").

**Independent Test**: On an installed build, launch and pick External AI.
Assert that no main desktop window is created, that the ready line and HTTP
readiness both pass before the address appears, that the address serves the
SPA, and that copying it into a browser opens SciStudio.

**Acceptance Scenarios**:

1. **Given** the splash picker, **When** the user picks External AI, **Then**
   the backend starts through the existing spawn chain, readiness is confirmed
   by the existing two-layer check, and the connection window shows the address
   only after readiness.
2. **Given** the shown address, **When** it is opened in a browser, **Then**
   the full app loads and the WebMCP bridge session works (per the spec-1
   contract).
3. **Given** "don't ask again" was ticked, **When** the app launches next,
   **Then** it starts in that mode without the picker, and File › Startup Mode,
   the tray, or the connection window can switch it back to asking.

### User Story 2 - Closing windows never kills the analysis; explicit stop does (Priority: P1)

Closing the connection window, or the browser using the service, leaves running
analyses untouched. An explicit stop control (or quitting the app) is the only
way the service shuts down, and stopping uses the existing process lifecycle
contract.

**Why this priority**: ADR-055 section 7 states it verbatim; silently killing
long analyses on window close would make the mode unusable.

**Independent Test**: Start a long workflow run through the backend in
external AI mode; close the connection window and the browser; assert the run
continues to completion; reopen the connection window from the tray (or by
launching again), observe the service as running, stop it, and assert the
backend process terminates and the status reads "Stopped".

**Acceptance Scenarios**:

1. **Given** a running analysis, **When** the connection window and browser
   close, **Then** the backend and the analysis keep running and the app stays
   resident.
2. **Given** the reopened connection window, **When** the user stops the
   service, **Then** the existing stopRuntime path terminates the backend and
   the window reflects the stopped state with a restart action.

### User Story 3 - Repeated launches reuse the running instance (Priority: P2)

Launching the app again reaches the already-running instance instead of
spawning a duplicate backend.

**Why this priority**: ADR-055 section 7: "repeated launches do not
accidentally create duplicate instances".

**Independent Test**: Start external AI mode; launch the app twice more, once
with no remembered choice and once with desktop remembered (or
`--scistudio-launch-mode=desktop`); assert that no second backend process
appears, that the first relaunch reveals the connection window, and that the
second opens a desktop window on the running backend.

**Acceptance Scenarios**:

1. **Given** a running external-AI instance, **When** the app is launched again
   with no mode preference, **Then** the running instance reveals its connection
   window and no backend is spawned. This is also how a Linux desktop without a
   tray host gets back to the instance.
2. **Given** a running external-AI instance, **When** the app is launched again
   asking for desktop mode, **Then** a desktop window opens on the existing
   backend.
3. **Given** a running desktop instance, **When** the app is launched again
   asking for external AI (or the user picks File › External AI Connection),
   **Then** the running instance switches to external AI mode on its existing
   backend: the tray and connection window appear and closing windows no longer
   quits.

### User Story 4 - The backend stops with the app on every platform (Priority: P2)

Quitting the app, including a force-kill of the Electron process, never leaves
the backend running.

**Why this priority**: With the Electron process as the only owner, an orphaned
backend would be an unowned server on a loopback port with no way to reach its
stop control.

**Independent Test**: On each platform, start external AI mode, then (a) use
Stop and Quit and (b) force-kill the Electron process; assert the backend
process is gone in both cases.

**Acceptance Scenarios**:

1. **Given** external AI mode on any platform, **When** the user chooses Stop
   and Quit (tray or connection window), **Then** `before-quit` runs the
   existing stopRuntime and the backend exits.
2. **Given** a force-killed Electron process, **When** no quit event runs,
   **Then** the backend still dies: on macOS and Linux through the unchanged
   parent watchdog, on Windows because the backend is a non-detached child
   (verification in section 4.4).

### User Story 5 - Updates and crashes recover predictably (Priority: P3)

Applying an OTA update stops the background backend and relaunches the app in
the same mode. If the backend crashes while the app is resident, the connection
window shows the failure and offers a restart.

**Why this priority**: Updates that leave an old backend serving old code are a
silent version skew; crash-without-visibility reads as "the tool is dead".

**Independent Test**: With the background instance running, apply a (test)
update and assert the update chain stops the old backend before relaunching,
and that the relaunch comes back in external AI mode without the picker. Kill
the backend process and assert the connection window reads "Stopped
unexpectedly" and its restart action brings the service back with a fresh ready
line.

**Acceptance Scenarios**:

1. **Given** a running background backend, **When** an update is applied,
   **Then** the backend exits before the relaunch, the relaunched app starts in
   external AI mode, and the new backend reports the new build.
2. **Given** a killed backend, **When** a window is open, **Then** the
   connection window shows the crashed status with a restart control that
   restores readiness, and the tray shows the crashed status.
3. **Given** a killed backend, **When** no window is open, **Then** the app
   quits (owner decision 2026-09-11; see FR-008).

### Edge Cases

- The remembered port is occupied by an unrelated process: the existing port
  probing falls back to an ephemeral port; the shown address always comes from
  the backend's ready line (the bound port), never the remembered one.
- The address uses `127.0.0.1`, the only interface the backend binds, rather
  than `localhost`, which some HTTP clients resolve to `::1` first.
- The splash is closed, or the app is quit, while the picker is asking: that is
  a quit, and no backend is started. The quit also releases the shell-OTA boot
  marker (FR-014), so a working patched shell is not quarantined by it. If the
  splash fails to load, takes longer than 15 s, or has no working picker, the
  app falls back to the desktop flow rather than refusing to start.
- Ready-line timeout (existing 120 s) or HTTP-readiness timeout in external AI
  mode: the connection window shows "Failed to start" with the error, a restart
  action, and a Show Logs button. A backend that exits during the readiness wait
  fails at once with its exit status, and Restart works immediately.
- Machine sleep/wake with a resident app: no action; the connection window
  re-validates the service on focus and shows "Not responding" when a running
  backend stops answering.
- The service is stopped, or Stop and Quit is chosen, while a desktop window is
  attached to it: the app asks for confirmation first, because that window
  stops working.
- External AI mode with no window open: when the service stops, crashes, or
  fails -- whether every window was already closed, or a Stop was still in
  progress when the connection window closed -- the app quits (owner decision
  2026-09-11), since it has no backend left to own and, on a Linux desktop
  without a tray host, would otherwise be invisible. The rule is re-evaluated on
  every service status change, not only when the last window closes.
- macOS: opening the running app again from Finder or the Dock activates the
  existing process instead of starting a second one, so the running app routes
  the `activate` event like a second launch (FR-006, FR-011).
- Two OS users on one machine: per-user userData, port memory, and
  single-instance locks keep instances separate (existing behavior, unchanged).

## 3. Requirements

### Functional Requirements

- **FR-001**: The splash MUST offer desktop use and external AI use at every
  launch, with a "don't ask again" option. A remembered choice MUST stay
  changeable from the application menu (File › Startup Mode), the tray, and the
  connection window. Choosing desktop MUST give today's flow unchanged.
- **FR-002**: External AI mode MUST start the backend through the existing
  spawn chain (python candidates, runtime env, OTA rollback, ready line + HTTP
  readiness, port memory) and MUST NOT create the main desktop window.
- **FR-003**: The connection window MUST show a copyable address only after
  readiness, MUST be closable without stopping the service, and MUST be
  reopenable from the tray, from File › External AI Connection, from the macOS
  dock, and by launching the app again. It shows the address, the status, and
  stop/restart controls.
- **FR-004**: Explicit stop MUST go through `stopRuntime`, which first asks the
  backend for a graceful stop and tree-kills it only after the FR-007 bound, and
  MUST make its effect visible in the connection window and tray.
- **FR-005**: Backend lifetime MUST be decoupled from window lifetime in
  external AI mode on all platforms, and MUST end with the Electron process in
  both modes: quitting runs `stopRuntime` and waits for the backend to exit
  (FR-015); a force-killed Electron process is
  covered by the unchanged POSIX parent watchdog on macOS/Linux and by the
  non-detached child's kill-on-close job on Windows.
- **FR-006**: There MUST be exactly one backend per machine. A second launch
  MUST reach the running instance through `second-instance` and be routed:
  reveal the connection window (external AI running, no desktop request), attach
  a desktop window to the running backend (external AI running, desktop
  requested), focus the desktop window (desktop running), or switch the running
  desktop instance to external AI mode (desktop running, external AI requested).
  Duplicate backends MUST NOT be spawned. On macOS, where reopening the app
  activates the running process instead, the `activate` event MUST be routed the
  same way, except that it never switches a desktop session to external AI mode.
- **FR-007**: Every relaunch (mandatory OTA, optional OTA, package-update) MUST
  stop the backend, the background instance included, and wait for it -- and for
  any backend a Stop already signalled -- to actually exit before relaunching,
  and MUST relaunch in the running mode. Stopping MUST first request a graceful
  stop: SIGTERM on macOS and Linux, and on Windows, where no graceful signal can
  be delivered, closing the backend's stdin (FR-015). A backend still running
  25 s later MUST be force-killed, with SIGKILL or `taskkill /T /F`. The 25 s
  covers the backend's shutdown budget (section 4.6): its long-lived streams end
  on the stop request, live workflow runs get 10 s to record their outcome, AI
  terminal sessions 3 s, and command processes a 5 s grace, at most 20 s in
  all. Liveness is judged by the process's exit status, never by Node's
  `killed` flag, which only records that a signal was sent. The wait is bounded
  at 30 s as a last resort.
- **FR-008**: Backend crash or death in external AI mode MUST surface, while a
  window is open, in the connection window as a crashed status with a restart
  action, and in the tray as the crashed status; restart MUST reuse the
  readiness chain. With no window open, the app MUST quit instead (owner
  decision 2026-09-11, on AU1 P2-3 / AU2 P2-1): a service that stops, crashes, or
  fails while no window is open ends the app.
- **FR-009**: Withdrawn by owner decision 3 (#2280). There is no watchdog
  opt-out; `scistudio gui` is unchanged.
- **FR-010**: The connection window MUST present the address of the backend's
  loopback server. The session token is delivered by the backend in the page it
  serves (per the `adr-055-webmcp-bridge` loopback contract), so the address
  alone is the working URL. Loopback binding stays `127.0.0.1` and CORS stays
  restrictive.
- **FR-011**: All behavior MUST ship on Windows, macOS, and Linux; per-platform
  differences are confined to those named in this spec: the macOS template tray
  image and `activate` routing, the Windows tray left-click, the Windows
  stdin stop request and `taskkill` escalation versus the POSIX SIGTERM/SIGKILL
  stop, and reaching the
  instance by relaunch on a Linux desktop without a tray host.
- **FR-012**: The tray icon MUST exist in external AI mode only. Its menu MUST
  offer: service status, open connection window, copy address, open in desktop
  mode, the Startup Mode choice, and stop and quit. macOS MUST use a template
  (monochrome) image, and the Tray object MUST be held by a strong reference.
- **FR-013**: In external AI mode the shell MUST record itself as known-good
  once the connection window is proven -- its page sent its first action over
  IPC, which takes the page script, the sandboxed preload, and the IPC handler
  all working -- and the backend is running, so the shell-OTA crash-loop guard
  does not quarantine a working patched shell in a mode with no main window.
- **FR-014**: A user-initiated quit (a closed splash, Cmd+Q, Stop and Quit)
  after the launch-mode picker rendered MUST release the shell-OTA boot marker,
  unless a shell fault was recorded (#2179). A shell that fails before the
  picker renders, or that crashes (no quit handler runs), MUST keep the marker,
  so the crash-loop guard still quarantines it.
- **FR-015**: Quitting MUST ask the backend for a graceful stop and wait for it
  to exit, within the FR-007 bounds, before the app quits. The windows MUST hide
  at once so the quit stays responsive. On Windows the request is closing the
  backend's stdin: the shell spawns the backend with a stdin pipe and
  `SCISTUDIO_STOP_ON_STDIN_EOF=1`. On macOS and Linux it keeps stdin closed and
  sends SIGTERM. On startup the backend moves the pipe to a private descriptor
  that its child processes cannot inherit, and gives them the null device.
  Otherwise, on Windows, git and every other child that inherited the pipe
  would hang while the backend waits on it. At end-of-file the backend raises
  SIGTERM in itself. Every stop signal first ends the backend's long-lived
  streams (the event socket, the log event stream and the AI terminal
  sessions), so uvicorn's wait for open connections finishes and the lifespan
  shutdown runs while pages are still connected (#2327). FR-005 still covers a
  force-killed Electron process.
- **FR-016**: Every workflow run MUST reach a terminal lineage status across a
  backend stop, a project reopen, and a project switch, as section 4.6
  specifies (#2327).

## 4. Implementation Plan

### 4.1 Technical Approach

**Decision logic** lives as pure functions in `desktop/background-mode.js`
(the `runtime-port.js` precedent): the persisted preference shape, startup-mode
resolution, relaunch arguments, second-instance and `activate` routing, the
`window-all-closed` verdict per mode and its re-evaluation on status changes,
process liveness, the boot-marker release rule, service-status transitions, the
bound address, and the connection-window view. `desktop/main.js` gathers facts
and acts; `desktop/test/main-orchestration.test.js` drives the real `main.js`
through those actions.

**Mode choice.** The preference lives in `userData/launch-mode.json` as
`{ version: 1, mode, askAtLaunch }`; `mode` is the last pick and preselects the
picker. The picker runs on the splash before the mandatory-update check, so an
update applied at startup relaunches straight into the chosen mode. The splash
stays preload-free: `splash.html` exposes `__scistudioSplashPickMode()`, which
returns a promise that `executeJavaScript` waits on. The picker counts as
rendered once the splash confirms the function exists; a splash that fails to
load, takes longer than 15 s, or has no picker falls back to the desktop flow.
A quit after the picker rendered releases the boot marker from `before-quit`
(FR-014). A relaunch carries the running mode as
`--scistudio-launch-mode=<mode>`, which overrides both the picker and a
remembered choice.

**External AI mode.** After the update check, `main.js` creates the tray and the
connection window, closes the splash, and runs `startRuntimeWithRollback` →
HTTP readiness → port memory → cache-build check. Only then does the status
become "Running" with the address (the origin of the ready line's URL). The
connection window (`connection.html` with the sandboxed `connection-preload.js`)
renders the view the main process pushes over `scistudio:connection-state`, and
sends actions over `scistudio:connection-action`: copy (main-process
clipboard), open desktop window, stop, restart, show logs, set startup mode,
stop and quit. Only the connection window's own webContents is answered, and
the page's first action is the proof FR-013 vouches on. Its focus event
re-probes the backend over HTTP. The backend's exit after readiness sets
"Stopped" after an explicit stop and "Stopped unexpectedly" otherwise; an exit
during the readiness wait ends that wait at once as "Failed to start". Stop and
Stop and Quit both ask first while a desktop window is attached.

**Tray.** `desktop/assets/tray.png` (+`@2x`) on Windows and Linux; the
`trayTemplate.png` (+`@2x`) template image on macOS. Both are derived from the
app icon. On Windows, a left-click opens the connection window; the context menu
is `menu.js`'s `buildTrayMenuTemplate`.

**Window-closed semantics.** Desktop mode quits on `window-all-closed` on every
platform, as before. External AI mode stays resident while its backend is
starting, running, not responding, or stopping, and quits once the backend is
stopped, crashed, or failed. The same rule is applied again on every service
status change while no window is open (`quitOnServiceChange`, owner decision
2026-09-11), so a stop or crash after the last window closed quits too. On
macOS, `activate` (a dock click, or reopening the app from Finder) is routed
like a second launch (`routeActivate`).

**Single instance.** The app lock is unchanged. The second process passes the
mode it would have started in (an explicit flag or a remembered choice; it quits
before it could show a picker) as `requestSingleInstanceLock` additional data,
and the running instance routes it (FR-006). "Attach" opens the ordinary main
window on the running backend's URL.

**Application menu.** File gains External AI Connection… (switches a desktop
session to external AI mode, or reopens the connection window) and a Startup
Mode radio submenu (Ask at Every Launch / Always Open the Desktop App / Always
Run for External AI).

**Relaunch.** The mandatory OTA, optional OTA, and package-update relaunches all
go through `stopRuntimeAndRelaunch`: `stopRuntime`, wait for every backend that
is still exiting to exit, then `app.relaunch({ args })` with the running mode.
`stopRuntime` records each backend it signals until that backend exits, so a
Stop already in flight is waited for too. It asks for a graceful stop first
(SIGTERM, or on Windows a closed stdin) and force-kills a backend still running
25 s later, judged by its exit status. The escalation used to test Node's
`killed` flag, which turns true as soon as SIGTERM is sent, so it never fired.
The wait is bounded at 30 s as a last resort. A quit waits the same way, with
its windows hidden (FR-015). Waiting lets the relaunched backend take the remembered port back, so
the address an AI tool holds stays valid.

**Shell OTA.** Every new shell file — `background-mode.js`,
`connection-preload.js`, `connection.html`, and the four tray images — is listed
in both `desktop/package.json` `build.files` and `scripts/ota_publish.py`
`SHELL_FILES`, and is resolved relative to `__dirname`, so a patched shell
carries its own copies. FR-013 keeps the crash-loop guard working in a mode with
no main window.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `desktop/background-mode.js` | create | Pure mode/lifetime/routing/status logic and the preference shape |
| `desktop/main.js` | modify | Mode branch at startup; picker; external-AI service lifecycle; tray; connection window; second-instance routing; `window-all-closed`/`activate`; `stopRuntimeAndRelaunch` |
| `desktop/menu.js` | modify | File › External AI Connection and Startup Mode; the tray menu template |
| `desktop/splash.html` | modify | Launch-mode picker |
| `desktop/connection.html` | create | Connection window page |
| `desktop/connection-preload.js` | create | Sandboxed bridge for the connection window |
| `desktop/assets/tray*.png` | create | Tray images (colour; macOS template), 1x and 2x |
| `desktop/package.json` | modify | `build.files` lists the new shell files |
| `scripts/ota_publish.py` | modify | `SHELL_FILES` lists the new shell files |
| `desktop/test/background-mode.test.js` | create | Pure-logic coverage and cross-file contracts |
| `desktop/test/menu.test.js` | modify | New File entries, Startup Mode radio, tray menu |
| `desktop/test/bootstrap.test.js` | modify | Shell file lists, every shipped module's requires and every page's assets, `__dirname`-relative files, relaunch helper, tray reference, boot-marker clear sites |
| `desktop/test/main-orchestration.test.js` | create | Behavioural scenarios that drive the real `main.js` |
| `desktop/test/harness/*.js` | create | Stubbed `electron`, Node fake backend, scenario runner for the orchestration tests |
| `desktop/test/shell-known-good.test.js` | modify | Anchor the #2179 readiness check on the desktop boot path |
| `tests/scripts/test_ota_publish.py` | modify | List parity and require/asset coverage for the published shell |
| `docs/specs/desktop-shell-ota-hot-update.md` | modify | Section 6 shell list brought up to date |
| `CHANGELOG.md` | modify | Unreleased entry |
| `src/scistudio/api/runtime/_run_lifetime.py` | create (#2327) | Run lifetime across a backend stop, reopen and switch (section 4.6) |
| `src/scistudio/api/runtime/_stop_request.py` | create (#2327) | The backend side of the Windows stdin stop request (FR-015) |
| `tests/api/test_runtime_run_lifetime.py`, `tests/api/test_runtime_stop_request.py` | create (#2327) | Section 4.6 and FR-015 coverage |

`src/scistudio/cli/main.py`, `src/scistudio/desktop/parent_watchdog.py`, and
`desktop/runtime-port.js` are unchanged (owner decision 3).

### 4.3 Implementation Sequence

1. **T-001**: pure logic in `background-mode.js` with unit tests.
2. **T-002**: Windows backend-lifetime verification (section 4.4); no backstop
   was needed.
3. **T-003**: splash picker; File › Startup Mode and External AI Connection.
4. **T-004**: external AI mode in `main.js`: service lifecycle, tray, connection
   window, attach and switch paths.
5. **T-005**: relaunch paths through `stopRuntimeAndRelaunch`.
6. **T-006**: shell file lists, this spec.

### 4.4 Verification Plan

- `desktop/test/background-mode.test.js`: preference parsing and persistence
  shape, startup resolution, relaunch round-trip, second-instance and `activate`
  routing, `window-all-closed` per mode and `quitOnServiceChange`, process
  liveness, the boot-marker release rule, status transitions, the connection
  view (address only while running), and the channel/action/mode contracts
  shared with `connection-preload.js`, `connection.html`, and `splash.html`.
- `desktop/test/main-orchestration.test.js`: the real `main.js`, driven through
  a stubbed `electron` and a Node fake backend, one process per scenario.
  - External AI start: no main window, and the address appears only after
    readiness.
  - The connection window: sender check, copy, second-instance reopen.
  - Service control: stop, restart on the remembered port, crash with a window
    open, attach, and stop confirmation.
  - Quitting and relaunch: Stop and Quit confirmation, relaunch waiting for
    exit, and quit when the service goes down with no window open.
  - SIGKILL escalation, and an in-flight stop, against a backend that ignores
    SIGTERM.
  - #2327: a quit hides the windows at once and waits for the backend's
    graceful stop (SIGTERM, or a closed stdin on Windows); on Windows a backend
    that ignores the request is `taskkill`ed after the bound.
- `tests/api/test_runtime_run_lifetime.py` and
  `tests/api/test_runtime_stop_request.py`: section 4.6 and the backend side of
  FR-015.
  - Restart immediately after a death during readiness.
  - Picker quit or close releasing the boot marker, a failure before the picker
    and a preload fault keeping it (judged by `desktop/ota.js`'s own marker
    functions), and a splash load failure falling back.
  - Platform behaviour: macOS `activate` routing and the template image, and the
    Windows tray left-click.
- `desktop/test/menu.test.js`: the File entries, the Startup Mode radio group,
  and the tray menu (entries, enablement, actions).
- `desktop/test/bootstrap.test.js` and `tests/scripts/test_ota_publish.py`:
  every file the shell requires or loads next to itself ships in both the asar
  and the OTA patch; every relaunch goes through `stopRuntimeAndRelaunch`.
- **Windows backend lifetime (owner decision 3), verified 2026-09-10 on
  Windows 11.** A Node script stands in for the Electron main process: it spawns
  a long-lived Python child with the options `desktop/main.js` uses (no
  `detached`, `windowsHide`, piped stdio), and the child spawns one grandchild.
  A driver starts that script detached, force-kills only the parent with
  `taskkill /F /PID <parent>` (no `/T`, so no signal reaches the child), and
  checks all three processes after 3 s. Parent run as Node 24.14.0 (3 runs) and
  as the Electron 42.2.0 binary with `ELECTRON_RUN_AS_NODE=1` (Node 24.15.0,
  2 runs): the child died every time, and the grandchild survived every time.
  The child's death is consistent with libuv placing non-detached children in a
  kill-on-close job object. No Windows backstop was added. The grandchild result
  is the separate worker-cleanup problem tracked in #2281.
- Installed-build verification on Windows, macOS, and Linux (a manager/owner
  e2e step): the five user stories end to end, including a Linux desktop without
  a tray host and the macOS template image in light and dark menu bars (ADR-055
  section 11 Local launch row: readiness, copy/open address, reuse, explicit
  stop, recovery, no developer tools).
- Existing desktop startup tests pass unchanged (desktop mode untouched).

### 4.5 Risks And Rollback

- Risk: a resident Electron process surprises users ("app won't quit").
  Mitigation: resident only in external AI mode and only while a backend is
  live; the tray and connection window expose Stop and Quit; desktop mode is
  unchanged.
- Risk: mode-aware second-instance routing mis-routes. Mitigation: pure-logic
  extraction with unit tests; attach falls back to showing the connection
  window when there is no running service.
- Risk: a patched shell is quarantined because external AI mode never paints a
  main window. Mitigation: FR-013 with a pinning test.
- Risk: worker processes spawned by the backend outlive it (all platforms).
  Tracked separately in #2281; out of scope here.
- Rollback: the mode branch is additive. With a remembered desktop choice the
  app behaves as before this spec; removing the branch restores today's
  startup. `launch-mode.json` is a plain preference file with no migration.

### 4.6 Workflow Runs Across A Backend Stop (#2327)

A workflow run belongs to the backend, not to a window or a browser. Closing
either never ends it (ADR-055 section 7), and neither does reopening its project
or switching to another project. A run ends when it completes, when someone
cancels it explicitly, or when its backend stops. Its lineage `runs` row must
reach a terminal status in every case (the #1500 guarantee), and a run that
finished must be recorded as what it was. `src/scistudio/api/runtime/_run_lifetime.py`
implements this contract.

- **Graceful stop.** uvicorn finishes open connections before it runs the
  lifespan shutdown. So every stop signal first calls
  `ApiRuntime.begin_shutdown()`: it closes the log event stream and kills the
  AI terminal sessions, and the event socket returns once the server closes
  it. The lifespan shutdown then calls `ApiRuntime.shutdown_workflow_runs()`.
  That cancels every live run and waits 10 s in total while each run records
  `cancelled`. For any run still going after that, it records `cancelled`
  itself, and that run's own later completion does not overwrite it. It then
  gives the AI terminal kills 3 s and command processes a 5 s grace. The
  budget is at most 20 s, and the desktop force-kills at 25 s (FR-007,
  FR-015).
- **Store lifetime.** Reopening the active project, as a page reload does, keeps
  its lineage store. Switching projects retires the previous store, which is
  closed only after the last live run writing through it ends. A run of the
  previous project therefore records its blocks and outcome in its own
  project. It is listed as running when the user switches back.
- **Owner markers.** A run first registers itself as live in its process. It
  then writes `<project>/.scistudio/run-owners/<run_id>.json` (pid, process
  creation time, machine id, host, claim time), and only then inserts its
  `running` row. The marker is removed once the row is terminal. If the
  terminal write failed, it is retried through a store opened by path. If that
  fails too, the marker stays, annotated with the outcome, and the next open
  records that outcome. A run whose marker cannot be written runs without a
  lineage row, as when the store is unavailable.
- **Reconciliation when a project opens.** Each `running` row that no live run
  in this process owns is judged by its marker:
  - Owner provably gone: no marker, invalid marker content, the PID gone, the
    PID reused (the creation time differs), a zombie, or this process no
    longer running it. The row is finalised `failed`, or with the outcome an
    annotated marker records.
  - Owner on another machine: left `running`, because a process on another
    machine cannot be checked from here. The machine id is `/etc/machine-id`
    or `/var/lib/dbus/machine-id` on Linux, `MachineGuid` on Windows, and
    `IOPlatformUUID` on macOS, with the hostname as the fallback. A row owned
    by another machine for more than 24 hours is reported in the backend log,
    because it keeps artifact retention (#1983) blocked.
  - Marker unreadable, for example a sharing violation or a network
    filesystem error: left `running`, with a warning.

  The `finished_at` of a reconciled row records when the problem was detected.
  The reason goes to the backend log and to the run's `run-<run_id>.log`; the
  lineage schema has no reason column.
- **Worker death** is handled by the engine unchanged: the block fails and the
  run records `failed`.
- **Runs waiting on a person.** A run parked on user input (an interactive
  block, or an engine-opened AI Block tab) keeps waiting while no browser is
  connected. Its row stays `running`, and retention stays blocked, until
  someone answers or cancels it or the backend stops.
- **Known limits.** Ownership assumes one PID namespace per machine id. Two
  containers that share an image's machine id and a project directory would
  judge each other's PIDs locally. A reconnecting page is not sent the states it
  missed; it sees the run in Run history and receives its later events.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: On all three platforms, external AI mode reaches a shown,
  working address with zero manual steps after the mode choice, in an
  installed build without developer tools.
- **SC-002**: Closing every window and browser during a running analysis
  leaves the analysis running in 100% of verification runs; explicit stop
  terminates the backend process in 100% of runs.
- **SC-003**: Repeated launches across mode combinations spawn zero duplicate
  backends (one backend process per machine at all times).
- **SC-004**: After an OTA update with the background instance running, the
  serving backend reports the new build (zero stale-backend cases), and the app
  is back in external AI mode.
- **SC-005**: Desktop mode passes the existing startup regression suite
  unmodified.

## 6. Assumptions

- The Electron main process is the background runtime's process owner; no OS
  service, daemon, or autostart is introduced, and the backend stops with it
  (source: owner session, 2026-09-05; owner decision 3, #2280).
- One backend per machine, shared by both modes; per-OS-user separation is
  existing behavior (source: owner decision 4, #2280; existing single-instance
  lock and per-user userData).
- Local mode binds loopback only and needs no Hub account or Docker (source:
  ADR-055 section 7).
- The loopback session token contract comes from `adr-055-webmcp-bridge`; this
  spec consumes it (source: owner session, 2026-09-05; #2271).
