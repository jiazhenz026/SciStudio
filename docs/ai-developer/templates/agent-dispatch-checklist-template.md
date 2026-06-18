---
title: "<Scope> Agent Dispatch Checklist"
status: Approved
owners:
  - "<owner>"
related_adrs: []
language_source: en
---

# <Scope> Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `<one sentence>`
- Task kind: `<feature|bugfix|hotfix|refactor|docs|maintenance|manager|guided>`
- Manager persona: `manager`
- Issue: `#<issue>`
- Gate record: `.workflow/records/<issue>-<task-slug>.json`
- Branch/worktree plan: `<manager branch/worktree and agent branch pattern>`
- Protected branch: `<main or other protected branch>`
- Umbrella branch: `<track/<scope> or other umbrella branch>`
- Umbrella PR: `#<pr-number or pending>`
- Umbrella PR title: `[DO NOT MERGE] <scope>`
- Final PR target: `<protected branch or integration target>`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `<path, module, behavior, or document>`
- Out of scope:
  - `<path, module, behavior, or document>`
- Protected paths:
  - `<path or N/A>`
- Deferred work:
  - `<TODO(#NNN) item or N/A>`

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

- [ ] Dedicated manager branch and worktree created.
- [ ] Existing issue linked, or new issue created only if none exists.
- [ ] Gate record started.
- [ ] Scope include/exclude recorded in the gate record.
- [ ] Umbrella branch created.
- [ ] Umbrella PR opened.
- [ ] Umbrella PR title includes `[DO NOT MERGE]`.
- [ ] Protected branch and umbrella PR number recorded in this checklist.
- [ ] No `pip install -e .` environment pollution found.
- [ ] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked
      below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `<human-authored|admin-approved:bypass|admin-approved:core-change|admin-approved:merge|N/A>`
- Owner authorization source: `<chat/date/link or N/A>`
- Reason: `<why bypass was needed or N/A>`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `<label or N/A>` | `[ ]` | `<output or summary>` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `<label or N/A>` | `[ ]` | `<output or summary>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `<label or N/A>` | `[ ]` | `<output or summary>` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `<broad label or N/A>` | `[ ]` | `<ledger reconcile event or error>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `<yes|no>`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `<paths or rationale>`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `<A1>` | `<implementer>` | `N/A` | `<prompt path>` | `<task>` | `<branch>` | `<path>` | `<files>` | `<paths>` | `<#issue or PR>` | `[ ]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: <Track Name>

### 7.1 Track Scope

- Owner: `<manager or agent label>`
- In scope:
  - `<item>`
- Out of scope:
  - `<item>`
- Required docs:
  - `<path or N/A reason>`
- Required tests:
  - `<path or N/A reason>`

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [ ] `<implementation row>` -> `<artifact>`
- [ ] `<test row>` -> `<artifact>`
- [ ] `<docs row or N/A>` -> `<artifact>`

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
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base <base-ref> --head HEAD` | `[ ]` | `<reconcile event or summary>` |
| Targeted tests | `<task-specific test commands recorded with gate_record amend --test-path/--check>` | `[ ]` | `<output summary or N/A reason>` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base <base-ref> --head HEAD` | `[ ]` | `<reconcile event or summary>` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<reconcile event or summary>` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#<issue>"` | `[ ]` | `<ledger path>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | `<output>` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `<YYYY-MM-DD>` | `<agent>` | `<what drifted>` | `<manager action>` | `<issue/TODO/N/A>` |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
