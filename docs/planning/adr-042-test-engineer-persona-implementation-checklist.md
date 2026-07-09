---
title: "ADR-042 Test Engineer Persona Implementation Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# ADR-042 Test Engineer Persona Implementation Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: implement ADR-042 Addendum 4 with implementation agents owning
  code changes while the manager maintains documentation and integration.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1467`
- Gate record: `.workflow/records/1467-test-engineer-persona-implementation.json`
- Branch/worktree plan: manager worktree
  `C:/Users/<user>/Desktop/workspace/SciStudio-issue1467-manager`; agent branches
  are based on `track/issue-1467/test-engineer-persona`.
- Protected branch: `main`
- Umbrella branch: `track/issue-1467/test-engineer-persona`
- Umbrella PR: `#1474`
- Umbrella PR title:
  `[DO NOT MERGE] ADR-042 test engineer persona implementation`
- Final PR target: `main` after manager integration
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `test_engineer` persona support in governance tooling.
  - `GateRecord.persona`, `gate_record start --persona`, and validation.
  - Persona-scoped `test_engineer_scope_guard`.
  - AI developer docs, dispatch docs, runtime skill pointers, and e2e metadata.
  - Targeted QA tests and full-audit evidence.
- Out of scope:
  - Product runtime, block, scheduler, API, lineage, plugin, MCP, or frontend
    production behavior changes.
  - New task kinds.
  - Sentrux semantics, semantic-duplication semantics, or bypass label changes.
  - Making e2e mandatory for every PR.
- Protected paths:
  - `docs/specs/adr-042-test-engineer-persona.md`
  - `docs/adr/ADR-042-addendum4.md`
  - governance tooling under `src/scistudio/qa/governance/**`
- Deferred work:
  - N/A. Any newly discovered deferral must use `TODO(#1467)` or a follow-up
    issue before integration.

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

- [x] Dedicated manager branch and worktree created ->
  `track/issue-1467/test-engineer-persona` in
  `C:/Users/<user>/Desktop/workspace/SciStudio-issue1467-manager`.
- [x] Existing issue linked -> `#1467`.
- [x] Gate record started ->
  `.workflow/records/1467-test-engineer-persona-implementation.json`.
- [x] Scope include/exclude recorded in the gate record ->
  `.workflow/records/1467-test-engineer-persona-implementation.json`.
- [x] Umbrella branch created -> `track/issue-1467/test-engineer-persona`.
- [x] Umbrella PR opened -> `#1474`.
- [x] Umbrella PR title includes `[DO NOT MERGE]` -> `#1474`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found ->
  `python -c "import scistudio; print(scistudio.__file__)"` resolved inside
  this worktree under `src/scistudio/__init__.py`.
- [x] Dispatch checklist copied from the template -> this file.
- [x] Dispatch prompts created from the correct prompt template ->
  `docs/planning/dispatch-prompts/issue-1467-agent-a-code-guard.md` and
  `docs/planning/dispatch-prompts/issue-1467-agent-b-gate-record.md`.
- [x] Sentrux baseline recorded, or N/A reason recorded -> gate record notes
  Sentrux CLI unavailable in manager environment.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | `pending` |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A-code-guard` | `implementer` | `N/A` | `docs/planning/dispatch-prompts/issue-1467-agent-a-code-guard.md` | Persona policy and test-engineer scope guard | `feat/issue-1467/test-engineer-scope-guard` | `C:/Users/<user>/Desktop/workspace/SciStudio-issue1467-agent-a` | `src/scistudio/qa/governance/persona_policy.py`, `src/scistudio/qa/governance/test_engineer_scope_guard.py`, `tests/qa/test_persona_policy.py`, `tests/qa/test_test_engineer_scope_guard.py` | gate_record files, AI docs, product code | `#1467`, commit `5546fdfd` cherry-picked as `653ff611` | `[x]` |
| `B-gate-record` | `implementer` | `N/A` | `docs/planning/dispatch-prompts/issue-1467-agent-b-gate-record.md` | Gate-record persona schema, CLI, and validation integration | `feat/issue-1467/gate-record-persona` | `C:/Users/<user>/Desktop/workspace/SciStudio-issue1467-agent-b` | `src/scistudio/qa/governance/gate_record/**`, `tests/qa/test_gate_record.py`, `tests/qa/test_gate_record_ci.py`, `tests/qa/test_gate_record_hooks.py` | persona_policy, scope guard implementation, AI docs, product code | `#1467`, commit `7c6e9c0e` cherry-picked as `408e5dec` | `[x]` |

## 7. Track: Governance Code

### 7.1 Track Scope

- Owner: `A-code-guard`
- In scope:
  - Add `test_engineer` to persona policy.
  - Add deterministic `test_engineer_scope_guard`.
  - Add targeted persona-policy and scope-guard tests.
- Out of scope:
  - Gate-record schema or CLI changes.
  - Product runtime behavior.
- Required docs:
  - N/A for agent A. Manager owns docs.
- Required tests:
  - `tests/qa/test_persona_policy.py`
  - `tests/qa/test_test_engineer_scope_guard.py`

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded ->
  `docs/planning/dispatch-prompts/issue-1467-agent-a-code-guard.md`.
- [x] Correct prompt template selected ->
  `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
- [x] Agent branch/worktree assigned -> prompt task identity.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] Persona policy accepts `test_engineer` -> commit `653ff611`.
- [x] Scope guard allows explicit test/e2e/audit/QA paths -> commit
  `653ff611`.
- [x] Scope guard blocks production source and broad frontend paths -> commit
  `653ff611`.
- [x] Targeted tests pass ->
  `PYTHONPATH=src pytest tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py -q --no-cov`.

### 7.4 Integration

- [x] Agent output reviewed by manager -> changed-file review against prompt
  scope.
- [x] Scope compliance verified -> only owned code/test files changed.
- [x] Conflicts resolved intentionally -> no conflict; cherry-picked
  `5546fdfd` as `653ff611`.
- [x] Track merged or integrated -> integration branch commit `653ff611`.

## 8. Track: Gate Record

### 8.1 Track Scope

- Owner: `B-gate-record`
- In scope:
  - Add `persona` to gate records for new records.
  - Require `--persona` on `gate_record start`.
  - Validate persona and invoke `test_engineer_scope_guard`.
  - Add targeted gate-record tests.
- Out of scope:
  - Persona-policy implementation.
  - AI docs and runtime skill pointers.
  - Product runtime behavior.
- Required docs:
  - N/A for agent B. Manager owns docs.
- Required tests:
  - `tests/qa/test_gate_record.py`
  - `tests/qa/test_gate_record_ci.py`
  - `tests/qa/test_gate_record_hooks.py`

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded ->
  `docs/planning/dispatch-prompts/issue-1467-agent-b-gate-record.md`.
- [x] Correct prompt template selected ->
  `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
- [x] Agent branch/worktree assigned -> prompt task identity.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [x] `GateRecord.persona` stored and validated -> commit `408e5dec`.
- [x] `gate_record start --persona` implemented -> commit `408e5dec`.
- [x] Validation invokes scope guard for `test_engineer` -> commit
  `408e5dec`, with manager integration interface fix.
- [x] Targeted tests pass ->
  `PYTHONPATH=src pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py -q --no-cov`.

### 8.4 Integration

- [x] Agent output reviewed by manager -> changed-file review against prompt
  scope.
- [x] Scope compliance verified -> only owned gate-record code/test files
  changed.
- [x] Conflicts resolved intentionally -> no conflict; cherry-picked
  `7c6e9c0e` as `408e5dec`.
- [x] Track merged or integrated -> integration branch commit `408e5dec`.

## 9. Manager Documentation Track

- [x] `docs/ai-developer/rules.md` updated -> local manager edit.
- [x] `docs/ai-developer/specific_rules/gated-workflow.md` updated -> local
  manager edit.
- [x] `docs/ai-developer/specific_rules/agent-dispatch.md` updated -> local
  manager edit.
- [x] `docs/ai-developer/specific_rules/test-engineering.md` created -> local
  manager edit.
- [x] `docs/ai-developer/personas/test-engineer.md` created -> local manager
  edit.
- [x] Dispatch templates/checklists updated -> local manager edit.
- [x] Runtime skill pointers created -> local manager edit.
- [x] E2E skill metadata updated -> local manager edit.
- [ ] Docs reviewed with owner.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[x]` | Passed after integration. |
| Format | `ruff format --check .` | `[x]` | Passed after integration. |
| Tests | `pytest tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py tests/qa/governance/test_gate_record_package.py -q --no-cov` | `[x]` | Passed after integrating A and B plus self-hosting fixture update. |
| Frontmatter | `python -m scistudio.qa.audit.frontmatter_lint docs/ai-developer/personas/test-engineer.md docs/ai-developer/specific_rules/test-engineering.md --repo-root . --format text` | `[ ]` | `pending` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-042-test-engineer-persona-implementation-full-audit.json` | `[x]` | `docs/audit/adr-042-test-engineer-persona-implementation-full-audit.json` |
| Sentrux | `N/A unless available in this session` | `[x]` | Sentrux CLI unavailable in manager environment; recorded in gate record. |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-22 | manager | N/A | checklist initialized | N/A |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
