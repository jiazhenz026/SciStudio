---
title: "Audit — ADR-055 Spec 4 O2 stdio MCP adapter, loopback token file, and owner-only MCP socket (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 42
related_specs:
  - adr-055-enterprise-support
  - adr-055-webmcp-bridge
  - adr-055-identity-seam
language_source: en
---

# Audit — ADR-055 Spec 4 O2: Stdio MCP Adapter, Loopback Token File, And Owner-Only MCP Socket (with-context)

Audit mode: **with-context** (agent AU3, `audit_reviewer` persona, task kind
`docs`).

- Subject: PR #2329, branch `feat/2308-webmcp-adapter` at `f130ee558`, based
  on `origin/main`. The audited delta is 11 files, +5014/-53.
- Issues: #2308 (the adapter and the token file) and #2333 (the owner-only MCP
  socket, added by the manager). The PR closes both.
- Umbrella: issue #2321; umbrella PR #2323 `[DO NOT MERGE]`.
- Checklist: `docs/planning/adr-055-spec4-checklist.md` §8, on
  `track/adr-055-spec4`.
- Gate ledger under audit: `.workflow/records/2308-feat-2308-webmcp-adapter.json`.
- Audit gate ledger: `.workflow/records/2308-audit-2308-o2-with-context.json`.

**Verdict: block until P1-1 is fixed. Fix the P2s or track them before
merge.**

Most of the claimed work holds.
- The adapter forwards to the bridge and keeps no registry.
- It passes bridge results through verbatim.
- It never sends the token file to a URL the user names that is not
  loopback.
- It never logs a credential or an argument.
- The token file is written owner-only, atomically, and never under a
  replacement guard.
- The #2333 socket fix is correct, and its POSIX tests ran on Linux CI.

One defect breaks the project-binding guarantee that ADR-055 §4 states in
plain words: "Opening another page must not silently redirect an in-flight
write to another project." A probe reproduces it, no test covers it, and the
Codex review flagged it on the PR as P1 with no response. The fix is small and
local.

Three more of Codex's automated review comments are also open and unanswered.
This audit confirms two of them by probe: P2-1 below, and P3-2.

## 1. Findings

### P1 — blocks merge

#### P1-1. After a stale-context refresh, a queued mutation runs against the new project

`WebMCPAdapter._tools_call` reads the adapter-wide snapshot `self.project_id`
at the moment it posts (`src/scistudio/cli/webmcp_adapter.py:676`). The
stale-context path moves that snapshot to the new project before the client
has re-listed: `_call_outcome` calls `_refresh_catalogue_and_notify`
(`webmcp_adapter.py:541-550`, `698-702`), which calls `_record_catalogue`.

The failure needs an AI app that issues parallel tool calls (Claude does this
routinely) and a project switch.
1. The app issues several mutation calls in parallel, all meant for project A.
2. The first reaches the bridge and gets `409`. The adapter re-fetches the
   catalogue, and the snapshot becomes B.
3. Every call from the same batch that has not posted yet then sends `B`.
4. The bridge accepts those calls, and the mutations execute against B.

A call has not posted yet when it is queued behind the 8 worker threads, or
when it started later.

The model never saw B's tool list, and the stale error for the first call has
not reached it yet.

Probe (throwaway, uncommitted), `serve_stdio`:
- Setup: `max_workers=1`, which models more calls in flight than workers.
- Fake bridge: the active project switches from A to B after `connect`.
- Input: two `write_file` calls written to stdin together.

| Call | Presented | Outcome |
|---|---|---|
| id 1 | `A` | `409`; `isError: true`; `list_changed` sent |
| id 2 | `B`, the refreshed snapshot | **executed against project B** (`executed_against: [('second', 'B')]`) |

Contract: Spec 4 FR-008 says the adapter "MUST carry the catalogue's project
snapshot". Spec 1 FR-005 and ADR-055 §4 say there is no silent redirect of an
in-flight write.

The test `test_stale_project_call_is_reported_refetched_and_never_retried`
covers only sequential calls. It passes because the second call there is a
deliberate re-issue.

There are two possible fixes; the owner or implementer chooses between them:
- capture the snapshot when `serve_stdio` reads the request line, before
  `pool.submit`;
- move the snapshot only on a client `tools/list`, never from the stale or
  restart refresh paths.

Either way, add a test with two queued mutation calls.

This matches the Codex thread on `webmcp_adapter.py:676`, which has no reply.

### P2 — fix before completion, or track

#### P2-1. A token-file target with a non-loopback URL receives the loopback token, through environment proxies

- **Where the URL comes from.** `scistudio serve --host 192.168.1.5` publishes
  `baseUrl: http://192.168.1.5:<port>`. `_worker_callback_host` returns a
  specific bind host unchanged (`src/scistudio/cli/main.py:422`, `438-448`),
  and `gui` builds the URL the same way.
- **No check on read.** With no `--base-url`, `resolve_target(None, None)`
  takes `record.base_url` with no loopback check (`webmcp_adapter.py:230-232`).
  The explicit-URL branch below it does check.
- **Proxies apply.** `_Bridge` sets
  `trust_env=not is_loopback_url(base_url)` (`webmcp_adapter.py:280`), so
  proxy settings from the environment apply to this target.

Probe:
- Setup: a token file with a LAN `baseUrl`, `HTTP_PROXY` pointing at a
  capture socket, and the adapter started with no base URL.
- The proxy received `GET http://192.168.1.5:8000/api/webmcp/tools` carrying
  the `x-scistudio-webmcp-token` header (`B_proxy_saw_loopback_token_header: True`).

This contradicts the spec text this PR adds (`adr-055-enterprise-support.md`
§4, adapter details). The spec says the token file's `baseUrl` is "loopback,
with any root path", and that "any other URL is refused, so the token file
never leaves the computer".

**Why P2 and not P1.** With a non-loopback bind, the open-source backend
already serves the same token to every page visitor
(`src/scistudio/api/spa.py:180-181`). The proxy leak adds exposure, but not a
privilege that LAN visitors lack. The documented guarantee is still false.

Possible fixes:
- refuse a token-file record whose `baseUrl` is not loopback;
- disable environment proxies for every `token-file` target;
- do not publish a token file for a specific non-loopback bind.

Add a test for whichever is chosen. This matches the Codex thread on
`webmcp_adapter.py:232`, which has no reply.

#### P2-2. #2308's ADR-055 §4 amendment is not done, and the PR closes #2308 anyway

The issue #2308 body requires "an ADR-055 §4 amendment recording this second
consumer of the bridge".

ADR-055 §4 today shows one bridge consumer, the page's WebMCP callbacks. It
also says "Existing desktop CLI-agent integration continues to use the local
MCP path." This PR gives CLI agents such as Claude Code and Codex a second
path: the HTTP bridge, with the `audience:external` tools.

The ledger records the omission as a docs N/A: "outside this dispatch's write
set … Reported to the manager". It is not a tracked deferral. No issue, TODO,
or follow-up reference exists, and AGENTS.md §3.6 requires one. `Closes #2308`
would therefore close an issue with an unmet documentation requirement.

This does not break a code contract. Before merge, either the manager lands
the amendment (it is not a governance surface), or a follow-up issue is filed
and the PR body cites it.

#### P2-3. #2333: `scistudio mcp-bridge` trusts `mcp.sock.path` without checking who owns the target

`_posix_socket_connect_path` (`src/scistudio/cli/mcp_bridge.py:297-306`)
connects to whatever existing path the pointer names. The problem arises in
the setting #2333 targets: a group-shared project, umask 002, and
`.scistudio` at 0775.
- The pointer is written with `write_text` (`server.py` `_write_socket_pointer`;
  `api/runtime/_projects.py:526-531`), so under that umask it is 0664 and group
  members can write it.
- A group member can therefore point the owner's bridge at their own socket.
- They then see the owner's MCP traffic, arguments included, and can return
  crafted tool results to the owner's agent.

**Not a regression.** Before this PR, a group member could replace the socket
itself in that directory. What this PR changes is how often the pointer path
is used:
- `open_project` creates `.scistudio` with the umask mode first
  (`_init_lineage_store`, `_projects.py:194`), and only then does the route
  call `ensure_project_mcp_server` (`routes/projects.py:47`).
- So under the common 022 umask, `.scistudio` is 0755.
- The socket therefore relocates, and every POSIX bridge connection now goes
  through the pointer.

`mcp_bridge.py` was outside A2's write set. A tracked follow-up should make
the client:
- verify the pointer file is owned by the user and not group- or
  world-writable;
- verify the target socket's `st_uid` matches the user before connecting.

### P3 — follow-up

- **P3-1. Stdin close waits forever for in-flight calls.**
  - `serve_stdio` exits through `ThreadPoolExecutor.__exit__`, which waits for
    running workers (`webmcp_adapter.py:756-761`).
  - Calls use an unbounded read timeout (`_CALL_TIMEOUT`, line 93).
  - So a long tool call keeps the adapter alive after its host has gone.
  - No data or security impact. This matches Codex thread `:760`, which has no
    reply.
- **P3-2. An IPv6 loopback bind publishes a URL the adapter cannot use.**
  - `serve --host ::1` writes `http://::1:<port>`, because `main.py:422` does
    not bracket the address.
  - Probe: `resolve_target(None, None)` fails with "the base URL is not a
    valid URL", naming a URL the user never passed.
  - `SCISTUDIO_ENGINE_API_URL` has the same problem, and it predates this PR.
  - This matches Codex thread `main.py:422`, which has no reply.
- **P3-3. The startup wait is not bounded by `--startup-timeout`.**
  - `connect` checks the deadline only after an attempt, and each attempt may
    take up to `_CATALOGUE_TIMEOUT` (30 s).
  - Probe: `--startup-timeout 1` against a socket that accepts and never
    answers exited after **30.1 s**.
  - With the defaults the worst case is about 50 s. That is above the Codex
    snippet's `startup_timeout_sec = 30`, and the spec says the adapter "waits
    up to the startup timeout".
  - Fix: cap each attempt at the time remaining.
- **P3-4. Removal on shutdown does not happen on Windows desktop quit.**
  - The desktop stops the backend with `taskkill /T /F` (`desktop/main.js:1581`),
    and POSIX escalates to SIGKILL. Either way the `finally` in
    `loopback_token_file` never runs.
  - FR-010 says "MUST remove the file on shutdown".
  - Mitigations: the token dies with its backend, readers skip dead-PID files,
    and the next writer prunes them.
  - Residual: a reused PID makes a stale file look live. The "newest live
    backend" rule may then prefer it over an older live backend. Comparing
    `psutil.Process(pid).create_time()` with `startedAt` would close this.
- **P3-5. Same-port collision (from reading the code, not reproduced).**
  - uvicorn runs the lifespan, and therefore the guard `build()` and the file
    write, before it binds.
  - A second `serve --port P` would overwrite the live backend's
    `loopback-P.json` and fail to bind.
  - It would then remove the file, because the PID recorded in it is its own.
    The first backend is left without a file.
- **P3-6. Launchers other than `serve` and `gui` get no file.**
  - `make dev` (`Makefile:17`, plain `uvicorn --factory --reload`) writes no
    token file. The spec documents this as intended ("with `uvicorn` run
    directly, writes nothing").
  - So the adapter cannot reach a `make dev` backend at all. Worth one line in
    the #2290 user guide.
- **P3-7. A bearer token is sent over plain `http://` to a non-loopback URL**
  without a warning. This is for the owner to decide; recorded as a fact.
- **P3-8. Spec hunks go beyond "the adapter section only".**
  - The PR also edits the frontmatter `governs` and `planned_governs`, Key
    Entities, the §4 file table, and Assumptions.
  - A1's branch `feat/2322-enterprise-ui` edits the same frontmatter blocks
    (hunks at `@@ -52` and `@@ -61`).
  - Expect a conflict for whichever of the two PRs merges second.
- **P3-9. Checklist rows §8.2 to §8.5 are still `[ ]`** on `track/adr-055-spec4`,
  with no evidence. These are manager-owned rows.

## 2. Claims Verified

### 2.1 Adapter forwarding (FR-008)

| Claim | Evidence | Result |
|---|---|---|
| `tools/list` → `GET <base>/api/webmcp/tools`; `tools/call` → `POST <base>/api/webmcp/call`, prefix-aware | `_TOOLS_PATH`/`_CALL_PATH` relative to `base_url/` (`webmcp_adapter.py:89-90`, `272-276`); `test_bearer_token_is_sent_on_every_request_under_the_service_prefix`, `test_round_trip_against_a_guarded_backend_under_a_prefix` | holds |
| No registry of its own | Only `_project_id` is kept; `test_tools_list_is_fetched_live_every_time` (a tool added later appears; 3 GETs) | holds |
| Spec 1 result contract preserved | A `200` body is returned verbatim; `_call_result` checks only that `content` is a list. The tests compare adapter and direct bridge on structured, mixed-image and raising tools, plus an unknown-field fixture | holds |
| `409` → re-fetch, `list_changed`, `isError`, never retried | `_call_outcome` 698-702; `list_changed` is written before the response on stdio (`test_list_changed_is_sent_before_the_stale_response_on_stdio`); one POST only | holds for sequential calls; **fails for queued parallel calls (P1-1)** |
| Parity includes `audience:external` | `test_tools_list_matches_bridge_catalogue_including_external_tools` | holds |

### 2.2 Credentials (FR-009)

| Claim | Evidence | Result |
|---|---|---|
| Bearer token on every request for remote backends | Header set on the client; test covers GET, GET, POST under the prefix | holds |
| Token file only for loopback, never for a URL the user names that is not loopback | Probe F: `https://lab.example.org`, `http://192.168.1.5:8000`, `127.0.0.1.nip.io`, `localhost.evil.test`, `0.0.0.0`, `127.1`. All refused, and `_read_token_file` was called **0** times | holds for `--base-url`; **fails for a recorded non-loopback URL (P2-1)** |
| Missing, stale, or non-owner-only file refused | `read_loopback_token_file`: `lstat`, symlink refusal, `O_NOFOLLOW` open, `fstat` re-check, PID liveness. Tests cover missing, stale and malformed on all platforms, and permission and symlink on Linux CI | holds |
| No credential in logs or errors; `--print-config` placeholder | Probe D: bearer and argument absent from stderr and stdout across 200, 500, `ConnectError`, `ReadTimeout`, bad JSON, 409, 401 (httpx exception messages carrying the header were not echoed). `test_logs_and_stderr_never_carry_credentials_or_arguments`, `test_print_config_command_never_prints_the_token` | holds |
| Bounded startup wait | Waits out refused, 502-504 and missing or stale file; exits at once on an unsafe file or on auth. `test_startup_*` | holds, but the bound can be exceeded by 30 s (P3-3) |

### 2.3 Token file (FR-010)

| Claim | Evidence | Result |
|---|---|---|
| `~/.scistudio/webmcp/loopback-<port>.json`, 0600 in 0700 (POSIX); Windows profile ACL, documented | `loopback_token_dir`, `_ensure_private_dir`, `mkstemp` then `chmod`; the assumption is stated in the `webmcp.py` header and spec §4. Mode test ran on Linux CI | holds |
| Atomic write; removed on shutdown | `mkstemp` + fsync + `os.replace` with retry; the `finally` removes it only if the PID matches. `test_default_guard_writes_owner_only_token_file_and_removes_it_on_shutdown` | holds for a graceful stop; not on a forced kill (P3-4) |
| Never written with a replacement guard | `create_app(guard=...)` never constructs `loopback_token_guard` (`app.py:457-461`), so `_publish_loopback_token` is unreachable. `test_replacement_guard_never_writes_a_token_file` | holds |
| "Newest live backend wins" | `max(started_at)` over live files; stale files skipped, unsafe ones refused. `test_several_backends_newest_running_one_wins` | sound; PID reuse is the residual gap (P3-4) |
| Armed from `serve` and `gui`, not from `create_app` | Acceptable. `app.py` stays out of A2's write set, and an edition uses its own launcher and a replacement guard, so it is excluded twice over. The desktop runs `-m scistudio.cli.main gui --bundled` (`desktop/main.js:1053-1062`), so it is covered. Gaps: plain uvicorn and `make dev` (P3-6), tests. `test_serve_/test_gui_publishes_the_token_file_while_uvicorn_runs` | acceptable |

### 2.4 #2333 MCP socket

| Claim | Evidence | Result |
|---|---|---|
| Socket 0600, directory 0700, whatever the umask | `_ensure_private_dir` does `mkdir(0o700)` then `chmod 0o700`; bind; `os.chmod(socket, 0o600)`. Because the directory is private, the window between bind and chmod is closed. `test_requested_directory_and_socket_are_owner_only_under_umask_002` | holds |
| A group- or world-accessible `.scistudio` is not used or chmod-ed; fallback to XDG or `scistudio-<uid>` | `_requested_dir_is_private` → `private_socket_dir`. Tests: shared directory, XDG, temp fallback, overlong path | holds |
| Hostile pre-existing directory refused | `socket_dir_problem` on `lstat` (not a directory or a symlink, foreign uid, group or other bits). `test_hostile_private_directory_is_refused[open-to-others, symlink]` | holds |
| `mcp.sock.path` keeps `scistudio mcp-bridge` working | The test connects through `_try_connect_attached` | holds; the pointer is not authenticated (P2-3) |
| Windows keeps TCP loopback, assumption documented | `server.py` module docstring; `runtime.py` Windows branch | holds |
| Predictable temp names removed | The `server.py` and `runtime.py` POSIX fallbacks now go through `private_socket_dir` | holds |

The POSIX tests are skipped on this Windows host. They are not in the Linux
CI skip list: `Test (Python 3.11)` on ubuntu-24.04 lists 52 `SKIPPED` lines,
and none name `test_mcp_socket_permissions`, `test_webmcp_adapter`, or the
token-file tests. They therefore ran on Linux. macOS is not covered by CI.

### 2.5 Docs and tests

- **Spec.** `adr-055-enterprise-support.md` §4 now carries the adapter
  details. The frontmatter moves `scistudio.cli.webmcp_adapter` into
  `governs`. The file table and Assumptions are updated.
- **CHANGELOG.** Entries under Added (#2308) and Fixed (#2333).
- **CLI help.** Present, through Typer.
- **ADR-055 §4.** Not amended; see P2-2.
- **Test gaps.** No test proves:
  - parallel or queued calls (P1-1);
  - a loopback check on a recorded URL (P2-1);
  - the IPv6 publish (P3-2);
  - stdin close during a call (P3-1);
  - the per-attempt startup bound (P3-3).

## 3. Scope, Checklist, And Evidence Drift

- **Write set.** Every changed file is inside A2's write set, or inside the
  #2333 scope addition (`server.py`, `runtime.py`,
  `tests/ai/test_mcp_socket_permissions.py`). `app.py`, `seam.py`, `spa.py`,
  `mcp_bridge.py`, `ai_pty/**`, `frontend/**` and `core/**` are untouched.
- **Scope addition.** The ledger records it as a directive event (manager
  directive, 2026-09-11). `issues` lists #2308 and #2333, both with
  `close_in_pr`, and the PR body has both closing keywords.
- **Spec hunks.** They exceed "adapter section only" (P3-8).
- **Checklist.** §8.3 rows are unfilled (P3-9).
- **Deferrals.** The ADR amendment is deferred without a tracker (P2-2).
- **Review threads.** Four Codex review threads are unresolved with no reply
  (P1-1, P2-1, P3-1, P3-2). The two CodeQL threads are resolved and outdated.
- **Ledger check.** The read-only
  `gate_record check --mode pre-pr --record .workflow/records/2308-feat-2308-webmcp-adapter.json --base origin/main --head origin/feat/2308-webmcp-adapter`
  reported tier 1, `reconciliation passed`. Its ledger changes were
  discarded, not committed.
- **Commit trailers.** All 10 commits carry `Gate-Record`, `Task-Kind`,
  `Issue`, `Assisted-by` and `Co-Authored-By`.

## 4. CI And Local Checks

- **PR #2329 CI.** All 17 checks pass at `f130ee558`. `Test (Python 3.11)` and
  `Test (Python 3.13)` each report 7782 passed, 94 skipped, 8 xfailed, plus a
  serial phase of 135 passed and 2 skipped.
- **Local run** (Windows). The command was:

  ```
  PYTHONPATH=src .venv/Scripts/python -m pytest tests/cli/test_webmcp_adapter.py tests/api/test_webmcp.py tests/ai/test_mcp_socket_permissions.py --no-cov
  ```

  Result: 84 collected, 73 passed, 11 skipped (POSIX-only, and one symlink
  test that needs a privilege), 0 failed.
- **Throwaway probes.** Uncommitted, in the audit session's scratchpad:
  - A: parallel stale calls;
  - B: token-file URL through a proxy;
  - C: IPv6 URL;
  - D: leak scan;
  - F: token-file reads for non-loopback URLs;
  - startup bound.
- **Sentrux.** N/A; MCP is not available in this runtime.

## 5. Recommendation

**Block until P1-1 is fixed**, with a test that sends queued parallel
mutation calls across a project switch.

Before merge, also do the following:
- Fix P2-1, or narrow the spec text to match the behavior.
- File a tracker for P2-2, or land the amendment.
- File a tracked follow-up issue for P2-3, since `mcp_bridge.py` is outside
  this PR's write set.
- Reply to or resolve the four Codex threads.

The P3 items can be follow-ups.

## 6. Re-verification (head 26af14cf8)

The implementer pushed a fix round, and this section re-checks every finding
against the new head.

- **Head.** PR #2329 at `26af14cf8`. The fix commits are `2dcf3b650` (audits
  and Codex review), `9cd55a627` (a comment reworded), and `24b20e4bb` (SHA-256
  for relocated socket names).
- **Merges.** `origin/main` (#2343, blocking docstring check) and both audit
  branches are merged in.
- **Scope of review.** This section reviews the fix delta
  `git diff f130ee558 26af14cf8` on the PR's own files only.
- **Probes.** Throwaway and uncommitted, as before. All of them were re-run
  against the new head.

### 6.1 Per-finding verdict

| Finding | Verdict | Evidence |
|---|---|---|
| **P1-1** Queued mutation runs on the new project | **Fixed** | `serve_stdio` binds each request on receipt (`adapter.bind()` before `work.put`), and `_tools_call` posts the bound `project_id`. The 409 and restart paths only send `list_changed`; only a client `tools/list` adopts a new snapshot. Probe, 1 worker with 3 queued writes, and 8 workers with 10 parallel writes: **all stale, none executed**. After the client re-lists, a re-issued call runs on B. Test: `test_queued_parallel_mutations_across_a_project_switch_never_run_on_the_new_project` (real backend, 3 queued writes, zero executed). |
| **P2-1** Token-file target with a LAN URL; proxy leak | **Fixed** | `resolve_target(None, None)` refuses a recorded URL that is not loopback, naming the file. `trust_env` is on only for a bearer token to a non-loopback host. Probe: a LAN record is refused. A capture proxy received **0** requests for a token-file loopback target and 0 for a bearer loopback target, and 1 for the remote-bearer control; no loopback token reached it. Tests: `test_token_file_naming_a_non_loopback_url_is_refused`, `test_loopback_targets_never_use_environment_proxies`, plus the control. |
| **P2-2** ADR-055 §4 amendment missing | **Fixed** | A new §4 paragraph records the stdio adapter as the bridge's second consumer. It says the adapter uses the same catalogue and adapter contract, adds no registry and no transport, and is the CLI agents' path to the external tools; authentication is deferred to `adr-055-enterprise-support`. The ADR is `Proposed` and has no amendment log, so the paragraph is enough. The §4 diagram is unchanged, which is acceptable. |
| **P2-3** `mcp-bridge` trusts `mcp.sock.path` | **Fixed (bridge side)** | `_posix_socket_connect_path` (`mcp_bridge.py:334-369`) requires the pointer to be a regular file, not a symlink, owned by the user. It requires the target to be a Unix socket owned by the user, in a directory without group or other write bits; anything else raises `PermissionError`, and `_try_connect_attached` falls back to standalone mode. The server writes the pointer 0600 with `O_EXCL | O_NOFOLLOW`. The pointer that `_projects._publish_mcp_port` writes is left to #2334, as the coordinator directed. The target-ownership check alone defeats the spoof even when that pointer can be edited: a planted socket belongs to another uid, so the worst outcome is a fallback to standalone mode. Tests: `test_try_connect_attached_refuses_a_pointer_another_user_could_control` (symlinked pointer; group-writable socket directory) and `test_pointer_and_socket_ownership_rules`. These are POSIX tests; the new-head Linux CI log lists none of them as skipped. |
| **P3-1** stdin close waits forever | **Fixed** | Daemon worker threads read from a queue. On EOF there is a 2 s drain, then queued calls are dropped, the client is closed, and a 1 s grace follows. Probe with three hung calls: `serve_stdio` returned in **3.0 s**. Test: `test_stdin_close_abandons_hung_calls_within_a_bound`. |
| **P3-2** IPv6 publish | **Fixed** | `_url_host` brackets IPv6 literals in `serve` and `gui`, for the token file, `SCISTUDIO_ENGINE_API_URL`, and the ready URL. Probe: `serve` publishes `http://[::1]:8001`, and the adapter resolves it as a loopback token-file target. Test: `test_serve_brackets_an_ipv6_host_in_the_published_url`. |
| **P3-3** Startup wait not bounded | **Fixed** | Each attempt is capped at the time left (minimum 0.5 s). Probe: `--startup-timeout 1` against a silent server exited 2 after **1.0 s**; before the fix it took 30.1 s. Test: `test_startup_timeout_bounds_a_backend_that_never_answers`. |
| **P3-4** File left after a forced kill; PID reuse | **Mitigated** | A forced kill still skips removal, which is inherent. The file now records `createTime`, and a PID running with a different create time counts as stale; the tolerance is 1 s, the same rule as `engine.runners.process_handle`. Probe: a live PID whose create time does not match is refused, `kind=stale`. Test: `test_a_reused_pid_does_not_make_a_leftover_file_look_live`. |
| **P3-5** Same-port collision | **Fixed** | The writer refuses to replace a file owned by another live process (`kind="busy"`). Removal needs this PID, its create time, and its token. Probe: a second backend on a busy port logged "not replacing it", and the live file survived with its token. Tests: `test_a_second_backend_on_a_busy_port_leaves_the_running_backends_file_alone`, `test_removal_needs_this_process_and_its_token`. |
| **P3-6** `make dev` writes no file | Unchanged, documented | This is intended behavior per the spec. |
| **P3-7** Bearer over plain http | **Addressed** | The adapter prints one warning on stderr. Test: `test_bearer_over_plain_http_to_another_computer_warns_once`. |
| **P3-8** Spec hunks beyond the adapter section | Unchanged | The risk of a frontmatter conflict with `feat/2322-enterprise-ui` remains, at merge time. |
| **P3-9** Checklist §8 rows | Not re-checked | These rows are manager-owned. |

Other fixes in the round:
- **`--print-config`.** Probe results:
  - a token without `--base-url` exits 2;
  - the Claude Code snippet carries no `--env` and no token;
  - a rejected base URL is no longer echoed (exit 2, `echoed=False`).
- **Fallback directory.**
  - A `/tmp/scistudio-<uid>` that another user has taken now falls back to a
    unique, verified 0700 `mkdtemp` directory.
  - An `XDG_RUNTIME_DIR` that is not private is not used.
  - Tests: `test_taken_over_temp_fallback_moves_to_a_unique_private_directory`,
    `test_xdg_runtime_dir_open_to_others_is_not_used`.
- **Umask at bind.** `_bind_owner_only` binds under umask 0077, then the
  socket is set to 0600. Test:
  `test_socket_is_created_owner_only_before_any_chmod`.
- **Leak scan.** Re-run across 7 error paths: no bearer token and no argument
  in stderr or stdout.
- **Docs.**
  - Spec 1 FR-012 now states the socket rules.
  - The Spec 4 adapter details and the CHANGELOG describe the new behavior;
    I checked them against the code.

### 6.2 New findings

- **P3-10. The stale-context and restart texts still say "the tool list has
  been refreshed".**
  - Where: `webmcp_adapter.py:116` (`_INSTRUCTIONS`), `:376`
    (`_stale_result`), `:393` and `:398` (`_restarted_result`).
  - The adapter no longer refreshes. It sends `list_changed` and keeps the old
    snapshot until the client calls `tools/list`.
  - With a host that honors `list_changed`, only the wording is wrong.
  - A host that ignores `list_changed` would be worse. The model re-issues
    after the "refreshed" message, and every mutation keeps failing stale
    until the host re-lists. That is a liveness gap, not a safety gap: nothing
    runs on the wrong project.
  - Suggested: correct the texts. Also confirm in a live session that each
    host named in the spec (Claude Desktop, Claude Code, Codex, Cursor)
    re-lists on `list_changed`. If any does not, this becomes P2.
- **P3-11. `_bind_owner_only` sets the process-wide umask to 0077 around
  `bind`** (`server.py:576-589`).
  - In the multithreaded backend, a file another thread creates during that
    instant gets owner-only permissions.
  - The failure is fail-safe and very short. Recorded for completeness only.
- **Out of scope (from main, #2343).** The automated docstring cleanup left an
  empty ```` ```` ```` literal in `LoopbackTokenBackend`'s docstring:
  `webmcp.py:127`, "served page bootstrap (the ```` SPA injection)". It came
  in with commit `96cde4baf` and is present on `origin/main`. It belongs to
  #2343's owner, not to this PR.

### 6.3 Evidence

- **CI.** All 17 checks pass at `26af14cf8`, and GitHub reports the PR
  mergeable. `Test (Python 3.11)` on ubuntu-24.04 reports 7863 passed, 94
  skipped, 8 xfailed. Its 52 `SKIPPED` lines name none of
  `test_mcp_socket_permissions`, `test_webmcp*`, or `test_mcp_bridge`, so the
  POSIX tests ran.
- **Local run** (Windows). The command was:

  ```
  pytest tests/cli/test_webmcp_adapter.py tests/api/test_webmcp.py tests/ai/test_mcp_socket_permissions.py tests/cli/test_mcp_bridge.py --no-cov
  ```

  Result: 118 collected, 101 passed, 17 skipped (POSIX-only), 0 failed.
- **Review threads.** All four Codex threads have a reply that cites
  `2dcf3b650` and a regression test. They are marked outdated but not
  resolved. The CodeQL SHA-1 thread is resolved, by `24b20e4bb`.
- **Ledger.** The read-only
  `gate_record check --mode pre-pr --record .workflow/records/2308-feat-2308-webmcp-adapter.json --base origin/main --head origin/feat/2308-webmcp-adapter`
  reported tier 1, `reconciliation passed`. Its changes were discarded.

### 6.4 Updated recommendation

**Pass.** P1-1, P2-1, P2-2 and P2-3 (bridge side) are fixed. Each has a probe
that now behaves correctly and a regression test that ran on Linux CI.
P3-1, P3-2, P3-3 and P3-5 are fixed; P3-4 is mitigated; P3-7 is addressed.

Before or soon after merge:
- correct the "refreshed" texts (P3-10);
- confirm `list_changed` handling per host in a live session;
- mark the four Codex threads resolved.

These do not block. The `_projects` pointer write remains with #2334.
