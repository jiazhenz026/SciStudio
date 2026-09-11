---
title: "ADR-054 Panels Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
related_specs:
  - adr-054-panels
language_source: en
---

# ADR-054 Panels Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: "As manager, implement ADR-054 and its spec
  (`docs/specs/adr-054-panels.md`) and submit PRs for owner review."
- Task kind: `feature` (phase PRs); `manager` (this checklist)
- Manager persona: `manager`
- Issue: `#2296` (coordination); `#2293` (Phase A), `#2294` (Phase B),
  `#2295` (Phase C); ADR-054 tracking `#2288` stays open
- Gate record: `.workflow/records/2296-track-adr-054-panels.json` (manager);
  `.workflow/records/2293-feat-2293-panels-phase-a.json` (Phase A integration)
- Branch/worktree plan: manager umbrella `track/adr-054-panels` at
  `.worktrees/track-adr-054-panels`. One integration branch per phase,
  based on `origin/main`: `feat/2293-panels-phase-a` at
  `.worktrees/feat-2293-panels-phase-a` (Phase B and C branches created when
  their phase starts). Agent branches are cut from the phase integration
  branch (`feat/2293-a1-backend`, `feat/2293-a2-frontend`), record
  `--base-ref feat/2293-panels-phase-a`, open no PR of their own, and are
  merged into the integration branch by the manager after review. Sub-PRs to a
  non-`main` base are avoided because they do not receive `ci.yml`.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-panels`
- Umbrella PR: `pending`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 panels dispatch — Phases A, B, C`
- Final PR target: `main` — one PR per phase (owner directive, 2026-09-11)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Filled prompts: `docs/planning/adr-054-panels-dispatch-prompts.md`

## 2. Scope

- In scope:
  - Phase A (#2293): spec T-001 to T-013, plus the owner's Panels tab
    amendment (FR-050 to FR-054) and sample mode (FR-046)
  - Phase B (#2294): spec T-014 to T-016
  - Phase C (#2295): spec T-017 to T-019, without the tutorial assets
- Out of scope:
  - The "What Is A Type" tutorial, copy and code assets (owner decision;
    FR-049; #2288)
  - ADR-055 Spec 4 Lab session middleware (does not exist; FR-026 TODO)
  - `docs/adr/ADR-054.md` (`agent_editable: false`)
  - `docs/architecture/ARCHITECTURE.md` (proposal text only, Phase C)
  - Everything the spec and #2288 list as out of scope
- Protected paths:
  - `src/scistudio/core/dropins.py` (FR-004): Phase A PR needs the owner to
    apply `admin-approved:core-change` on the PR
  - `docs/adr/ADR-049.md` (`agent_editable: false`): the T-009 contract ids
    must appear in it for `check_package_contract_tables.py`; owner decision
    pending
- Deferred work:
  - `TODO(#2288)`: Lab session middleware accepts the per-mount token (FR-026)
  - `TODO(#2288)`: "What Is A Type" migrates to panels (FR-049)

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. ->
      `track/adr-054-panels` at `.worktrees/track-adr-054-panels`
- [x] Existing issue linked, or new issue created only if none exists. ->
      #2288 is the ADR-054 tracker and must stay open, so #2293, #2294,
      #2295, and #2296 were created
- [x] Gate record started. -> `.workflow/records/2296-track-adr-054-panels.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. -> `track/adr-054-panels`
- [ ] Umbrella PR opened.
- [ ] Umbrella PR title includes `[DO NOT MERGE]`.
- [ ] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found. -> gate CLI runs via
      `PYTHONPATH=./src`
- [x] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked
      below.
- [x] Sentrux baseline recorded, or N/A reason recorded. -> N/A: Sentrux MCP
      is not available in this runtime; guard evidence is recorded by
      `gate_record check` where applicable.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<pending>` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<pending>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `<pending>` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | `<pending>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — no AI-workflow behavior changes`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `adr-054-panels-dispatch-prompts.md` (A1) | Phase A backend: T-001 to T-009, backend of FR-050 to FR-054 | `feat/2293-a1-backend` | `.worktrees/feat-2293-a1-backend` | see prompt | `frontend/**`, `src/scistudio/panels/sdk/**`, ADR/spec files | `#2293` | `[ ]` |
| `A2` | `implementer` | `N/A` | `adr-054-panels-dispatch-prompts.md` (A2) | Phase A frontend and SDK: T-010 to T-013, FR-046, FR-050 to FR-054 UI | `feat/2293-a2-frontend` | `.worktrees/feat-2293-a2-frontend` | see prompt | backend Python, ADR/spec files | `#2293` | `[ ]` |
| `AU-A1` | `audit_reviewer` | `with-context` | pending | Phase A audit | pending | pending | audit report only | implementation files | `#2293` | `[ ]` |
| `AU-A2` | `audit_reviewer` | `no-context` | pending | Phase A audit | pending | pending | audit report only | implementation files | `#2293` | `[ ]` |

Phase B and Phase C rows are added when those phases start.

## 7. Track: Phase A — Mechanism And Panels Tab (#2293)

### 7.1 Track Scope

- Owner: `manager` (integration), `A1`, `A2`
- In scope: spec §3 Phase A requirements, FR-046, FR-050 to FR-054
- Out of scope: Phase B core panels, Phase C docs, tutorial, Lab middleware
- Required docs:
  - `docs/specs/adr-054-panels.md` (owner amendment, manager)
  - `CHANGELOG.md` (T-007 hardening entry)
- Required tests:
  - spec frontmatter `tests` list for Phase A

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [~] Spec amendment for the owner's decisions -> `docs/specs/adr-054-panels.md`
- [ ] A1 backend -> `<commit>`
- [ ] A2 frontend and SDK -> `<commit>`
- [ ] Integration merge and cross-agent contract reconciliation -> `<commit>`
- [ ] Frontend smoke in the dev app (Panels tab, preview, maximize, drill-down, interactive modal) -> `<evidence>`

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `<pending>` |
| Targeted tests | `<recorded with gate_record amend --test-path/--check>` | `[ ]` | `<pending>` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `<pending>` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<pending>` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2293"` | `[ ]` | `<pending>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | `<pending>` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-09-11` | `manager` | Spec §4.3 splits Phase A into two PRs; owner directed one PR per phase | Phase A integrates backend and frontend on one branch; spec amended | `#2293` |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
