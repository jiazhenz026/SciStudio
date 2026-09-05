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
