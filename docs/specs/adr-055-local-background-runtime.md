---
spec_id: adr-055-local-background-runtime
title: "ADR-055 Spec 3 — Local Startup Modes And The Background Runtime"
status: Draft
feature_branch: docs/2263-adr-055-specs
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 3 covers ADR-055 section 7. Owner decisions recorded: the installed launcher offers desktop use and external AI use at startup; the external AI mode runs the bundled backend without requiring a full desktop window, with the Electron main process staying resident as the process owner (the piggyback route — spawn, readiness, port memory, stop, and OTA chains already live there); all three platforms (Windows, macOS, Linux) ship; platform-specific work is confined to the POSIX parent-watchdog opt-out, per-platform window-closed semantics, and per-mode single-instance handling. Investigation evidence: desktop/main.js startRuntimeWithRollback/readiness/port-memory/stopRuntime; src/scistudio/cli/main.py gui --bundled is already a headless 127.0.0.1 server that prints a ready line; src/scistudio/desktop/parent_watchdog.py kills the backend on parent death and must gain an opt-out."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 34
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
scope:
  in:
    - "A startup mode choice in the installed launcher: desktop use (current behavior) or external AI use."
    - "External AI mode: the Electron main process starts the bundled backend without creating the full desktop window, waits for real service readiness, and presents a copyable localhost:port address."
    - A connection window that can be closed without stopping the service, and reopened to see the address, service status, and an explicit stop control.
    - "Discovery and reuse: repeated launches detect and reuse the running instance instead of spawning duplicates."
    - Explicit shutdown following the existing process/task lifecycle contracts, with visible effect.
    - The POSIX parent-watchdog opt-out so backend lifetime is decoupled from the launcher process when the mode requires it.
    - Per-platform semantics for window-closed behavior, single-instance locking per mode, and recovery when the backend dies while the launcher stays resident.
    - "OTA interplay: applying an update stops and replaces the background instance through the existing chain."
    - All three desktop platforms (Windows, macOS, Linux).
  out:
    - OS-level autostart/login-item registration (not required by ADR-055 section 7; the launcher manages its own backend).
    - Hub accounts, Docker, branded domains, or DNS (excluded by ADR-055 sections 7 and 10).
    - The loopback session token mechanics (defined in adr-055-webmcp-bridge); this spec only consumes the contract so the connection window carries a working URL.
    - Lab deployment (adr-055-lab-deployment).
    - The AI-host presentation (deferred by owner).
governs:
  modules:
    - scistudio.cli.main
    - scistudio.desktop.parent_watchdog
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-055-local-background-runtime.md
    - desktop/main.js
    - desktop/menu.js
    - desktop/runtime-port.js
    - src/scistudio/cli/main.py
    - src/scistudio/desktop/parent_watchdog.py
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - desktop/background-mode.js
  excludes: []
tests:
  - desktop/test/background-mode.test.js
  - tests/cli/test_gui_background_mode.py
acceptance_source: adr
language_source: en
---

# ADR-055 Spec 3 — Local Startup Modes And The Background Runtime

## 1. Change Summary

This spec comes from ADR-055 (section 7) and umbrella issue #2263.

A local user choosing external AI use should not have to keep a full desktop
window open, understand ports, or supervise processes. The installed launcher
gains a startup choice: desktop use (today's behavior) or external AI use. The
latter starts the bundled backend without creating the full desktop window,
waits for real readiness, and shows a copyable `localhost:port` address in a
small connection window that can be closed and reopened; the service keeps
running until explicitly stopped.

The process-ownership decision (owner-directed): **the Electron main process
stays resident and owns the backend; no new daemon, supervisor, or OS service
is introduced.** Investigation showed the spawn, readiness, port-memory,
stop, logging, crash capture, and OTA-rollback chains all already live in
`desktop/main.js` and are battle-tested; "no window" is the delta, not a new
process model. The CLI already has the matching headless server mode
(`scistudio gui --bundled` binds `127.0.0.1`, opens no browser, and prints a
ready line), so no backend serving changes are needed either.

Three platform-specific conflicts were found and are in scope as modifications
to existing code, not new systems: the POSIX parent watchdog that kills the
backend when its parent dies (must gain an opt-out so a window close or
launcher restart does not take the backend down where the mode requires it),
the app-level single-instance lock (must distinguish desktop mode from
external-AI mode so a second launch reuses rather than mis-focuses), and the
`window-all-closed → quit` semantics (must become mode- and platform-aware).

## 2. User Scenarios & Testing

### User Story 1 - External AI mode starts a ready backend and shows the address (Priority: P1)

A scientist opens the installed SciStudio launcher, picks external AI use, and
shortly sees a copyable `localhost:port` address once the service is actually
ready — without any full desktop window and without developer tools.

**Why this priority**: This is the mode's core promise (ADR-055 section 7:
"waits for actual service readiness, and presents a copyable localhost:port
address").

**Independent Test**: On an installed build, launch into external AI mode;
assert no main desktop window is created, the ready line and HTTP readiness
both pass before the address is shown, the shown address serves the SPA, and
copying it into a browser opens SciStudio.

**Acceptance Scenarios**:

1. **Given** the installed launcher, **When** the user picks external AI use,
   **Then** the backend starts via the existing spawn chain, readiness is
   confirmed by the existing two-layer check, and the connection window shows
   the address only after readiness.
2. **Given** the shown address, **When** it is opened in a browser, **Then**
   the full app loads and the WebMCP bridge session works (per the spec-1
   contract).

### User Story 2 - Closing windows never kills the analysis; explicit stop does (Priority: P1)

Closing the connection window, or the browser using the service, leaves running
analyses untouched; an explicit, visible stop control is the only way the mode
shuts the service down, and stopping follows the existing process/task
lifecycle contracts.

**Why this priority**: ADR-055 section 7 states it verbatim; silently killing
long analyses on window close would make the mode unusable.

**Independent Test**: Start a long workflow run through the backend in
external AI mode; close the connection window and the browser; assert the run
continues to completion; reopen the connection window, observe the service as
running, invoke stop, and assert the backend process tree terminates and the
status becomes visibly stopped.

**Acceptance Scenarios**:

1. **Given** a running analysis, **When** the connection window and browser
   close, **Then** the backend and the analysis keep running.
2. **Given** the reopened connection window, **When** the user stops the
   service, **Then** the existing stopRuntime path terminates the process tree
   and the window reflects the stopped state.

### User Story 3 - Repeated launches reuse the running instance (Priority: P2)

Launching the launcher again — in either mode — discovers the already-running
backend and reuses or offers to reveal it, instead of spawning a duplicate.

**Why this priority**: ADR-055 section 7: "repeated launches do not
accidentally create duplicate instances"; the remembered-port mechanism exists
for exactly this class of problem and is reused.

**Independent Test**: Start external AI mode; launch the launcher twice more,
once choosing external AI and once choosing desktop; assert no second backend
process appears, the second external-AI launch reopens the connection window,
and the desktop-mode launch follows the declared conflict behavior (attach to
the running backend by opening the desktop window on it, per FR-006).

**Acceptance Scenarios**:

1. **Given** a running external-AI instance, **When** the launcher starts again
   in external AI mode, **Then** it reuses the instance and shows the
   connection window without a new backend process.
2. **Given** a running external-AI instance, **When** the launcher starts in
   desktop mode, **Then** the desktop window opens against the existing
   backend (single backend per machine, per the remembered-port contract).

### User Story 4 - The backend survives its launcher on every platform (Priority: P2)

The platform-specific lifetime rules hold: on POSIX the backend no longer dies
when the launcher process exits (watchdog opt-out honored); on Windows the
existing tree-kill protections still prevent orphans; on macOS the resident-
without-window convention is honored.

**Why this priority**: The watchdog conflict is a real cross-platform
correctness bug for this mode (investigation evidence:
`src/scistudio/desktop/parent_watchdog.py` kills the backend 2–5 s after
parent death; Windows has no equivalent and relies on `taskkill /T`).

**Independent Test**: On Linux/macOS, start external AI mode, quit the launcher
process entirely (not just windows), and assert the backend survives per the
mode's declared policy; on Windows, assert no orphan is left after an explicit
stop and that launcher exit follows the declared policy.

**Acceptance Scenarios**:

1. **Given** external AI mode on POSIX, **When** the launcher process exits,
   **Then** the backend survives or stops according to the declared policy
   (FR-005 picks one; default: survives, with the next launcher start
   re-adopting it via discovery).
2. **Given** external AI mode on Windows, **When** the user stops the service,
   **Then** the full process tree is gone and no orphan remains.

### User Story 5 - Updates and crashes recover predictably (Priority: P3)

Applying an OTA update stops and replaces the background backend through the
existing update chain; if the backend crashes while the launcher is resident,
the connection window shows the failure and offers restart.

**Why this priority**: Updates that leave an old backend serving old code are a
silent version skew; crash-without-visibility reads as "the tool is dead".

**Independent Test**: With the background instance running, apply a (test)
update and assert the update chain stops the old backend before relaunch;
kill the backend process and assert the connection window reflects the dead
state and its restart action brings the service back with a fresh ready line.

**Acceptance Scenarios**:

1. **Given** a running background backend, **When** an update is applied,
   **Then** the existing stop-then-relaunch chain includes the background
   instance and the post-update backend reports the new build.
2. **Given** a killed backend, **When** the launcher is resident, **Then** the
   connection window shows stopped/crashed status and its restart control
   restores readiness.

### Edge Cases

- The remembered port is occupied by an unrelated process: existing port
  probing falls back to an ephemeral port; the shown address always reflects
  the actual bound port (never the remembered one).
- The user picks desktop mode first, then external AI: one backend per machine;
  mode transitions attach to the running backend rather than duplicating it.
- Backend ready-line timeout (existing 120 s) in external AI mode: the
  connection window shows the failure with logs reachable, mirroring desktop
  startup failure handling.
- Machine sleep/wake with a resident launcher: no action; the backend keeps
  its port; the connection window re-validates status on focus.
- Two OS users on one machine each running the mode: per-user userData and
  port memory keep instances separate (existing behavior, asserted not
  changed).

## 3. Requirements

### Functional Requirements

- **FR-001**: The launcher MUST offer desktop use and external AI use at
  startup; the choice UX may be minimal (a small picker or the connection
  window's mode affordance) and MUST NOT block the current default desktop
  flow for users who never choose.
- **FR-002**: External AI mode MUST start the backend through the existing
  spawn chain (python candidates, runtime env, OTA rollback, ready line + HTTP
  readiness) and MUST NOT create the main desktop window.
- **FR-003**: The connection window MUST show a copyable `localhost:port`
  address only after readiness, MUST be closable without stopping the service,
  and MUST be reopenable (launcher relaunch and, where the platform supports
  it, a resident affordance) showing address, status, and stop.
- **FR-004**: Explicit stop MUST go through the existing `stopRuntime`
  tree-kill contract and MUST make its effect visible in the connection
  window.
- **FR-005**: Backend lifetime MUST be decoupled from window lifetime on all
  platforms, and from launcher-process lifetime where the declared policy says
  so: the POSIX parent watchdog MUST gain an explicit opt-out used by this
  mode; the chosen policy (survive vs stop on launcher exit) MUST be one
  declared behavior per platform, documented and tested.
- **FR-006**: Single-instance behavior MUST be mode-aware: exactly one backend
  per machine; a second launch reuses it (external AI) or attaches a desktop
  window to it (desktop mode); duplicate backends are never spawned.
- **FR-007**: OTA application MUST include the background instance in the
  existing stop-then-relaunch chain; a background backend MUST NOT keep
  serving pre-update code after an update is applied.
- **FR-008**: Backend crash or death while the launcher is resident MUST
  surface in the connection window as a stopped/crashed status with a restart
  action; restart MUST reuse the readiness chain.
- **FR-009**: `scistudio gui` MUST gain the watchdog opt-out flag (or
  equivalent env) so the Electron-spawned background mode controls lifetime;
  the flag MUST NOT change default desktop-mode behavior.
- **FR-010**: The connection window MUST present the working URL including any
  session token delivery per the `adr-055-webmcp-bridge` loopback contract;
  loopback binding stays `127.0.0.1` and CORS stays restrictive.
- **FR-011**: All behavior MUST ship on Windows, macOS, and Linux; per-platform
  differences are confined to lifetime/lock/window semantics named in this
  spec.

## 4. Implementation Plan

### 4.1 Technical Approach

Add a background-mode module (`desktop/background-mode.js`) owning: mode
choice state, the connection window (a small BrowserWindow, not the main
window), status polling against the backend, and the stop/restart actions that
call the existing `stopRuntime`/`startRuntime` functions. `desktop/main.js`
gains the mode branch at startup: external AI mode runs
`startRuntimeWithRollback` and skips `createWindow` for the main window;
`window-all-closed` becomes mode- and platform-aware (macOS already expects
resident-without-window; Windows/Linux keep quit-on-close for desktop mode and
stay resident for external AI mode while the connection window lives or the
user leaves it running).

Single-instance: keep the app lock; on second-instance, inspect the running
mode and either reveal the connection window (same mode) or attach a desktop
window to the running backend (desktop chosen while external AI runs), using
the remembered port as the attach target.

Backend: `cli/main.py` `gui` gains `--no-parent-watchdog` (or
`SCISTUDIO_NO_PARENT_WATCHDOG`) passed by the Electron spawn in external AI
mode; `parent_watchdog.py` honors it. Readiness, ports, logging, crash
capture, and OTA paths are reused unchanged.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `desktop/background-mode.js` | create | Mode state, connection window, status, stop/restart |
| `desktop/main.js` | modify | Mode branch at startup; window-all-closed semantics; second-instance routing; OTA chain inclusion |
| `desktop/menu.js` | modify | Entry to reopen the connection window / stop the service |
| `desktop/runtime-port.js` | modify | Reuse/attach helpers if discovery needs extension |
| `src/scistudio/cli/main.py` | modify | Watchdog opt-out flag on `gui` |
| `src/scistudio/desktop/parent_watchdog.py` | modify | Honor the opt-out |
| `desktop/test/background-mode.test.js` | create | Mode/lock/window semantics (pure-logic extraction, following `runtime-port.js` precedent) |
| `tests/cli/test_gui_background_mode.py` | create | Watchdog opt-out behavior |

### 4.3 Implementation Sequence

1. **T-001** (foundation): extract mode/lifetime pure logic into
   `background-mode.js` with unit tests (runtime-port.js precedent).
2. **T-002** (US4): watchdog opt-out end to end (CLI flag → spawn env →
   watchdog).
3. **T-003** (US1/US3): startup mode branch, connection window, reuse and
   attach behavior.
4. **T-004** (US2): explicit stop + window-closed semantics per platform.
5. **T-005** (US5): OTA chain inclusion and crash/restart surfacing.
6. **T-006** (cross-cutting): three-platform verification per ADR-055 section
   11 Local launch row; session-token URL wiring (FR-010).

### 4.4 Verification Plan

- `desktop/test/background-mode.test.js`: pure-logic coverage of mode
  transitions, second-instance routing, and window-closed policy per platform.
- `tests/cli/test_gui_background_mode.py`: watchdog opt-out honored; default
  unchanged.
- Installed-build manual verification on Windows, macOS, and Linux: the five
  user stories end-to-end, with evidence recorded (ADR-055 section 11 Local
  launch row: readiness, copy/open address, reuse, explicit stop, recovery,
  no developer tools).
- Existing desktop startup tests pass unchanged (desktop mode untouched).

### 4.5 Risks And Rollback

- Risk: resident Electron processes surprise users ("app won't quit").
  Mitigation: the connection window and menu expose explicit stop; desktop
  mode behavior is unchanged.
- Risk: mode-aware single-instance routing mis-locks. Mitigation: pure-logic
  extraction with unit tests; attach falls back to showing the connection
  window.
- Risk: watchdog opt-out leaves orphans on POSIX after a hard launcher kill.
  Mitigation: discovery/re-adoption on next launch; explicit stop remains the
  owner-approved shutdown path; documented as the chosen policy.
- Rollback: the mode branch is additive; removing it restores today's startup.
  No data migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: On all three platforms, external AI mode reaches a shown,
  working address with zero manual steps after the mode choice, in an
  installed build without developer tools.
- **SC-002**: Closing every window and browser during a running analysis
  leaves the analysis running in 100% of verification runs; explicit stop
  terminates 100% of the backend process tree.
- **SC-003**: Repeated launches across mode combinations spawn zero duplicate
  backends (one backend process per machine at all times).
- **SC-004**: After an OTA update with the background instance running, the
  serving backend reports the new build (zero stale-backend cases).
- **SC-005**: Desktop mode passes the existing startup regression suite
  unmodified.

## 6. Assumptions

- The Electron main process is the background runtime's process owner; no OS
  service, daemon, or autostart is introduced (source: owner session,
  2026-09-05).
- One backend per machine, shared by both modes; per-OS-user separation is
  existing behavior (source: existing-system, single-instance lock and
  per-user userData).
- Local mode binds loopback only and needs no Hub account or Docker (source:
  ADR-055 section 7).
- The loopback session token contract comes from `adr-055-webmcp-bridge`; this
  spec consumes it (source: owner session, 2026-09-05).
