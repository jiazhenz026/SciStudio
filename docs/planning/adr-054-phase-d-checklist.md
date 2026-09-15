---
title: "ADR-054 Phase D Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 51
  - 53
  - 54
  - 55
related_specs:
  - adr-054-miniapp
  - adr-054-panels
language_source: en
---

# ADR-054 Phase D Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Deliver ADR-054 Phase D (panel Python and MiniApps) front to
  back — the complete backend and frontend implementation of
  `docs/specs/adr-054-miniapp.md` FR-001..FR-040 / T-001..T-014 — through
  dispatched implementation and audit agents, ending in one reviewable PR, then
  start a backend and frontend so the owner can test the feature by hand.
  Phases C and E (authoring docs, tutorial rewrite) are a separate guided
  session and are out of scope here.
- Task kind: `feature`
- Manager persona: `manager`
- Issue: `#2354` (coordination `#2296`, tracker `#2288`)
- Gate record: `.workflow/records/2354-feat-2354-miniapp-phase-d.json`
- Branch/worktree plan: manager/integration branch `feat/2354-miniapp-phase-d`
  in `/Users/jiazhenz/SciStudio/.worktrees/adr054-phase-d`; agent branches
  `feat/2354-miniapp-<slug>` each with a dedicated worktree
  `/Users/jiazhenz/SciStudio/.worktrees/2354-<slug>`. Agent branches are not
  named under `track/adr-054-phase-d/` — git cannot create a ref below an
  existing branch ref of the same name.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-phase-d`
- Umbrella PR: `#2368`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 Phase D: panel Python and MiniApps`
- Final PR target: `main`, opened after `#2367` (Phases A+B) merges. This branch
  is stacked on `feat/2294-panels-phase-b`; the gate ledger records
  `base_ref: feat/2294-panels-phase-b`.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/panels/**` — descriptor rule, process host, `miniapp`
    context, directory watcher, SDK `call`
  - `src/scistudio/api/routes/panels.py`, `user_library.py`, `projects.py`,
    `src/scistudio/api/schemas.py`, `src/scistudio/api/ws.py`
  - `src/scistudio/engine/runners/process_handle.py`
  - `src/scistudio/ai/agent/mcp/**`, `src/scistudio/_skills/**`,
    `src/scistudio/agent_provisioning/skills.py`
  - `frontend/src/miniapps/**`, `frontend/src/panels/**`,
    `frontend/src/store/**`, `frontend/src/App.parts/ProjectWorkspace.tsx`,
    `frontend/src/components/{ActivityBar,PreviewerPalette,DataPreview,WorkflowCanvas}.tsx`,
    `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx`,
    `frontend/src/components/promotion/promotable.ts`,
    `frontend/src/components/palette/tips/tipPool.ts`,
    `frontend/src/hooks/useWebSocket.parts/**`,
    `frontend/src/components/LearningCenter.parts/targets.ts`,
    `frontend/src/types/api.ts`
  - `src/scistudio/tutorials/core/*/tutorial.yaml` (FR-040 copy only)
  - `docs/specs/adr-053-learning-center.md` (FR-040 amendment),
    `docs/specs/adr-054-miniapp.md` (status), this checklist
  - `tests/**`, `frontend/src/**/*.test.*`
- Out of scope:
  - Python for `preview` and `interactive` panels (ADR-054 §10; `#2288`)
  - Any change to the ADR-051 runtime, its pause, or interaction memory
  - Lineage records or typed data objects for what a MiniApp computes
  - Reserving memory for MiniApp processes (`#2288`)
  - Editing a MiniApp's source in-app other than through the agent (`#2288`)
  - Mechanical conversion of a MiniApp into a block (ADR-054 §11.5)
  - `promote_to_user_library` agent tool and ADR-053 canvas promotion (`#2288`)
  - Phase C authoring/migration docs and Phase E tutorial rewrite
  - `docs/architecture/ARCHITECTURE.md` — owner-controlled, never edited here
- Protected paths:
  - `docs/architecture/ARCHITECTURE.md` (owner approval label required; not touched)
  - `docs/ai-developer/**` (governance surface; not touched — the spec's e2e
    scenario file is deferred, see Deferred work)
- Deferred work:
  - E2E scenario under `docs/ai-developer/e2e/` (spec §4.4): deferred to the
    Phase C/E guided session because `docs/ai-developer/**` is a governance
    surface requiring a separate `governance_touch` declaration and owner
    review. Tracked in `#2288`.

## 3. Conventions

- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every completed row MUST include an artifact: commit, test command, report
  path, or gate-record entry. Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.
- Agents do **not** create their own gate ledgers. One ledger
  (`.workflow/records/2354-feat-2354-miniapp-phase-d.json`) covers the
  integrated diff; a second active ledger on the same branch makes the CI gate
  exit 2.
- Agents do **not** open PRs. The manager integrates every branch and opens the
  single final PR.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created —
      `feat/2354-miniapp-phase-d` @ `.worktrees/adr054-phase-d`, rebased onto
      `feat/2294-panels-phase-b` (clean, 142 Phase D backend tests pass).
- [x] Existing issue linked — `#2354`; no new issue created.
- [x] Gate record started — `.workflow/records/2354-feat-2354-miniapp-phase-d.json`.
- [x] Scope include/exclude recorded in the gate record (amendment 2026-09-11).
- [x] Umbrella branch created — `track/adr-054-phase-d`.
- [x] Umbrella PR opened — `#2368`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found — agents run with
      `PYTHONPATH=<worktree>/src`.
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked below.
- [x] Sentrux baseline: Sentrux MCP is not available in this session; evidence
      is recorded as the guard event inside `gate_record check`.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A — no bypass requested or used.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-PR reconcile | `gate_record check --mode pre-pr --base feat/2294-panels-phase-b --head HEAD --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2354"` | `N/A` | `[ ]` | |

### 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked: `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A — Phase D changes no wrapper, hook,
  gate-record, CI, or AI-runtime behaviour. Product docs updated:
  `docs/specs/adr-053-learning-center.md` (FR-040 amendment).

## 6. Dispatch Matrix

Filled at dispatch time. See §7 tracks for per-agent scope.

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence, commit, and PR evidence.
- [ ] PR closes `#2354`.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.


## Guided audit repair checkpoint (2026-09-13)

Owner-directed continuation fixes the recorded frontend integration, process
lifetime, API responsiveness and asset-confinement findings. Regression evidence
is recorded in `.workflow/records/2354-guided-miniapp-audit-fixes.json`.
The owner located the macOS menu-bar icon hidden by excess status items; no
desktop code change was required.

- Project-wide source discovery replaces the previous FR-023 listing deferral.
- Native Windows SC-004 evidence is not claimed on this macOS workstation.
  TODO(#2288): verify suspended launch, Job Object assignment failure and full
  process-tree cleanup on a native Windows runner before cross-platform closure.
  Out of scope per the current macOS guided validation session.
  Followup: https://github.com/jiazhenz026/SciStudio/issues/2288.
- This checkpoint is for desktop testing; final PR/CI readiness remains pending.


## Guided final integration (2026-09-14)

The owner's guided directives extend the original Phase D scope with GUI screenshot
access for AI, reusable presentation components extracted from all nine core
previewers, production MiniApp authoring instructions and runtime reference docs,
and canvas hover actions replacing the block context menu. The shared provider and
permission controls retain their existing behavior. Broader Phase C migration and
Phase E tutorials remain tracked separately; this PR includes documentation needed
for its delivered features.

- Task kind/persona: `guided` / `live_implementer`.
- Active integration ledger: `.workflow/records/2354-guided-miniapp-audit-fixes.json`.
- Final base: `origin/main`; Phases A+B and subsequent upstream fixes are merged.
- Owner authorization: push and open one PR after all ongoing changes complete;
  merging is not authorized.
- Independent worker ledgers remain provenance for their dedicated branches. The
  active integration ledger reconciles the final combined diff.

| Work | Owner | Status / evidence |
| --- | --- | --- |
| Audit fixes, project isolation, initial desktop UX | Integration | Implemented; original checkpoint and integration ledger |
| MiniApp skill rewrite and unambiguous source labels | Integration | `d03d9cdc`; frontend tests passed |
| Icon-only dialog close buttons | Integration | `3c1439d1`; frontend tests passed |
| Nine reusable core UI components | Component worker | Integrated from `5a0cc503`; worker frontend 2631 tests/build and Python 121 tests passed |
| Desktop GUI screenshot and image transport | GUI worker | Integrated as `3e966a1b`; native screenshot round-trip remains unverified |
| Hover actions and source editor entry | Canvas worker | Integrated as `048ab10a`; worker frontend 2625 tests and build passed |
| ADR documentation completeness review | Documentation reviewer | Report and follow-up integrated as `63ba5c54` and `38242082`; final source reconciliation below |
| Production skill/reference consistency | Integration and GUI worker | Integrated: `ce8c6ffb`, renderer reference and `3e966a1b` production guides |
| Combined desktop smoke, local gate, PR and CI | Integration | All worker code integrated; prior frontend 2653 tests/build passed; full Python runs timed out or were interrupted; owner directed direct PR submission and no further local full-suite runs; CI pending |


### Desktop hover smoke

On the running development desktop after `048ab10a`, the owner test workflow's
Load node displayed View source, both compatible MiniApps, and New MiniApp in
its detail card. Moving into and clicking the card text kept its actions
available. New MiniApp opened the creation dialog with the selected node instance
`load_all` and its `data` port preselected. Clicking the X closed that dialog
without creating an app. No workflow configuration or output was changed.
Source-path editing and Escape/viewport invalidation are covered by the worker's
focused frontend tests; this smoke does not claim a native edit/save test.


### Documentation and verification reconciliation (2026-09-15)

The combined tree contains `sdk/1/renderers.js`, all nine renderer modules,
`renderers.css`, their asset allowlist entries and contract tests. The production
MiniApp guide explains that library promotion moves the directory, distinguishes
file exports from typed workflow outputs, and identifies All Previewers in the
preview column. The D1–D4 document repairs in the documentation audit now land
together with their implementations. General Phase C work stays on #2295.

SciStudio supplies only `screenshot_gui`; authoring instructions use the agent's
available computer use tools for interaction and require honest disclosure when
interaction cannot be exercised. No additional interaction MCP is promised.

The original development desktop was no longer running at final integration.
The installed SciStudio application held the single-instance lock and had a live
session, so it was left untouched. An isolated Electron compositor fixture and
separate API/MCP/WebSocket regressions are included. The final local full-suite
run was stopped before native screenshot evidence was produced. Neither a
successful fixture run nor a screenshot round-trip through the installed
application is claimed.

The owner supplied the final MiniApp skill routing and GUI navigation wording
and requested immediate PR submission without further local full-suite runs.
The branch includes upstream main at `f70c0087`. Existing passing checks are
historical evidence, not a claim that this final merged head passed all checks.
CI remains required; no CI checks or thresholds are changed for this exception.

### PR #2392 review follow-up (2026-09-15)

- The MiniApps sidebar now provides Reload, using the existing full registry
  rescan endpoint before updating its list and compatible canvas actions.
  Creation, registry invalidation, and promotion also refresh both consumers;
  responses from a previous project are discarded.
- The Python 3.11 and 3.13 CI failures were the same user-guide navigation
  fixture missing the new MiniApps guide. The fixture now includes that entry.
- Focused validation: 15 MiniApp palette tests, 11 creation dialog tests, and
  all 30 user-documentation API tests passed. Frontend type checking and lint
  and formatting checks of the changed frontend files passed. No local full
  test suite was run for this follow-up; final CI remains required.
- Backend audit repairs use per-socket presence tokens and fresh disconnect
  grace timers, and a locked, recoverable directory swap for overwrite.
  All 28 focused promotion and WebSocket identity regressions passed in the
  worker checkout, including failed landing/rollback, concurrent writers,
  cleanup failure, and overlapping reconnects. Changed Python files passed
  Ruff lint and format checks. Integration reviewed the worker implementation.

### Latest-main integration (2026-09-15)

Merged upstream `8ff9b9fe` into the PR branch. The skill installation conflict
resolutions retain all ten skills (twenty files across Claude/Codex), upstream
protection for user-edited skills, and MiniApp runtime/user-guide references.
MiniApp focus handling now carries the exact backing workflow tab identity,
preserving upstream #2362 isolation for copies sharing a workflow id, including
revisits, chained preview opens, and closing a workflow into a MiniApp.

Focused validation: 70 frontend tests across tab state, composite identity,
version vectors and MiniApp dialogs passed; frontend type checking and changed
store-file lint passed. Provisioning/package checks passed 31 tests in the
resolution worktree; six orchestrator tests passed again after reference-copy
assertions were added. No local full suite was run.

The shared upstream permission picker exposes Auto. MiniApp creation and
conversion now accept it only for providers declaring Auto support, rejecting
unsupported requests before filesystem/session side effects. All 31 focused
MiniApp API tests passed in the resolution worktree. The OpenAPI snapshot was
regenerated from the integrated tree.

Before the final push, upstream advanced to `72c039dd` (#2393, bounded local
Python gate execution). That update merged without conflicts or edits to its
implementation; no additional test execution was needed for the unchanged
upstream code.
