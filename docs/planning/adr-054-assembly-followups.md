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

#### M-005 - READ THIS ONE FIRST: the gate counts a timed-out test run as a passing one

- **Severity**: P1, and it is about the evidence rather than the feature.
- **Found by**: S5-B4, blocked by it; corroborated by S5-B1, the kernel fix
  agent, and the manager, each of whom hit a piece of it separately.
- **The chain**, which is worse than any of its three links alone:
  1. Two tests in `tests/qa/**` walk the whole repository and are not
     `serial`-marked, so they crash their xdist worker (`[gwN] node down`).
     That is the class `pyproject.toml` already documents as serial-only
     (#1867, #1896). Registered by S5-B4 as **F-B4-10**.
  2. A parallel-phase failure makes the runner **skip the serial phase**. So
     `test_a_branch_switch_kills_the_real_kernel_process`, genuinely red on
     the spec 5 track, was never reported at all. Registered as **F-B4-9**.
     A red test that cannot be seen is worse than a red test.
  3. When the run instead exceeds the gate CLI's own 600-second
     `subprocess.run(timeout=...)` budget, **the gate records `python_tests` as
     satisfied**. Registered as **F-B4-8** (and independently as **F-A1-009**).
     **FIXED** on `fix/2253-gate-timeout-not-satisfied` — see the `fix-gate`
     section below. Do not open an issue for it.
- **Why the manager is elevating it here.** Step 3 means a `gate_record`
  reconciliation can pass on a test run that never finished. Every branch in
  this dispatch went through that path, so it bears on how much the gate
  evidence in this PR is worth — not because anything is known to be wrong,
  but because the mechanism that would have told us is unreliable in exactly
  the case we kept hitting. The manager has **not** touched the gate tooling
  to fix it: `src/scistudio/qa/governance/**` is a governance surface, the
  change needs owner review, and repairing the evaluator mid-dispatch would
  change the meaning of evidence already recorded under the old behaviour.
- **What was done instead**: S5-B4 marks the two `tests/qa/**` tests `serial`
  under a manager scope amendment, which breaks link 1 and therefore link 2.
- **Link 3 is now closed**, on its own branch and under its own gate record so
  the change is reviewable in isolation: `fix/2253-gate-timeout-not-satisfied`
  makes a timeout its own recorded outcome, makes it unsatisfied, gives the
  budget an env knob defaulting to today's 600s, and makes `check` and
  `finalize` share one predicate. **Evidence already recorded under the old
  behaviour was left exactly as it stands** — no ledger event was rewritten or
  re-evaluated — so the manager's reservation above still applies to every gate
  record written before that branch, and this fix does not retroactively make
  any of it worth more.
- **Status of the hidden red test**: on the integration branch, which carries
  the kernel-death fix (#2262), `-k "branch_switch or branch_change"` runs
  4 tests and all 4 pass on Windows — they run, they are not skipped. So
  F-B4-9 is likely a symptom the kernel fix already cured on the spec 5 track
  rather than a live defect. Likely, not certain: it has not been seen green
  on Linux in the serial phase, because the serial phase is what gets skipped.
- **Suggested title**: `fix(qa): gate_record must not record a timed-out python_tests as satisfied`

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

Triage of the CodeQL alerts the assembly branch adds over `main`. The first
pass (`fix/2229-panel-codeql-findings`, PR #2260, merged) took the delta from
**12 to 5**: the four `js/prototype-polluting-assignment` alerts and the three
`py/path-injection` alerts on `panels/assets.py` cleared. The second pass
(`fix/2229-codeql-barrier`) established why the remaining four cannot be
cleared in code and what this repository can and cannot do about them.

**Where it stands, measured on `eb8b3588` (check-run `101292090119`):** the
assembly carries 60 open alerts and `main` carries 55. The delta is five —
four on `core.plot.basic/index.html` (FC-004) and one on `api/routes/git.py`
(FC-003). Nothing else on the branch is new.

#### FC-001 — every `py/path-injection` alert on the assembly is also on `main`, at identical counts

- **Severity**: P3 — not new, not this branch's, and not a regression. Whether
  any of the 51 is a real vulnerability is unexamined; only their provenance
  is settled here.
- **Found by**: fix-codeql. Re-checked in the second pass because
  `api/routes/user_library.py` appeared in a second annotation set and looked
  new. It is not: GitHub caps a check run at ~30 annotations, so the 22 paths
  in the first sample and the 26 in the second are two different samples of
  one unchanged set.
- **Evidence** — group both refs by path and compare, rather than trusting a
  line-number match, because the assembly's diff moves lines:

  ```bash
  for ref in refs/heads/main refs/pull/2255/head; do
    echo "== $ref"
    gh api "repos/jiazhenz026/SciStudio/code-scanning/alerts?state=open&per_page=100&ref=$ref" \
      --jq '[.[]|select(.rule.id=="py/path-injection")|.most_recent_instance.location.path]
            |group_by(.)|map({(.[0]):length})|add'
  done
  ```

  Both refs return the same object, byte for byte — 51 alerts across 11 paths:

  ```text
  {"src/scistudio/api/routes/data.py":3,"src/scistudio/api/routes/projects.py":3,
   "src/scistudio/api/routes/user_library.py":16,"src/scistudio/api/routes/workflow_watcher.py":2,
   "src/scistudio/desktop/package_installer.py":1,"src/scistudio/desktop/package_manager.py":7,
   "src/scistudio/plot/_context.py":2,"src/scistudio/plot/scaffold.py":5,
   "src/scistudio/plot/targets.py":1,"src/scistudio/utils/atomic_io.py":5,
   "tests/desktop/test_package_manager.py":6}
  ```

  `src/scistudio/panels/assets.py` is absent from both, having been 3 on the
  assembly before PR #2260: the lexical pre-check added there registered as a
  barrier CodeQL can see.
- **Why it is here and not done**: fixing them would turn a scoped security fix
  into a repo-wide sweep across five subsystems the ADR-054 dispatch does not
  own, on a branch that has to merge. The set is now bounded and reproducible,
  which is what a triage pass owes the next person.
- **Suggested title**: `Triage the 51 inherited py/path-injection alerts CodeQL reports on main`

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

#### FC-004 — the four `core.plot.basic` alerts cannot be cleared in code, and this repository honours no suppression mechanism except dismissal

- **Severity**: P2 — the code is correct and tested; what is unresolved is the
  alert, and it needs an owner decision rather than more engineering.
- **Found by**: fix-codeql, after PR #2260 failed to clear them.
- **The alerts**, on `refs/pull/2255/head` at `eb8b3588`:

  | # | Rule | Location | Severity |
  |---|---|---|---|
  | 260 | `js/xss` | `core.plot.basic/index.html:445` | high |
  | 258 | `js/client-side-unvalidated-url-redirection` | `core.plot.basic/index.html:445` | medium |
  | 272 | `js/xss` | `core.plot.basic/index.html:452` | high |
  | 271 | `js/client-side-unvalidated-url-redirection` | `core.plot.basic/index.html:452` | medium |

  They moved from 379/386 to 445/452 when `safeAssetUrl` was inserted above
  them; they are the same two sinks.
- **Why the code cannot clear them**: an allowlist validator returns the string
  it validated, so `payload.src` -> `url` -> `return url` -> `setAttribute` is
  an intact dataflow whatever the checks in between decided. Two ways to break
  it were considered and both rejected as contortions, with the reasoning
  written out beside `safeAssetUrl` in the document itself: re-encoding the
  base64 payload character by character through a constant alphabet is an
  identity function written as a loop over a megabyte-scale payload on the
  render path; decoding to a `Blob` for `URL.createObjectURL` buys the panel
  choosing the media type — which the element already constrains — in exchange
  for an object URL the panel must revoke on every zoom click or leak.
- **Why neither named suppression mechanism is available here**:
  - `.github/codeql/codeql-config.yml` query filters require **advanced
    setup**. This repository is on **default setup** —
    `gh api repos/jiazhenz026/SciStudio/code-scanning/default-setup` returns
    `{"state":"configured","query_suite":"default",...}`, and every alert
    instance carries
    `analysis_key: dynamic/github-code-scanning/codeql:analyze`. A config file
    would be inert.
  - Inline `// codeql[...]` / `# lgtm[...]` comments are not acted on by
    GitHub Code Scanning; they only populate a `suppressions` property in
    SARIF, which something else then has to consume. See FC-005 for the proof
    already sitting in this tree.
- **What is actually available**: dismissal, via the UI or the API. That is a
  repository security-state change with no diff for a reviewer to see, on
  exactly the class of thing that ends up hiding a real vulnerability, so it is
  the owner's to make rather than an agent's. If the owner agrees the four are
  false positives:

  ```bash
  for n in 258 260 271 272; do
    gh api -X PATCH "repos/jiazhenz026/SciStudio/code-scanning/alerts/$n" \
      -f state=dismissed -f dismissed_reason='false positive' \
      -f dismissed_comment='core.plot.basic gates every src through safeAssetUrl: an allowlist of data: media types per element plus a root-relative path. CodeQL follows the flow, not the condition, because the validator returns the string it validated. Pinned by frontend/src/panels/__tests__/panelHostilePayload.test.ts (23 cases fail without the gate).'
  done
  ```

- **The fact that should shape the decision**: `CodeQL` is **not** a required
  status check for merging to `main`. The active ruleset "Rules for Agents"
  (id 14656629) requires exactly five — `Lint & Format`,
  `Test (Python 3.11)`, `Test (Python 3.13)`, `Type Check`,
  `Import Contracts`:

  ```bash
  gh api repos/jiazhenz026/SciStudio/rules/branches/main \
    --jq '.[]|select(.type=="required_status_checks")|.parameters.required_status_checks[].context'
  ```

  So a red `CodeQL` check does not block the merge; it is a standing red mark
  on the PR. FK-005's `Test (Python 3.13)` timeout is the one that does block.
- **Suggested title**: `Decide whether to dismiss the four core.plot.basic CodeQL alerts that the allowlist cannot clear`

#### FC-005 — two `# lgtm[py/path-injection]` comments in the tree read like controls and are not

- **Severity**: P2 — not a vulnerability, but a comment that looks like a
  suppression and silently is not is worse than no comment: the next reader
  believes the alert was handled.
- **Found by**: fix-codeql, looking for a suppression idiom to follow.
- **Evidence**: `src/scistudio/api/routes/user_library.py:404` and
  `src/scistudio/api/routes/projects.py:358` each carry a
  `# lgtm[py/path-injection]` above a call the author judged safe. Both alerts
  are still open on `main`: alert **#247** at `user_library.py:408`, four lines
  below its comment and on the `tempfile.mkstemp(dir=str(resolved.parent))`
  call it was written to cover, and alert **#236** at `projects.py:370`.

  ```bash
  gh api "repos/jiazhenz026/SciStudio/code-scanning/alerts?state=open&per_page=100&ref=refs/heads/main" \
    --jq '.[]|select(.most_recent_instance.location.path|test("user_library|projects"))
          |"#\(.number) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)"'
  ```

- **What to do**: keep the prose — the containment reasoning in both is
  genuine and worth reading — and drop the `lgtm[...]` line, or replace it
  with a dismissal (FC-004's mechanism) so the claim and the alert state
  agree.
- **Why it is here and not done**: `api/routes/**` is outside this fix's write
  set, and editing those two files perturbs 19 open path-injection alerts for
  a comment change.
- **Suggested title**: `Remove or honour the two lgtm[py/path-injection] comments that suppress nothing`

#### FC-006 — `core.plot.basic`'s `payload.path` branch builds a URL that can never resolve

- **Severity**: P2 — a real dead path, found while tracing what
  `safeAssetUrl` actually has to accept. Not a security issue.
- **Found by**: fix-codeql.
- **Evidence**: when the payload carries no inline `src`, `bulkSource` builds
  `context.asset_base_url + "/" + encodeURIComponent(name)`.
  `asset_base_url` is `/api/panels/assets/core.plot.basic/`
  (`panels/descriptor.py:panel_asset_base_url`), and that route confines to
  `panel.directory` — the built-in panel's own folder
  (`api/routes/panels.py:218`). That folder holds `index.html` and
  `panel.json` and nothing else, which
  `tests/panels/test_builtin_panels.py::test_panel_directory_holds_nothing_but_its_own_two_files`
  asserts. A plot artifact is never in it, so the request is a guaranteed 404
  and the panel renders "No renderable plot artifact."
- **What it means in practice**: the only figure source that works today is
  the inline `data:` URI, which the provider produces only for artifacts at or
  under `PreviewLimits.max_bytes`. A plot above that bound shows nothing, and
  the panel reports it as an absent artifact rather than as one too large to
  inline.
- **Why it is here and not done**: fixing it means either a route that serves
  run artifacts to a panel or a spec decision about how a panel reaches bulk
  bytes — ADR-054 spec 1's question, not a security fix's.
- **Suggested title**: `A plot too large to inline renders as "no artifact" because the panel asset route cannot serve run artifacts`

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

### fix-gate

The repair of M-005's link 3 — the gate counting a timed-out check as a passing
one — on `fix/2253-gate-timeout-not-satisfied`. **F-B4-8** and **F-A1-009** are
the same defect found twice and are fixed by this branch; the entries are marked
in place so neither becomes an issue.

#### FG-000 — What the fix changed, for the record

Not a follow-up. Written down so a later reader can tell what this branch did
from what it deliberately left alone.

- A `subprocess.TimeoutExpired` is now `status="timeout"` with the budget in its
  summary, not `status="unknown"` / `"execution error: TimeoutExpired"`. The
  `unknown` branch keeps its own meaning for a check that could not be launched.
- Only a `pass` discharges a check obligation. `skipped`, `timeout` and
  `unknown` are unsatisfied in `pre-pr` / `ci`, recorded-not-blocking in the WIP
  modes — the posture `skipped` already had.
- `SCISTUDIO_GATE_CHECK_TIMEOUT` (seconds, default `600`, unusable values
  ignored) makes the budget configurable. Named after `SCISTUDIO_GATE_BASE`.
- `check` and `finalize` now call one predicate,
  `checks.event_discharges_obligation`. They diverged because each carried its
  own idea of what counted: the executing path treated everything that was not
  `fail` as satisfied, the evidence-reuse path required `pass`.
- **Nothing was made easier to satisfy.** No command was shortened, no test
  skipped, no scope narrowed. A run that legitimately passed before still
  passes; runs that falsely passed now correctly fail.
- **No existing ledger event was rewritten or re-evaluated.** The change applies
  to events recorded from here on.

#### FG-001 — `run_python_tests` skips the serial phase when the parallel phase fails

- **Severity**: P2 — a red test in the serial phase goes unexecuted and
  unreported, which is worse than a red test.
- **Found by**: fix-gate, reading M-005's chain. S5-B4 named it first, in a
  closing line of its own entry, and it was never registered on its own.
- **Evidence**: `src/scistudio/qa/testing/run_python_tests.py:67-69` —
  `rc = _run(parallel)` then `if rc not in (0, _NO_TESTS_COLLECTED): return rc`.
  The serial phase at line 71 is never reached. There is no dependency between
  the phases; they are split so PTY/subprocess tests cannot crash an xdist
  worker. Link 2 of M-005's chain is entirely this, and it is what hid
  `test_a_branch_switch_kills_the_real_kernel_process`.
- **Why it is not fixed here**: `src/scistudio/qa/testing/**` is outside this
  branch's write set, and the change wants its own reasoning about exit-code
  aggregation across two phases rather than a drive-by edit inside a governance
  fix.
- **Suggested title**: `run_python_tests must run the serial phase even when the
  parallel phase failed`

#### FG-002 — The gate's timeout and CI's `timeout 600` are two different walls with one number

- **Severity**: P3 — documentation and diagnosis, not behaviour.
- **Found by**: fix-gate, and the confusion is already in this file: FK-005 and
  the first draft of M-005's link 3 both say "`timeout 600`" for what are two
  unrelated mechanisms.
- **The two**: the gate CLI's `subprocess.run(timeout=...)` around a whole check
  (now `SCISTUDIO_GATE_CHECK_TIMEOUT`, this branch's), and `ci.yml`'s shell
  `timeout 600` around each pytest phase inside the CI job (FK-005's, a
  different agent's). They fire in different processes, produce different
  evidence, and want different fixes. Raising one does nothing for the other.
- **Why it is worth recording**: FK-005's diagnosis depends on the distinction —
  its point is that the shell wall hard-kills the phase before pytest-timeout
  can print a traceback, which is a property of the CI wall specifically. The
  gate CLI's docs now say which wall they mean; `ci.yml` says nothing about
  either.
- **Suggested title**: `chore(ci): name the pytest phase timeout so it is not
  confused with the gate CLI's per-check budget`

#### FG-003 — The `timeout` status is a ledger vocabulary addition, and old readers do not know it

- **Severity**: P3 — no known break; recorded because it is a schema change to
  the file ADR-042 Addendum 6 makes the single source of truth.
- **Found by**: fix-gate, making the change.
- **Evidence**: `CheckEvent.status` gains `"timeout"`. Ledgers written by this
  code and read by an older checkout would fail pydantic validation on that
  member. Nothing outside `gate_record` reads the field — the whole vocabulary
  is confined to `checks.py` and `evaluator.py`, and the frontend and CI never
  see it — so the blast radius is one repository at two different commits.
- **Why it is not a problem in practice**: CI runs the branch's own code against
  the branch's own ledger. It would only bite someone checking out an older
  commit to read a newer record.
- **Suggested title**: `chore(qa): gate ledger readers should tolerate an
  unknown CheckEvent status rather than refuse the record`

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
