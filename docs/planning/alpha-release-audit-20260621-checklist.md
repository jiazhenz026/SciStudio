---
title: "Alpha Release Audit 20260621 Agent Dispatch Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Alpha Release Audit 20260621 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Run a full alpha-readiness audit of the latest remote SciStudio core runtime before a planned small internal alpha release.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1733`
- Gate record: `.workflow/records/1733-alpha-release-audit.json`
- Branch/worktree plan: manager branch `track/alpha-release-audit-20260621` at `/Users/jiazhenz/SciStudio-alpha-audit-20260621`; audit agents use disjoint report paths under `docs/audit/2026-06-21-alpha-release-*`.
- Protected branch: `main`
- Remote baseline: `origin/main` at `1948ab2c`
- Umbrella branch: `track/alpha-release-audit-20260621`
- Umbrella PR: `#1734`
- Umbrella PR title: `[DO NOT MERGE] Alpha release audit for core runtime`
- Final PR target: `main`
- Dispatch prompt templates:
  - Audit with context: `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context: `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Core runtime alpha-readiness criteria and severity rubric.
  - Workflow graph validation, scheduler execution, block lifecycle, and runtime state.
  - Core block contracts, schemas, artifact persistence, storage, lineage, and versioning.
  - API, desktop runtime bridge, manual review path, and AI orchestration boundary as core-runtime surfaces.
  - Test, CI, governance, gate ledger, Sentrux/audit posture, and release evidence.
  - Docs, ADR/spec consistency, known limitations, and release-readiness reporting.
- Out of scope:
  - Package catalog completeness and package content quality.
  - Extension catalog completeness and extension content quality.
  - Product runtime code fixes; this task produces audit evidence only.
- Protected paths:
  - `docs/ai-developer/**` is read-only for this task.
  - `.github/**`, `.sentrux/**`, `src/**`, `tests/**`, and frontend production code are read-only for this task.
- Deferred work:
  - N/A for manager evidence. Product fixes found by agents must be classified in the final report and tracked by follow-up issues before implementation.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own report paths.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. Evidence: `/Users/jiazhenz/SciStudio-alpha-audit-20260621`, branch `track/alpha-release-audit-20260621`.
- [x] Existing issue linked, or new issue created only if none exists. Evidence: new scoped issue `#1733` after search found no alpha/readiness issue.
- [x] Gate record started. Evidence: `.workflow/records/1733-alpha-release-audit.json`.
- [x] Scope include/exclude recorded in the gate record. Evidence: gate `init` and `amend` events.
- [x] Umbrella branch created. Evidence: `track/alpha-release-audit-20260621`.
- [x] Umbrella PR opened. Evidence: draft PR `#1734`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`. Evidence: `[DO NOT MERGE] Alpha release audit for core runtime`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found. Evidence: no install command used.
- [x] Dispatch checklist copied from the template and committed. Evidence: this file, commit pending.
- [x] Dispatch prompts created from the correct prompt template and linked below. Evidence: `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md`.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `pending` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[x]` | `passed before PR creation; wrapper dry-run blocked because wrapper uses --skip-execution and gate reports --skip-execution as non-final readiness` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: no AI workflow behavior changed; manager audit evidence only.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1-runtime-engine | `audit_reviewer` | `with-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A1-runtime-engine` | Runtime graph, scheduler, block lifecycle, run state | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-runtime-engine.md` | implementation files | `#1733/#1734` | `[ ]` |
| A2-contracts-storage | `audit_reviewer` | `with-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A2-contracts-storage` | Block contracts, schemas, artifacts, lineage, storage, versioning | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-contracts-storage-lineage.md` | implementation files | `#1733/#1734` | `[ ]` |
| A3-api-desktop-ai | `audit_reviewer` | `with-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A3-api-desktop-ai` | API, desktop bridge, manual review, AI orchestration boundaries | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-api-desktop-ai.md` | implementation files | `#1733/#1734` | `[ ]` |
| A4-test-ci-governance | `test_engineer` | `with-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A4-test-ci-governance` | Test coverage, CI, gate ledger, audit tooling, Sentrux readiness | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-test-ci-governance.md` | production code | `#1733/#1734` | `[ ]` |
| A5-docs-spec-drift | `audit_reviewer` | `no-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A5-docs-spec-drift` | Independent docs/spec/code consistency audit | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-docs-spec-drift.md` | manager issue, checklist, PR claims | `#1733/#1734` | `[ ]` |
| A6-security-ops | `audit_reviewer` | `with-context` | `docs/planning/alpha-release-audit-20260621-dispatch-prompts.md#A6-security-ops` | Core runtime security, data integrity, operational readiness | manager-spawned | agent workspace | `docs/audit/2026-06-21-alpha-release-security-ops.md` | implementation files | `#1733/#1734` | `[ ]` |

## 7. Tracks

### 7.1 A1-runtime-engine

- Owner: `A1-runtime-engine`
- In scope: `src/scistudio/workflow/**`, `src/scistudio/engine/**`, runtime-facing block lifecycle code, matching tests and docs.
- Out of scope: package/extension content completeness, implementation fixes.
- Required docs: `docs/audit/2026-06-21-alpha-release-runtime-engine.md`
- Required tests: command evidence or explicit N/A in report.

### 7.2 A2-contracts-storage

- Owner: `A2-contracts-storage`
- In scope: `src/scistudio/blocks/**`, `src/scistudio/core/**`, schemas, artifact, storage, lineage, versioning, matching tests and docs.
- Out of scope: package/extension content completeness, implementation fixes.
- Required docs: `docs/audit/2026-06-21-alpha-release-contracts-storage-lineage.md`
- Required tests: command evidence or explicit N/A in report.

### 7.3 A3-api-desktop-ai

- Owner: `A3-api-desktop-ai`
- In scope: `src/scistudio/api/**`, `src/scistudio/desktop/**`, `src/scistudio/ai/**`, manual review and runtime truth boundary docs/tests.
- Out of scope: UI polish unrelated to core runtime, implementation fixes.
- Required docs: `docs/audit/2026-06-21-alpha-release-api-desktop-ai.md`
- Required tests: command evidence or explicit N/A in report.

### 7.4 A4-test-ci-governance

- Owner: `A4-test-ci-governance`
- In scope: tests, CI workflows, gate ledger behavior, QA/audit tooling, Sentrux availability, release evidence.
- Out of scope: production code changes.
- Required docs: `docs/audit/2026-06-21-alpha-release-test-ci-governance.md`
- Required tests: command evidence, check evidence, or explicit N/A in report.

### 7.5 A5-docs-spec-drift

- Owner: `A5-docs-spec-drift`
- In scope: independent docs/spec/ADR/code/test consistency across core runtime surfaces.
- Out of scope: current issue, manager checklist, dispatch prompts, PR claims, implementation fixes.
- Required docs: `docs/audit/2026-06-21-alpha-release-docs-spec-drift.md`
- Required tests: command evidence or explicit N/A in report.

### 7.6 A6-security-ops

- Owner: `A6-security-ops`
- In scope: security-sensitive core runtime behavior, path handling, subprocess/PTY, artifact/data integrity, operational readiness.
- Out of scope: package/extension content completeness, implementation fixes.
- Required docs: `docs/audit/2026-06-21-alpha-release-security-ops.md`
- Required tests: command evidence or explicit N/A in report.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `pending` |
| Targeted tests | agent-selected commands recorded in audit reports | `[ ]` | `pending` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `pending` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `pending` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1733"` | `[ ]` | `pending` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "[DO NOT MERGE] Alpha release audit for core runtime" --body "<body>"` | `[ ]` | `pending` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-21 | manager | No pre-existing alpha/readiness issue found. | Created `#1733`. | N/A |
| 2026-06-21 | manager | Gate-aware PR wrapper could not create the umbrella PR because its fixed `--skip-execution` preflight conflicts with gate check semantics that mark `--skip-execution` as non-final readiness. | Ran full `gate_record check --mode pre-pr`, then opened draft umbrella PR `#1734` through the GitHub connector. | Track as release/governance audit evidence in A4 report. |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
