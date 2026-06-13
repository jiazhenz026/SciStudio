---
title: "ADR-042 Change Contract Gate Implementation Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# ADR-042 Change Contract Gate Implementation Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Arrange agents to implement the ADR-042 change contract gate spec.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1617`
- Spec PR: `#1615`
- Gate record: `.workflow/records/1617-change-contract-gate-manager.json`
- Manager branch/worktree: `track/change-contract-gate-implementation` /
  `C:\Users\jiazh\Desktop\workspace\sci-wt\change-contract-gate-manager`
- Agent branch pattern: `feat/change-contract-gate-<track>`
- Agent worktree pattern:
  `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-<track>`
- Protected branch: `main`
- Umbrella branch: `track/change-contract-gate-implementation`
- Umbrella PR: `#1622`
- Umbrella PR title: `[DO NOT MERGE] implement ADR-042 change contract gate (#1617)`
- Final PR target: `main` after `#1615` lands or this branch is rebased.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Implement `docs/specs/adr-042-change-contract-gate.md`.
  - Add change contract schema, audit checker, baseline handling, reachability checks,
    full audit integration, gate-record routing, docs, and tests.
  - Preserve existing ADR/spec frontmatter as the authoritative governance index.
- Out of scope:
  - Immediate cleanup of historical repository drift.
  - Replacing `governs` or `planned_governs`.
  - ADR-048-specific previewer checks.
  - Broad semantic call-graph analysis beyond the conservative first rollout.
- Protected paths:
  - `src/scistudio/qa/governance/gate_record/**`
  - `docs/ai-developer/**`
  - `.github/**`, `.workflow/**`
- Deferred work:
  - N/A. New deferrals must use tracked `TODO(#NNN)` format.

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

- [x] Dedicated manager branch and worktree created:
  `track/change-contract-gate-implementation`.
- [x] Existing issue linked, or new issue created only if none exists:
  `#1617`.
- [x] Gate record started:
  `.workflow/records/1617-change-contract-gate-manager.json`.
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened: `#1622`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found by manager command use.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked below.
- [x] Sentrux baseline recorded, or N/A reason recorded: manager-only docs
  dispatch setup; no Sentrux evidence required.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[x]` | Git hook passed on manager commits. |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[x]` | Git hook passed on manager commits. |
| Pre-push | `git push -u origin track/change-contract-gate-implementation` | `N/A` | `[x]` | Push succeeded. |
| Pre-PR reconcile | `python scripts/scistudio_pr_create.py --draft --base main --head track/change-contract-gate-implementation --title "[DO NOT MERGE] implement ADR-042 change contract gate (#1617)" --body-file .workflow/local/change-contract-gate-umbrella-pr.md` | `N/A` | `[x]` | Wrapper preflight passed; PR `#1622` created. |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no` for this
  manager checklist PR; implementation agents will update this for their scopes.
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale:
  `docs/planning/change-contract-gate-implementation-checklist.md`.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/change-contract-gate-prompts/A1-schema.md` | Schema and frontmatter contract declarations | `feat/change-contract-gate-schema` | `...\sci-wt\ccg-schema` | `src/scistudio/qa/schemas/change_contracts.py`, schema exports, schema tests | Audit checking, gate wiring | `#1618`; PR `#1624` CI green; agent `019ebdf2-5ac8-74a1-8812-81c748044f53` | `[x]` |
| A2 | implementer | N/A | `docs/planning/change-contract-gate-prompts/A2-audit-core.md` | Contract discovery, governance coverage, forbidden references, baseline reconciliation | `feat/change-contract-gate-audit-core` | `...\sci-wt\ccg-audit-core` | `src/scistudio/qa/audit/change_contracts.py`, `docs/audit/baselines/change-contract-baseline.json`, audit tests | Gate wiring, docs standards | `#1619`; integrated in umbrella `#1622` | `[x]` |
| A3 | implementer | N/A | `docs/planning/change-contract-gate-prompts/A3-reachability.md` | Conservative reachability helpers for Python, frontend, entry points, canaries | `feat/change-contract-gate-reachability` | `...\sci-wt\ccg-reachability` | `src/scistudio/qa/audit/change_contract_reachability.py`, reachability tests | Core schema ownership, full audit wiring | `#1620`; PR `#1625` CI green; agent `019ebdf2-973b-72c2-8245-1a8637189abe` | `[x]` |
| A4 | implementer | N/A | `docs/planning/change-contract-gate-prompts/A4-gate-wiring-docs.md` | Full audit integration, gate-record check catalog/routing, authoring docs | `feat/change-contract-gate-wiring` | `...\sci-wt\ccg-wiring` | `src/scistudio/qa/audit/full_audit.py`, `src/scistudio/qa/governance/gate_record/checks.py`, `docs/ai-developer/specific_rules/document-standards.md`, integration tests | Schema and checker internals | `#1621`; integrated in umbrella `#1622` | `[x]` |
| V1 | audit_reviewer | with context | `docs/planning/change-contract-gate-prompts/V1-audit.md` | Audit integrated implementation after A1-A4 land | `audit/change-contract-gate` | `...\sci-wt\ccg-audit` | `docs/audit/change-contract-gate-implementation-audit.md` | Production edits unless assigned by manager | `#1617`; report `docs/audit/change-contract-gate-implementation-audit.md` | `[x]` |

## 7. Track A1: Schema

- Owner: A1
- Required docs: schema examples if needed, otherwise N/A in gate ledger.
- Required tests: schema validation tests.

### 7.1 Dispatch

- [~] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.2 Implementation

- [x] Schema models implemented -> PR `#1624`.
- [x] Tests added -> `pytest tests/qa/test_change_contract_schemas.py --no-cov` passed.
- [x] Docs or N/A recorded -> spec frontmatter metadata updated in PR `#1624`.

## 8. Track A2: Audit Core

- Owner: A2
- Required docs: update docs only if public contract syntax changes.
- Required tests: checker and baseline tests.

### 8.1 Dispatch

- [~] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.2 Implementation

- [x] Contract discovery implemented -> `src/scistudio/qa/audit/change_contracts.py`.
- [x] Governance coverage and forbidden-reference checks implemented -> `tests/qa/test_change_contracts.py`.
- [x] Baseline reconciliation implemented -> `docs/audit/baselines/change-contract-baseline.json`; `tests/qa/test_change_contracts.py`.

## 9. Track A3: Reachability

- Owner: A3
- Required docs: N/A unless checker UX changes.
- Required tests: Python, frontend, entrypoint, and canary fixtures.

### 9.1 Dispatch

- [~] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 9.2 Implementation

- [x] Python import roots implemented -> PR `#1625`.
- [x] TypeScript import roots implemented -> PR `#1625`.
- [x] Entrypoint/canary path implemented -> PR `#1625`.

## 10. Track A4: Gate Wiring And Docs

- Owner: A4
- Required docs:
  `docs/ai-developer/specific_rules/document-standards.md`.
- Required tests: full audit and gate selection tests.

### 10.1 Dispatch

- [~] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 10.2 Implementation

- [x] Full audit child report wired -> `src/scistudio/qa/audit/full_audit.py`.
- [x] Gate-record check selection wired -> `src/scistudio/qa/governance/gate_record/checks.py`.
- [x] Authoring docs updated -> `docs/ai-developer/specific_rules/document-standards.md`.

## 11. Track V1: Audit

- Owner: V1
- Required docs:
  `docs/audit/change-contract-gate-implementation-audit.md`.
- Required tests: audit should run existing targeted checks and inspect CI.

### 11.1 Dispatch

- [x] Audit report file path assigned -> `docs/audit/change-contract-gate-implementation-audit.md`.
- [x] Findings recorded -> no blocking findings after local verification.
- [x] P1 findings fixed before final integration -> signature-contract and planned-governs drift fixed.
- [x] Audit report committed in final umbrella candidate.

## 12. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --record .workflow/records/1617-change-contract-gate-manager.json --base origin/docs/change-contract-gate-spec --head HEAD --mode local` | `[x]` | `reconciliation passed` |
| Targeted tests | manager-only docs/checklist N/A | `[x]` | `--test-na "manager:dispatch checklist and prompts only; implementation agents will own code tests."` |
| Pre-push gate check | Git push hook | `[x]` | `git push -u origin track/change-contract-gate-implementation` succeeded. |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --record .workflow/records/1617-change-contract-gate-manager.json --base origin/docs/change-contract-gate-spec --head HEAD --mode pre-pr --pr-body-file .workflow/local/change-contract-gate-umbrella-pr.md` | `[x]` | `reconciliation passed` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit b1c00c608b0477464a07267928ff764d693ddbe7 --pr-body-file .workflow/local/change-contract-gate-umbrella-pr.md --closes "#1617"` | `[x]` | `ledger is PR-ready` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --draft --base main --head track/change-contract-gate-implementation --title "[DO NOT MERGE] implement ADR-042 change contract gate (#1617)" --body-file .workflow/local/change-contract-gate-umbrella-pr.md` | `[x]` | `reconciliation passed`; PR `#1622`. |
| Targeted implementation tests | `PYTHONPATH=src python -m pytest tests/qa/test_change_contracts.py tests/qa/test_change_contract_schemas.py tests/qa/test_change_contract_reachability.py tests/qa/test_audit_full_audit.py tests/qa/test_griffe_facts.py --no-cov` | `[x]` | `27 passed`. |
| Change-contract audit CLI | `PYTHONPATH=src python -m scistudio.qa.audit.change_contracts --repo-root . --format text` | `[x]` | `pass`; 2 contracts checked; 0 findings. |
| Full audit CLI | `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json` | `[x]` | `pass`. |
| Semantic duplication ratchet | `python scripts/semantic_dup_scan.py --check docs/audit/baselines/semantic-dup-baseline.json` | `[x]` | `OK: all ratchets within limits`. |
| Lint | `ruff check src/scistudio/qa/audit/_util.py src/scistudio/qa/audit/change_contracts.py src/scistudio/qa/audit/full_audit.py src/scistudio/qa/audit/griffe_facts.py src/scistudio/qa/schemas/frontmatter.py src/scistudio/qa/governance/gate_record/checks.py tests/qa/test_change_contracts.py` | `[x]` | `All checks passed`. |
| Format | `ruff format --check src/scistudio/qa/audit/_util.py src/scistudio/qa/audit/change_contracts.py src/scistudio/qa/audit/full_audit.py src/scistudio/qa/audit/griffe_facts.py src/scistudio/qa/schemas/frontmatter.py src/scistudio/qa/governance/gate_record/checks.py tests/qa/test_change_contracts.py` | `[x]` | `7 files already formatted`. |
| Type check | `PYTHONPATH=src mypy src/scistudio/qa/audit/_util.py src/scistudio/qa/audit/change_contracts.py src/scistudio/qa/audit/full_audit.py src/scistudio/qa/audit/griffe_facts.py src/scistudio/qa/schemas/frontmatter.py src/scistudio/qa/governance/gate_record/checks.py --ignore-missing-imports` | `[x]` | `Success: no issues found in 6 source files`. |
| Gate ledger check (final local pre-PR) | `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --record .workflow/records/1617-change-contract-gate-manager.json --base origin/main --head HEAD --mode pre-pr --pr-body-file .workflow/local/change-contract-gate-final-pr.md` | `[!]` | All selected checks passed except local Windows full-suite `python_tests`; latest raw log shows `tests/api/test_workflows.py::test_execute_after_completion_is_allowed` timing out under xdist. GitHub CI remains authoritative. |

## 13. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-12 | manager | Implementation manager branch is based on draft spec PR `#1615` so agents can see the spec before it merges. | Final implementation branch must rebase or retarget after `#1615` lands. | `#1617` |
| 2026-06-12 | manager | A1 and A3 dispatched first; A2/A4 wait for schema/reachability interfaces to reduce conflicts. | Spawned A1 `019ebdf2-5ac8-74a1-8812-81c748044f53` and A3 `019ebdf2-973b-72c2-8245-1a8637189abe`. | `#1618`, `#1620` |
| 2026-06-12 | manager | A1/A3 agents stalled in long local gate checks and did not return after interrupt. | Closed agents, preserved their worktrees, ran targeted tests/lint, opened PRs `#1624` and `#1625`, and pushed post-PR ledger evidence. | `#1618`, `#1620` |
| 2026-06-12 | manager | A1 updated `docs/specs/adr-042-change-contract-gate.md` frontmatter although prompt ownership was schema-focused. | Accepted as a narrow governance metadata update moving implemented schema surfaces from planned to governed and adding the schema test path. | `#1618` |
| 2026-06-12 | manager | A1/A3 foundation PRs are CI green, but A2/A4 depend on those interfaces being integrated. | Hold A2/A4 dispatch until owner authorizes merging foundation PRs into the umbrella or approves stacked PRs. | `#1624`, `#1625` |
| 2026-06-12 | manager | A2/A4 were completed in the umbrella worktree after A1/A3 were integrated, instead of spawning more stalled worker branches. | Manager recorded implementation, audit report, targeted tests, and final PR evidence in the umbrella candidate. | `#1617`, `#1619`, `#1621` |
| 2026-06-12 | manager | Local final pre-PR gate cannot satisfy full `python_tests` on Windows due an unrelated API workflow timeout under xdist. | Preserve targeted implementation evidence, semantic/full-audit passes, and wait for GitHub Linux CI on final PR. | `#1617` |

## 14. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
