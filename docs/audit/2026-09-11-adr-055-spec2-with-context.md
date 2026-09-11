---
title: "Audit — ADR-055 Spec 2 agent context, workspace, and execution tools (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 42
related_specs:
  - adr-055-agent-context-workspace
  - adr-055-webmcp-bridge
  - adr-055-lab-deployment
language_source: en
---

# Audit — ADR-055 Spec 2 Agent Context, Workspace, And Execution Tools (with-context)

Audit mode: **with-context** (agent AU3, `audit_reviewer` persona, task kind
`maintenance`).
Subject: branch `feat/2279-agent-context-workspace` @ `b1693f913`, stacked on
`feat/2271-webmcp-bridge` (PR #2275, open). No PR exists yet. Audited delta:
`git diff origin/feat/2271-webmcp-bridge...origin/feat/2279-agent-context-workspace`
(24 files, +5864/-471).
Issue: #2279 (its "Owner decisions" override the spec). Umbrella PR: #2283
`[DO NOT MERGE]`. Checklist: `docs/planning/adr-055-spec2-3-checklist.md` on
`track/adr-055-spec2-3` (sections 7 and 10).
Gate ledger under audit: `.workflow/records/2279-feat-2279-agent-context-workspace.json`.
Audit gate ledger: `.workflow/records/2279-audit-2279-spec2-with-context.json`.

**Verdict: block until P1-1 and P1-2 are fixed.** All six #2279 decisions are
implemented and their stated tests pass. The blacklist held against every
Windows path trick probed (case, backslash, `./`, `..`, trailing dot/space,
NTFS stream names, 8.3 short names, junctions into `data/`). No `ai`→`api`
import exists. Two defects lose data or leave processes behind on a supported
platform, and neither is covered by a test. Both fixes are small and local.
The rest is a fix round, not a redesign.

## 1. Findings

### P1 — blocks merge

#### P1-1. `delete_path` and `move_path` act on a link's target, not on the link the agent named

`_resolve_author_path` (`src/scistudio/ai/agent/mcp/tools_workspace.py:319-349`)
returns the **realpath** of the argument. `delete_path` and `move_path` then pass
that resolved path to the shared write path (`tools_workspace.py:1114-1122`,
`1162-1171`; `_file_writes.py:533` `shutil.rmtree`, `:604` `os.replace`). When the
named path is a symlink or junction to another directory or file inside the
project, the tool deletes or moves **the target**. It reports `status: ok`.

Reproduced on Windows through the real bridge (`POST /api/webmcp/call`,
`create_app()` lifespan):

| Setup | Call | Result |
|---|---|---|
| `notes/k` = junction → `scratch/` (holds `keep.txt`) | `delete_path(path="notes/k", recursive=true)` | `status=ok`; `scratch/` and `scratch/keep.txt` **deleted** |
| `notes/m` = junction → `scratch2/` (holds `keep.txt`) | `move_path(path="notes/m", destination="notes/m2")` | `status=ok`; `scratch2/` moved to `notes/m2/`; `notes/m` left dangling |

POSIX symlinks behave the same way, because `os.path.realpath` is the same
operation there. That was not run on this Windows host: file symlinks need a
privilege it lacks. The agent's intent ("remove this link") is replaced by an
unrequested, unrecoverable deletion of real content. `affected_paths` honestly
lists the target's files, but after the fact.

Spec: FR-005 and FR-006 require confinement and a blacklist check on "the
lexical and the symlink-resolved path". They do not license operating on the
resolved path. US2 AS4 names "a symlink out" as a case to refuse. No test
creates a link (`tests/ai/test_mcp_workspace_tools.py` has none).

Fix options: (a) resolve only for the confinement and blacklist checks, and
operate on the lexical path. Remove a link with `os.unlink`, or `os.rmdir` for a
junction, rather than its target (`Path.is_junction` exists since 3.12, and a
fallback is needed for 3.11). (b) Refuse links in the author tools with a
refusal code that points to `run_command`. In either case, add a test: on
Windows, `mklink /J` needs no privilege; on CI's Linux runner, `os.symlink`
works.

#### P1-2. Windows: `cancel_command` leaves descendants alive once their parent has exited, and the job never reaches a terminal state

`run_command` on Windows spawns `cmd.exe /c <command>` (`tools_execution.py:312-314`).
Cancellation calls `ProcessHandle.terminate` → `WindowsOps.terminate_tree`
(`src/scistudio/engine/runners/platform.py:257-300`), which walks
`psutil.Process(pid).children(recursive=True)` (`:271`). Windows does not
reparent orphans, so a descendant whose parent already exited is not reachable
from `cmd.exe` and is never signalled. POSIX uses `killpg` on the new session
(`platform.py:82-137`) and does not have this gap.

Reproduced (Windows, Python 3.13.12): the command
`python spawner.py && python -c "import time; time.sleep(90)"`, where
`spawner.py` starts a sleeping grandchild and exits at once. After
`cancel_command(grace_seconds=1)`:

- the grandchild is **alive**;
- the job reports `state="running"`, with the note "Termination was requested
  but the command has not exited yet". The grandchild holds the output pipes,
  which is where this finding combines with P2-2.

The same gap applies at backend shutdown. `ProcessRegistry.terminate_all`
identity-checks `cmd.exe`'s PID (`process_handle.py:167-170`). Once `cmd.exe` is
dead, it drops the handle without touching the orphan.

Spec: SC-004 requires "zero live descendant processes and zero registry residue
in 100% of test runs **on all supported platforms**". ADR-055 §11, Execution
row: "cancellation observes process-tree and terminal-state behavior". The
existing test (`tests/ai/test_mcp_execution_tools.py:221-257`) keeps every
intermediate process alive until cancel, so it never reaches the orphan path.

Fix options: (a) put each command in a Windows Job Object
(`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, terminate the job on cancel).
`PlatformOps.create_job_object` / `assign_to_job` already exist. There is a
window between spawn and assignment to handle. (b) The owner narrows SC-004 on
Windows and tracks orphan descendants together with #2281. Either way, add a
test with an exited intermediate.

### P2 — fix before completion

#### P2-1. Read tools swallow the watcher's external-change event, so the open UI goes stale

`get_file_info`, `read_file`, and `patch_file` (for its base version) call
`ProjectFileService.state_version` → `observed_entity_version`
(`src/scistudio/api/runtime/_file_writes.py:183-198`). On a newer disk mtime it
calls `bump_entity_version(..., path=target)`, which also records the new disk
mtime as the cached disk version (`src/scistudio/api/runtime/__init__.py:559-560`).
The watcher emits `file.changed` only when `disk_mtime > cached_disk_version`
(`src/scistudio/api/routes/workflow_watcher.py:465-473`). After such a read, the
event is dropped as a "delayed echo", and no one emits `file.changed` for that
edit.

Measured through the bridge on the real runtime, after an external edit to a
tracked file:

```text
after external edit: state_version=1 cached_disk=…505812551400 disk=…507817249500 -> watcher guard emits: True
after get_file_info:  state_version=2 cached_disk=…507817249500 disk=…507817249500 -> watcher guard emits: False
```

The common trigger is the agent's own workflow: `run_command` edits a file,
then `read_file` checks it. The user's open editor tab never learns the file
changed. That breaks "writes update the UI / the browser remains a view of
backend state" (ADR-055 §5.2, §11 Workspace row). The docstring at
`_file_writes.py:190-191` notes the no-op as intended for the conflict check,
but not its UI consequence.

Limit of the evidence: under `TestClient`, the watcher emitted nothing even for
a control edit, so the end-to-end UI effect is inferred from the deterministic
guard, not observed.

Fix options: emit the external `file.changed` wherever a read advances the
version; or compute the conflict version without mutating the cache
(compare-only), and bump only inside a write's precondition check, which then
emits.

#### P2-2. A command whose background child keeps the pipes open is reported `running` until that child exits

`_supervise` awaits `process.wait()` before its drain-grace branch
(`tools_execution.py:335-344`). On both CI interpreters, asyncio resolves
`Process.wait()` only after every pipe disconnects. `_process_exited` calls only
`_try_finish()`, and the exit waiters are woken in `_call_connection_lost`.
This was verified from the stdlib source of 3.11.16 and 3.13.12. The
`_PIPE_DRAIN_GRACE_SECONDS` branch and its note are therefore unreachable.

Reproduced (Windows, 3.13.12): `python spawner.py` prints "spawner done" and
exits immediately. It leaves a grandchild that sleeps for 20 s.
`run_command(wait_seconds=8)` → `state=running`, `exit_code=None`. The job turns
`exited` only when the grandchild exits (20.1 s), and `note=None`.

Spec edge case (`docs/specs/adr-055-agent-context-workspace.md:328-330`): "the
job is reported exited and output capture stops at exit, with a note". The
branch contradicts it. There is no test. On POSIX, `cmd &` patterns keep jobs
"running". On Windows this compounds P1-2.

Fix: detect the shell's exit independently of the pipes. For example, poll
`process.returncode`, which is set in `_process_exited` before the pipes close,
alongside the pumps, then apply the drain grace. Add a test.

#### P2-3. Refusals and conflicts travel as `isError: false` — owner decision needed

Every policy refusal and conflict is a normal result: `status` plus `refusal`.
Wire shape, through the bridge:

```json
{"content": [{"type": "text", "text": "{\"status\":\"refused\",\"refusal\":{\"code\":\"protected_data_dir\", …}}"}],
 "isError": false,
 "structuredContent": {"status": "refused", "refusal": {"code": "protected_data_dir", "message": "…", "use_instead": ["run_workflow"]}, …}}
```

Assessment:

- **Spec 1 contract (FR-003):** not a breach. The adapter propagates the flag
  when a result sets it, and these results do not set it.
- **ADR-055 §4 ("preserve … failure information"):** satisfied in substance.
  The code, message, and alternatives are in both `structuredContent` and the
  text block, so an LLM reading the text sees `"status":"refused"`.
- **Risk:** the MCP convention reports tool-level failure with `isError: true`.
  Hosts that key on the flag will count refusals as successes: UI badges, retry
  and abort logic, and step summaries. `scaffold_block` through the bridge now
  returns a "successful" result with `path=""` and `bytes_written=0`
  (`tools_authoring.py:384-392`).
- **Provenance:** the choice is spec-silent in #2279. The implementer wrote it
  into Spec 2 FR-003 and logged it for audit (checklist drift log, 2026-09-11).
  No owner decision covers it.

Options:
- **(a)** Keep it, and document in the Spec 1 adapter contract that policy
  refusals are `isError: false` with `status`.
- **(b)** Set `isError: true` for `status ∈ {refused, conflict}` while keeping
  `structuredContent`. This can be done in the tools (a FastMCP result carrying
  the flag) or in the bridge adapter (a Spec 1 file).
- **(c)** Have the bridge pass through the message of one whitelisted refusal
  exception type.

#### P2-4. The implementer's gate ledger was reconciled against an empty diff

In `.workflow/records/2279-feat-2279-agent-context-workspace.json`:

- `observed_diff` has `base_sha` = `head_sha` = `e817f9b82` (the base) and
  `changed_files: []`;
- every `reconcile_event` carries `diff_fingerprint`
  `sha256:e3b0c442…b855`, the hash of empty input;
- `docs_events` and `test_events` have `verified_in_diff: null`, and `commit`
  is `null`.

The "Tier-1 check exit 0 + pre-PR check exit 0" in checklist §7.3 was recorded
before the work was committed. Repo-wide commands (`python_tests`,
`lint_format`, `type_check`, `import_contracts`) did run against the working
tree. Scope, docs-landing, and test reconciliation, however, proved nothing
about `b1693f913`. The planned rebase onto `main` must re-run
`gate_record check --mode pre-pr` from a committed head. It must not be skipped
as "already passed".

#### P2-5. Tests do not reach the failure paths the spec names

- FR-006 ("lexical **and symlink-resolved** path") and US2 AS4 ("a symlink
  out"): no test creates a symlink or junction. Such a test would have exposed
  P1-1.
- SC-004 on Windows: the tree test uses an all-alive chain (P1-2).
- Edge case "background child keeps its output pipes open": no test (P2-2).
- UI sync after reads: no read-then-watcher test (P2-1).
- US5 "originating request aborted": tested by cancelling the coroutine
  (`test_mcp_execution_tools.py:260-283`), not by an HTTP abort through the
  bridge. Acceptable at unit level, but narrower than the claim.
- FR-012: `test_author_tool_logs_carry_no_contents_or_paths`
  (`test_mcp_workspace_tools.py:634-643`) asserts path absence only for
  `scistudio.ai.agent.mcp*` and `scistudio.api.routes.webmcp` loggers
  (see P3-3).

### P3 — improvements and follow-ups

1. **CLI denial is parity, not containment.** I ran the hook regex
   (`hook_deny_scistudio_cli.py:20`) and `invokes_scistudio_cli` on the same 20
   commands. The hook denies 1; the server denies 4 and is never weaker. Both
   allow quoted names (`"scistudio" run`), subshells, `sh -c` / `bash -c` /
   `cmd /c`, `start /b`, `nice` / `timeout` / `env -i` / `xargs`,
   `python -m scistudio.cli.main` (`cli/main.py:556` has a `__main__` guard), and
   `python -c "from scistudio.cli.main import app; app()"`. This is consistent
   with spec §4.5. Adding `-m scistudio.` prefixes and the common launchers is
   cheap.
2. **Hook guidance overstates enforcement.** `_HOOK_EXECUTION_LOCATION`
   (`tools_qa.py:481-487`) says the server-side equivalents are enforced "on
   every call, whichever host is connected". In fact, the `scaffold_block` rule
   applies only to bridge calls. Also, `protect_data_dir` and the
   list_blocks-first hook match `Bash` locally (`agent_provisioning/hooks.py:13-15`),
   but `run_command` applies neither, by design (§4.5). An honest index would
   say so.
3. **FR-012: a filename reaches the logs.** `_file_writes._lint_clean`
   (`_file_writes.py:349-354`) logs `"<file>.py has N lint diagnostic(s)"` at
   INFO for MCP-authored block writes (reproduced). The line is inherited from
   the editor route.
4. **Directories created before the check.** `ProjectFileService.write_text`
   and `move` create parent directories (`_file_writes.py:709-710`, `812-813`)
   before the precondition check. A `conflict` result can therefore leave new
   empty directories behind.
5. **Directory operations run on the event loop.** `files_under`, `rmtree`,
   per-file event emission, lint (ruff), and the registry rebuild all run
   synchronously on the loop. Spec §4.1 says "filesystem work runs in threads".
   The work is bounded by the 2000-file limit.
6. **Pipe transports are not closed.** After a job whose pipes outlive the
   process (P1-2, P2-2), the transports stay open: the repro prints an
   "unclosed transport" `ResourceWarning`.
7. **The bridge marker is inherited by spawned tasks.** Tasks created inside a
   bridge dispatch inherit the marker (`spawned_in_scope=True`), for example the
   `run_command` supervisor. Isolation between concurrent requests and from the
   local transport is verified (`concurrent_local=False`, `outer=False`), so
   this is harmless today; it is noted for future background tool calls.
8. **Spec frontmatter is stale.** `feature_branch: docs/2263-adr-055-specs` is
   out of date, and `governs.files` omits `src/scistudio/api/app.py` and
   `src/scistudio/api/routes/webmcp.py`, both listed as modified in §4.2.
9. **Special files can block a thread (unverified).** Absolute reads of POSIX
   special files (a FIFO without a writer) block a worker thread with no
   timeout. This is from reading the code; the Windows host could not test it.
10. **Vocabulary is inconsistent.** `get_agent_context` returns
    `status="no_active_project"` (`tools_qa.py:592`), while the other external
    tools use `status="refused"` with `refusal.code`. Separately,
    `list_commands` entries carry no label to tell jobs apart.

## 2. Claims Verified

| Claim | Evidence | Result |
|---|---|---|
| D1: no transfer tools; transfer moved to Spec 4 | 14 new tools, none upload/download; Spec 4 gains US6, FR-012..015, TransferRecord, T-007, SC-006; `capabilities.transfer` states none registered | Verified |
| D2: inspect reads any OS-readable absolute path, bounded while streaming | `_read_window` window buffer + 1-byte probe; `test_read_file_is_bounded_while_streaming` counts disk bytes ≤ cap+1 on a 4×cap file; search reads ≤ 2 MiB/file via bounded `readline` | Verified |
| D3: author tools project-confined; `workflows/*.y(a)ml` and `data/` blacklist on source and target | Repro: case, backslash, `./`, `..`, `data./`, `workflows/new.yaml.`, `new2.yaml ` (trailing space), `main.yaml::$DATA`, `WORKFL~1/main.yaml`, rename into `workflows/…yaml.`, junction → `data/` (write, move-into, delete) — all refused, disk unchanged. Tree ops check every file | Verified (see P1-1 for link semantics) |
| D4a: list_blocks-first per backend lifetime, incl. `scaffold_block` via bridge only | Module flag set in `list_blocks` (`read.py:120`); bridge-only gate (`tools_authoring.py:384`); tests cover any-transport marking, reset, move-into-blocks, local scaffold unchanged | Verified |
| D4b: port-type warning reuses the hook scanner | `_port_type_scanner` execs the provisioned template via `agent_provisioning.hooks._load_template`; template unmodified | Verified |
| D4c: CLI denial | Server ≥ hook on 20 probes (P3-1) | Verified |
| D4d: additive `run_workflow` poll hint | `RunWorkflowStartedResult(RunWorkflowResult)` + test on unchanged fields | Verified |
| D5: optional expected `state_version`; editor route unchanged | Route delegates to `_file_writes.write_project_file`; 409 only when the field is sent; parity spy test is real (patches the module attribute the route calls); `test_file_endpoints`, `test_reload_on_save` pass unchanged | Verified |
| D6: in-memory job state; `app.state.registry` | `_JOBS` module dict; adapter returns `app.state.registry` (`app.py:156-160`); lifespan `terminate_all` precedes `set_context(None)` (`app.py:220/226`); test shows termination on shutdown | Verified (Windows orphans: P1-2) |
| Shared helper: FILE_CHANGED + block reload for both callers, no ai→api import | Tool test spies the helper and the event bus; `lint-imports` 13 kept / 0 broken | Verified |
| `run_command`: loop never blocked; bounded capture; env; request abort | Env built and terminate run in threads; `_BoundedTail` ≤ cap+chunk; `SCISTUDIO_ENGINE_IPC_TOKEN` stripped (only backend-exported credential found); project cwd and `SCISTUDIO_PROJECT_DIR`; shielded wait | Verified (P2-2, P1-2) |
| Bridge marker cannot leak | Contextvar repro: concurrent task and outer scope see `False` | Verified (P3-7) |
| `get_agent_context` paths resolve; diagnostics accurate | Tests provision through `install_project_agent_assets` and exercise every retrieval; `get_block_schema` and other listed tools exist | Verified (P3-2) |
| Real-pip test skip | Skips only when `find_spec("pip") is None` (uv venv); CI installs into the setup-python interpreter (`uv pip install --system`), which ships pip, so CI runs it | Justified |

## 3. Scope, Checklist, And Gate Evidence

- Every changed file is inside the A1 write set, its conditional clause
  (`webmcp.py`, three lines), or a drift-log approval (`api/app.py`,
  `test_mcp_fastmcp.py`, `test_finish_ai_block_skeleton.py`,
  `test_runtime_import_contract.py`). `tests/ai/test_mcp_tools_workflow.py` is
  covered by "the existing test file covering run_workflow … amend first", and
  its scope event exists. No scope drift.
- Nothing touches `src/scistudio/core/**`, `docs/ai-developer/**`,
  `agent_provisioning/templates/**`, `api/routes/data.py`, or
  `engine/runners/local.py`.
- The spec-silent choices in the drift log (2026-09-11, A1) are assessed here:
  refusal shape (P2-3); bridge marker (verified); scanner reuse (verified);
  Windows `create_subprocess_shell` (P1-2); environment (verified);
  `list_commands`; and `move_path` (P1-1).
- Gate evidence gap: P2-4.
- Missing docs: none beyond P3-8. The ADR and changelog N/A rationales in the
  ledger are reasonable for external-only tools.
- Missing tests: P2-5.

## 4. Checks Run

| Check | Command | Result |
|---|---|---|
| Targeted suites | `pytest tests/ai/test_mcp_agent_context.py tests/ai/test_mcp_workspace_tools.py tests/ai/test_mcp_execution_tools.py tests/api/test_projects.py tests/ai/test_mcp_fastmcp.py tests/ai/test_mcp_tools_workflow.py tests/api/test_reload_on_save.py tests/api/test_file_endpoints.py -q --no-cov -rs` | 141 collected: 140 passed, 1 skipped (real-pip test), 0 failed |
| Import contracts | `lint-imports` (via `importlinter.cli`; the uv trampoline script failed to canonicalize its path) | 13 kept, 0 broken |
| Audit repros | scratch pytest modules outside the repo (bridge + real runtime; not committed) | Results quoted in the findings |
| Gate | `gate_record check --mode local --base origin/feat/2279-agent-context-workspace --head HEAD` | Recorded in the audit ledger |
| Sentrux | — | N/A: Sentrux is unavailable in this runtime |
| Frontend/browser smoke | — | N/A: no frontend change |

## 5. Recommendation

**Block until P1-1 and P1-2 are fixed.** Fix or track P2-1, P2-2, P2-4, and
P2-5 before completion, and get the owner's call on P2-3. The P3 items can
become follow-ups with tracked TODOs.
