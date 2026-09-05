---
title: "ADR-054 Assembly Follow-Up Register"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Follow-Up Register

This file exists because the owner forbade opening new GitHub issues during
the ADR-054 assembly:

> 除了实现代码对应的issue外，任何follow-up issue均不开，放到一个文件里等我醒了看。
>
> (Open no follow-up issue beyond the ones the implementation code needs; put
> them in one file for me to read when I wake up.)

Every deferral, edge case, cleanup, missing test, design question and drift
found during the assembly lands here instead of in the tracker. Each entry is
written so the owner can turn it into an issue in one step, or decide it is
not worth one.

The two issues that **were** opened, because they are the implementation
issues the directive permits:

- `#2253` — ADR-054 spec 4, the Explore tab and the notebook frontend.
- `#2254` — ADR-054 spec 5, the workspace focus, the panel skill, the session
  tools.

## How To Read An Entry

| Field | Meaning |
|---|---|
| **Severity** | `P1` blocks the feature; `P2` is a real defect that does not block; `P3` is cleanup or polish |
| **Found by** | The agent label, so its report and branch can be found |
| **Evidence** | A file and line, a test, or a command output — never a claim alone |
| **Suggested title** | Ready to paste into `gh issue create --title` |

## Register

### Manager

#### M-001 — PR #2255 needs the `admin-approved:core-change` label, applied by the owner

- **Severity**: P1 — CI's `Verify Workflow Compliance` job fails without it.
- **Found by**: manager, from PR #2238's CI run 33808346838.
- **Evidence**: `guard.core_change_guard` reports
  `protected core/runtime change requires admin-approved:core-change applied
  by an authorized maintainer or administrator approval`, affecting
  `src/scistudio/blocks/base/interactive.py`,
  `src/scistudio/blocks/process/builtins/data_router.py`,
  `pair_editor.py`, `src/scistudio/blocks/registry/__init__.py` and
  `_capability.py`.
- **Why it is here and not done**: the manager attempted
  `gh pr edit 2255 --add-label admin-approved:core-change` and the action was
  refused by this session's permission classifier. The owner's blanket
  pre-approval does not override that refusal, and the label's whole purpose
  is a human attestation whose actor provenance CI verifies — so it is the
  owner's to apply, deliberately.
- **What the label attests**: every affected file is named in the approved
  specs' own `governs.files`. ADR-054 spec 1 §3 changes the panel manifest on
  the block base and the registry's capability resolution; spec 3 §4.5 adds
  `on_new_input` to the same base and the packaged block's ask pause to the
  scheduler's dispatch. The change is what the approved specs ask for.
- **Action**: `gh pr edit 2255 --add-label "admin-approved:core-change"`, or
  the same from the PR page.
- **Suggested title**: N/A — this is an owner action, not an issue.

#### M-004 - The frontend's `ActiveContextResponse` does not declare the `focus` the server echoes

- **Severity**: P3 - not a break; the frontend ignores the extra field and
  nothing reads it today.
- **Found by**: manager, checking the spec 4 / spec 5 focus wire field by field.
- **Evidence**: `frontend/src/lib/api/ai.ts` declares
  `interface ActiveContextResponse { workflow_id: string | null }`. The server's
  `ActiveContextResponse` in `src/scistudio/api/routes/ai.py` returns
  `{workflow_id, focus}`, where `focus` is the **stored** record including the
  backend-stamped `reported_at`.
- **Why it is worth recording**: the request half of this wire is exact - the
  manager diffed `WorkspaceFocusPayload` against `WorkspaceFocusModel` and all
  seven fields match with nothing extra on either side. The response half is
  the one place the two descriptions differ, and it differs by omission rather
  than by disagreement, which is the benign direction. It is listed so that
  whoever first wants to read the echo back - to show a stale focus in the UI,
  say - finds the type already waiting rather than discovering the field by
  accident.
- **Suggested title**: `chore(frontend): ActiveContextResponse omits the focus the server returns`

#### M-003 - A stale `split_collection` entry point breaks block discovery at startup

- **Severity**: P3 - environment, not code; the server starts anyway.
- **Found by**: manager, launching the merged backend for the e2e readiness
  check.
- **Evidence**: the server logs
  `ModuleNotFoundError: No module named 'scistudio.blocks.process.builtins.split_collection'`
  during startup, then reaches `Application startup complete` and serves 135
  routes. The module exists **neither on this branch nor on `origin/main`** -
  `git cat-file -e origin/main:src/scistudio/blocks/process/builtins/split_collection.py`
  reports absent, and `grep -rn split_collection src/ pyproject.toml` finds
  nothing.
- **Reading**: a stale entry point in an installed distribution on this
  machine, left by an earlier install of a version that had the module. It is
  not an ADR-054 regression and nothing in this dispatch caused it.
- **Why it is worth recording**: it will keep appearing in every local
  startup log and in every e2e transcript, where it reads like a defect in
  whatever work is being tested. The e2e scenario now names it so it is not
  reported as one. Worth an environment clean-up, or a startup log line that
  distinguishes a stale registration from a broken import.
- **Suggested title**: `chore(env): a stale split_collection entry point logs a ModuleNotFoundError at every startup`

#### M-002 - `eslint-config.test.ts` flakes under machine load on a 5s timeout

- **Severity**: P3 - pre-existing, unrelated to ADR-054, and green in isolation.
- **Found by**: manager, taking the frontend baseline on the merged assembly
  branch before spec 4 lands.
- **Evidence**: `frontend/src/__tests__/eslint-config.test.ts:12`,
  `loads the project flat config without parser errors`, failed with
  `Test timed out in 5000ms` after running 12334ms during a full
  `npm run test` on a machine with several agents active. Re-run alone,
  `npx vitest run src/__tests__/eslint-config.test.ts` gives 8 passed.
  Full-suite baseline otherwise: **2315 passed, 1 failed, 198 files**; with
  the re-run the suite is 2316/2316.
- **Why it matters**: the test performs a real ESLint flat-config resolution,
  which is I/O-bound and easily exceeds 5s on a loaded runner. It will flake
  in CI on a busy day and will look like a frontend regression in whichever
  PR happens to be running.
- **Suggested title**: `flaky(frontend): eslint-config.test.ts resolves a real flat config on a 5s timeout`

### S4-A1

_No entries yet._

### S4-A2

_No entries yet._

### S4-A3

_No entries yet._

### S4-A4

_No entries yet._

### S5-B1

_No entries yet._

### S5-B2

_No entries yet._

### S5-B3

_No entries yet._

### S5-B4

_No entries yet._

### S4-D1 / S5-D1 (adversarial testing)

_No entries yet._

### S4-E1 / S5-E1 / INT-E1 (audits)

_No entries yet._

### fix-codeql

Triage of the 12 CodeQL alerts the assembly branch adds over `main`. Nine were
fixed on `fix/2229-panel-codeql-findings`; the three entries below are what was
left, plus what the fix could not reach from this branch.

#### FC-001 — 22 `py/path-injection` alerts in `plot/**`, `desktop/**` and `api/routes/data.py` are inherited from `main`

- **Severity**: P3 — not new, not this branch's, and not a regression. Whether
  any of them is real is unexamined.
- **Found by**: fix-codeql.
- **Evidence**: the code-scanning API says these are already open on the
  default branch, so the PR check counts them only because the assembly's diff
  moved their line numbers:

  ```bash
  gh api "repos/jiazhenz026/SciStudio/code-scanning/alerts?state=open&ref=refs/heads/main" \
    --jq '.[]|"\(.rule.id) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)"'
  ```

  returns 55 alerts including every `plot/_context.py`, `plot/scaffold.py`,
  `plot/targets.py`, `desktop/package_manager.py` and
  `tests/desktop/test_package_manager.py` line the PR annotates.
  `git diff --quiet origin/main HEAD -- <path>` is clean for all of them, and
  `api/routes/data.py:506` is `main`'s `data.py:770` after the assembly deleted
  288 lines above it.
- **Why it is here and not done**: fixing them would turn a scoped security fix
  into a repo-wide sweep across three subsystems the ADR-054 dispatch does not
  own, on a branch that has to merge.
- **Suggested title**: `Triage the 33 inherited py/path-injection alerts CodeQL reports on main`

#### FC-002 — the `scaffold_panel` skeleton and the agent-facing panel contract do not exist on this base, so the safe URL pattern is not in them yet

- **Severity**: P2 — the next authored panel reintroduces the finding this PR
  fixed in `core.plot.basic`.
- **Found by**: fix-codeql.
- **Evidence**: `src/scistudio/ai/agent/mcp/tools_panels/` and
  `src/scistudio/_agent_reference/panel-contract.md` are both absent from
  `track/adr-054-integration`; they are S5-B2's work on PR #2257, which targets
  `track/adr-054-spec5-agent-enablement`. The pattern this PR establishes is
  `safeAssetUrl` in
  `src/scistudio/panels/builtin/core.plot.basic/index.html` (an allowlist of
  `data:` media types per element plus a root-relative path, with TAB/LF/CR
  stripped before the check) and `idMap()` in
  `src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html`
  (`Object.create(null)` for any map keyed by something out of the payload).
- **Why it is here and not done**: editing files that do not exist on this
  branch is not possible, and creating them here would collide with #2257.
- **Suggested title**: `Carry the panel URL allowlist and null-prototype map pattern into the scaffold_panel skeleton and the agent panel contract`

#### FC-003 — one `py/stack-trace-exposure` alert in `api/routes/git.py` is new on the assembly branch and outside the panel dispatch's scope

- **Severity**: P3 — medium severity, not among the 46 the PR check calls high,
  and untriaged.
- **Found by**: fix-codeql.
- **Evidence**: alert 270, `src/scistudio/api/routes/git.py:685`, present on
  `refs/pull/2255/head` and absent from `refs/heads/main`;
  `git diff --stat origin/main HEAD -- src/scistudio/api/routes/git.py` shows
  `+52` lines on this branch. It was not in the annotation set the dispatch
  named, and `api/routes/git.py` is in no agent's write set.
- **Why it is here and not done**: out of scope for this fix, and whichever
  spec added those 52 lines should own it.
- **Suggested title**: `Triage the py/stack-trace-exposure alert the assembly adds at api/routes/git.py:685`

### fix-kernel

#### FK-001 — `test_kernel_session.py` carries a second `_process_gone` that still counts a zombie as alive

- **Severity**: P3 — latent, not currently failing.
- **Found by**: fix-kernel, while fixing #2240's death detection.
- **Evidence**: `tests/explore/test_kernel_session.py:98` checks only
  `psutil.pid_exists` and `Process.is_running()`. psutil reports both as true
  for an unreaped zombie, so this copy has exactly the defect the manager
  fixed in `tests/explore/test_explore_session.py:113`. It passes today only
  because every one of its callers reaps first — either
  `psutil.Process(pid).wait(...)` in the test, or `KernelHandle.stop()`'s
  `_wait_for_exit` — so nothing currently reaches it with a live zombie.
- **Why it is here and not done**: changing it is not needed to fix #2240 and
  the bug-fix rule forbids widening a fix past its cluster. The moment a new
  test in that file kills a kernel without reaping it, it will hang for its
  full 10 s timeout and then report a dead kernel as alive.
- **Suggested title**: `Unify the three _process_gone test helpers on the
  zombie-aware reading`

#### FK-002 — three copies of `_process_gone` now exist across the explore tests

- **Severity**: P3 — duplication, not a defect.
- **Found by**: fix-kernel.
- **Evidence**: `tests/explore/test_explore_session.py:113`,
  `tests/explore/test_kernel_session.py:98`, and the branch-switch assertions
  in `tests/api/test_explore_branch_switch.py` all need the same "is this pid
  really gone" reading, and they have drifted apart (only one of them counts
  a zombie). A shared helper — plausibly next to `KernelHandle` itself, since
  the product now needs the same reading — would keep them honest.
- **Suggested title**: `Share one zombie-aware process-liveness helper between
  the explore kernel tests`

#### FK-003 — the death-detection test is a race the suite only loses under load

- **Severity**: P2 — the fix holds, but the end-to-end test does not prove it
  reliably.
- **Found by**: fix-kernel, reproducing #2240 in WSL.
- **Evidence**: `test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart`
  passes in isolation and passes when only `tests/explore` runs; it fails only
  in the full `-m serial` phase, where the process holds eight live threads and
  the killed kernel's thread group takes long enough to drain that
  `/proc` says `Z` while `waitpid` still says "not yet". A test that only
  fails on a loaded machine is a test that will go quiet again. The
  platform-independent guarantee now lives in the stub-driven tests added to
  `tests/explore/test_kernel_session.py`; the end-to-end test is kept because
  it is the only one that proves the wiring, not because it is dependable.
- **Suggested title**: `Make the explore kernel-death end-to-end test
  deterministic rather than load-dependent`

#### FK-004 — the app-block file watcher reads liveness the same untrustworthy way

- **Severity**: P3 — different subsystem, and its failure mode is bounded.
- **Found by**: fix-kernel, sweeping for the same pattern after #2240.
- **Evidence**: `src/scistudio/blocks/app/watcher.py:191` `_handle_is_alive()`
  answers `poll() is None` for a plain `Popen`, which is exactly the reading
  that reported a dead explore kernel as healthy — on Linux `waitpid`
  withholds a killed multi-threaded process while its sibling threads exit,
  so `poll()` returns `None` about a corpse.
- **Why it is here and not done**: `src/scistudio/blocks/**` is outside this
  fix's write set, and the consequence there is milder — the docstring says a
  handle whose liveness is unknown is treated as alive "so the watcher relies
  on its timeout instead", so a false "alive" costs a delay rather than a
  wrong answer to the person. Worth aligning on the same pid-aware reading if
  the watcher ever grows a tighter deadline.
- **Suggested title**: `Give the app-block watcher the same pid-aware liveness
  reading as the explore kernel`

#### FK-005 — `Test (Python 3.13)` stalls out its whole 600 s parallel phase on the track branch

- **Severity**: P1 — it fails every CI run on `track/adr-054-integration` and
  on every branch cut from it, so no sub-PR of this assembly can go green.
- **Found by**: fix-kernel, while proving #2240's fix in CI.
- **Evidence**: it is **not** caused by the #2240 fix — the same job fails
  identically on the branch point. On `track/adr-054-integration` at
  `fa678c7ff` (run 33957302816, the exact base of PR #2262): 3.13's parallel
  phase printed 31 dots and was killed by `timeout 600` with exit 124, while
  3.11 finished the same phase with `9308 passed ... in 443.05s`. On PR
  #2262 at `151738a87` (run 33957753781): 3.13 printed 16 dots and was killed
  at exactly 600 s; 3.11 passed both phases in 11m48s. Runs 33955810545 and
  33957302816 on the track branch both fail 3.13 the same way.
- **The one asymmetry worth starting from**: `ci.yml` runs 3.13 **with
  coverage** and 3.11 with `--no-cov`. The same test set that completes in
  443 s uncovered does not get past a few dozen tests in 600 s covered, which
  looks like a stall rather than slowness. Nothing diagnosable survives,
  because the shell-level `timeout 600` hard-kills the phase before
  pytest-timeout's per-test 60 s kill can print a traceback — so the first
  step is probably to let pytest-timeout win (raise the shell timeout, or
  lower the per-test one) and get a stack out of it.
- **Why it is here and not done**: it is a CI-wide defect on the integration
  branch, not part of #2240's cluster, and fixing it would mean editing
  `.github/workflows/ci.yml`, which is outside this fix's write set.
- **Suggested title**: `Test (Python 3.13) stalls its parallel phase under
  coverage and is killed at the 600 s shell timeout`
- **Resolved by**: the `fix-citime` entries below, on
  `fix/2253-ci-test-budget`. Two corrections to the reading above, both from
  the raw job logs rather than the web log view: it is **not a stall** -- the
  killed runs print progress all the way to 96-97% (126 progress lines in run
  33952874542; the "31 dots" and "16 dots" counts are what the collapsed web
  log shows, not what the job printed) -- and the asymmetry called out here is
  exactly right: coverage is ~1.5x, and it is what pushed an honest 662 s
  parallel phase past a 600 s guard. The instinct to raise the shell timeout
  to get a diagnosis was also right, and is what produced the numbers in
  FT-001.

### fix-citime

Entries are prefixed `FT-` because `FC-` is already taken by `fix-codeql`.

#### FT-001 — `tests/qa/test_audit_full_audit.py` runs the whole ADR-042 audit against the real repository, twice, inside the unit suite

- **Severity**: P3 — cleanup with a real price, not a defect.
- **Found by**: fix-citime, measuring where the 3.13 parallel phase goes.
- **Evidence**: CI run 33960011315, `Test (Python 3.13 sysmon)`,
  `--durations=40` over 9313 tests:
  `test_full_audit_renders_human_readable_facts_summary` 11.63 s (3rd
  slowest) and `test_full_audit_reports_stale_generated_facts` 8.21 s (6th).
  Both call `full_audit.run(REPO_ROOT, ...)`, which is the same repository-wide
  work the dedicated `Full Audit` CI job already does in its own parallel job
  — frontmatter lint, fact drift, doc drift, developer docs, closure,
  signature drift, architecture drift and vulture, over the whole tree.
- **Why it is here and not done**: every cheap reduction costs coverage. The
  markdown test asserts that *every* child report appears in the rendered
  summary, so the children cannot be disabled; pointing `run()` at a
  synthetic tree would keep the assertions but stop them being about this
  repository. Which of those is acceptable is an owner call, not a fix
  agent's.
- **Suggested title**: `tests/qa/test_audit_full_audit.py duplicates the Full Audit job inside the unit suite`

#### FT-002 — `generate_facts` has no cache, so every caller pays a full griffe walk of the package

- **Severity**: P3.
- **Found by**: fix-citime.
- **Evidence**: before this fix, `tests/qa/test_generate_facts_cli.py` was the
  1st and 2nd slowest tests in the whole parallel phase — 30.52 s and 22.57 s
  on CI (run 33960011315) — because two tests made **four** CLI invocations
  and each one walks `src/scistudio` with griffe from scratch. Locally a
  single `--write` is 13 s and a single `--check` 17-19 s. This PR shares one
  `--write` across the module and takes it to three invocations; the
  remaining three are irreducible from the test side because `--check`
  regenerates by definition.
- **Why it is here and not done**: the cache would belong in
  `src/scistudio/qa/audit/facts.py`, keyed on source file hashes, and
  `src/scistudio/**` is outside this fix's write set. It would also speed up
  the `Full Audit` job and every local `gate_record check`.
- **Suggested title**: `cache generate_facts so the griffe walk is paid once per source state`

#### FT-003 — raising the xdist worker count nearly halves the parallel phase, and crashed a worker once out of two tries

- **Severity**: P2 — a real, large speedup that is not safe to take on the
  evidence available.
- **Found by**: fix-citime, CI run 33960875235 (three legs, same commit, same
  runner class, coverage on, `COVERAGE_CORE=sysmon`).
- **Evidence**:

  | workers | parallel phase | result |
  |---|---|---|
  | `-n auto` (4 on ubuntu-latest) | 534.33 s | clean, coverage 88% |
  | `-n 6` | 383.99 s | **`[gw0] node down: Not properly terminated`** while running `tests/qa/test_generate_facts_cli.py::test_generate_facts_write_and_check_round_trip`; coverage collapsed to 55% because the dead worker returned no data |
  | `-n 8` | 310.65 s | clean, coverage 88% |

  A 42% cut in wall clock for a one-token change is the largest single lever
  found anywhere in this investigation — the suite is I/O-bound enough that
  4 workers leave the runner idle. But a crashed worker is worse than a slow
  job: it fails a random PR for no reason a reader can act on, and it
  silently destroys that worker's coverage data, which on the serial phase
  would trip `--cov-fail-under=70` and blame the wrong change.
- **Why it is here and not done**: one crash in two oversubscribed runs is
  not enough to characterise. Taking it needs a handful of repeat runs at
  `-n 8` to see whether the crash recurs, and a look at whether it is memory
  (the griffe walk under N workers) or something in that test. Worth doing —
  it would take the whole `Test` job under five minutes — but it is a
  deliberate reliability trade the owner should make, not one to land while
  he is asleep.
- **Suggested title**: `measure -n 8 for the CI parallel phase: 42% faster, one unexplained worker crash`

#### FT-004 — the `Test` matrix legs run different workloads and nothing said so

- **Severity**: P3 — fixed by this PR's comment, recorded because it cost
  three agents a diagnosis.
- **Found by**: fix-citime; independently by fix-kernel (FK-005).
- **Evidence**: `Test (Python 3.11)` runs `--no-cov`; `Test (Python 3.13)`
  measures coverage. On run 33960011315 that is 435.70 s versus 662.34 s for
  the identical test set. Every reading of the failure started from "3.13 is
  broken" because the workflow's comment described the two-phase split and
  the coverage split, but not that the 3.13 leg therefore carries ~1.5x the
  runtime of the leg people compare it against.
- **Why it matters beyond the comment**: the same asymmetry means the 3.11
  leg is not a usable early-warning signal for the 3.13 leg's budget. If the
  owner wants one, the cheapest version is to keep printing `--durations`
  (this PR does) and watch the 3.13 parallel total.
- **Suggested title**: `document, or remove, the coverage asymmetry between the two Test matrix legs`

## Already-Tracked Follow-Ups Inherited From Specs 1 To 3

These already have issues. They are listed so the owner sees the whole
ADR-054 debt in one place, not so they are opened again.

| Issue | Subject | Source |
|---|---|---|
| `#2212` | Let a plot panel declare the producing capability | ADR-054 §10.2, explicitly out of scope |
| `#2233` | A producing panel's emission has no time bound and runs on the scheduler's event loop | spec 1 dispatch |
| `#2236` | Revise the human-facing panel vocabulary and documentation (ADR-054 spec 6) | ADR-054 §10.1 |
| `#2237` | Nothing checks the API wire between `schemas.py` and `types/api.ts` | spec 1 dispatch — the mechanism behind three fixed wire breaks |
| `#2242` | The ADR and the explore-frontend spec name `ExploreTab.test.tsx` at two different paths | spec 4 input defect |
| `#2243` | Spec 2 FR-015's unresolved-read exception rests on a false premise | needs an owner decision |
| `#2244` | `test_concurrent_write_workflow_serialises` is not marked serial | spec 2 dispatch |
| `#2245` | `gate_record` cannot correct a runtime recorded wrong at init | spec 3 dispatch |
| `#2249` | A concurrent `gate_record check` silently overwrites an amend | spec 3 dispatch |
| `#2250` | Spec 3 FR-050's panel channel needs an event type FR-057 does not list | needs an owner decision |

`#2242`, `#2243` and `#2250` are **input defects in the approved specs** and
may change what spec 4 and spec 5 should build. The manager's reading of each
is recorded in the assembly checklist's drift log as the agents hit them.
