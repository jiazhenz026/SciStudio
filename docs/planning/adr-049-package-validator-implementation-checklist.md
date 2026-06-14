---
title: "ADR-049 Package Validator Implementation Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 49
related_specs:
  - adr-049-package-validator-implementation
language_source: en
---

# ADR-049 Package Validator Implementation Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Implement the ADR-049 package validator module specified by PR #1662; verify with e2e and run it against every existing SciStudio package.
- Task kind: `manager` for umbrella coordination; dispatched implementation agents use `feature`.
- Manager persona: `manager`
- Issue: `#1664`
- Gate record: `.workflow/records/1664-track-adr-049-package-validator-implementation.json`
- Branch/worktree plan: manager branch `track/adr-049-package-validator-implementation` in `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-impl`; agent branches use `feat/1664-pv-*` and `audit/1664-pv-*` from the umbrella branch.
- Protected branch: `main`
- Umbrella base: `design/package-validator-contract-survey` (PR #1662 ADR/spec branch)
- Umbrella branch: `track/adr-049-package-validator-implementation`
- Umbrella PR: `#1665`
- Umbrella PR title: `[DO NOT MERGE] feat(#1664): implement ADR-049 package validator runtime`
- Final PR target: stacked onto PR #1662 until ADR/spec lands on `main`; final merge target remains `main`.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/packages/validation/**`
  - `src/scistudio/cli/package_validator.py`
  - `src/scistudio/cli/main.py`
  - `pyproject.toml`
  - `tests/packages/**`
  - `docs/block-development/package-validator.md`
  - `docs/planning/adr-049-package-validator-implementation-checklist.md`
  - `docs/planning/adr-049-package-validator-implementation/prompts/**`
  - `docs/audit/**`
  - `docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md`
  - `CHANGELOG.md`
- Conditional scope:
  - `src/scistudio/blocks/registry/**`
  - `src/scistudio/core/types/registry.py`
  - `src/scistudio/previewers/**`
  - Only touch these if temporary registry composition is impossible; amend this checklist with the exact reason before editing.
- Out of scope:
  - Weakening tolerant startup discovery paths.
  - Partial production registration or quarantine UI.
  - Moving ADR-049 contract tables out of `docs/planning`.
  - Broad registry refactors.
  - Relaxing governance, CI, Sentrux, or quality thresholds.
- Protected paths:
  - `docs/ai-developer/**` is touched only for the required e2e scenario file; gate ledger marks `governance_touch=true`.
- Deferred work:
  - N/A unless implementation discovers an explicit ADR-049 out-of-scope item; any deferral must cite #1664, ADR-049, the spec, or a new follow-up issue.

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

- [x] Dedicated manager branch and worktree created -> `track/adr-049-package-validator-implementation`, `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-impl`
- [x] Existing issue checked; new implementation issue created because #1659 is design-only -> #1664
- [x] Gate record started -> `.workflow/records/1664-track-adr-049-package-validator-implementation.json`
- [x] Scope include/exclude recorded in the gate record -> `gate_record init` and `gate_record amend`
- [x] Umbrella branch created -> `track/adr-049-package-validator-implementation`
- [x] Umbrella PR opened -> #1665
- [x] Umbrella PR title includes `[DO NOT MERGE]` -> #1665
- [x] Protected branch and umbrella PR number recorded in this checklist -> #1665
- [x] No `pip install -e .` environment pollution found -> `python -c "import scistudio"` failed without `PYTHONPATH`
- [x] Dispatch checklist copied from the template and committed -> commit `8973688e`
- [x] Dispatch prompts created from the correct prompt template and linked below -> commit `8973688e`
- [x] Sentrux baseline recorded, or N/A reason recorded -> N/A at preflight; final `gate_record check` owns guard evidence

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `pending` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `pending` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `pending` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/design/package-validator-contract-survey --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[x]` | `Tier 3 full_audit reconciliation passed` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A; only a task-specific e2e scenario under docs/ai-developer/e2e is planned.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| PV-F1 | `implementer` | `N/A` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-f1-foundation.md` | Models, contract loader, inventory builder | `feat/1664-pv-foundation` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-foundation` | `src/scistudio/packages/validation/{__init__.py,models.py,contracts.py,inventory.py}`, focused tests/fixtures | Engine, registration, CLI docs, core registry edits | #1664 / #1665 | `[!]` shutdown before implementation |
| PV-F1-R2 | `implementer` | `N/A` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-f1-foundation-r2.md` | Models, contract loader, inventory builder | `feat/1664-pv-foundation-r2` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-foundation-r2` | `src/scistudio/packages/validation/{__init__.py,models.py,contracts.py,inventory.py}`, focused tests/fixtures | Engine, registration, CLI docs, core registry edits | #1664 / #1665 | `[~]` |
| PV-T1 | `test_engineer` | `N/A` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-t1-fixtures-tests.md` | Fixture packages and report/contract test matrix | `feat/1664-pv-fixtures-tests` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-fixtures-tests` | `tests/packages/**` only | Production code, docs except checklist rows | #1664 / #1665 | `[~]` |
| PV-E1 | `implementer` | `N/A` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-e1-engine-registration.md` | Validation engine, dry-run registries, production handoff | `feat/1664-pv-engine-registration` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-engine` | `src/scistudio/packages/validation/{engine.py,registration.py}`, production tests | CLI docs, e2e, broad registry refactor | #1664 / #1665 | `[ ]` |
| PV-C1 | `implementer` | `N/A` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-c1-cli-docs-evidence.md` | CLI, author docs, changelog, e2e scenario, all-package scan evidence | `feat/1664-pv-cli-docs-evidence` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-cli-docs` | `src/scistudio/cli/package_validator.py`, `src/scistudio/cli/main.py`, `pyproject.toml`, docs/evidence files | Engine internals, registry internals | #1664 / #1665 | `[ ]` |
| PV-A1 | `audit_reviewer` | `with-context` | `docs/planning/adr-049-package-validator-implementation/prompts/pv-a1-with-context-audit.md` | Audit integrated implementation against #1664, ADR-049, spec, tests, and package scan evidence | `audit/1664-pv-with-context` | `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-audit` | `docs/audit/2026-06-14-adr-049-package-validator-with-context.md`, checklist audit rows | Implementation code changes | #1664 / #1665 | `[ ]` |

For `test_engineer` rows, production code is out of scope by default.

## 7. Track: Foundation, Contracts, Inventory

### 7.1 Track Scope

- Owner: `PV-F1`
- In scope:
  - Validation data models and JSON report serialization.
  - Contract table loading and applicability normalization from ADR-049 JSON tables.
  - Candidate source tree, wheel/sdist, installed distribution, and no-entry-point inventory paths.
- Out of scope:
  - Live registry mutation.
  - CLI presentation.
  - E2E scenario execution.
- Required docs:
  - Public API exported in module docstrings; author-facing docs handled by PV-C1.
- Required tests:
  - `tests/packages/test_package_validator_reports.py`
  - foundation portions of `tests/packages/test_package_validator.py`

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded -> `docs/planning/adr-049-package-validator-implementation/prompts/pv-f1-foundation.md`
- [x] Correct prompt template selected -> `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
- [x] Agent branch/worktree assigned -> `feat/1664-pv-foundation`, `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-foundation`
- [x] Write set and out-of-scope paths included in prompt -> prompt file
- [x] TODO rule included in prompt -> prompt file
- [x] Required checks included in prompt -> prompt file

### 7.3 Implementation

- [ ] Models/report serialization implemented -> `pending`
- [ ] Contract loader/applicability implemented -> `pending`
- [ ] Inventory builder implemented -> `pending`
- [ ] Tests added/updated -> `pending`
- [ ] Docs row or N/A recorded -> `pending`

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

## 8. Track: Validation Engine And Production Registration

### 8.1 Track Scope

- Owner: `PV-E1`
- In scope:
  - Per-surface validation dispatch and not-applicable classification.
  - Dry-run type/block/previewer/IO capability/runner/API summaries by composition first.
  - Cross-surface consistency checks.
  - Atomic production registration handoff with live-registry unchanged-on-failure tests.
- Out of scope:
  - Partial registration or quarantine UI.
  - Tolerant startup discovery behavior changes.
  - Registry refactors without manager amendment.
- Required docs:
  - N/A except API docstrings; author-facing docs handled by PV-C1.
- Required tests:
  - `tests/packages/test_package_validator.py`
  - `tests/packages/test_package_validator_production_registration.py`

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded -> `docs/planning/adr-049-package-validator-implementation/prompts/pv-t1-fixtures-tests.md`
- [x] Correct prompt template selected -> `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
- [x] Agent branch/worktree assigned -> `feat/1664-pv-fixtures-tests`, `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-fixtures-tests`
- [x] Write set and out-of-scope paths included in prompt -> prompt file
- [x] TODO rule included in prompt -> prompt file
- [x] Required checks included in prompt -> prompt file

### 8.3 Implementation

- [ ] Per-surface validation dispatch implemented -> `pending`
- [ ] Dry-run registry summaries implemented -> `pending`
- [ ] Cross-surface checks implemented -> `pending`
- [ ] Production registration handoff implemented -> `pending`
- [ ] Tests added/updated -> `pending`

### 8.4 Audit

- [ ] Audit report covers production atomicity and dry-run behavior.
- [ ] P1 findings fixed before integration.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Track: CLI, Docs, E2E, Existing Package Sweep

### 9.1 Track Scope

- Owner: `PV-C1`
- In scope:
  - CLI JSON output and exit codes.
  - Test helper public API documentation.
  - Author-facing docs and changelog.
  - E2E scenario file and final runtime validation evidence.
  - Scan all existing packages: core, imaging, SRS, LCMS, and any generated/scaffold package present in this repository.
- Out of scope:
  - Validation engine internals except import/use.
  - Production registry internals.
- Required docs:
  - `docs/block-development/package-validator.md`
  - `CHANGELOG.md`
  - `docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md`
  - `docs/audit/2026-06-14-adr-049-existing-package-sweep.md`
- Required tests:
  - `tests/packages/test_package_validator_cli.py`

### 9.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 9.3 Implementation

- [ ] CLI wrapper implemented -> `pending`
- [ ] Docs and changelog updated -> `pending`
- [ ] E2E scenario created and run -> `pending`
- [ ] Existing packages scanned -> `pending`
- [ ] Sweep evidence committed -> `pending`

### 9.4 Audit

- [ ] Audit report checks package sweep completeness and CLI behavior.
- [ ] P1 findings fixed before integration.

### 9.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| ADR-049 contract table checker | `python scripts/audit/check_package_contract_tables.py` | `[x]` | preflight: `summary: 0 error(s), 9 warning(s)` |
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/design/package-validator-contract-survey --head HEAD` | `[ ]` | `pending` |
| Targeted tests | `python -m pytest tests/packages --timeout=60` | `[ ]` | `pending` |
| Existing package sweep | package validator CLI/API over core, imaging, SRS, LCMS | `[ ]` | `pending` |
| E2E | `docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md` | `[ ]` | `pending` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/design/package-validator-contract-survey --head HEAD` | `[ ]` | `pending` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/design/package-validator-contract-survey --pr-body-file .workflow/local/pr-body.md` | `[x]` | `Tier 3 full_audit reconciliation passed before initial umbrella PR` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --base origin/design/package-validator-contract-survey --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1664"` | `[ ]` | `pending` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --base design/package-validator-contract-survey --title "<title>" --body-file .workflow/local/pr-body.md` | `[ ]` | `pending` |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-14 | manager | Implementation issue did not exist; #1659 explicitly tracks design only. | Created #1664 and recorded in gate ledger. | #1664 |
| 2026-06-14 | manager | Initial gate ledger was started as `feature`, making the empty umbrella/checklist PR run Tier 1 full-suite checks before implementation dispatch. | Corrected manager-owned setup task kind to `manager`; implementation agents remain feature-scoped. | `.workflow/records/1664-track-adr-049-package-validator-implementation.json` |
| 2026-06-14 | PV-F1 | Agent remained running with only an untracked feature ledger and no implementation changes, then was shut down by manager. | Reassigned foundation track to PV-F1-R2 on a fresh branch/worktree. | `docs/planning/adr-049-package-validator-implementation/prompts/pv-f1-foundation-r2.md` |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
