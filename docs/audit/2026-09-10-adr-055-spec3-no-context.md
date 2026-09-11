# Audit: ADR-055 Spec 3 — Local Startup Modes And The Background Runtime (no-context)

- Date: 2026-09-11 (report path fixed by dispatch as 2026-09-10)
- Persona: audit_reviewer, `no-context` mode
- Branch / worktree: `audit/2280-spec3-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2280-spec3-nc`
- Change under review: `origin/main...origin/feat/2280-local-background-runtime`
  (`origin/main` = `ca54fe77`, merge base = `f87c6ad4`, branch head = `5c0ddefa`)
- Judged against: `docs/specs/adr-055-local-background-runtime.md` (the spec),
  `docs/adr/ADR-055.md` section 7, `docs/specs/desktop-shell-ota-hot-update.md`,
  and the code and tests themselves.

Per the dispatch I did not read any issue or PR, anything under
`docs/planning/**`, any commit message, or any `.workflow/records/**` ledger
other than the one this audit creates. Everything below comes from the source
tree, the docs listed above, and commands I ran myself. I did not launch the
Electron app.

## 0. What I Ran

| Command | Result |
|---|---|
| `cd desktop && npm ci && npm test` | 193 tests, 193 pass |
| `pytest tests/scripts/test_ota_publish.py -o addopts="" -q` | 43 pass. With the repository's default `addopts` the single-file run exits non-zero on the global 70% coverage floor (3.01%); no test fails. |
| `git show origin/main:desktop/main.js` (lifecycle handlers, `stopRuntime`) | baseline for "new vs pre-existing" (§1, §2) |
| Node repro `killed-semantics.js` (Node 24.14.0): spawn a child, `kill("SIGTERM")`, read `child.killed` | `killed: true`, `exitCode: null`, `signalCode: null` right after `kill()` returns (§2, P2-2) |
| Node repro `winjob-driver.js`, 3 runs: detached stand-in parent spawns a child with `main.js`'s spawn options; `taskkill /F /PID <parent>` without `/T`; check after 3 s | child dead in 3/3 runs (§4, FR-005) |
| PNG header/pixel decode of `desktop/assets/tray*.png` | colour icons 16/32 px; template icons 16/32 px, single colour (black) under alpha (§4, FR-012) |
| `grep` of `app.quit(`, `windowAllClosedAction`, and relative `require("./…")` across `desktop/*.js` | §2 P2-1, §4 packaging |
| `gate_record init` / `gate_record check --mode local` | see §6 |
| Sentrux | N/A. Not available in this runtime. |

## 1. Summary Judgement

**Recommendation: pass-with-fixes.** No P1 findings. Two P2 findings and seven
P3 findings.

The spec and code agree on the main contracts. The launch-mode choice and its
persistence match, and so do relaunch mode carry-over and second-instance
routing. The address comes from the ready line on `127.0.0.1`. Desktop-mode
`window-all-closed` still always quits. The connection-window sandbox and IPC
checks match the spec, and the shell OTA and installer file lists agree. I
independently re-ran the spec's Windows backend-lifetime check, and it holds.

Both P2s are lifecycle problems in `desktop/main.js` that the pure-function tests
cannot catch:

- **P2-1:** external-AI mode can stay resident with no backend, against the
  spec's quit rule.
- **P2-2:** the SIGKILL escalation the spec relies on never fires. This bug
  already exists on `origin/main`, but this branch makes it reachable from a new
  user-visible state.

## 2. Findings

### P2-1 — External-AI mode stays resident with no backend after a stop or crash that completes while no window is open (new)

**Contract.** Spec §4.1, "Window-closed semantics": external AI mode "stays
resident while its backend is starting, running, not responding, or stopping,
and quits once the backend is stopped, crashed, or failed." Spec Edge Cases:
"External AI mode with the service stopped, crashed, or failed and every window
closed: the app quits, since it has no backend left to own and, on a Linux
desktop without a tray host, would otherwise be invisible."

**Code.** The quit decision is evaluated only inside the `window-all-closed`
handler (`desktop/main.js:2251-2262`). `windowAllClosedAction` has exactly one
call site (`main.js:2254`). Status transitions go through `setServiceState`
(`main.js:1769-1774`), which pushes the view, updates the tray, and tries to
vouch for the shell. It never re-evaluates residency. None of the `app.quit(`
call sites (`main.js:128, 609, 627, 643, 1983, 2186, 2242, 2260`) is driven by a
status change.

**Reachable sequences** (both derived from the code; I did not run them in
Electron):

1. Service running, connection window open. Click **Stop Service**
   (`stopBackgroundService`, `main.js:1892-1919`), and the status becomes
   `stopping`. Close the connection window before the backend has exited.
   `window-all-closed` fires with `stopping`, which is in `LIVE_STATUSES`
   (`background-mode.js:90-95`), so the verdict is `stay`. The backend then
   exits, `trackRuntime` sets `stopped` (`main.js:1821-1829`), and nothing
   quits.
2. The normal background state: connection window closed, service running. The
   backend dies, `trackRuntime` sets `crashed`, and nothing quits.

**Effect.** A resident Electron process with no backend and no window. On
Windows and macOS the tray still shows "Stopped" or "Stopped unexpectedly". On a
Linux desktop without a tray host the process is invisible until SciStudio is
launched again, which reaches it through `second-instance`. That invisible case
is exactly the one the spec's edge case exists to prevent. This is new with this
branch: on `origin/main`, `window-all-closed` always calls `app.quit()`
(`origin/main:desktop/main.js:1565-1567`).

**Spec tension to resolve.** FR-008 wants a crash "while the app is resident" to
surface "in the connection window and tray as a crashed status with a restart
action". Quitting on every crash while windows are closed would make that
impossible. The current code keeps the app resident in that case, which may be
intended, but the spec does not say so.

**Fix, either direction:**

- Re-evaluate `windowAllClosedAction` on each status change when
  `BrowserWindow.getAllWindows().length === 0`, at least for the
  `stopping` → `stopped` path.
- Or amend spec §4.1 and the edge case to state that the rule is evaluated only
  when the last window closes. A stop or crash that completes afterwards would
  then leave the app resident, reachable from the tray or by launching again.

**Tests.** `desktop/test/background-mode.test.js` pins the pure verdict only. The
`bootstrap.test.js` check "window-all-closed follows the launch mode…" asserts
that the handler source contains the call. Neither covers a transition after the
windows have closed.

### P2-2 — `stopRuntime`'s SIGKILL escalation never fires; the spec relies on it and the new Stop action can hang at "Stopping…" (pre-existing code, newly relied on)

**Contract.** Spec §4.1, "Relaunch": "wait for the backend to exit (bounded at
8 s; `stopRuntime`'s own SIGKILL escalation fires at 5 s)". `main.js:65-67`
repeats that claim.

**Code.** On POSIX, `stopRuntime` (`main.js:1543-1548`) sends SIGTERM, then
after 5 s runs `if (!child.killed) child.kill("SIGKILL")`. Node sets
`child.killed = true` as soon as `kill()` delivers a signal, not when the child
exits. After a successful SIGTERM the guard is always false, so the escalation
is dead code.

**Evidence.** In the Node 24.14.0 repro, immediately after `kill("SIGTERM")`
returned `true`: `{"killed":true,"exitCode":null,"signalCode":null,"wouldEscalate":false}`.
The code is byte-identical on `origin/main`
(`origin/main:desktop/main.js:1475-1497`), so the defect is pre-existing.

**What this branch adds.** The branch introduces two paths that depend on the
escalation. Both apply only on POSIX; Windows uses `taskkill /T /F` in
`stopRuntime`.

- **Explicit Stop.** If the backend does not exit on SIGTERM, the status stays
  `stopping` indefinitely. That view has `canStop: false` and
  `canRestart: false` (`background-mode.js:357-358`), so the connection window
  offers only **Stop and Quit**. This is the "stop leaves the UI lying about
  state" case. Stop and Quit then recovers: Electron exits and the unchanged
  POSIX parent watchdog reaps the backend.
- **`stopRuntimeAndRelaunch`.** The relaunch waits the full 8 s, then goes ahead
  with the old backend still alive until the watchdog reaps it. That takes up to
  about 5 s after Electron exits (`PARENT_WATCH_INTERVAL_S = 2.0` plus
  `ORPHAN_SHUTDOWN_GRACE_S = 3.0` in
  `src/scistudio/desktop/parent_watchdog.py:27-28`). Meanwhile the relaunched
  process's port probe can find the remembered port taken and fall back to an
  ephemeral one. That changes the address an AI tool holds, which is exactly
  what §4.1 says the wait prevents.

**Not verified.** I did not check how often the real backend outlives SIGTERM
for more than 5 s. That needs a POSIX machine and a running backend.

**Fix.** Escalate on `child.exitCode === null && child.signalCode === null`
instead of `!child.killed`, or correct the spec sentence.

### P3-1 — Restart does nothing for up to 30 s after a backend dies during HTTP readiness, and the crash detail is then overwritten

In `startBackgroundService` (`main.js:1837-1888`), a backend that exits during
`waitForHttpReady` is set to `failed` at once by `trackRuntime`. `canRestart`
becomes true, but `serviceStartInFlight` stays true until `waitForHttpReady`
times out (`HTTP_READY_TIMEOUT_MS = 30000`). Until then
`restartBackgroundService` is silently rejected by the guard at
`main.js:1838`. The catch block then replaces the exit detail ("The SciStudio
service exited (code …)") with the less accurate "Timed out waiting for
SciStudio HTTP endpoint".

### P3-2 — A relaunch issued while a Stop is still in progress does not wait for the backend

`stopRuntimeAndWait` (`main.js:1555-1569`) keys off `runtimeProcess`, but
`stopRuntime` sets it to null as soon as the signal is sent (`main.js:1532-1533`).
If Stop was pressed and an OTA or package-update relaunch follows while the
backend is still exiting, the relaunch sees `runtimeProcess === null` and does
not wait. That reopens the port race FR-007 exists to close. `serviceChild`
still references the exiting process and could be the handle to wait on.

### P3-3 — Stop and Quit skips the confirmation that Stop Service asks for

The spec edge case says "The service is stopped while a desktop window is
attached to it: the app asks for confirmation first". `stopBackgroundService`
does ask (`main.js:1897-1910`). `stopAndQuit` (`main.js:1981-1984`), reached from
the tray and from the connection window's **Stop and Quit**, calls `app.quit()`
without asking, even with an attached desktop window holding unsaved work.

### P3-4 — New lifecycle tests are source-text checks; `main.js` glue has no behavioural coverage

- The six new `desktop/test/bootstrap.test.js` checks (relaunch helper, tray
  reference, background vouching, `window-all-closed`, `__dirname` files) are
  regexes and substring searches over `main.js`. For example, the vouching test
  passes even if `maybeVouchForShellInBackground` is never called. The
  `window-all-closed` test passes whatever status is passed.
- Nothing exercises `startBackgroundService`, `stopBackgroundService`,
  `trackRuntime`, the `handleConnectionAction` sender check, or
  `handleSecondInstance`. P2-1, P2-2, P3-1 and P3-2 all live in that untested
  glue.
- `windowAllClosedAction` discards `platform` (`background-mode.js:290`,
  `void platform`). The per-platform loops in `background-mode.test.js:266-295`
  therefore cannot fail per platform. The behaviour that actually differs by
  platform lives untested in `main.js`: the macOS `activate` dock reopen, the
  Windows tray left-click, and the macOS template image.
- No test ties the HTML `src=` references in `splash.html` and
  `connection.html` to `build.files` or `SHELL_FILES`. By hand: both reference
  only `assets/icon.png`, which both lists carry.
- The require-parity tests scan only `main.js` and `menu.js`. By grep, no other
  shell module has a relative require today, so this is currently sufficient.

The spec's §4.4 names installed-build e2e on all three platforms as a
manager/owner step. This audit could not observe that.

### P3-5 — macOS re-launch probably never reaches `second-instance`; this platform difference is not named in the spec (unverified here)

On macOS, opening an already-running app from Finder or the Dock normally
activates the existing process rather than starting a second one. If so, the
running app gets `activate` (`main.js:2264-2273`), which shows the main window or
the connection window, and a remembered desktop preference is never routed. The
spec's User Story 3 scenario 2 and FR-006 "attach a desktop window" path would
then be reachable on macOS only from the CLI (`open -n`, or the flag). FR-011
confines per-platform differences to those the spec names, and this one is not
named. I have no macOS machine here to confirm.

### P3-6 — Documentation drift

- `docs/specs/desktop-shell-ota-hot-update.md` §6 (lines 218-231) shows the
  snapshot's `shell/` holding five files. `SHELL_FILES` now has 14.
  `menu.js` and `assets/icon.png` were already missing from that diagram on
  `origin/main`; this branch adds `background-mode.js`, `connection-preload.js`,
  `connection.html` and four tray images.
- Spec frontmatter: `feature_branch: docs/2263-adr-055-specs` names the docs
  branch, not the implementing branch. `tests:` omits
  `tests/scripts/test_ota_publish.py`, although §4.2 lists it as modified and
  §4.4 relies on it. `status: Draft` sits alongside a §4.4 that reports
  completed verification.

### P3-7 — FR-013 vouching in external-AI mode proves only the connection window

`maybeVouchForShellInBackground` (`main.js:1792-1801`) records known-good once
`connection.html` and `connection-preload.js` load and the backend runs. A patch
that broke `preload.js` or the main window would be written to
`known-good.json` (the backend rollback target) by an external-AI launch. The
crash-loop guard itself is unaffected: `ota.shellMarkerAction` returns `record`
on every launch of a patch (`desktop/ota.js:202-210`), so a later desktop
launch that fails to paint still gets quarantined. Informational.

## 3. Where Spec And Code Agree (checked)

- **Launch choice (FR-001).** Implemented by `resolveStartupMode`,
  `parseModePreference`, `preferenceAfterPick`, `applyStartupSetting` and
  `splash.html` `__scistudioSplashPickMode`. The picker runs before
  `maybeEnforceMandatoryUpdate` (`main.js:2182-2194`). Closing the splash while
  it is asking quits (`main.js:2183-2188`). An unusable answer falls back to
  desktop (`main.js:1697-1710`). Startup Mode is changeable from the File menu,
  the tray and the connection window, all through `setStartupSetting`.
- **External AI start (FR-002, FR-003).** Same chain as desktop:
  `startRuntimeWithRollback`, then `waitForHttpReady`, `rememberRuntimePort` and
  `clearCacheOnBuildChange`. No `createWindow`. The address appears only when
  the status is `running` (`connectionView`). The connection window can be
  reopened from the tray, File › External AI Connection, `activate` and
  `second-instance`.
- **Address (FR-010).** Taken from the ready line. `scistudio gui --bundled`
  prints `http://127.0.0.1:<bound port>` (`src/scistudio/cli/main.py:439-455`).
  ADR-055 §7 says "localhost:port". The spec's deliberate use of `127.0.0.1` is
  explained in its Edge Cases and is consistent with the backend.
- **One backend (FR-006).** `startBackgroundService` refuses while a start is in
  flight or a child is tracked. Promotion and attach reuse the running backend.
  No path spawns a second one.
- **Relaunch (FR-007).** `app.relaunch` is called only inside
  `stopRuntimeAndRelaunch` (`main.js:1575-1585`). The package-update, mandatory
  OTA and optional OTA paths all await it. `relaunchArgs` carries the running
  mode.
- **Window-closed per mode.** Desktop mode always quits, the same as
  `origin/main`. External AI mode follows `LIVE_STATUSES`, subject to P2-1.
- **Backend lifetime (FR-005).**
  - `parent_watchdog.py`, `cli/main.py` and `runtime-port.js` are unchanged in
    the diff, as §4.2 states.
  - Windows: my own Node repro reproduced the §4.4 claim. A non-detached child
    spawned with `main.js`'s options died with its force-killed parent in 3/3
    runs.
- **Connection window security.**
  - `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`.
  - The preload requires only `electron` and exposes only `act` and `onState`.
  - The main process answers only `connectionWindow.webContents`
    (`main.js:1987`), whitelists action names (`main.js:1990`), and normalises
    the `set-startup` payload.
  - Navigation and `window.open` are denied. CSP is `default-src 'none'`. The
    window menu is removed. `preload-error` is treated as a shell fault.
- **Tray (FR-012).** Exists only in external AI mode (`enterExternalAiMode`).
  Held at module level (`let tray = null`, `main.js:82`). The menu entries match
  FR-012. The macOS template images are single-colour black under alpha, and
  `setTemplateImage(true)` is set. The @2x siblings exist.
- **Shell packaging.** Every relative require (`./ota`, `./menu`,
  `./runtime-port`, `./background-mode`), every `path.join(__dirname, …)` file,
  every HTML asset reference (`assets/icon.png`) and every tray image appears in
  both `desktop/package.json` `build.files` and `scripts/ota_publish.py`
  `SHELL_FILES`. `test_fake_desktop_covers_every_published_file` keeps the
  pytest fixture complete.
- **Shell known-good (FR-013).** Implemented, subject to the scope note in
  P3-7.

## 4. What I Could Not Verify

- No installed-build run on any platform. §4.4's e2e step, including the five
  user stories, the macOS light and dark menu bars, and a Linux desktop with no
  tray host, is outside what this audit could observe.
- POSIX behaviour (P2-2's practical frequency, the parent watchdog timing) and
  macOS relaunch routing (P3-5) need machines this runtime does not have.
- The WebMCP session in the page served at the shown address (User Story 1
  scenario 2) is spec-1 territory and was not exercised.

## 5. Recommendation

**pass-with-fixes.** Before merge, resolve P2-1, either in code or by amending
spec §4.1 and the edge case, and correct P2-2's escalation guard or the spec
sentence that relies on it. The P3 findings can be tracked as follow-ups.

## 6. Gate Evidence

- `gate_record init --task-kind maintenance --persona audit_reviewer --runtime claude-code:claude-opus-5 --branch audit/2280-spec3-no-context --base-ref feat/2280-local-background-runtime --include docs/audit/2026-09-10-adr-055-spec3-no-context.md`
  created this audit's ledger.
- `gate_record check --mode local --base origin/feat/2280-local-background-runtime --head HEAD`,
  run on `da013b31` (the commit that first added this report): tier 2, with
  checks `commit_hygiene`, `format_check`, `full_audit` and `lint_format`, all
  of which passed. The only unsatisfied obligation was `guard.issue_link` ("at
  least one linked issue is required").
- Known gap: no issue is linked. Per the dispatch's context limits I did not
  look one up.
- Sentrux: N/A, unavailable in this runtime.
