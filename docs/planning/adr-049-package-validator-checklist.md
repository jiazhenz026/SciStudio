---
title: "ADR-049 Package Validator Agent Dispatch Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 49
language_source: en
---

# ADR-049 Package Validator Agent Dispatch Checklist

> Mandatory tracking file for the ADR-049 package validator contract survey.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: derive strict package validator contracts for ADR-049 from
  code-first evidence, using ADRs as secondary evidence.
- Task kind: `manager`
- Manager persona: `test_engineer`
- Issue: #1659
- Gate record:
  `.workflow/records/design-package-validator-contract-survey-design-package-validator-contract-survey.json`
- Branch/worktree plan: manager branch
  `design/package-validator-contract-survey` in
  `C:/Users/jiazh/Desktop/workspace/sci-wt/package-validator-design`;
  subagents write disjoint JSON tables only.
- Protected branch: `main`
- Umbrella branch: local manager branch for ADR/design PR submission.
- Umbrella PR: pending until gate-aware PR wrapper completes.
- Umbrella PR title: `[DO NOT MERGE] ADR-049 package validator contract survey`
- Final PR target: `main` when owner asks to submit ADR-049.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Saved prompts: `docs/planning/adr-049-package-validator/prompts/*.md`

## 2. Scope

- In scope:
  - `docs/planning/package-validator-contract-survey-draft.md`
  - `docs/adr/ADR-049.md`
  - `docs/specs/adr-049-package-validator-implementation.md`
  - `docs/planning/adr-049-package-validator-checklist.md`
  - `docs/planning/adr-049-package-validator/contracts/**`
  - `docs/planning/adr-049-package-validator/prompts/**`
  - `scripts/audit/check_package_contract_tables.py`
- Out of scope:
  - Production runtime changes under `src/scistudio/**`
  - Frontend changes
  - Runtime validator implementation
- Protected paths:
  - `docs/ai-developer/**` is read-only for this task.
- Deferred work:
  - N/A for this investigation pass.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact path, command, or check result.
- Code evidence is authoritative. ADR evidence is secondary and may be stale.
- A contract row with failing code evidence is an error in the table.
- A contract row with passing code evidence but failing ADR evidence is an ADR
  drift warning.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created.
  -> `design/package-validator-contract-survey`
- [x] Gate record started.
  -> `.workflow/records/design-package-validator-contract-survey-design-package-validator-contract-survey.json`
- [x] Scope include/exclude recorded in the gate record.
  -> `gate_record init` / `gate_record amend`
- [x] Dispatch checklist copied from the template.
  -> `docs/planning/adr-049-package-validator-checklist.md`
- [x] Dispatch prompt paths assigned.
  -> `docs/planning/adr-049-package-validator/prompts/*.md`
- [x] Five subagents dispatched.
  -> PV-A1 `019ec4e0-3020-7141-ab8f-608c9dfe8b4d`,
  PV-A2 `019ec4e0-5829-7ef3-8277-3b48f591ba94`,
  PV-A3 `019ec4e0-82e8-7353-8f3e-cabd9840eb66`,
  PV-A4 `019ec4e0-ab38-72a3-829a-500d27741939`,
  PV-A5 `019ec4e0-d7f8-7bb2-88c2-66616587d7b5`
- [x] Five subagent JSON contract tables landed.
  -> `docs/planning/adr-049-package-validator/contracts/pv-a*.json`
- [x] Consistency checker implemented.
  -> `scripts/audit/check_package_contract_tables.py`
- [x] Consistency checker run and errors corrected.
  -> `python scripts/audit/check_package_contract_tables.py`
  returned `summary: 0 error(s), 9 warning(s)`
- [x] ADR-049 draft created.
  -> `docs/adr/ADR-049.md`
- [x] ADR-049 implementation spec created.
  -> `docs/specs/adr-049-package-validator-implementation.md`
- [x] ADR frontmatter lint passed.
  -> `$env:PYTHONPATH='src'; python -m scistudio.qa.audit.frontmatter_lint docs/adr/ADR-049.md --repo-root . --format text`

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: N/A
- Owner authorization source: N/A
- Reason: N/A

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | N/A | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | N/A | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | N/A | `[ ]` | pending |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | N/A | `[x]` | `mode=pre-pr tier=3 checks=['full_audit']; reconciliation passed` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: no
- AI docs checked: N/A, no AI workflow docs edited.
- Updated docs or N/A rationale:
  `docs/planning/package-validator-contract-survey-draft.md`,
  `docs/specs/adr-049-package-validator-implementation.md`,
  `docs/planning/adr-049-package-validator-checklist.md`,
  `docs/planning/adr-049-package-validator/contracts/**`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| PV-A1 | test_engineer | N/A | `docs/planning/adr-049-package-validator/prompts/pv-a1-sections-01-03.md` | Sections 1-3: package metadata, entry points, types | local subagent fork | subagent-isolated | `contracts/pv-a1-sections-01-03.json` | production code | pending/N/A | `[x]` |
| PV-A2 | test_engineer | N/A | `docs/planning/adr-049-package-validator/prompts/pv-a2-sections-04-06.md` | Sections 4-6: blocks, config/dynamic/variadic, IO capabilities | local subagent fork | subagent-isolated | `contracts/pv-a2-sections-04-06.json` | production code | pending/N/A | `[x]` |
| PV-A3 | test_engineer | N/A | `docs/planning/adr-049-package-validator/prompts/pv-a3-sections-07-09.md` | Sections 7-9: data boundary, AppBlock/CodeBlock, previewers | local subagent fork | subagent-isolated | `contracts/pv-a3-sections-07-09.json` | production code | pending/N/A | `[x]` |
| PV-A4 | test_engineer | N/A | `docs/planning/adr-049-package-validator/prompts/pv-a4-sections-10-12.md` | Sections 10-12: preview provider behavior, plot jobs, security/isolation | local subagent fork | subagent-isolated | `contracts/pv-a4-sections-10-12.json` | production code | pending/N/A | `[x]` |
| PV-A5 | test_engineer | N/A | `docs/planning/adr-049-package-validator/prompts/pv-a5-section-13-omissions.md` | Section 13 and omitted contracts | local subagent fork | subagent-isolated | `contracts/pv-a5-section-13-omissions.json` | production code | pending/N/A | `[x]` |

## 7. Track: Contract Table Survey

### 7.1 Track Scope

- Owner: manager / test_engineer
- In scope:
  - Code-first contract extraction.
  - ADR drift annotation.
  - JSON contract tables suitable for ADR-049 subsections.
- Out of scope:
  - Runtime validator implementation.
  - Final ADR prose until tables are corrected.
- Required docs:
  - Contract tables under `docs/planning/adr-049-package-validator/contracts/`.
- Required tests:
  - `python scripts/audit/check_package_contract_tables.py`

### 7.2 Dispatch

- [x] PV-A1 prompt dispatched.
  -> agent `019ec4e0-3020-7141-ab8f-608c9dfe8b4d`
- [x] PV-A2 prompt dispatched.
  -> agent `019ec4e0-5829-7ef3-8277-3b48f591ba94`
- [x] PV-A3 prompt dispatched.
  -> agent `019ec4e0-82e8-7353-8f3e-cabd9840eb66`
- [x] PV-A4 prompt dispatched.
  -> agent `019ec4e0-ab38-72a3-829a-500d27741939`
- [x] PV-A5 prompt dispatched.
  -> agent `019ec4e0-d7f8-7bb2-88c2-66616587d7b5`

### 7.3 Implementation

- [x] PV-A1 contract table landed.
  -> `contracts/pv-a1-sections-01-03.json`
- [x] PV-A2 contract table landed.
  -> `contracts/pv-a2-sections-04-06.json`
- [x] PV-A3 contract table landed.
  -> `contracts/pv-a3-sections-07-09.json`
- [x] PV-A4 contract table landed.
  -> `contracts/pv-a4-sections-10-12.json`
- [x] PV-A5 contract table landed.
  -> `contracts/pv-a5-section-13-omissions.json`
- [x] Checker script landed.
  -> `scripts/audit/check_package_contract_tables.py`
- [x] Tables corrected until checker reports zero errors.
  -> full checker `0 error(s), 9 warning(s)`

### 7.4 Audit

- [x] Manager reviewed every JSON table.
  -> contract summary extracted with Python JSON scan
- [x] Manager reviewed checker diagnostics.
  -> full checker `0 error(s), 9 warning(s)`
- [x] ADR drift warnings recorded or explained.
  -> warnings are declared `adr_missing`, `adr_drift`, or `adr_planned`

### 7.5 Integration

- [x] Corrected contract tables are ready to become ADR-049 subsections.
  -> five corrected JSON tables under `contracts/`

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Contract table checker | `python scripts/audit/check_package_contract_tables.py` | `[x]` | `summary: 0 error(s), 9 warning(s)` |
| ADR/spec frontmatter lint | `$env:PYTHONPATH='src'; python -m scistudio.qa.audit.frontmatter_lint docs/adr/ADR-049.md docs/specs/adr-049-package-validator-implementation.md --repo-root . --format text` | `[x]` | pass |
| Python compile | `python -m py_compile scripts/audit/check_package_contract_tables.py` | `[x]` | pass |
| Gate ledger check | `$env:PYTHONPATH='src'; python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[x]` | `mode=local tier=3 checks=['full_audit']; reconciliation passed` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-14 | manager | No issue/umbrella PR opened for local owner-directed investigation pass. | Recorded as pending/N/A; final PR flow will need issue linkage before submission. | Owner decides when ADR-049 moves to PR. |
| 2026-06-14 | manager | `gate_record check --mode local` failed on `guard.issue_link`. | Kept as expected blocker for non-PR investigation; checker and py_compile passed. | Link issue before PR readiness. |
| 2026-06-14 | manager | ADR-049 is currently `is_code_implementation: false` to satisfy frontmatter without a tracking issue. | Kept `planned_governs` and implementation plan in ADR. | Switch to `true` and add tracking issue before implementation PR. |
| 2026-06-14 | manager | Owner requested PR submission. | Created #1659, restored ADR implementation tracking, and moved gate evidence to PR-ready flow. | Open PR with gate-aware wrapper. |
| 2026-06-14 | manager | Owner requested an executable ADR-049 implementation spec before PR submission. | Added `docs/specs/adr-049-package-validator-implementation.md` and explicit contract applicability metadata. | Re-run contract checker, frontmatter lint, and gate checks before push. |

## 10. Final Readiness

- [x] All dispatched agents have final outputs.
- [x] Manager reviewed every changed file.
- [x] Checker reports zero errors.
- [x] ADR drift warnings are understood.
- [x] Gate record includes final local checks.
