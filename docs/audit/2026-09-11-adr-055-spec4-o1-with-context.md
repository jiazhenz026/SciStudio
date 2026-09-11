---
title: "Audit — ADR-055 Spec 4 O1 capability-gated enterprise UI and seam project access (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 52
  - 42
related_specs:
  - adr-055-enterprise-support
  - adr-055-identity-seam
language_source: en
---

# Audit — ADR-055 Spec 4 O1 Capability-Gated Enterprise UI And Seam Project Access (with-context)

Audit mode: **with-context** (agent AU1, `audit_reviewer` persona, task kind
`docs`).

Subject: PR #2336, branch `feat/2322-enterprise-ui` @ `79cfe2b7d`, based on
`origin/main` @ `8f90db3ef`. The PR changes 41 files (+5437/-224).

Context:

- Issues: #2322 (O1) and #2328 (seam project access). The shared capability
  contract is in umbrella issue #2321.
- Umbrella PR: #2323 `[DO NOT MERGE]`.
- Checklist: `docs/planning/adr-055-spec4-checklist.md` §7, on
  `track/adr-055-spec4`.
- Dispatch prompt: A1 in `docs/planning/adr-055-spec4-dispatch-prompts.md`.

Ledgers:

- Gate ledger under audit: `.workflow/records/2322-feat-2322-enterprise-ui.json`.
- Audit gate ledger: `.workflow/records/2322-audit-2322-o1-with-context.json`.

**Verdict: block until P1-1 is fixed.** The capability contract is implemented
as #2321 describes, and so are the #2328 wrappers. All 278 backend tests and
227 frontend tests in scope pass.

The capability injection is script-safe. Every script-breakout payload I
probed stayed inside its string literal, at the root mount and under
`/user/alice/scistudio`. URL validation rejects every scheme, `//`, backslash,
whitespace and control-character case I tried.

One defect lets an unauthenticated WebSocket past any replacement guard, and
it spawns a PTY. The PR introduces it, and no test covers it. The fix is
small and local. Besides that, CI has one red check, and four P2 findings
need either a fix or an owner decision.

## 1. Findings

### P1 — blocks merge

#### P1-1. `/api/ai/pty/internal` (no trailing slash) bypasses the replacement guard and reaches the PTY WebSocket, which spawns a shell

`internal_routes.py:64` registers `/api/ai/pty/internal/` through
`register_self_authenticating_prefix`. The seam normalizes it to
`/api/ai/pty/internal`. `is_self_authenticating_path` (`seam.py:317`) then
matches that exact path as well as everything below it:
`path == prefix or path.startswith(f"{prefix}/")`.

The exact path is not only the parent of the two internal routes. It is also
a complete match for the user-launched PTY WebSocket route
`@router.websocket("/pty/{tab_id}")` (`websocket.py:35`, under `/api/ai`), with
`tab_id = "internal"`. `GuardDispatchMiddleware` (`seam.py:201`) therefore
sends a WebSocket upgrade to `/api/ai/pty/internal?provider=...&project_dir=...`
straight past whichever guard is installed. `pty_endpoint` does no
authentication of its own: it accepts, validates the query, and calls `_spawn`.

Reproduced with a throwaway probe (uncommitted). The probe uses
`create_app(guard=FakeCookieGuard)` with no session cookie, and replaces
`_spawn` with a recorder.

| Mount | Request | Result |
|---|---|---|
| `/` | `WS /api/ai/pty/tab-1?provider=user-terminal&project_dir=…` (control) | refused at handshake, code 1008 |
| `/` | `WS /api/ai/pty/internal?provider=user-terminal&project_dir=…` | **accepted; `_spawn(provider="user-terminal", …)` reached** |
| `/user/alice/scistudio` | same control | refused, 1008 |
| `/user/alice/scistudio` | `WS /user/alice/scistudio/api/ai/pty/internal?…` | **accepted; `_spawn` reached** |
| both | `WS …/api/ai/pty/internal/?…` (trailing slash) | no route; closed |
| both | `%2e%2e`, `..%2F`, `internal%2F..` HTTP variants | 404, reaching no route |

The route walk confirms that `'/api/ai/pty/{tab_id}'` is the only route whose
regex fully matches `/api/ai/pty/internal`.

Impact:

- In an edition, anyone who can reach the service prefix gets an interactive
  shell as the backend's OS user, with no login. The enterprise Hub guard is
  the reason this prefix was registered at all. Behind JupyterHub the proxy
  forwards `/user/<name>/…` without authenticating, and the single-user guard
  is the only check. Without `ai_chat_disabled`, the same request can also
  start any agent provider.
- The open-source edition's exposure is unchanged. The default loopback guard
  only covers `/api/webmcp/*` (`app.py:462-472`), so the PTY WebSocket was
  never behind a guard there.

Why the tests miss it:

- `tests/api/test_ai_pty_internal_guard.py::_internal_route_paths` lists only
  routes that start with `prefix + "/"`.
- `test_the_rest_of_ai_pty_stays_behind_the_replacement_guard` checks
  `/api/ai/pty/tab-1`, but not the bare prefix.
- The docstring's claim that "the prefix is matched on segment boundaries, and
  the rest of `/api/ai` stays behind the replacement guard" is therefore false
  for this one path.

The spec is also involved. Identity seam FR-007 and its docstring tell a
registrant to "register the narrowest prefix that covers those routes". They
do not warn that the prefix path itself is exempted too, or that it can
collide with a parameterized sibling route.

Fix options, for the manager and owner to pick:

- (a) Refuse `tab_id == "internal"` in `pty_endpoint` before `accept()`. This
  is local to `ai_pty/**`, which is in A1's write set.
- (b) Register a prefix that no sibling route can match exactly. Today the
  seam cannot express this.
- (c) Change the seam so that a prefix covers only paths strictly below it
  (`startswith(prefix + "/")`). This is a provisional seam change that needs
  a changelog entry. It would also cover the future `/api/panels/t/` prefix
  (#2288), which has the same shape of risk if a `/api/panels/{id}` route
  exists.
- (d) Have `register_self_authenticating_prefix` refuse a prefix whose exact
  path is matched by a route that is not self-authenticating.

Whichever option is chosen, add a regression test at both mounts: a WebSocket
and an HTTP request to the bare `{mount}/api/ai/pty/internal`, under the fake
guard, must be refused by the guard.

### P2 — fix before completion

#### P2-1. CI is red: the "Deferral discipline ratchet" fails on the word "placeholder"

`python scripts/deferral_scan.py --diff origin/main` (CI run 34596585667)
flags four lines in `src/scistudio/api/seam.py`: lines 330, 393, 395 and 418.
Each one uses "placeholder" in its literal sense, the `{path}` slot of a
download template. None is a deferral, but CI requires the check to pass.

Every other check on PR #2336 passes, including Python 3.11 and 3.13,
Frontend, E2E, Full Audit, Type Check and CodeQL.

The local `gate_record check --mode pre-pr` selects `deferral_discipline` and
still reports "reconciliation passed". The local ledger check and the CI
ratchet therefore disagree. The ledger is not wrong, but it does not prove
this check.

Fix: rename the constant and the docstrings (for example "the `{path}`
marker"). The alternative is the scanner's documented false-positive route: a
tracked `TODO(#NNN)` and a refinement of the EXCLUSIONS list.

#### P2-2. Restart can be confirmed on a stale `runs_active`, so the runs-active warning can be skipped

In `UpdateNotice.tsx:102-107`, `openConfirmation` opens the dialog and calls
`void refresh()` without awaiting it. The dialog renders from the last poll,
which can be up to 60 s old. The confirm button (`:75-80`) is disabled only
while `restarting`.

If runs became active since the last poll, the user sees "Restart now" with no
warning. They can confirm before the fresh `GET status_url` answers, and the
POST then stops those runs. FR-007 says Restart "MUST warn when runs are
active".

Codex flagged the same race on the PR (inline comment, rated P1). I rate it
P2: the gap is one poll interval plus a round trip, and the edition's restart
route can re-check. The spec wording is a MUST, though, and the fix is local.

Fix: keep Confirm disabled until the refresh after opening resolves, render
the dialog from that answer, and add a test in which `runs_active` flips
between the poll and the click.

#### P2-3. `ai_chat_disabled` also hides tutorial replays, and the CHANGELOG says the opposite

`TerminalTabs.tsx:124` files every `source === "tutorial-replay"` tab under the
`chat` surface. `BottomPanel` now hides that surface, and never mounts it,
when `aiChatDisabled` is set. A Learning Center replay therefore has nowhere
to render.

The contract says otherwise:

- The A1 prompt (step 5) says: "`user-terminal`, including tutorial-replay
  adoption, is never gated".
- The backend honors that: `test_tutorial_replay_is_joined_under_the_terminal_provider`
  passes.
- The CHANGELOG entry (#2322, "Added") says "The Terminal, and a tutorial
  replay that plays into it, still work". The UI does not bear that out.

The implementer reported this as a known gap.

Fix options, for the owner:

- (a) When the chat surface is hidden, file replays under the Terminal surface
  and route replay steps there. `BottomPanel.parts/**` is in A1's set;
  `AIChat/TerminalTabs.tsx` would need a `gate_record amend`.
- (b) Accept the gap, correct the CHANGELOG, and track it with a
  `TODO(#NNN)` and an issue.

#### P2-4. Bring In My Work stays visible with `ai_chat_disabled` and ends in HTTP 500 after writing a brief

The Toolbar still shows the Bring In My Work entry. The dialog collects every
answer. Then `create_work_import_session` (`work_import.py:283-306`) writes the
session brief under `.scistudio/`. After that, `open_work_import_tab` raises
`AgentSessionsDisabledError`, a `RuntimeError` whose message does not contain
"cap", and the route maps it to **500**.

No process starts, so FR-006's "no spawned process" holds, and the message is
clear. But:

- a policy refusal is reported as a server fault;
- an orphan brief is left in the project;
- an AI entry point stays in the UI, even though `Toolbar.tsx` was in A1's
  write set.

The implementer reported this as a known gap.

Fix:

- Hide the entry when `aiChatDisabled` is set (Toolbar, in scope).
- Have `work_import.py` refuse before composing the brief, with a 4xx status.
  That file is outside A1's set, so it needs a manager amend or a
  `TODO(#NNN)` with a follow-up issue.

#### P2-5. The upload listener's `started` event fires only after the whole body has arrived, so it cannot count uploads "in flight"

FastAPI resolves `UploadFile = File(...)` by awaiting `request.form()`
(`fastapi/routing.py:406`) before the endpoint runs. By the time
`upload_data` calls `notify_upload_listeners(..., "started")` (`data.py:121`),
the entire multipart body has already crossed the network and been spooled.
That is also why `file.size` is already the full size at that point.

When a client cancels mid-transfer (the new Cancel button), the request never
reaches the handler, so neither `started` nor `discarded` fires.

This contradicts four places:

- FR-027 and the `add_upload_listener` docstring give the reason for
  `started` as "so an edition can count uploads in flight as activity". That
  was the reason the edition consumer asked for the status (drift log,
  2026-09-11).
- `data.ts` says "The route streams the body into a staged file and discards
  it when the request is aborted". Starlette discards its own spooled file on
  disconnect; the route never runs.
- `test_the_started_event_fires_before_the_file_is_placed` proves only
  "before placement", not "before receipt".

Fix: correct FR-027, the seam docstring, the `data.ts` comment and the
CHANGELOG, and tell the edition that `started` marks the staging copy, not the
network transfer. True in-flight notification would need a streaming upload
route, which is out of scope and needs a tracked follow-up if the owner wants
it.

### P3 — improvements and follow-ups

- **P3-1. Route-path validation accepts dot segments.**
  - `UpdateCapability(status_url="/../../user/bob/x", …)` is accepted, and
    the frontend's `isRoutePath` accepts it too.
  - `apiUrl` yields `/user/alice/scistudio/../../user/bob/x`, and the browser
    normalizes that to another user's server on the same Hub origin.
  - Editions are trusted, so this is hardening only. The contract does say
    "resolved under the service prefix", so reject `.` and `..` segments on
    both sides.
- **P3-2. Backend and frontend validation disagree on U+FEFF.**
  - Python's `str.isspace()` accepts it, while JavaScript's `/\s/u` rejects
    it.
  - A declared URL containing a BOM is therefore accepted at boot but read as
    off in the browser, silently.
- **P3-3. The upload path degrades if the project changes mid-upload.**
  - `notify_upload_listeners` recomputes the root on every call.
  - If the active project changes or closes between `started` and
    `completed`, the listener receives `destination.name` instead of the
    project-relative path. Codex raised the same point on the PR, rated P2.
  - Fix: capture the relative path once, when staging.
- **P3-4. CodeQL alert on `internal_routes.py:115`.**
  - CodeQL reports "Information exposure through an exception" (alert 286)
    for the new `return {"tab_id": None, "error": str(exc)}`.
  - The message is the fixed `agent_session_refusal` sentence, and the route
    requires the IPC token, so the alert is benign.
  - Either return the message from `agent_session_refusal` directly, or
    dismiss the alert with this rationale.
- **P3-5. The refusal flag is process-wide.**
  - `_agent_sessions_disabled` is set by the lifespan and cleared at any
    app's teardown.
  - Two apps in one process (tests, or an embedding edition) can clobber each
    other. The code comment documents the process-wide scope; consider
    keying the flag per app later.
- **P3-6. Two different types share the name `ToolRefusal`.**
  - `scistudio.api.seam.ToolRefusal` is an exception.
  - `scistudio.ai.agent.mcp.tools_workspace.ToolRefusal` is the Pydantic
    refusal model; the seam imports it as `RefusalDetail`.
  - The name is the #2328 contract. A one-line cross-reference in both
    docstrings would help readers.
- **P3-7. The canonical-root table is not updated.**
  - `src/scistudio/_agent_reference/public-api.md` was in A1's include set,
    but its `scistudio.api.seam` row still omits the #2328 project-access
    names.
  - The generated reference pages were regenerated.
- **P3-8. A mypy error in the tests predates this PR.**
  - `tests/api/test_identity_seam.py:171` reports `"object" not callable`.
  - The line is identical on `origin/main`, and CI's Type Check covers only
    `src/`. It is not introduced here and needs no action in this PR.

## 2. Claims Verified

| Claim | Evidence | Result |
|---|---|---|
| `identity.logout_url` optional | `seam.py:376-382`; `capabilities.ts` `readIdentity` | verified |
| `TransferCapability {inline_max_bytes, download_url_template}`, exactly one `{path}` | `seam.py:404-419`; probe: `{path}{path}`, no placeholder, `{PATH}` rejected | verified |
| `ai_chat_disabled` bool | `seam.py:475, 491` | verified |
| `UpdateCapability {status_url, restart_url}` | `seam.py:438-443` | verified |
| URLs are route paths without the prefix; scheme, `//`, whitespace, control characters and backslash rejected | `_validate_route_path`; probe rejected `https:`, `//`, `/\`, `javascript:`, space, NBSP, U+2028, DEL, relative, empty | verified (dot segments: P3-1) |
| Absent means off; nothing injected by default | `any_enabled`; `spa.py:77-81`; `test_identity_seam` default page | verified |
| Escaped, versioned injection cannot break out | `_script_safe_json`; probe: `</script>…`, `<!--<script>`, `</SCRIPT >`, U+2028/9 in the user name and URLs, at both mounts: one script element, value round-trips | verified |
| `transfer=True` raises; ADR-052 provisional break documented | `seam.py:481-485`; CHANGELOG "Changed" entry; ADR-052 §5 requires only a changelog entry for `provisional` | verified |
| Capability URLs resolve under the prefix like API calls | `enterpriseApi.ts` uses `apiFetch` and `apiUrl`; XHR upload uses `apiUrl`; `EnterpriseChrome` and `TransferControls` tests at `/user/alice/scistudio` | verified |
| Logout is a same-origin POST that follows `location` | `postForLocation` (`credentials: "same-origin"`); only an `http(s)` location is followed | verified |
| Update polls every 60 s and on focus; never steals focus; confirms before restart; warns when runs are active | `useUpdateStatus.ts`; `role="status"`, no autofocus; `RestartDialog` | verified (stale-warning race: P2-2) |
| Upload through staged `/api/data/upload` with progress and cancel | `uploadDataWithProgress` (XHR, `upload.onprogress`, `AbortSignal`) | verified (backend event timing: P2-5) |
| Download uses the template | `downloadRoutePath` + `encodeURIComponent`; tree paths are project-relative (`useTreeNodes.ts:85`) | verified |
| Nothing renders for an absent capability | `EnterpriseToolbarControls` and `DownloadToComputerItem` return `null`; tests | verified |
| AI Chat hidden; agent PTY refused on every spawn path before a process starts | `websocket.py:59` before join and spawn; `engine.py:207` before reclaim and spawn; `_spawn` backstop; internal route soft error; chat never mounted | verified (Bring In My Work 500: P2-4) |
| `user-terminal` and tutorial replay never gated | backend: yes (tests); frontend: replay hidden | **partially** (P2-3) |
| Every `/api/ai/pty/internal/*` route enforces the IPC token; prefix registered | `_check_ipc_token` fails closed on an empty env token; tests at both mounts and both guards; encoded and `..` probes reach only 404s | verified for the two routes; **bare-prefix bypass: P1-1** |
| #2328 `active_project_root` | `seam.py:557-569` | verified |
| #2328 `ToolRefusal(code, message, alternatives)`, wire `use_instead` | `seam.py:592-630`; middleware on the shared registry; bridge test at both mounts | verified |
| #2328 `check_author_path` (confinement plus Spec 2 blacklist) | wraps `_resolve_author_path(project_root=…)`; no duplicated logic | verified |
| #2328 `write_project_file` async, shared write path | `ProjectFileService.write_text` → `confine_to_project` (`PermissionError` → `outside_project`) → `write_project_file` | verified |
| #2328 `add_upload_listener(callback(path, size, status))`, unsubscribe; a failing listener never breaks the upload | `seam.py:707-761` (`except Exception`, logged); tests for started, completed, discarded and removal | verified (timing: P2-5) |
| `tools_workspace.py` and `_file_writes.py` hunks minimal and correct | +5/-2 and +16/-4; string behavior unchanged; bytes skip the lint reload unless the content is UTF-8 | verified |
| Specs, CHANGELOG, snapshot, regenerated reference | diffs; `test_public_surface.py` passes | verified (public-api.md: P3-7) |

## 3. Scope, Checklist, And Gate Evidence

- **Write set.**
  - Every changed file is covered by the ledger's declared include set or by
    one of its seven `add-include` scope events.
  - Those events cover the `ContextMenu.tsx` amend, the generated
    `_user_guide` pages, the internal-guard test, and the four #2328 paths.
  - Three directive events record the plan and the two manager scope
    additions (drift log, 2026-09-11).
  - No `core/**`, `webmcp.py`, `cli/**` or `docs/ai-developer/**` file is
    touched.
- **Gate ledger.**
  - Read-only `gate_record check --mode pre-pr --base origin/main --head origin/feat/2322-enterprise-ui`
    selects tier 1 with ten checks and ends in "reconciliation passed". Its
    ledger mutation was discarded.
  - `issues` lists #2322 and #2328 with `close_in_pr: true`, and the PR body
    carries `Closes #2322` and `Closes #2328`.
  - The Sentrux N/A is recorded.
  - The ledger does not reflect the CI deferral failure (P2-1).
- **Checklist drift.**
  - §6 still shows A1 as `[ ]`, and every row in §7.2 to §7.5 is unchecked,
    although PR #2336 is open. Those rows are the manager's to update.
  - §7.1 lists `tests/api/test_identity_seam.py` "(extended)". It is updated.
- **Known gaps the implementer reported, assessed:**
  - Bring In My Work returns 500: P2-4.
  - Tutorial replay hidden: P2-3.
  - mypy error at `test_identity_seam.py:171`: P3-8 (pre-existing).
- **Missing evidence.**
  - No test covers the bare internal prefix (P1-1).
  - No test covers a `runs_active` flip before the confirm click (P2-2).
  - No test sends an upload notification across a project switch (P3-3).

## 4. Checks Run

| Check | Result |
|---|---|
| `PYTHONPATH=src .venv/Scripts/python -m pytest tests/api/test_enterprise_capabilities.py tests/api/test_ai_pty_capability.py tests/api/test_ai_pty_internal_guard.py tests/api/test_seam_project_access.py tests/api/test_identity_seam.py tests/api/test_public_surface.py -q --no-cov` | 278 passed (with coverage enabled the run passes but trips the repo-wide 70 % threshold, as expected for a partial run) |
| `npm --prefix frontend run test -- --run src/lib/capabilities.test.ts src/components/Enterprise BottomPanel Toolbar` | 16 files, 227 tests passed |
| `mypy tests/api/test_identity_seam.py src/scistudio/api/seam.py` | 1 error at `test_identity_seam.py:171`, on a line identical to main (P3-8); `seam.py` clean |
| Probe: internal-prefix bypass (fake guard, both mounts, encoded and `..` paths) | bare-prefix WebSocket bypass reproduced (P1-1); encoded and `..` variants reach only 404s |
| Probe: script breakout and URL validation | no breakout at either mount; validation gaps P3-1 and P3-2 |
| `gh pr checks 2336` | all pass except **Deferral discipline ratchet** (P2-1) |
| Read-only `gate_record check --mode pre-pr` on the PR ledger | reconciliation passed; ledger change discarded |
| Sentrux | N/A: MCP not available in this runtime |
| Browser smoke | N/A: component tests at both mounts cover the rendering; no live edition backend is available |

## 5. Recommendation

**Block** until P1-1 is fixed and covered by a regression test at both mounts.
The following must also be closed before completion:

- turn CI green (P2-1);
- fix the restart-confirmation race (P2-2);
- for P2-3, P2-4 and P2-5, either fix each one or record an owner decision
  with a tracked `TODO(#NNN)`, and correct the CHANGELOG and spec text that
  currently misdescribes replay and upload behavior.

The P3 items can be follow-ups. The rest of the PR matches the #2321 contract
and the #2328 signatures as the manager fixed them. Once these are resolved I
expect a pass.
