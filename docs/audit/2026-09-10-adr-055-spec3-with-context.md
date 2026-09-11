---
title: "Audit — ADR-055 Spec 3 local startup modes (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 42
related_specs:
  - adr-055-local-background-runtime
  - desktop-shell-ota-hot-update
language_source: en
---

# Audit — ADR-055 Spec 3 local startup modes (with-context)

Audit mode: **with-context** (agent AU1, `audit_reviewer` persona).
Subject: PR #2284, `feat/2280-local-background-runtime` @ `5c0ddefac`, closing
#2280. Implementation commit `d12e43ac8`, ledger commits `c23786daf`, `5c0ddefac`.
Audit branch: `audit/2280-spec3-with-context`.
Gate ledger: `.workflow/records/2280-audit-2280-spec3-with-context.json`.
Evidence read: issue #2280 (owner decisions 1-5), the rewritten spec
`docs/specs/adr-055-local-background-runtime.md`, ADR-055 sections 7 and 11,
PR #2284 body, diff, CI and review comments, the checklist
(`origin/track/adr-055-spec2-3:docs/planning/adr-055-spec2-3-checklist.md`,
sections 8 and 10), the A2 dispatch prompt, the implementer's ledger, and
`docs/ai-developer/release-runbook.md`.

**Verdict: pass-with-fixes.** No P1. The owner decisions are all implemented,
the Windows lifetime claim reproduces, the connection window's security surface
is sound, and the two shell file lists are held in parity. Five P2 findings
remain. One is a new way to quarantine a working patched shell. Two are
automated-review (Codex) findings, still unaddressed at `5c0ddefac`, which this
audit confirms independently. One is that the `main.js` orchestration has no
behavioural tests: nine mutations of it and of the file-list checks pass the full
committed suite. The last is a missing CHANGELOG entry.

## 1. Findings

### P1 — blocks merge

None.

### P2 — should fix before completion

#### P2-1. Quitting at the launch-mode picker quarantines a working patched shell

The frozen loader writes the shell boot marker *before* it requires a patched
shell (`desktop/bootstrap.js:203-206`). Only `recordKnownGood` clears it,
through `host().clearBootAttempt()` (`desktop/main.js:384-410`). If the next
launch finds a marker naming the same build, the patch is refused and the
baseline shell runs (`ota.shellMarkerAction` → `"keep"`). The baseline may not
clear the marker (`ota.mayClearShellMarker`), so the refusal holds for every
later launch until a *different* patch build is published.

The PR adds a pre-readiness wait of unbounded length: the picker. It also adds
a designed exit from it: splash closed while asking → quit
(`main.js:2182-2188`, `pickModeOnSplash` resolving `null`; this is scenario 4 of
the implementer's harness). Neither path clears the marker. The same holds for
Stop and Quit in external-AI mode before the service is `running`.

Reproduced against the shipped decision module:

```text
launch1 action record
launch2 action keep (keep = run the baseline shell)
baseline may clear marker? false
launch3 action keep
next patch build 32 action record
```

Consequence: a packaged user on a patched shell who opens the app and quits at
the picker (Cmd+Q on macOS, Alt+F4 on the frameless splash) is moved silently
and persistently to the baseline shell. If that baseline predates #2280, the
picker and external-AI mode disappear with no message. This is not a brick:
the backend `src/` patch keeps working (runbook section 5, the mixed state is
supported). The hazard class existed before, since quitting during the
desktop-mode splash also leaves the marker. The PR turns that short, silent
window into an indefinite user interaction with an explicit "quit" outcome.

The owner's Windows live run used a checkout shell
(`loading checkout shell (build 0)`), which never writes a marker, so it did not
exercise this.

Options (owner's call):
- (a) Clear the boot marker, without recording known-good, when the user quits
  at the picker. By then the shell has loaded, rendered the splash, and answered
  `executeJavaScript`.
- (b) Clear it once the picker has returned an answer.
- (c) Accept it, and track it as an issue with the quit-at-picker case written
  into the spec's Risks section.

The loader is frozen, so any fix has to live in the shell.

#### P2-2. The relaunch wait relies on a SIGKILL escalation that never fires (Codex review, unaddressed)

`stopRuntimeAndRelaunch` waits up to `RELAUNCH_STOP_TIMEOUT_MS` (8 s) for the
backend to exit (`main.js:1555-1585`). The comment at `main.js:66-68` and spec
section 4.1 both justify the bound with the claim that
"`stopRuntime`'s own SIGKILL escalation fires at 5 s".

It does not. `stopRuntime` escalates only `if (!child.killed)`
(`main.js:1543-1548`), and Node sets `ChildProcess.killed` as soon as a signal
is *sent*. Verified locally with Node 24.14.0:

```text
{"killReturned":true,"killedImmediately":true,"exitCodeImmediately":null}
{"exited":true,"code":null,"signal":"SIGTERM","killedAtExit":true}
```

On macOS/Linux, a backend that stalls on SIGTERM for more than 8 s is still
alive when the app relaunches. The new backend then finds the remembered port
taken and falls back to an ephemeral one, which changes the address an external
AI tool is holding — the exact outcome FR-007's wait exists to prevent. The old
backend is left to the POSIX parent watchdog once Electron exits.

The escalation bug predates this PR, but the PR's new guarantee and its spec
text depend on it. The same finding was posted by `chatgpt-codex-connector` on
`desktop/main.js:1567` at `c23786daf`, and has no reply or follow-up.

Options:
- Make the escalation check `exitCode`/`signalCode` rather than `killed`.
  `stopRuntime` is in `main.js`, which is inside the A2 write set.
- Or correct the spec/comment text and track the escalation bug as an issue.

#### P2-3. Backend death after every window is closed leaves a resident process with no backend (Codex review, unaddressed)

`window-all-closed` is the only place that evaluates
`windowAllClosedAction`. Consider this sequence:
- the connection window is closed while the service is live, so the app stays;
- the backend later crashes or is stopped from the tray.

`trackRuntime` then only records the status (`main.js:1806-1831`), and nothing
makes the app quit.

Spec section 2, "Edge Cases", states the opposite: "External AI mode with the
service stopped, crashed, or failed and every window closed: the app quits".
FR-008 pulls the other way, since the crash must surface in the tray, which
means staying resident. On a Linux desktop without a tray host the instance is
still reachable by relaunching (the second-instance route is
`show-connection-window`), so recovery exists.

Code and spec disagree. Codex raised this on `desktop/main.js:1829`, and it too
has no reply.

The owner has two ways to resolve it:
- re-evaluate the policy in `trackRuntime` when no window is open, or
- reword the edge case to cover only windows closed *after* the service went
  down.

#### P2-4. The `main.js` orchestration (+760 lines) has no behavioural test; the five harness scenarios are uncommitted

The decision logic is well placed. Preference parsing, startup resolution,
relaunch args, second-instance routing, the `window-all-closed` verdict, status
transitions and the connection view are pure functions in
`desktop/background-mode.js`, covered by 34 unit tests. Everything `main.js`
does with those verdicts is covered only by source-text regexes
(`bootstrap.test.js`, `shell-known-good.test.js`).

To test that, ten mutations were applied in a scratch copy and the full
committed suite was run against each (desktop `node --test` over the bootstrap,
background-mode, menu, shell-known-good and ota tests, plus
`tests/scripts/test_ota_publish.py`). A mutation counts as caught only if it adds
failures beyond the unmutated baseline. Results for M6 to M10:

| Mutation | Caught |
|---|---|
| M6 `maybeVouchForShellInBackground` ignores the bridge (vouches on readiness alone) | no |
| M7 `connectionBridgeReady = true` set before the bridge is checked | no |
| M8 `handleConnectionAction` drops the sender check (answers any webContents) | no |
| M9 `stopRuntimeAndRelaunch` no longer awaits the backend exit | no |
| M10 external-AI startup also creates the main window (breaks FR-002) | no |

Behaviours the uncommitted harness exercised that have **no committed test**:

- **Scenario 1 (external AI):**
  - the address is published only after the ready line *and* HTTP readiness
    (`markServiceRunning` ordering in `startBackgroundService`);
  - Copy through the main-process clipboard;
  - the second-instance dispatch in `handleSecondInstance`;
  - stop → `stopping` → `stopped`;
  - restart on the remembered port;
  - crash → `crashed`, through `trackRuntime`;
  - attach a desktop window;
  - the stop-confirm dialog when a desktop window is attached.
- **Scenario 2 (desktop remembered):** that desktop mode creates no tray (the
  counterpart of M10).
- **Scenario 3 (desktop → external-AI switch):** `promoteToExternalAi`.
- **Scenario 4 (splash closed at the picker):** quit with no backend
  (`pickModeOnSplash` → `null`), and the fallback to desktop when the picker is
  broken.
- **Scenario 5 (relaunch flag):** covered in pure form (`relaunchArgs` round
  trip). The call site is covered only by regex.

The implementer's report says the harness already drives the real `main.js`
with a stubbed `electron` module, so committing it, or targeted tests for M6-M10,
is feasible. The security-relevant pieces (M8) and the OTA-relevant ones (M6,
M7, M9) matter most.

#### P2-5. CHANGELOG entry missing for a user-visible feature

Repository practice calls for an entry:
- Recent desktop features have entries: #2159 (application menu,
  `CHANGELOG.md:306`), #2097 (shell OTA, `:391`) and #1986 (port memory,
  `:1784`).
- `27ce66aa4` (#2167) back-filled six user-visible changes that shipped without
  one. Its message says release announcements point readers at `CHANGELOG.md`
  "for the full list".
- `docs/ai-developer/specific_rules/gated-workflow.md` sections 3.3 and 3.5
  require changelog landing or an N/A rationale.

The ledger's N/A ("CHANGELOG.md is outside the A2 dispatch write set; the
manager owns changelog landing") hands the entry to the manager rather than
saying why none is needed. The checklist drift log records the owner decision
as pending. Either the manager or an amended A2 scope must land an `[#2280]`
entry under `[Unreleased] / Added` before merge.

### P3 — improvements and follow-ups

1. **File-list coverage is only partly enforced.** List-to-list parity is
   enforced: M1 (drop `connection.html` from `SHELL_FILES`) and M2 (drop
   `background-mode.js` from `build.files`) are both caught. File-to-list
   coverage scans only `require("./…")` in `main.js` and `menu.js`, plus
   `path.join(__dirname, "…")` literals in `main.js`. These pass undetected:
   - M3: a new relative require in `ota.js`;
   - M4: a new relative require in `background-mode.js`;
   - M5: a new `src=` asset in `connection.html`.

   Today the claim holds on inspection. Relative requires exist only in
   `main.js` (4) and `menu.js` (1). Both HTML files reference only
   `assets/icon.png`, which is in both lists. `appIconPath()` resolves against
   `host().appRoot` (the asar), so the window icon never needs the patch.
   Extending the scan to every shipped `.js` and to HTML `src`/`href` would make
   "the parity test enforces this" fully true.
2. **Known-good vouching is correct in code but enforced only textually.** The
   code satisfies all three conditions:
   - vouching needs `launchMode === external-ai`, `connectionBridgeReady` and
     `status === running` (`main.js:1792-1801`);
   - `connectionBridgeReady` is set only after `did-finish-load` *and*
     `Boolean(window.scistudioConnection)` (`main.js:2047-2057`);
   - a preload error calls `noteShellFault`, and `recordKnownGood` refuses
     while a fault stands.

   The tests only check that the tokens are present (M6, M7). The checklist
   section 8.3 manager-review row ("holds semantically, not only textually") is
   true of the code, not of the tests. Separately, the anchor in
   `shell-known-good.test.js`, `code.indexOf("await waitForHttpReady")`, now
   resolves to `startBackgroundService` instead of the desktop boot path. It
   still passes, but it now checks a wider slice than the test intends.
3. **The bridge check proves the preload, not the page script.**
   `window.scistudioConnection` is exposed by the preload even when a patched
   `connection.html` script throws. Vouching on the first `get-state` IPC from
   the connection window would also prove the page script and the IPC handler.
4. **The picker has no timeout or load-failure path.** `pickModeOnSplash` waits
   on `did-finish-load` with no `did-fail-load` handling and no timeout
   (`main.js:1669-1718`). Before this PR the splash was cosmetic ("must never
   break startup"); it now gates startup. Real-Electron timing of
   `isLoading()`/`executeJavaScript` has only the owner's Windows dev-run
   confirmation.
5. **Restart does nothing during a failed start.** If the backend crashes
   during the HTTP-readiness wait, the status turns `failed` and Restart shows.
   But `restartBackgroundService` is a no-op while `serviceStartInFlight` is set
   (up to `HTTP_READY_TIMEOUT_MS`, 30 s). The exit detail is then overwritten by
   the timeout message.
6. **macOS reopening fires `activate`, not `second-instance`.** Launching the
   app again from Finder or the Dock does not start a second process. So the
   FR-006 "attach desktop window" and "promote to external AI" second-launch
   routes are reachable on macOS only through `open -n` or the menus/tray.
   FR-011 says platform differences are confined to those named, so the spec
   should name this one.
7. **Stop confirms, Stop and Quit does not.** Stop asks for confirmation when a
   desktop window is attached (`main.js:1892-1919`); Stop and Quit, from the
   tray and the connection window, does not.
8. **A promoted session relaunches headless.** After a desktop → external-AI
   promotion, an OTA relaunch comes back in external-AI mode with no main
   window. That is consistent with "relaunch in the running mode", but worth the
   owner confirming.
9. **FR-008 wording.** It reads as if the tray needs a restart action. The tray
   shows the crashed status; Restart lives in the connection window. Clarify the
   wording.
10. **Address host.** ADR-055 section 7 says "`localhost:port`". The spec and
    code use the bound `127.0.0.1:<port>`, recorded with rationale in the spec's
    Edge Cases. This is a defensible spec refinement; no ADR change needed.
11. **Spec frontmatter.** `tests:` omits `tests/scripts/test_ota_publish.py`,
    which sections 4.2 and 4.4 list, and `feature_branch` still names
    `docs/2263-adr-055-specs`.
12. **User guide.** The ledger's "no user guide page covers desktop launch" N/A
    was checked: no non-API page under `src/scistudio/_user_guide/` mentions the
    desktop app. `ai-assistant.md` would be a natural home for "use SciStudio
    from an external AI tool" once the mode ships.

## 2. Claim Verification

### 2.1 Owner decisions (#2280)

| Decision | Result | Evidence |
|---|---|---|
| 1. Picker every launch, "don't ask again", changeable later | pass | `splash.html` picker, both modes and the Remember box; `resolveStartupMode`; File › Startup Mode radio (`menu.js`), tray Startup Mode, connection-window `<select>` → `set-startup` → `applyStartupSetting`. A corrupt preference falls back to the picker (unit tested). Desktop flow otherwise unchanged. |
| 2. Tray in external-AI mode only, with the five items | pass | `ensureTray` is called only from `enterExternalAiMode`. The menu has status, Open Connection Window, Copy Address, Open in Desktop Mode and Stop and Quit, plus Startup Mode (`menu.test.js`). `trayTemplate.png` is a monochrome glyph set with `setTemplateImage(true)`. The Tray is held in a module-level `let tray`. |
| 3. Backend stops with Electron; watchdog untouched; no opt-out, no adoption; `runtime-port.js` untouched | pass | `git diff --stat f87c6ad40 HEAD -- src desktop/runtime-port.js desktop/bootstrap.js desktop/ota.js desktop/preload.js` is empty, and no `no-parent-watchdog` or adoption code exists. Quitting runs `before-quit` → `stopRuntime`. Windows lifetime was reproduced (2.2). |
| 4. One backend per machine via `second-instance` | pass | The lock carries `{ requestedMode }`. `routeSecondInstance` returns show-connection-window, attach-desktop-window, focus-main-window, promote-to-external-ai or focus-splash, and never spawns a backend. Pure routing is unit tested; dispatch is untested (P2-4); macOS caveat in P3-6. |
| 5. OTA relaunch includes the background instance and honours the mode | pass, with P2-2 | All three `app.relaunch` sites go through `stopRuntimeAndRelaunch` (regex-pinned). It carries `--scistudio-launch-mode=<running mode>`, and the picker runs before the mandatory-update check. The bounded wait is weaker than documented (P2-2). |

### 2.2 Windows backend lifetime — reproduced independently

Own scripts, no Electron GUI:
- `parent.js` spawns a long-lived base-interpreter Python child with
  `spawnRuntimeCandidate`'s options (`main.js:1082-1089`: not detached,
  `windowsHide`, `stdio ["ignore","pipe","pipe"]`).
- The child spawns one grandchild.
- `driver.js` starts `parent.js` detached, runs `taskkill /F /PID <parent>`
  (no `/T`), waits 3 s, and checks all three PIDs. It then cleans up only its
  own PIDs.

| Parent runtime | Runs | Backend child after the parent kill | Grandchild |
|---|---|---|---|
| Node v24.14.0 | 3 | dead 3/3 | alive 3/3 |
| Electron 42.2.0 binary with `ELECTRON_RUN_AS_NODE=1` (Node v24.15.0) | 2 | dead 2/2 | alive 2/2 |

This matches the implementer's result. No Windows backstop is needed. The
surviving grandchild is #2281 (out of scope). Only a direct interpreter was
tested, which is the bundled `resources/python/python.exe` shape. System-Python
or launcher candidates were not re-verified. No repro process remained
afterwards (checked by PID).

### 2.3 Connection window security

- `webPreferences`: `sandbox: true`, `contextIsolation: true`,
  `nodeIntegration: false`. The preload requires only `electron` (unit tested).
- Bridge: `act(action, payload)` over one fixed invoke channel, and `onState`
  over one fixed push channel.
- Main process:
  - answers only when `event.sender === connectionWindow.webContents`;
  - rejects actions outside `CONNECTION_ACTIONS`;
  - uses a payload only for `set-startup`, normalised by `applyStartupSetting`.
- Navigation: `will-navigate` is prevented, `setWindowOpenHandler` denies, and
  the CSP is `default-src 'none'` (identical to `splash.html`). There are no
  frames, and rendering uses `textContent`/`value` only.
- What the renderer can make the main process do: copy the running address to
  the clipboard, open a desktop window on the running backend, stop or restart
  the service, open the fixed desktop log directory, change the startup
  preference, and quit. No renderer-supplied path, URL or command reaches the
  main process.
- Gap: the sender check has no test (M8).

### 2.4 Shell OTA lists

- `background-mode.js`, `connection-preload.js`, `connection.html` and the four
  tray images are in both `desktop/package.json` `build.files` and
  `scripts/ota_publish.py` `SHELL_FILES`.
- `bootstrap.js` and `package.json` are bundled but never published, so runbook
  section 5 holds.
- The APIs used (`requestSingleInstanceLock` additional data, `Tray`,
  `setTemplateImage`, `setWindowOpenHandler`, `shell.openPath`) all predate
  Electron 42.2.0, the pinned version, and the patched shell uses no new host
  facts from the frozen loader.
- Enforcement strength is covered in P3-1.

### 2.5 Spec-silent choices (checklist drift row A2)

| Choice | Assessment |
|---|---|
| A second launch passes only an explicit flag or a remembered choice | Correct: the second process quits before it could ask. Consistent with decision 4. |
| Desktop → external-AI switches in place on the same backend | Correct under "one backend per machine". A relaunch afterwards is headless (P3-8). |
| In external-AI mode, closing the last window quits only once the service is stopped, crashed or failed | Consistent with ADR section 7 ("closing the connection window … does not stop an active analysis"). The later-crash case contradicts the spec's own edge case (P2-3). |
| Relaunch stops, waits up to 8 s, and returns in the running mode without the picker | Consistent with decision 5. The stated SIGKILL basis is false on POSIX (P2-2). |
| External-AI known-good vouching (FR-013) | Necessary and correct in code. It does not cover the picker-quit path (P2-1), and enforcement is textual (P3-2). |
| Picker runs before the mandatory-update check | Correct: it makes an applied mandatory update relaunch into the chosen mode. |
| Address is the bound `127.0.0.1:<port>` | Defensible refinement of the ADR's "localhost:port" (P3-10). |
| Stop with a desktop window attached asks for confirmation | Sensible. Stop and Quit is inconsistent with it (P3-7). |
| CHANGELOG recorded N/A (outside the write set) | Not an N/A under repository practice (P2-5). |

### 2.6 Decision logic placement

Mostly in `background-mode.js`, as the claim says: 19 exported pure functions
(plus 13 constants) under unit test. A few decisions remain inline in `main.js`:
- the vouching conditions (`maybeVouchForShellInBackground`);
- the stop precondition, which duplicates `connectionView.canStop`;
- confirm-when-attached;
- the `openDesktopWindow` fallback;
- `startBackgroundService`'s choice between `stopped` and `failed` after a
  failed start.

Of these, only the vouching rule carries OTA risk (P3-2). The untested
orchestration is P2-4.

## 3. Checklist And Scope Drift

- **Scope:** all 18 changed files are inside the A2 write set and the ledger's
  declared scope. `desktop/preload.js` was declared but is untouched. There are
  no `src/`, `runtime-port.js`, `bootstrap.js` or `ota.js` edits, and no
  governance-surface edits (`governance_touch: false` is correct).
- **Checklist 8.3 manager-review row:** overstates what the tests enforce
  (P3-2). Neither Codex P2 review comment (P2-2, P2-3) appears in the checklist
  or drift log.
- **Checklist 8.3 Windows row:** reproduced independently (2.2).

## 4. Tests, Docs, Gate Evidence, CI

| Check | Result |
|---|---|
| `desktop` `npm ci` + `npm test` (audit worktree @ `5c0ddefac`) | 193/193 pass |
| `pytest tests/scripts/test_ota_publish.py --no-cov` | 43 passed. With the default `addopts`, the run fails only the repository-wide 70% coverage gate, which is expected for a single-file run. |
| CI at `5c0ddefac` | 16/16 pass. The `Desktop` job runs `node --test test/*.test.js`: 193 pass in its log. |
| Implementer ledger `.workflow/records/2280-feat-2280-local-background-runtime.json` | Tier 1 `feature`. The observed diff matches the 18 files. One `python_tests` failure was re-run to pass, and the final reconcile is `pre-pr` pass with no unsatisfied obligations. PR #2284 provenance is recorded. Docs are the spec plus three N/As (CHANGELOG, see P2-5). Tests list 4 paths. All three commits carry the Gate-Record, Task-Kind, Issue and Assisted-by trailers. |
| Live evidence | Manager-run Windows dev launch (checkout shell, build 0), with the launch-mode flow owner-verified (PR comment, 2026-09-11). Still pending: macOS/Linux installed builds, and any packaged patched-shell run in external-AI mode (P2-1, FR-013). |
| Sentrux | N/A: Sentrux MCP and CLI are unavailable in this runtime. |
| Frontend/browser smoke | N/A: no frontend change. |

Missing: a CHANGELOG entry (P2-5); committed orchestration tests (P2-4);
installed-build runs on macOS/Linux, and a packaged patched-shell run
(manager/owner e2e).

## 5. Recommendation

**pass-with-fixes.** Before merge, fix P2-1 to P2-5 or have the owner accept
them with tracked issues. P2-2 and P2-3 are also open automated-review threads
on the PR. P3 items can be tracked as follow-ups.
