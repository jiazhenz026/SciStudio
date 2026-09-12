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
