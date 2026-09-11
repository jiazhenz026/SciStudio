---
title: "Audit — ADR-055 Spec 2 agent context, workspace, and execution tools (no-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 40
  - 36
  - 42
related_specs:
  - adr-055-agent-context-workspace
  - adr-055-webmcp-bridge
  - adr-055-lab-deployment
language_source: en
---

# Audit — ADR-055 Spec 2 Agent Context, Workspace, And Execution Tools (no-context)

Audit mode: **no-context** (`audit_reviewer` persona, task kind `maintenance`).
Audited head: `b1693f913` (`origin/feat/2279-agent-context-workspace`).
Audited delta: `git diff origin/feat/2271-webmcp-bridge...HEAD` (merge-base
`e817f9b82`, 24 files). Governing documents read: ADR-055 §5 and §9.2,
`docs/specs/adr-055-agent-context-workspace.md`,
`docs/specs/adr-055-webmcp-bridge.md` (FR-004),
`docs/specs/adr-055-lab-deployment.md` (transfer delta).
Audit gate ledger:
`.workflow/records/audit-2279-spec2-no-context-audit-2279-spec2-no-context.json`.

Context limits observed: no issue, PR, `docs/planning/**`, commit message, or
other gate ledger was read. One command (`git worktree add --detach` for the
base reproduction) echoed a commit subject line to the terminal; it was not
used as evidence.

**Recommendation: block** until P1-1 is fixed and covered by a regression
test. The P2 findings should be fixed in the same pass. Most of the declared
contract verifies against code, tests, and probes (section 2). That includes
the author-tool blacklist, which held against every Windows path variant
tried.

## 1. Findings

### P1 — blocks merge or breaks a declared contract

#### P1-1. A command whose background descendant holds the output pipes never finishes, cannot be cancelled, and survives backend shutdown

Declared contract (spec §2, §5):

- Edge case: "A command whose background child keeps its output pipes open
  after the command exits: the job is reported exited and output capture stops
  at exit, with a note."
- US4 AS1: after cancellation "the process tree is terminated … and the
  ProcessRegistry shows no residue".
- US4 AS5: `terminate_all` at shutdown stops a running command.
- SC-004: "A cancelled managed command leaves zero live descendant processes
  and zero registry residue in 100% of test runs on all supported platforms."

What the code does:

- **The drain-grace path is never reached.** `tools_execution._supervise`
  awaits `job.process.wait()` and only then applies
  `_PIPE_DRAIN_GRACE_SECONDS` and sets the note. On the CPython 3.13 in this
  environment, `asyncio/base_subprocess.py` `_process_exited` does not resolve
  `_exit_waiters`. They are resolved only in `_call_connection_lost`, which
  `_try_finish` calls after every pipe has disconnected. So `Process.wait()`
  does not return while a descendant still holds stdout or stderr, and the
  drain-grace branch and its note are unreachable. Other supported versions
  (`requires-python >= 3.11`) were not checked.
- **Cancel targets the dead leader.** `cancel_command` →
  `ProcessHandle.terminate` → `terminate_tree(leader_pid)`:
  - Windows (`WindowsOps.terminate_tree`): `psutil.Process(pid)` raises
    `NoSuchProcess` for the exited leader, so it returns "process already
    dead" without walking descendants.
  - POSIX (`PosixOps.terminate_tree`): `os.getpgid(pid)` on the reaped leader
    raises `ProcessLookupError`, so it returns before `killpg`. The descendant
    is still in the leader's process group, because `run_command` starts a new
    session.
- **Shutdown drops the handle without killing.** The handle stays registered,
  since `deregister` runs only in `_supervise`'s `finally`.
  `ProcessRegistry.terminate_all` then discards a handle whose PID identity no
  longer matches (`_pid_identity_matches` is False for a dead PID) and
  terminates nothing.

Reproduced on Windows (audit probe, two variants):

- `python launcher.py`, where the launcher `Popen`s a child with inherited
  stdout/stderr and exits.
- `start /b python gc.py`.

Both variants gave the same result:

| Step | Observed |
|---|---|
| `run_command(wait_seconds=6)` | leader exited; `state=running`, `note=None` |
| `cancel_command(grace_seconds=1)` | `state=running`, note "Termination was requested but the command has not exited yet"; grandchild alive; registry residue `[leader pid]` |
| `registry.terminate_all(1)` | residue cleared; grandchild still alive |
| audit kills the grandchild | job becomes `state=cancelled`, `exit_code=0` |

POSIX was not reproduced (Windows host); the POSIX conclusion rests on the code
paths cited above.

Tests: `tests/ai/test_mcp_execution_tools.py` has no test for this edge case.
`test_cancel_terminates_the_process_tree_and_clears_the_registry` keeps every
ancestor alive, so it never reaches the failing branch. The pattern this
misses is ordinary for an agent: starting a server or daemon (`… &`,
`nohup`, `start /b`, a launcher that detaches).

New in this delta (`tools_execution.py` does not exist on the base). Options
visible in the codebase:

- Record the process-group id at spawn and signal it directly (POSIX).
- Use the Job Object hooks `PlatformOps` already exposes (`create_job_object`,
  `assign_to_job`) on Windows.
- Detect leader exit from the process itself rather than `Process.wait()`.

### P2 — should fix

#### P2-1. `delete_path` and `move_path` act on the target of an in-project link, not on the link

`_resolve_author_path` returns `os.path.realpath(...)`, and the tools pass that
resolved path to `ProjectFileService.delete` / `.move`. Probe results (Windows
junctions; POSIX symlinks take the same code path):

- **Delete removes the target's contents.** With `lnk` → `keep/`,
  `delete_path(path="lnk", recursive=true)` returned `status=ok` and
  `path="keep"`. It deleted `keep/` and its file, and left `lnk` dangling.
- **Move renames the target.** With `lnk2` → `keep2/`,
  `move_path("lnk2", "lnk2_renamed")` renamed `keep2/` into a real directory
  `lnk2_renamed` and left `lnk2` dangling.
- **Links to outside the project cannot be removed.** A link to a directory
  outside the project is refused (`outside_project`), so the author tools
  cannot remove a link to an external dataset at all.

The spec (§2 edge cases, US2) describes deleting or renaming "a path" and does
not define link semantics. No author-tool test uses a link. New in this delta.

#### P2-2. Read-side state-version observation can suppress the UI's `file.changed` event for an external edit

- **The new function records the edit as already seen.**
  `_file_writes.observed_entity_version` bumps the version when the disk mtime
  is newer than the cached disk version. Through `_entity_version_locked(bump=True,
  path=...)` it also stores that mtime as the cached disk version. It runs from:
  - `ProjectFileService.state_version`, which is called by `read_file`,
    `get_file_info`, and `patch_file` (without an expected version);
  - `check_write_preconditions`, whenever an expected version is supplied
    (author tools and the editor PUT route).
- **The watcher then skips the event.** `_ProjectFileHandler.on_any_event`
  returns without emitting when `disk_mtime <= cached_disk_version`
  (`api/routes/workflow_watcher.py` lines 465-473). The function's docstring
  says so: "a later watcher event for that same mtime is then a no-op."
- **No other code emits the event.** Nothing emits `file.changed` for the bump.
  If an agent read, or any conflict check, lands between an external edit and
  the watcher processing it, the UI never receives that edit.

Probe results:

- **Deterministic.** The real `_ProjectFileHandler` object was driven directly
  after stopping the observer, so the ordering is fixed:
  - control file (no agent read): one `('external', 'modified')` event;
  - probe file (agent `read_file` first): no event, while `read_file` returned
    `state_version=2`.
- **Real observer, Windows.** 0 of 15 edits lost in trials spaced 1.5 s apart;
  the watcher won the race each time on this host.
- **Exposure depends on watcher latency** (debounce, platform backend, load).
  A common trigger is `run_command` editing a file, then an immediate
  `read_file`.

This conflicts with ADR-055 §5.2 ("The browser remains a view of backend
state") and with US2. New in this delta: on the base, `api/routes/projects.py`
bumps file versions only in the write path (`_emit_file_changed`). No test
covers the interplay.

#### P2-3. `search_files` walk is not bounded by its documented cap

The documented contract:

- Docstring: "Bounded: stops at `max_results` hits, at 20000 scanned files, and
  reads at most the first 2 MiB of each file".
- Spec §4.1: "searches bound results, scanned files, and bytes per file".

What the code does:

- **The cap counts only matches.** `_SEARCH_MAX_FILES` is compared with
  `files_scanned`, which increments only for files whose name matches
  `name_pattern`.
- **The walk itself is unbounded.** `os.walk` continues over every
  non-matching entry, with no directory or entry ceiling.
- **The root can be huge.** Inspect tools accept absolute paths (decision 2),
  so the root may be `/`, `C:\`, or a network share.
- **The work cannot be stopped.** It runs in `asyncio.to_thread`, which cannot
  be cancelled when the request ends, and holds a default-executor thread for
  its full duration.

Probe: over 25,000 files with `name_pattern="*.nomatch"`, the walk visited
25,000 files in 51 directories and returned `files_scanned=0`,
`truncated=False`, `notes=[]`. New in this delta.

#### P2-4. Tests assert less than the behavior they claim

- **Background-child edge case (spec §2).** No test exists, which is how P1-1
  went undetected.
- **US2 AS4 "a symlink out" and FR-006 "the symlink-resolved path".** No
  author-tool test uses a symlink or junction;
  `test_author_tools_are_confined_to_the_project` covers only an absolute path
  and `..`. The audit's probes found escape refusal correct (section 2), but
  link semantics wrong (P2-1).
- **FR-012.** `test_author_tool_logs_carry_no_contents_or_paths` exercises only
  successful calls; failing calls log paths (P3-1).
- **Watcher interplay.** No test checks that inspect or conflict-check reads
  leave `file.changed` delivery intact (P2-2).

### P3 — follow-up

#### P3-1. Failing tool calls are logged with full exception text, including path arguments (pre-existing)

`fastmcp/server/server.py` line 1289 logs `logger.exception(f"Error calling
tool {name!r}")` with the traceback. Evidence:

- **Head.** The probe `write_file("workflows/new.yaml::$DATA")` (which fails
  inside `atomic_write_bytes`) produced a logged traceback containing the
  target's absolute project path.
- **Base.** Reproduced on a detached checkout of
  `origin/feat/2271-webmcp-bridge` with
  `get_doc(path="../SECRETARG7731/x.md")`. The marker appeared twice in the
  output on both base and head.

The webmcp route itself logs only the exception type. The mechanism
pre-exists; the new tools inherit it, which contradicts Spec 2 FR-012 ("full
arguments MUST NOT be logged") on error paths.

#### P3-2. External-audience tools are hidden from, but callable through, the local socket transport (pre-existing mechanism)

`MCPServer.dispatch` filters `audience:external` out of `tools/list`, but
`tools/call` only checks that the name exists in `mcp.list_tools()`. Probe: a
local-transport `tools/call` of `read_file` returned the file content and its
absolute path.

Spec 1 FR-004 specifies listing only. Spec 2 §6 says local agents "never see
the external-tagged tools". The audience tag controls visibility, not call-time
enforcement, and neither spec says so. `server.py` is not in the delta.

#### P3-3. Author tools run disk work and the ruff lint subprocess on the event loop

`ProjectFileService.write_text`, `.delete` and `.move` are awaited on the loop
and do the following work synchronously:

- `atomic_write_bytes` (with `fsync`, up to 10 MiB);
- `files_under` walks, and `shutil.rmtree` / `os.replace` over up to 2000 files;
- for every drop-in `.py` save or move, `_lint_clean` → `lint_python_source`,
  which calls `subprocess.run(..., timeout=10.0)`.

Spec §4.1 says workspace "filesystem work runs in threads so the event loop
stays free", and ADR-055 §9.2 requires a responsive request path. The
lint-on-loop call pre-exists in the editor PUT route (this delta moves it into
`_file_writes`); `write_file`, `patch_file`, and `move_path` now also reach it.

#### P3-4. `read_file` observes the state version after reading

`_read_file_sync` reads the window first, then calls `files.state_version`. The
failure sequence:

1. An edit lands between the read and the version lookup.
2. `read_file` returns a version newer than the content it returned.
3. A later write with that version passes the conflict check and overwrites
   content the agent never saw.

`patch_file` takes the version before reading, which is the correct order.

#### P3-5. `status="ok"` on outcomes a caller could read as success

- **Non-zero exit.** `run_command` returns `status="ok"` for a command that
  exits non-zero; the field is documented as "'ok', or 'refused' (nothing
  ran)".
- **Cancel that did not stop the process.** `cancel_command` returns
  `status="ok"` with `state="running"` plus a note.
- **Final state after P1-1.** The job ends as `state="cancelled"`,
  `exit_code=0`, although the cancel had no effect: `_supervise` sets
  `cancelled` whenever `cancel_requested` is set.

#### P3-6. Conflict results can leave new directories behind

`ProjectFileService.write_text(create_parents=True)` and
`.move(create_parents=True)` create parent directories before the
precondition checks. A `conflict` result (for example `already_exists` or
`stale_version`) then leaves those directories on disk. Found by reading the
code; not probed.

#### P3-7. The job table is process-global, and running jobs are unbounded

`tools_execution._JOBS` is shared by every bridge caller: any caller can list,
inspect, or cancel any job. Retention caps only finished jobs (50), and nothing
limits concurrent running commands. The spec defines one user per instance, so
no requirement is violated today; this is relevant to the multi-session lab
deployment.

## 2. Verified Without Findings

- **Author blacklist and confinement (Windows probes through the real bridge).**
  Nothing protected changed on disk in any case:
  - refused with the correct code: `workflows/main.yaml::$DATA` (write, patch,
    move, delete), `workflows/main.yaml.`, `workflows/main.yaml ` (trailing
    space), `Workflows/MAIN.YAML`, the 8.3 name `WORKFL~1/main.yaml` and
    `WORKFL~1/new.yaml`, `data./raw.txt`, `data::$INDEX_ALLOCATION/raw.txt`,
    `data:$I30:$INDEX_ALLOCATION/raw.txt`, `data/raw.txt::$DATA` (move,
    delete);
  - `workflows/new.yaml::$DATA` failed as `isError` (write failed);
  - a junction into `data/` was refused for write, delete, and move;
  - deleting a tree that contains a junction to `data/` left `data/` intact.
- **Project escapes.** Absolute paths outside the project and `..` traversal
  are refused, and deleting the project root is refused.
- **Bounded reads.** A window plus a one-byte probe, correct UTF-8 boundaries,
  and binary refusal with a base64 fallback (tests and code).
- **Command output and environment.** Command output tails stay bounded
  during capture. `SCISTUDIO_ENGINE_IPC_TOKEN` is stripped from the command
  environment, and it is the only credential the backend exports
  (`api/routes/ai_pty/internal_routes.py:41`).
- **Process registry.** `run_command` registers in `app.state.registry` under
  the `mcp-command` namespace, and lifespan shutdown terminates a live leader
  (test passes).
- **Bridge marker and dispatch.** The `bridge_call_scope` ContextVar is set and
  reset around `mcp.call_tool`, and there are only two dispatch sites
  (`server.py`, `webmcp.py`).
- **Hook-parity rules.** `scaffold_block` is gated only for bridge calls;
  `list_blocks` sets a process-lifetime flag from any transport, as the spec
  states; the `run_workflow` `poll_hint` is additive.
- **Editor PUT route.** It runs the shared helper, returns 409 only when
  `expected_state_version` is supplied, and keeps its 500 details.
- **`get_agent_context`.** Its hook script paths match the provisioning
  destination names (`agent_provisioning/hooks.py` strips the `hook_` prefix),
  and `.codex/config.toml` matches `codex_config.py`.
- **Lab-deployment spec.** It absorbs the transfer scope consistently with
  decision 1.

## 3. Checks

| Check | Result |
|---|---|
| `pytest tests/ai/test_mcp_workspace_tools.py tests/ai/test_mcp_execution_tools.py tests/ai/test_mcp_agent_context.py tests/ai/test_mcp_tools_workflow.py tests/ai/test_mcp_fastmcp.py tests/ai/test_finish_ai_block_skeleton.py tests/api/test_projects.py tests/contracts/test_runtime_import_contract.py tests/api/test_file_endpoints.py tests/api/test_reload_on_save.py tests/api/test_webmcp.py -q --no-cov` | 182 collected: 181 passed, 1 skipped (the declared pip-wheel skip: no pip in this venv) |
| Audit probes (scratch only, not committed) | Results quoted in section 1 and section 2 |
| Base reproduction (detached checkout of `origin/feat/2271-webmcp-bridge`, removed afterwards) | P3-1 reproduced on base; P1-1, P2-1, P2-2, and P2-3 are in modules or functions absent from base |
| `gate_record init` / `gate_record check --mode local` | Recorded in the audit ledger; the issue-linkage gap is a known gap (no issue looked up under no-context rules) |
| Sentrux | N/A: unavailable in this runtime |
