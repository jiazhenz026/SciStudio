---
title: Comprehensive Repository Audit — Doc Drift, High-Risk Bugs, Test Quality, Design
issue: 1513
branch: claude/code-repository-audit-t95gyn
author: audit_reviewer agent
date: 2026-06-10
status: committed
---

# Comprehensive Repository Audit — 2026-06-10

## 1. Scope and method

Owner-directed full-repository audit (issue #1513) on four axes:
documentation ↔ implementation drift, high-risk latent bugs, low-quality
tests, and system design flaws. Four parallel audit passes covered
`src/scistudio/` (~57k LOC Python), `tests/` (~66k LOC, 320 files, 3,317
test functions), `frontend/src` (~40k LOC TS/TSX), `packages/`, `scripts/`,
`.github/workflows/`, and `docs/`. Every P1/P2 finding below was verified
against the actual code at merge-base `4985c37`; file:line evidence is given
per finding.

Baseline: the repository's own `python -m scistudio.qa.audit.full_audit`
reports `status: pass` with **0 findings** at this commit. Everything below
is therefore invisible to the current automated drift/audit tooling — see
finding D-2 for why.

**Recommendation: pass-with-fixes.** No finding blocks day-to-day
development, but the P1 set (data-loss windows in checkpoint/artifact
persistence, unenforced block contracts, run-identity-free event model, and
the broken first-contact developer docs) should each get a tracked follow-up
issue before the next feature cascade builds on those layers.

## 2. Severity index

| ID | Severity | Axis | One-line summary |
|---|---|---|---|
| BUG-1 | P1 | Bugs | Checkpoint written non-atomically into a single slot; crash mid-write permanently breaks "run from here" |
| BUG-2 | P1 | Bugs | All SaveData artifact writers write directly to the final path; crash corrupts/destroys persisted outputs |
| DSN-1 | P1 | Design | One process-global EventBus, no run identity on events; schedulers never unsubscribe; concurrent runs cross-contaminate |
| DSN-2 | P1 | Design | Block contracts and workflow validation are not enforced at runtime; `Block.validate()` is never called |
| DSN-3 | P1 | Design | ADR-042 gate/receipt machinery is only effective against cooperative agents; CI runs PR-controlled guard code |
| DOC-1 | P1 | Doc drift | README "Writing Custom Blocks" example fails in four independent ways at import/run time |
| DOC-2 | P1 | Doc drift | `scistudio install --skill` installs the nested skill layout that the provisioning code itself documents as undiscoverable |
| TST-1 | P1 | Tests | Worker environment-contract test wraps all assertions in `if "error" not in parsed:` — silently passes on regression |
| TST-2 | P1 | Tests | Worktree write guard (the AI enforcement hook) has no positive-path test and no hook script is ever executed by tests |
| BUG-3 | P2 | Bugs | `GET /api/filesystem/browse` skips the path sanitiser its own module docstring mandates — arbitrary directory enumeration |
| BUG-4 | P2 | Bugs/Design | Re-`execute` of a running workflow silently orphans the live run; two schedulers race on checkpoint/lineage |
| BUG-5 | P2 | Bugs | `/api/data/upload` buffers entire body in RAM before the 2 GB check — OOM DoS |
| BUG-6 | P2 | Bugs | EventBus + LineageRecorder swallow subscriber/store errors; failed provenance writes leave run finalized as `completed` |
| DSN-4 | P2 | Design | Sync git/SQLite/snapshot work on the asyncio event loop; single-active-project global |
| DSN-5 | P2 | Design | Lineage is best-effort and references mutable paths with no content hash — provenance can silently dangle |
| DSN-6 | P2 | Design | No schema versioning/migration story for lineage.db, checkpoints, or wire format |
| DSN-7 | P2 | Design | Drop-in block scan executes arbitrary top-level code in the server process on every palette refresh |
| DSN-8 | P2 | Design | No authoritative REST read path for live run state; WS-disconnect policy cancels all runs after 2 s |
| DOC-3 | P2 | Doc drift | README claims 85% coverage enforced in CI; the actual gate is 70% and only on one matrix leg |
| DOC-4 | P2 | Doc drift | README documents removed ViewProxy API, never-built `ai/{generation,synthesis,optimization}` layer, retired workspace layout |
| DOC-5 | P2 | Doc drift | Packaged agent skill catalog advertises nonexistent MCP tool `list_block_runs`; tool counts disagree (25/26/27) across docs |
| DOC-6 | P2 | Doc drift | `docs/agent-provisioning.md` documents 6 hooks + nested skills; code installs 7 hooks + flat skills |
| DOC-7 | P2 | Doc drift | README claims MIT license with badge; no LICENSE file exists in the repository |
| TST-3 | P2 | Tests | 5 empty-body skipped stubs in `test_registry.py` for a rename that never landed; no issue reference |
| TST-4 | P2 | Tests | 67 tests module-skipped pending #1012 with materially thinner replacement coverage (incl. #790 regression guard now off) |
| TST-5 | P2 | Tests | Coverage gate lowered to 70% marked "TEMP" with no tracked restoration issue — violates §3.6 |
| TST-6 | P2 | Tests | Assertion-free tests named `test_state_transitions`; stale scheduler test describing a "no-op placeholder" that is now real |
| BUG-7..12 | P3 | Bugs | Process-handle leak/PID reuse; non-atomic workflow YAML save; EventBus live-list iteration; pickle opt-in RCE surface; unenforced "read-only" SQL; gate_record CLI bricks its own record on bad plan input |
| DSN-9..13 | P3 | Design | Frontend re-implements port semantics by hand; governance friction breeds untyped backdoors; vacuous dist-staleness CI check; unbounded in-memory registries |
| DOC-8..12 | P3 | Doc drift | Stale Implemented/Planned contradictions; broken cross-references; CONTRIBUTING type-checks wrong tree; changelog/release bookkeeping |
| TST-7..9 | P3 | Tests | Dead xfail/skeleton stub files; environment-conditional skips guarding the very condition under test; no warnings-as-errors policy |

## 3. P1 findings

### BUG-1 — Non-atomic single-slot checkpoint write (data loss)

`save_checkpoint` (`src/scistudio/engine/checkpoint.py:259-264`) does
`json.dump` directly onto `checkpoint_<workflow_id>.json` — no temp file,
no `os.replace`, no fsync. This single slot is overwritten on every
terminal block event (`checkpoint.py:347-359`) and after every block in
`engine/scheduler/_dispatch.py`. A SIGKILL/OOM/power loss mid-write leaves
truncated JSON; `load_checkpoint` (`checkpoint.py:281-284`) then raises,
and because there is no prior-good copy, every "run from here" affordance
(`scheduler/__init__.py:385`, `api/runtime/_runs.py:247`) is dead until a
full re-run. Fix: write to `<path>.tmp`, fsync, `os.replace`.

### BUG-2 — Non-atomic artifact writes in SaveData (data corruption)

Every `_save_*` in `src/scistudio/blocks/io/savers/save_data.py` writes
straight to the final destination: `pickle.dump` (L393/476/526), `np.save`
(L400), `pq.write_table` (L448), `path.write_text` (L616), `shutil.copy2`
(L635), JSON manifest (L714). `_ensure_save_target_available`
(`blocks/io/savers/_capability.py:642`) checks existence only *before*
writing. A worker crash mid-write leaves a half-written file; with
`overwrite=True` the prior good artifact is already destroyed. These are
the persisted scientific outputs that lineage then references — silent
corruption of the product the system exists to protect. Same fix as BUG-1
(temp + atomic rename in one shared helper).

### DSN-1 — No run identity in the event/runtime model

- `ApiRuntime` owns one `EventBus` for the whole server
  (`api/runtime/__init__.py:222`); every `DAGScheduler` subscribes six
  handlers (`engine/scheduler/__init__.py:168-173`) and **never
  unsubscribes** — finished runs keep reacting to future runs' events and
  keep overwriting the checkpoint slot with stale state
  (`engine/scheduler/_events.py:55-63`). The identical bug class was
  already fixed once for `LineageRecorder`
  (`core/lineage/recorder.py:136-158`, "Codex P1 on PR #926") yet the
  design persists for schedulers.
- `EngineEvent` carries no run id (`engine/events.py:58-64`).
  `_on_cancel_workflow` (`engine/scheduler/_events.py:198`) ignores
  `event.data["workflow_id"]` — verified: it cancels every RUNNING/PAUSED
  block of every live scheduler on the shared bus. `ProcessRegistry` keys
  subprocess handles by bare `block_id`
  (`engine/runners/process_handle.py:115,121`), so same-named nodes in two
  workflows collide and `terminate()` can kill the wrong run's process.
- Fix direction: mandatory `run_id` on every event with subscribe-time
  filtering (or a per-run bus), registry keyed `(run_id, block_id)`,
  symmetric subscribe/dispose in scheduler lifecycle.

### DSN-2 — Contracts are convention, not enforcement

- `Block.validate()` — the advertised contract hook
  (`blocks/base/block.py`, port/required/constraint checks at L151-222) —
  is never called in the execution path; the worker invokes `block.run`
  directly (`engine/runners/worker.py:445`). `postprocess()` is only
  invoked on the subworkflow path (`blocks/subworkflow/subworkflow_block.py:182`),
  never in the main worker path. Runtime port/type checking is dead code.
- `save_workflow` runs `validate_workflow` but on errors only
  `logger.warning(...)` and saves anyway (verified,
  `api/runtime/_workflows.py:49-56`); `start_workflow → load_workflow`
  never validates (`api/runtime/_runs.py:238`). An ill-typed graph saves
  cleanly and fails deep inside a block at run time. This contradicts
  AGENTS.md ("typed workflow graphs, formal block contracts", "do not
  bypass schemas, lineage, runtime checks") — the documented invariants are
  not wired in.
- Fix direction: call `block.validate(inputs)` in the worker pre-`run`,
  validate outputs against effective output ports post-`run`, and make
  save/start reject (or require explicit force) on validation errors.

### DSN-3 — Governance machinery is process documentation, not enforcement

The ADR-042 stack (~9.2k LOC in `qa/`, ~5.2k LOC tests, 26 docs) polices
agents with code those agents control:

- `workflow-gate.yml:222,278-385` runs `gate_record ci` and the guard
  orchestration from the PR's own checkout on `pull_request` — a PR editing
  `src/scistudio/qa/governance/` is validated by its own modified guards
  (`mod_guard` included, since mod_guard is the code being run).
- Gate "evidence" is self-reported: `check_record(..., status="pass")` and
  `sentrux_record` persist agent-declared statuses unverified
  (`qa/governance/gate_record/stages.py:163-232`); amendments are
  self-approved (`stages.py:98-124`).
- Receipts are forgeable by documented design: `gate_receipt exec --name
  mypy -- true` records exit 0 under any check name
  (`qa/governance/gate_receipt.py:411-427`), receipts live in gitignored
  `.workflow/local/` and CI never sees them.
- Local hooks honour agent-settable env vars
  (`SCISTUDIO_GATE_BYPASS_LABELS`, `gate_record/validation.py:100-101`;
  `SCISTUDIO_GOVERNANCE_CHANGE_APPROVED=1`, `qa/governance/mod_guard.py:16,62-63`);
  the worktree write guard matches only `Edit|Write|MultiEdit`
  (`agent_provisioning/hooks.py:82`) so `Bash` writes (`sed -i`) bypass it;
  and no committed `.claude/settings.json` registers the PreToolUse hooks
  in the dev repo itself.

Real enforcement is `ci.yml` (independent ruff/mypy/pytest/full-audit) plus
branch protection and human review. That is a defensible design for
cooperative agents — but AGENTS.md §3.1/§3.7 and
`docs/ai-developer/specific_rules/gated-workflow.md` present the gate as
hard evidence ("hard fail points", "hook-verifiable transcript"), which
overstates the guarantee. Either document the cooperative-agent threat
model explicitly, or move verification server-side (CI recomputing checks
from the base ref's guard code). Issue #1509 (gate-record ledger + single
shared evaluator) and #1498 (anti-direct-edit provenance) already point
this direction; this finding adds the PR-controlled-guard-code and
receipt-forgeability gaps to that scope.

### DOC-1 — README block-development example is broken four ways

`README.md:283-304` (verified):

1. `from scistudio.blocks.base import ProcessBlock` — `ProcessBlock` is not
   exported there (`blocks/base/__init__.py`; it lives in
   `blocks/process/process_block.py:23`). ImportError on line 1.
2. `from scistudio.core.types import Spectrum` — no `Spectrum` class exists
   anywhere in the repo (core types module explicitly says domain types
   live in plugin packages; none of `packages/scistudio-blocks-*` defines
   it).
3. `category = "spectroscopy"` — the Block ABC has no `category` ClassVar
   (real attribute: `subcategory`, `blocks/base/block.py:32-41`).
4. `item.view().to_memory()` — `DataObject` has no `view()`; ADR-031
   removed ViewProxy (`core/types/base.py:399-446`).

The first code a prospective block developer copies fails at import. The
working example exists in `docs/block-development/quickstart.md`; README
should embed or link it.

### DOC-2 — `scistudio install --skill` installs an undiscoverable layout

`cli/install.py:399-421` installs the skill tree nested under
`~/.claude/skills/scistudio/` (sub-skills at
`skills/scistudio/scistudio-write-block/SKILL.md`), while
`agent_provisioning/skills.py:7-18` documents — from ADR-040 Phase 4 e2e —
that Claude Code and Codex skill discovery walk one level only and the
nested layout yields `Skill(scistudio-write-block) -> Unknown skill`.
Project provisioning was fixed to install FLAT; the user-scope installer
was not. `docs/cli-integration.md:119-147` meanwhile promises auto-discovery
of all 5 sub-skills. Documented user-facing behavior does not work.

### TST-1 — Worker contract test can pass having asserted nothing

`tests/engine/test_worker.py:191-235`
(`test_main_outputs_include_environment_key`, issue #54 contract): all five
assertions sit under `if "error" not in parsed:` (verified, L228). If the
stub block ever becomes unimportable from the subprocess (an easy
regression in a src-layout repo), the test degenerates to `json.loads` and
stays green while the documented environment/lineage contract goes
untested. Fix: `assert "error" not in parsed, parsed` first.

### TST-2 — The AI write guard is untested in the direction that matters

`tests/qa/test_worktree_write_guard.py` (3 tests) covers only blocking
cases. There is no positive-control test (in-scope write → no error), no
missing-gate-record case, and **none of the 6 scripts in `scripts/hooks/`
is ever executed by any test** — `tests/qa/test_gate_record_hooks.py:14`
only greps hook text for expected strings. A guard that blocks everything,
or a payload parser that returns `[]` for every input, passes the current
suite. For the mechanism AGENTS.md presents as the enforcement hook, this
is false confidence at the governance core. Fix: execute the hook scripts
in tests with fabricated PreToolUse payloads, assert both allow and deny
paths.

## 4. P2 findings

### Bugs

- **BUG-3 — `/api/filesystem/browse` skips the mandated sanitiser.**
  `api/routes/filesystem.py:231-250` does `Path(path)` + `iterdir()`
  directly; sibling `stat`/`reveal` use `_resolve_safe_path`, and the
  module docstring (L24-37) explicitly states browse needs it (verified).
  Unauthenticated enumeration of any server-readable directory
  (`?path=/etc`). One-line fix; also a doc-vs-code drift inside one module.
- **BUG-4 — No double-start guard.** `api/runtime/_runs.py:297`
  unconditionally replaces `workflow_runs[workflow_id]`; the prior
  scheduler keeps running (uncancellable, unreachable via API), racing the
  new run on the shared checkpoint slot, lineage recorder, and process
  registry. Verified at `_runs.py:297-302` and
  `api/routes/workflows.py:454-470`. Reject or queue when a live run
  exists; key runs by `run_id`.
- **BUG-5 — Upload size cap enforced after full buffering.**
  `api/routes/data.py:27-29`: `await file.read()` then the 2 GB check.
  Stream with a running counter instead.
- **BUG-6 — Error isolation converts provenance loss into silent success.**
  `engine/events.py:105-115` catches all subscriber exceptions;
  `core/lineage/recorder.py:118-134,200-228` treats every store error as
  non-fatal; `_finalize_lineage_run` (`api/runtime/_runs.py:124-160`)
  derives status only from task exception + block states. A run whose
  lineage rows failed to write still finalizes `completed` with only a log
  line as evidence. At minimum surface a degraded-provenance flag on the
  run row.

### Design

- **DSN-4 — Blocking work on the event loop; single-project global.**
  Pre-run git auto-commit, YAML IO, `EnvironmentSnapshot.capture(full=True)`
  run inline in async routes (`api/runtime/_runs.py:189-228`); lineage
  SQLite writes happen synchronously inside event handlers in the scheduler
  hot path (`recorder.py:164-228`). `ApiRuntime.active_project` is one
  process-global slot (`runtime/__init__.py:199`); WS clients can cancel
  any workflow without auth (`api/ws.py:272-295`). Acceptable for a local
  single-user app, but the ceiling is nowhere documented; sync work belongs
  in executors.
- **DSN-5 — Lineage references mutable bytes.** `data_objects.storage_path`
  has no content hash, no size/mtime captured; checkpoint module itself
  documents intermediates "may be overwritten by subsequent runs"
  (`engine/checkpoint.py:19-21`); `INSERT OR IGNORE` upserts
  (`core/lineage/store.py:422-452`) are first-writer-wins. Provenance for a
  *scientific* runtime should be tamper-evident: digest at write time +
  run-scoped output dirs.
- **DSN-6 — No persisted-state versioning.** `lineage.db` has no
  `user_version`/migrations (`store.py:129-180`); checkpoints are
  versionless JSON dumps; wire format carries no version;
  `metadata_store.py:23` states "no historical data migration". Any format
  change strands existing projects. Only the gate record has
  `schema_version`.
- **DSN-7 — Scan-time arbitrary code execution.** Tier-1 discovery
  `exec_module`s every `*.py` in scan dirs on each registry refresh
  (`blocks/registry/_scan.py:135-139`), with mtime-stamped module names
  accumulating in `sys.modules`, and mutates global `sys.path`
  (`_scan.py:328-329`). Dropping a file runs its top-level code at palette
  refresh, not at user-initiated run. Related open issue #1374 covers name
  collisions only. Consider subprocess/AST-based spec extraction for
  discovery.
- **DSN-8 — Live run state unreadable; disconnect kills runs.** No REST
  endpoint exposes scheduler `block_states` (MCP reaches into the private
  `_block_states`, `ai/agent/mcp/tools_workflow/read.py:267`); the frontend
  rebuilds state purely from WS events with no sequence numbers or
  reconnect resync (`frontend/src/store/executionSlice.ts`; open issue #177
  notes missing reconnection). The GUI-disconnect policy cancels **all**
  running workflows 2 s after the last WS client drops
  (`api/ws.py:40,160-220`) — a flaky tab kills a long computation. Add a
  snapshot endpoint + sequence numbers + an explicit detached-run mode.

### Doc drift

- **DOC-3 — Coverage claims.** `README.md:356,432` say 85% enforced;
  actual gate is 70% (`pyproject.toml:171,259`) and only on the
  Python 3.13 leg (`.github/workflows/ci.yml:131-136`; 3.11 runs
  `--no-cov`). Verified.
- **DOC-4 — README describes a previous architecture generation.**
  ViewProxy lazy loading presented as implemented (`README.md:40,205,419`)
  though ADR-031 eliminated it; `ai/generation|synthesis|optimization`
  modules (`README.md:222-225`) don't exist (`src/scistudio/ai/` has only
  `agent/`); workspace layout (`README.md:261-274`) shows `checkpoints/`,
  `lineage/` dirs retired by ADR-038 (`cli/main.py:101-116` creates
  `.scistudio/`, `data/exchange/`). `docs/architecture/ARCHITECTURE.md` is
  accurate throughout — README is the stale surface.
- **DOC-5 — Agent-facing tool catalog drift.** 27 tools are registered via
  `@mcp.tool` under `ai/agent/mcp/`; the packaged static catalog
  (`src/scistudio/_skills/scistudio/SKILL.md:90-103`) says 26 and lists
  `list_block_runs`, which is registered nowhere, while omitting the real
  `get_block_config` and `get_active_workflow_context`; README/cli docs say
  25. Agents steered by the fallback catalog will call a nonexistent tool.
- **DOC-6 — Provisioning docs vs code.** `docs/agent-provisioning.md:16-39,145-148`
  documents 6 hooks and a nested skill tree; `agent_provisioning/hooks.py:39-50`
  installs 7 (the docstring of that very module still says 6) and
  `skills.py` installs flat.
- **DOC-7 — License.** MIT badge and license section
  (`README.md:7,463-465`) but no LICENSE file exists (verified);
  `PROJECT_TREE.md` lists one. Public licensing claim is not legally
  effected.

### Tests

- **TST-3 — Five empty skipped stubs.** `tests/blocks/test_registry.py:481-517`,
  skip reason "Agent B implements in Stage 10.1 Part 2", bodies are
  docstrings only (verified); the described source rename never landed
  (`blocks/registry/__init__.py:272` still `source == "tier1"`). No issue
  cited (violates §3.6); un-skipping converts a known gap into green.
- **TST-4 — 67 module-skipped MCP tests with thinner replacements.** Five
  files (`tests/ai/test_mcp_server_skeleton.py:35` and four siblings) all
  `pytestmark = skip` for #1012; replacement `test_mcp_fastmcp.py` (15
  tests) does not restore the disk-integration coverage that existed
  specifically to catch the #790 CWD-relative path bug.
  `ai/agent/mcp/tools_authoring.py:263` still `raise NotImplementedError`.
- **TST-5 — "TEMP" coverage downgrade untracked.** `pyproject.toml:170-171`:
  `# TEMP: lowered until ADR-034 Phase 1-3 restores test coverage` with no
  `TODO(#NNN)` (verified); history shows it never went back up. The repo's
  own deferral rule (AGENTS.md §3.6) forbids exactly this.
- **TST-6 — Assertion-free / self-contradicting tests.**
  `tests/blocks/test_process_block.py:41` and
  `tests/blocks/test_subworkflow.py:102` are named `test_state_transitions`
  but assert nothing; `tests/engine/test_scheduler.py:575-580` docstring
  claims `save_checkpoint` is "a no-op placeholder" while
  `engine/scheduler/__init__.py:360` implements full persistence called
  from 10 sites.

## 5. P3 findings (abridged)

- **BUG-7** Process handles never deregistered after `proc.communicate()`
  (`engine/runners/local.py:276-283`); `terminate_all`
  (`engine/runners/process_handle.py:129-144`) on accumulated dead PIDs can
  kill an unrelated reused PID at shutdown.
- **BUG-8** Workflow YAML saved non-atomically
  (`workflow/serializer.py:114-131`) while watcher/other clients read
  concurrently — transient 422s; git history backstops recovery.
- **BUG-9** `EventBus.emit` iterates the live subscriber list
  (`engine/events.py:105`); one in-dispatch (un)subscribe makes it a real
  bug. Snapshot with `list(...)`.
- **BUG-10** `allow_pickle` block config turns "open shared workflow + run"
  into code execution (`blocks/io/savers/save_data.py:393,476,526`,
  `loaders/load_data.py:341,465,557`). Opt-in and documented — flagged as
  accepted-risk surface worth a louder UI warning.
- **BUG-11** `LineageStore.execute_query` docstring says read-only but
  nothing enforces it (`core/lineage/store.py:553-565`).
- **BUG-12** `gate_record plan` does not validate field values at write
  time: passing `--tests "na:<rationale>"` (a form the docs invite for N/A
  rationales via the adjacent `--docs` flag) persists a non-test path into
  `changed_test_paths`, after which **every** subsequent CLI operation on
  that record fails load-time validation — the CLI bricks its own record
  with no repair path other than recreating it. Reproduced live during
  this audit. Validate-before-persist in every mutator. Related UX gap,
  same module: the only CLI path that marks the IMPLEMENT stage done is
  `amend` (`gate_record/stages.py:123`), so a task with no scope change
  must issue a no-op amendment to satisfy `gate_record ci` — undocumented
  in `gated-workflow.md`.
- **DSN-9** Frontend hand-mirrors backend port semantics
  (`frontend/src/utils/portCompat.ts:1-13`, `computeEffectivePorts.ts`) with
  no shared conformance fixture — a drift machine.
- **DSN-10** Protected-path friction breeds untyped backdoors:
  `event_bus.runtime = self  # type: ignore` (`api/runtime/__init__.py:223-227`),
  duck-typed consumption in `ws.py:162-204`, duplicated event-name strings
  (`core/lineage/recorder.py:38-46`, `api/ws.py:43-48` citing "frozen by
  ADR-035/036 hard-scope"). The guard granularity is producing the coupling
  it exists to prevent.
- **DSN-11** Vacuous CI check: `ci.yml:208-223` compares `frontend/src`
  mtimes against an `index.html` rebuilt earlier in the same job — can
  never fail; its premise (committed `dist/`) is obsolete (`dist/` is
  gitignored).
- **DSN-12** `workflow_runs` and `data_catalog` grow unboundedly per
  session (`api/runtime/__init__.py:200-201`).
- **DSN-13** WS cancel/auth posture and single-user ceiling undocumented
  (overlaps DSN-4).
- **DOC-8** README lists Block SDK / BlockTestHarness as both Implemented
  (`README.md:69,311-314`) and Planned (`:435`); both exist
  (`cli/main.py:311-349`, `testing/harness.py:28`).
- **DOC-9** README understates implemented surface: R/Julia runners called
  stubs (`:423,438`) but are full subprocess implementations
  (`blocks/code/runners/{r_runner,julia_runner}.py`); ADR-041 backends add
  MATLAB/shell/notebook/Quarto.
- **DOC-10** Broken cross-references: `docs/adr/ADR.md`, `docs/roadmap/`
  (`README.md:393,248`); `docs/guides/ai-chat.md`,
  `docs/specs/eca-spike-codex-format.md` (`docs/cli-integration.md:248-252`).
- **DOC-11** `CONTRIBUTING.md:19` says `mypy packages/`; CI/Makefile gate
  `src/scistudio/` — contributors verify the wrong tree.
- **DOC-12** "Five Block Categories" heading enumerates six
  (`README.md:42-51`); "adapter registry" terminology is pre-ADR-043;
  CHANGELOG has only `[Unreleased]` despite `version = "0.2.1"`, no git
  tags, and a PyPI quick start (`README.md:146-151`) with no release
  machinery having run.
- **TST-7** Dead skeleton stubs: 8 `xfail(run=False)` in
  `tests/engine/test_pty_control_skeleton.py:34-88` (real coverage exists
  in `test_pty_control.py`); 13 `it.skip` in
  `frontend/src/components/AIChat/__tests__/TerminalTabs.skeleton.test.tsx:22-90`
  (real file has ~20 tests). Delete both.
- **TST-8** Environment-conditional `pytest.skip` guarding the condition
  under test: `tests/api/test_runtime_rerun_parent_id.py:49,82` skips when
  the lineage store is None — the exact regression it should catch.
- **TST-9** No `filterwarnings = ["error"]` decision recorded
  (`pyproject.toml:168-185`).

## 6. What was checked and found sound

- DAG cycle handling (`engine/dag.py:128-129` raises `CycleError`;
  traversals use visited sets); no `shell=True`/`os.system`/unsafe
  `yaml.load`/`eval` in the audited tree; IPC token auth uses
  `secrets.compare_digest`; MCP/PTY path validation uses allowlist checks.
- Layering discipline is above average: import-linter contracts with cited
  carve-outs (`pyproject.toml:187-232`), architecture tests, cycle
  baseline guard (open issues #1336/#1341 track the known SCC).
- Governance *unit* tests are substantive where they exist
  (`tests/qa/test_gate_record.py` 36 tests, real-git-repo guard tests);
  the gap is hook execution and positive controls (TST-2).
- `docs/architecture/ARCHITECTURE.md`, `docs/block-development/`, gate CLI
  docs (`rules.md` §5) match the code exactly (every documented subcommand
  and flag verified); `scripts/scistudio_pr_create.py` and all
  personas/templates referenced by AGENTS.md exist.
- Test hygiene basics: no `assert True` tests, no try/except-swallowed
  assertions, no out-of-tmp writes or network dependence found;
  `tests/integration/test_smoke_workflows.py` runs real end-to-end
  execution.

## 7. Recommended follow-up grouping

1. **Durability batch (BUG-1, BUG-2, BUG-8):** one shared atomic-write
   helper (temp + fsync + `os.replace`); adopt in checkpoint, all savers,
   YAML serializer.
2. **Run-identity batch (DSN-1, BUG-4, DSN-8, BUG-6):** mandatory `run_id`
   on events, scheduler unsubscribe/dispose, double-start guard, run-state
   snapshot endpoint, degraded-provenance flag. This is the largest
   architectural item and should get an ADR.
3. **API hardening (BUG-3, BUG-5):** add `_resolve_safe_path` to browse;
   streamed upload cap. Small, immediate.
4. **Contract enforcement (DSN-2):** wire `Block.validate` into the worker;
   make save/start validation rejecting. Needs an ADR amendment since it
   changes runtime behavior.
5. **Governance honesty (DSN-3, TST-2):** fold the PR-controlled-guard-code
   and receipt-forgeability gaps into existing #1509/#1498 scope; add hook
   execution tests + positive controls; document the cooperative-agent
   threat model in AGENTS.md.
6. **Docs sweep (DOC-1..12):** rewrite README against
   ARCHITECTURE.md/quickstart.md; fix the install --skill flat layout
   (DOC-2 is a code fix); regenerate the MCP tool catalog from the
   registered tool list so it cannot drift; add LICENSE.
7. **Test hygiene (TST-1, TST-3..7):** invert the worker-test conditional;
   delete dead stubs; file the missing #NNN for the coverage TEMP and
   registry stubs.

Severity totals: **9 P1, 17 P2, 22 P3.** Recommendation:
**pass-with-fixes** — file tracked issues for groups 1-5 before the next
cascade builds on these layers; groups 6-7 are routine cleanups.
