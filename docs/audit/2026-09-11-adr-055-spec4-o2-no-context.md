---
title: "Audit — ADR-055 Spec 4 stdio MCP adapter, loopback token file, and local MCP socket permissions (no-context)"
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

# Audit — ADR-055 Spec 4 Stdio MCP Adapter, Loopback Token File, And Local MCP Socket Permissions (no-context)

Audit mode: **no-context** (`audit_reviewer` persona, task kind `docs`).
Audited head: `f130ee558` (`origin/feat/2308-webmcp-adapter`).
Audited delta: `git diff origin/main...HEAD` (merge-base `8f90db3ef`, 11 files).
Governing documents read: `docs/specs/adr-055-enterprise-support.md` (FR-008
to FR-011, §4.1 adapter details, Key Entities, Assumptions),
`docs/specs/adr-055-webmcp-bridge.md` (FR-001 to FR-007),
`docs/specs/adr-055-identity-seam.md` (default guard), `docs/adr/ADR-055.md`
§4, §8 and §9.2, and `CHANGELOG.md` (the #2308 and #2333 entries).
Audit gate ledger: `.workflow/records/2308-audit-2308-o2-no-context.json`.

Context limits observed: no issue, PR, `docs/planning/**`, commit message, or
dispatch text for this work was read. The branch's own gate ledger
(`.workflow/records/2308-feat-2308-webmcp-adapter.json`) was not opened.

**Recommendation: block** until P1-1 is fixed and covered by a regression
test. The three P2 findings should be fixed in the same pass. Most of the
declared contract verifies against code, tests, and probes (section 2),
including a real end-to-end run of `scistudio serve` plus
`scistudio webmcp-adapter` over stdio on Windows.

## 1. Findings

### P1-1. A queued `tools/call` is stamped with a snapshot that another call refreshed, so it runs silently against the new project

Contract: ADR-055 §4 says "opening another page must not silently redirect an
in-flight write to another project". Spec 4 FR-008 and §4.1 *Calls* require
the adapter to carry the catalogue's project snapshot. The adapter has one
mutable snapshot, `WebMCPAdapter._project_id`. It reads that value when a
worker thread starts the call, not when the request arrives:

- `src/scistudio/cli/webmcp_adapter.py:676`:
  `bridge.post_call({"name": name, "arguments": arguments, "projectId": self.project_id})`;
- the value is replaced by every catalogue fetch (`_record_catalogue`,
  lines 536-538), including the automatic refresh that a *different* call's
  `409 stale_project_context` triggers (`_refresh_catalogue_and_notify`,
  lines 541-550);
- `serve_stdio` queues requests on a `ThreadPoolExecutor` (8 workers,
  lines 756-760). Tool calls have no read timeout (`_CALL_TIMEOUT`, line 93).
  A request that waits behind eight in-flight calls, or that the client sends
  a moment after another call, is stamped only when a worker takes it.

Probe P-b (below) reproduces this deterministically. The bridge's active
project changes from `p1` to `p2`. The client then sends two mutation calls
back to back, both issued while its catalogue said `p1`. The first gets the
409 and the adapter refreshes. The second call is then stamped `p2` and
**executes** with `isError: false`:

```
POST bodies: [('write_a', 'p1'), ('write_b', 'p2')]
id 1 isError True  | SciStudio's active project changed ...
id 2 isError False | ran on p2
```

The adapter never *retries* a call (verified, section 2). But the second
write was in flight from the client's point of view, and it was redirected
to another project without an error. The existing test
`test_stale_project_call_is_reported_refetched_and_never_retried` issues its
calls one at a time, so it cannot see this.

Options for the owner:

- stamp the snapshot when the request line is read, before it is queued, and
  pass it into `handle`;
- or replace the snapshot only on a client-initiated `tools/list`, and never
  as a side effect of another call's stale response.

Either option needs a regression test that uses queued calls (for example
`serve_stdio(..., max_workers=1)` with two calls on stdin).

### P2-1. A second backend on the same port deletes the running backend's token file

Spec 4 §4.1 and `webmcp.py` promise one file per port. They also say a file
that another backend has since written for the same port is left alone
(`remove_loopback_token_file` docstring). In practice the default guard
writes the file while the middleware stack is built, at lifespan startup.
uvicorn runs lifespan startup before it binds the port. So a second
`scistudio serve` or `scistudio gui` on a port that is already in use goes
through these steps:

1. It overwrites the live backend's `loopback-<port>.json` unconditionally
   (`write_loopback_token_file`, `webmcp.py:356-365`).
2. It fails to bind.
3. On exit it removes the file, because the file now carries its own PID.

Probe P-g/P-f ran two real `scistudio serve` processes on Windows. After the
second one exited, the first backend was still running, and its token file
was gone:

```
P-f: second serve on the same port exit 1   ([Errno 10048] error while attempting to bind ...)
  backend A still running: True
  A's token file exists after B exited: False
  adapter against the still-running A: exit 2 | ... loopback-62368.json does not exist; is SciStudio running?
```

This is easy to trigger by accident: `serve` and `gui` both default to port
8000. The adapter then cannot reach a running backend until that backend
restarts. No test covers two backends on one port.

A possible fix is to refuse to replace a target whose recorded PID is alive
and is not this process, or to write the file only after the port is bound.

### P2-2. With no `--base-url`, the loopback token is used for whatever base URL the token file records, loopback or not, and environment proxies apply

The adapter docstring (`webmcp_adapter.py:37-39`) says: "The token file is
never used for a non-loopback URL". Spec 4 §4.1 *Credentials* says: "the token
file never leaves the computer". The Key Entity calls `baseUrl` "its loopback
base URL". But the writer records
`http://{_worker_callback_host(host)}:{port}{root_path}` (`main.py:422` and
`main.py:538`), and `_worker_callback_host` returns the bind host itself for
any specific bind (`main.py:446-448`). `resolve_target(None, None)` then uses
`record.base_url` with no `is_loopback_url` check (`webmcp_adapter.py:230-232`).
`_Bridge` sets `trust_env=True` for a non-loopback URL (line 280), so
`HTTP_PROXY` is honored.

Probe P-a writes what `serve --host 10.1.2.3` records:

```
target: http://10.1.2.3:8931 token-file is_loopback: False
httpx client trust_env: True proxy mounts: [<URLPattern ...>]
same URL passed explicitly is refused: no credential for http://10.1.2.3:8931 ...
```

The same URL is refused when passed explicitly, but it is accepted when it
comes from the file. With a hostname bind (`--host myhost.lan`), the token
goes wherever DNS points. With a proxy configured, it crosses the proxy in
cleartext.

The incremental exposure is limited, because a specifically bound open-source
backend already serves `/api/*` without a login (the ADR-055 §8 status quo).
But the documented rule is not implemented. A possible fix is to apply
`is_loopback_url` to the record's URL. The writer could also always record a
loopback URL, which needs a separate answer for a specific non-loopback bind.

### P2-3. The relocated-socket pointer lives in the directory the server just classified as untrusted, and both reader and writers trust it

Since #2333, a project `.scistudio` that is not a 0700 directory owned by the
user no longer holds the socket. The CHANGELOG and the tests cover a lab's
group-shared `0775` directory. The socket moves to the private per-user
directory, and `mcp.sock.path` in the shared directory names it:

- **The reader.** `scistudio mcp-bridge` follows the pointer without checking
  who owns the target or its directory
  (`mcp_bridge.py:297-305 _posix_socket_connect_path`, then
  `_try_connect_attached`). A group member who can write the shared
  `.scistudio` can point another user's bridge at their own socket. That
  user's CLI agent then talks to an attacker-controlled MCP server, which
  receives the tool arguments and returns forged tools and results. Probe
  P-i shows that the connect path is taken verbatim from the pointer.
- **The writers.** `ApiRuntime._publish_mcp_port`
  (`src/scistudio/api/runtime/_projects.py:532`, outside this diff but on the
  path the diff makes normal) writes `mcp.sock.path` with `write_text`, which
  follows a symlink planted there. Probe C-4, run as one user on Linux,
  planted `mcp.sock.path -> victim-file.txt`. After publishing, the victim's
  file contained the socket path. `_write_socket_pointer` in `server.py`
  unlinks first, which narrows this to a race.

Before #2333 the socket sat in the project directory only when the directory
was usable. Now the pointer is written in exactly the shared-directory case.

A possible fix: the bridge client refuses a pointer target whose parent fails
`socket_dir_problem`, or whose socket is not owned by the current user. The
writers create the pointer with `O_NOFOLLOW`/`O_EXCL` (or replace it
atomically).

### P3-1. A base URL refusal echoes secret-bearing input

`normalize_base_url` promises that a URL carrying credentials is refused
"without echoing the URL". The scheme check still echoes the whole input
(`webmcp_adapter.py:179-183`, `got {text!r}`). Probe P-c: a scheme-less
`alice:pw-SECRET-3@lab.example.org` and a token pasted into the base-URL slot
(`hub-SECRET-token-...`) are both printed to stderr, which AI apps keep in
their MCP logs. The existing test only uses `"nonsense"`.

### P3-2. `--print-config` edge cases

- `--print-config claude-desktop --token x` with no `--base-url` exits 0. It
  prints a snippet with `SCISTUDIO_MCP_TOKEN` and no `--base-url`, which the
  adapter then refuses at runtime ("a token needs --base-url"; probe P-d).
- The Claude Code snippet puts `--env SCISTUDIO_MCP_TOKEN=PASTE_YOUR_TOKEN_HERE`
  on a `claude mcp add` command line (`webmcp_adapter.py:799-804`). A user who
  follows it puts the real token into shell history and process arguments.
  That is the exposure the `--token` help text warns against.

### P3-3. `serve --host ::1` records an unusable base URL

`_worker_callback_host("::1")` yields `http://::1:8932`, without brackets.
The adapter then rejects that as "the base URL is not a valid URL" (probe
P-e). The user passed no URL at all, so the message is confusing. The flaw is
older than this diff (`SCISTUDIO_ENGINE_API_URL` has it too), but the token
file now depends on it.

### P3-4. One malformed or newer-format token file blocks discovery of every backend

`find_loopback_token_file(None)` re-raises any non-retryable error
(`webmcp.py:476-481`). `_prune_stale_token_files` removes only files whose PID
is dead, and skips files it cannot parse. So a single `loopback-*.json` with
`version: 2` (from a newer SciStudio) or with corrupt content makes every
no-base-URL adapter fail. That holds even when a valid, newer file exists
(probe P-j: `refused, retryable= False | loopback-9999.json has an unknown format`).

### P3-5. A bearer credential is sent over plain `http://` to any host without warning

`resolve_target` accepts `http://` for a remote bearer target, and the
Authorization header goes on the first request. When a lab redirects
http→https, the adapter reports a "browser login" (`_auth_message`), after
the token has already crossed in cleartext. Spec 4 says nothing about
transport security for the bearer case.

### P3-6. Private-directory edge cases in the #2333 socket and token-file code

- A missing project `.scistudio` is now created 0700 by the MCP server (probe
  C-2 under umask 002: `project .scistudio mode: 0o700`). In a group-shared
  project this locks collaborators out of project metadata. Whether it
  happens depends on who creates the directory first. It is stated in the
  `server.py` docstring but not in the CHANGELOG, which says only that an open
  `.scistudio` "is left as it is", and not in any spec.
- When `XDG_RUNTIME_DIR` is unset, the fallback `/tmp/scistudio-<uid>` has a
  predictable name. Another local user can pre-create it. The server then
  refuses to start, which is correct and documented, but it has no alternate
  location. `ensure_project_mcp_server` only logs the failure. `XDG_RUNTIME_DIR`
  itself is not checked for being private.
- The directory check and the bind are separate steps
  (`_requested_dir_is_private`, then `start_unix_server`, then `chmod`).
  When the project directory itself is writable by others, `.scistudio` can
  be swapped in that window. The socket carries umask permissions until the
  `chmod`. The window is narrow.
- `read_loopback_token_file` re-checks owner and mode with `fstat` after
  `open`, but not `S_ISREG`. A FIFO swapped in would make `open` block.
  `_ensure_private_dir` in `webmcp.py` neither chmods nor refuses a token
  directory that another user owns. The per-file owner and mode checks keep
  both cases confidential; the remaining effect is denial of service.

### P3-7. The Windows assumptions are documented but not enforced or tracked

- The token file is never permission-checked on Windows
  (`token_file_permission_problem` returns `None`, `webmcp.py:294-296`).
  Spec 4 relies on the profile ACL. That ACL holds on this machine: `icacls`
  shows SYSTEM, Administrators and the user, plus an AppContainer SID with
  `(S,X)` only. But `Path.home()` follows `USERPROFILE`, so a redirected
  profile brings whatever ACL it has.
- On Windows the local MCP transport listens on TCP loopback with no
  authentication. Every local account can reach it. `server.py` now documents
  a shared Windows host as unsupported, but nothing at runtime warns, and no
  tracked issue or TODO covers it (AGENTS.md §3.6).

### P3-8. Documentation drift

- `docs/adr/ADR-055.md` does not mention the stdio adapter. In §4 the only
  front doors are the WebMCP page and the local MCP transport, and it says
  that CLI agents keep the local MCP path. Spec 4 is the only governing text
  for this third client of the bridge.
- The #2333 socket contract lives only in `CHANGELOG.md` and `server.py`
  docstrings: the private per-user directory, `$XDG_RUNTIME_DIR/scistudio` or
  `scistudio-<uid>`, the pointer semantics, and the Windows single-user
  assumption. No spec states it. `docs/architecture/ARCHITECTURE.md` (the
  table at about line 2007) lists `.scistudio/mcp.sock` and `.port` but not
  `mcp.sock.path`, which is now the common case on POSIX. That document is
  owner-controlled; this audit only flags it.
- Spec 4 §4.1 writes `loopback_token_file(port, base_url)`, but the code is
  keyword-only: `loopback_token_file(*, port, base_url, directory=None)`.
- The Spec 4 frontmatter `tests:` list omits `tests/api/test_webmcp.py`,
  which holds the FR-010 token-file tests.

### P3-9. Test gaps for documented behavior

These behaviors have no test:

- A loopback target ignoring environment proxies. The autouse fixture deletes
  every proxy variable, so the claim is never exercised; probe P-h confirms
  that it holds.
- The mid-call `ReadError` path that reports "whether it ran is unknown"
  after a restart (`outcome_unknown=True`).
- `_fetch_catalogue` following a restarted backend.
- A token file that records a non-loopback URL (P2-2).
- Two backends on one port (P2-1).
- Queued calls (P1-1).
- A test that runs the adapter as a real subprocess over stdio. Probe P-g
  covers this manually.

One misreport is also untested: a 404 in mid-session is always reported as
"unknown tool" (`-32602`), even when the base path itself is gone.

## 2. What Verifies

Code reading, tests and probes confirm the following:

- **Catalogue parity (FR-008).** `tools/list` is fetched live every time and
  includes `audience:external` tools. `_meta.category` and `_meta.mutation`
  are mapped, and no registry is kept.
- **Result contract.** A `200` body is passed through verbatim, including
  unknown fields, `isError`, `structuredContent` and `substitutedFrom`
  blocks.
- **Stale context.** A stale `409` is never retried. `list_changed` is written
  before the stale response. The model-facing text says the call was NOT
  executed.
- **Error codes.** They match §4.1: `-32602` for an unknown tool, `-32001` for
  a rejected credential or a redirect (naming the base URL, never the
  token), and `-32002` for an unreachable backend (saying whether the call
  was delivered).
- **Transport.** A bearer token goes on every request, under a service
  prefix. Redirects are never followed. A loopback target does not use
  environment proxies (probe P-h: `trust_env: False`, no mounts).
- **Clean output.** Stdout carries only protocol messages, and no credential
  reaches logs or stderr. Probe P-g ran a real `scistudio serve` on Windows
  plus `python -m scistudio webmcp-adapter` with no credential configured:
  initialize, 50 tools listed, `list_types` called, no non-JSON lines on
  stdout, and the token absent from stderr.
- **Desktop app.** The desktop app runs `gui --bundled`
  (`desktop/main.js:1053-1061`), so it arms the token file as the CHANGELOG
  claims.
- **Token file permissions.** Linux (WSL) tests confirm: 0600 file and 0700
  directory whatever the umask, refusal of a symlink or a non-owner-only
  file without waiting, and a replacement guard never writing a file. A
  backend built without a launcher writes no file either.
- **MCP socket (#2333).** Linux tests confirm: the socket is 0600 under umask
  002, a shared project directory is left alone while the socket relocates,
  and the bridge follows the pointer. A hostile per-user directory (mode
  0777, or a symlink) is refused. The standalone bridge socket without a
  project is private.

## 3. Checks Run

- **Windows** (`.venv`, `PYTHONPATH=src`, `--no-cov`):
  `tests/cli/test_webmcp_adapter.py`, `tests/api/test_webmcp.py`, and
  `tests/ai/test_mcp_socket_permissions.py` gave **73 passed, 11 skipped**.
  Every skip is POSIX-only, except that the symlink test skipped because the
  account lacks the symlink privilege.
- **Linux** (WSL Ubuntu, Python 3.12.3, a throwaway venv holding only the
  project's dependencies, source from `git archive HEAD`, umask 022): the
  three files above plus `tests/cli/test_mcp_bridge.py`,
  `tests/api/test_mcp_transport_publish.py`, and
  `tests/ai/test_mcp_server_stop.py` gave **105 passed, 0 skipped**. That run
  executed the POSIX-only claims on Linux as a single account. The "another
  user owns it" rules were exercised only through stat-value unit tests and
  `chmod`-opened directories, not with a second real account. macOS was not
  run.
- **Uncommitted probes** written for this audit:
  - P-a to P-e and P-h to P-j: `WebMCPAdapter`, `resolve_target`, `_Bridge`,
    `normalize_base_url`, `--print-config`, and `_posix_socket_connect_path`,
    with `httpx.MockTransport` and a temporary home;
  - P-f and P-g: real `scistudio serve` and `scistudio webmcp-adapter`
    subprocesses on Windows, with `USERPROFILE` set to a temporary directory;
  - C-1 to C-4: POSIX token directory, socket and pointer probes under WSL.
- Sentrux: N/A (the Sentrux MCP server was not available).
- `gate_record check --mode pre-pr` was run on this audit's ledger before
  the push.

## Re-audit (head 26af14cf8)

Scope and rules are unchanged from the first pass: no-context, the same
allowed surfaces, and no commit message, PR text, issue, `docs/planning/**`,
or other audit report or gate ledger read. The audit branch was updated by
merging `origin/feat/2308-webmcp-adapter` at `26af14cf8`. Evidence comes from
plain diffs against `f130ee558`, the current code, the test runs, and the
re-run probes. One `git log --oneline` run, used to confirm this audit's own
commits after the push, also printed the subject line of `26af14cf8`. That
happened after this section was written, and it was not used as evidence.

**Updated recommendation: pass-with-fixes.** The P1 and two of the three P2
findings are fixed and covered by new tests. One P2 remains in part: the
runtime publisher still writes `mcp.sock.path` through a planted symbolic
link. It should be fixed before completion. The rest are P3 follow-ups.

### R.1 Verdicts on the first-pass findings

| Finding | Verdict | Evidence at `26af14cf8` |
|---|---|---|
| P1-1 queued call re-stamped | **Fixed** | `serve_stdio` binds the snapshot when it reads a line (`work.put((message, adapter.bind()))`), and `_tools_call` posts that bound value. A stale 409 no longer adopts a new snapshot; only `tools/list` does. Probe P-b: `POST bodies: [('write_a', 'p1'), ('write_b', 'p1')]`, both `isError: true`, nothing ran on `p2`. New test: `test_queued_parallel_mutations_across_a_project_switch_never_run_on_the_new_project`. |
| P2-1 second backend removes the token file | **Fixed** | `write_loopback_token_file` raises `kind="busy"` rather than replace a file owned by another live process, identified by PID plus the recorded `createTime`. Removal also requires this process's token. Real-process probe P-f: the second `serve` failed to bind, backend A's file survived with A's PID and token, and the adapter then connected to A (exit 0). New tests cover the busy port, a reused PID, and removal. |
| P2-2 non-loopback URL from the token file | **Fixed** | `resolve_target(None, None)` refuses a recorded URL that is not loopback (probe P-a), and `_Bridge` sets `trust_env` only for a remote bearer target (probe P-h: token-file and loopback targets `trust_env=False`, 0 mounts; remote bearer `True`). Tests were added. |
| P2-3 socket pointer in an untrusted directory | **Partially fixed, still P2** | See R.2-1. The reader is fixed: `_posix_socket_connect_path` refuses a pointer that is not a regular file owned by the user, and a socket not owned by the user or sitting in a group- or world-writable directory. Probe E-1 shows both refusals, and a legitimate private socket is still followed. The server's `_write_socket_pointer` now unlinks and then creates the pointer with `O_EXCL \| O_NOFOLLOW`, mode 0600; probe E-2 left the victim file intact. The runtime publisher is not fixed. |
| P3-1 base URL refusal echoes input | **Fixed** | The scheme refusal no longer contains the input (probe P-c: `echoes secret: False` for both cases). |
| P3-2 `--print-config` edge cases | **Fixed** | A token without a base URL exits 2 (probe P-d). The Claude Code snippet has no `--env` and tells the user to set the variable in Claude Code's environment. Tests were added. |
| P3-3 IPv6 loopback base URL | **Fixed** | `_url_host` adds brackets. `serve --host ::1` records `http://[::1]:8932`, which normalizes (probe P-e). A test was added. |
| P3-4 one bad file blocks discovery | **Fixed** | `find_loopback_token_file` skips `kind="malformed"` files with a warning and still refuses `unsafe` ones. Probe P-j resolved the valid backend beside a `version: 2` file. A test was added. |
| P3-5 bearer over plain http | **Fixed** | `run` warns once on stderr (test added). A redirect is still reported as a likely browser login, which is minor and left as is. |
| P3-6 private-directory edge cases | **Fixed** | Four sub-items. A new project `.scistudio` created 0700 is now documented in the CHANGELOG and in `adr-055-webmcp-bridge` FR-012. A taken `scistudio-<uid>` makes the server fall back to a unique `mkdtemp` directory (probe E-4). `XDG_RUNTIME_DIR` is used only when it is private (test added). The socket is bound under a 0077 umask (`_bind_owner_only`), and the umask is restored afterwards (probe E-3). The token reader adds `O_NONBLOCK` plus an `S_ISREG` re-check, and the token directory is refused when another user owns it. |
| P3-7 Windows assumptions | **Partially fixed** | FR-012 now states that the Windows TCP transport is reachable by every local account, that a shared Windows host is unsupported, and that authenticating it is outside #2333. There is still no tracked follow-up issue (AGENTS.md §3.6). The Windows token file still relies on an unchecked profile ACL that follows `USERPROFILE`. |
| P3-8 documentation drift | **Partially fixed** | ADR-055 §4 now describes the adapter as the bridge's second consumer. `adr-055-webmcp-bridge` FR-012 records the #2333 socket contract, and Spec 4 shows `loopback_token_file` as keyword-only. Still open: `docs/architecture/ARCHITECTURE.md` (about line 2007) lists `mcp.sock` and `.port` but not `mcp.sock.path` (owner-controlled; flagged only), and the Spec 4 frontmatter `tests:` list still omits `tests/api/test_webmcp.py`. |
| P3-9 test gaps | **Partially fixed** | New tests cover queued calls, the non-loopback record, the busy port, proxies, IPv6, pointer ownership, shutdown bounds and the startup bound. Still untested: the mid-call `ReadError` restart path (`outcome_unknown=True`), `_fetch_catalogue` following a restarted backend, and an adapter run as a subprocess over stdio (probe P-g still covers it and passes). A mid-session 404 is still always "unknown tool". |

### R.2 Findings still open or new

#### R.2-1 (P2, residual of P2-3). `ApiRuntime._publish_mcp_port` still writes the pointer through a planted symbolic link

Two writers produce `<project>/.scistudio/mcp.sock.path`. The server writer is
fixed. The runtime publisher, which `ensure_project_mcp_server` calls right
after `server.start()` through `runtime.set_mcp_port`, still uses
`path_file.write_text(...)` (`src/scistudio/api/runtime/_projects.py:550`).
That call follows a symbolic link. `port_file.write_text` at line 541 does the
same on the Windows branch.

Probe E-2 ran on Linux as one user. With `mcp.sock.path` planted as a symlink
to a user-owned file, the server writer left the file intact. The runtime
publisher then overwrote it:
`after runtime publisher: victim = /tmp/.../xdg/scistudio/mcp-1-abc.sock`.

In the group-shared `.scistudio` case that FR-012 and the CHANGELOG
explicitly cover, a group member can plant that link. The next project open
then truncates a file the victim owns, such as `~/.ssh/authorized_keys`. It
does not disclose anything or grant access, but it destroys data.
`adr-055-webmcp-bridge` FR-012 says the pointer is "written 0600 without
following a symbolic link", which is true for only one of the two writers.

A fix is to route the publisher through the same `O_EXCL | O_NOFOLLOW`
helper, or to publish nothing when the server has already written the
pointer.

#### R.2-2 (P3, new). Stale and restart messages still say the tool list was refreshed

The adapter no longer re-fetches the catalogue on a stale 409 or a restart;
it only sends `list_changed`. The model-facing text still says otherwise, in
`_INSTRUCTIONS` (`webmcp_adapter.py:116`), `_stale_result` (line 376) and
`_restarted_result` (lines 393 and 398).

Probe P-k: after a stale result, a re-issue with no `tools/list` in between
is sent with the old snapshot and fails stale again. It succeeds only after
the client re-lists. With a client that ignores `list_changed`, every
mutation stays blocked until the client lists tools. That fails closed, so
it is safe, but the text tells the model to re-issue as if nothing else were
needed.

A fix is to word it as "ask for the tool list again, then re-issue", or to
adopt the new snapshot only when the client lists tools.

#### R.2-3 (P3, new, informational). The owner-only bind changes the process-wide umask

`_bind_owner_only` sets `os.umask(0o077)` around `sock.bind` and restores it
afterwards (probe E-3 confirms the restore). The umask is per process, so any
file another backend thread creates during that window is owner-only. That
is the safe direction, but in a group-shared lab project it could leave a
concurrently written file unreadable to collaborators. Keep the window as
short as it is now, or document it.

### R.3 Checks run for the re-audit

- **Windows** (`.venv`, `PYTHONPATH=src`, `--no-cov`):
  `tests/cli/test_webmcp_adapter.py`, `tests/api/test_webmcp.py`,
  `tests/ai/test_mcp_socket_permissions.py`, `tests/cli/test_mcp_bridge.py`,
  `tests/api/test_mcp_transport_publish.py` and
  `tests/ai/test_mcp_server_stop.py` gave **109 passed, 19 skipped**. The
  skips are the POSIX-only tests, plus the symlink test for lack of the
  privilege.
- **Linux** (WSL Ubuntu, Python 3.12.3, the same throwaway dependency-only
  venv, source from `git archive HEAD`, umask 022): the same six files gave
  **128 passed, 0 skipped**. It ran as a single account; "another user"
  cases were exercised through stat-value tests and `chmod`-opened
  directories. macOS was not run.
- **Uncommitted probes re-run or added:**
  - P-a to P-e and P-h to P-k (Windows, `httpx.MockTransport`, temporary
    home);
  - P-f and P-g (real `scistudio serve` and `scistudio webmcp-adapter`
    subprocesses on Windows: 50 tools listed, `list_types` called, clean
    stdout, no token on stderr);
  - C-1 to C-4 and E-1 to E-4 (POSIX, under WSL).
- Sentrux: N/A (the Sentrux MCP server was not available).
- `gate_record check --mode pre-pr` was run on this audit's ledger before
  the push.
