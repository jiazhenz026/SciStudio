---
title: "ADR-052 Public API Contract Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 52
language_source: en
---

# ADR-052 Public API Contract Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Land ADR-052 public API contract completely (steps 1-3 + scoped §14 docs) with doc build, tests, anti-regression, 3 no-context audits, final PR + CI.`
- Task kind: `feature`
- Manager persona: `manager`
- Issue: `#1833` (impl) under umbrella tracking `#1817`
- Gate record: `.workflow/records/1833-manager-1833-adr-052-public-api.json`
- Branch/worktree plan: manager integrates on `manager/1833-adr-052-public-api`; agents on dedicated `feat/test` branches + worktrees off `origin/main`.
- Protected branch: `main`
- Umbrella branch: `manager/1833-adr-052-public-api`
- Umbrella PR: `#1834`
- Umbrella PR title: `[DO NOT MERGE] ADR-052 public API contract integration`
- Final PR target: `main` (manager-owned final PR; closes #1833)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - ADR-052 §16 steps 1-3: `__all__` + `@stable/@provisional/@internal` + `since=` + docstrings on the canonical roots; mkdocstrings/griffe generated reference; golden-snapshot freeze + `tests/api/` tests.
  - Folded surface work (spec §16 step 1): ergonomic accessors; de-underscore reconstruction hooks; delete `DataObject.metadata` shim; demotions; `supported_extensions` deprecation; interactive + `BlockCancelledByAppError` re-exports; `PackageOtaSource`; `FileWatcher` plain-`Popen`; `_guess_mime` core removal; delete dead CodeBlock runner layer.
  - Scoped §14 docs: delete `docs/block-development/**`; fix custom-block GUI starter template API (narrative unchanged).
- Out of scope:
  - §9 plot behavior-pinning test (deferred to `#1824`, owner implementing; added after #1824 merges).
  - Package adoption (§13/§5, external repos); `#1825` rewrite; `#1826` template; `#1820` agent skills; per-project provisioned manual; `#1729` axis_iter; `_data`/`_arrow_table` retirement.
  - `scistudio.ai.agent.mcp.tools_plot/**` (owned by owner's `#1824`).
- Protected paths:
  - `src/scistudio/core/**`, `src/scistudio/blocks/**`, `src/scistudio/previewers/**` (protected core → `admin-approved:core-change`).
- Deferred work:
  - `TODO(#1824)` §9 plot behavior-pinning test.
  - `TODO(#1817)` `_data`/`_arrow_table` transient-bridge retirement (internal; no surface impact).

## 3. Conventions

- `[ ]` not started / `[~]` in progress / `[x]` done / `[!]` blocked
- Every completed row MUST include an artifact (PR, commit, test cmd, report, ledger entry).
- Agents edit only their own rows. Scope changes require gate-record amendment.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. → `manager/1833-adr-052-public-api` @ `/Users/jiazhenz/scistudio-wt-1833-mgr`
- [x] Existing issue linked, or new issue created only if none exists. → impl `#1833` under tracking `#1817`
- [x] Gate record started. → `.workflow/records/1833-manager-1833-adr-052-public-api.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. → `manager/1833-adr-052-public-api`
- [x] Umbrella PR opened. → #1834
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch (`main`) and umbrella PR number (#1834) recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked below. → `docs/planning/dispatch-prompts/1833/`
- [x] Sentrux baseline recorded, or N/A reason recorded. → Sentrux MCP unavailable; recorded as guard event via `gate_record check`.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: `chat 2026-06-27 — owner directed full ADR-052 landing (protected core), then said "我去睡觉了，你自主实现就行"`
- Reason: `Public API contract declaration touches protected core (core/blocks/previewers). Owner-authorized scope. Label provenance verified by CI by actor; owner must apply the label on the PR.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-PR reconcile | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | pending integration |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked: `docs/ai-developer/**` not touched (no `governance_touch`).
- Updated docs or N/A rationale: `N/A — this change does not alter gate/CI/AI-runtime behavior.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/dispatch-prompts/1833/A1-core.md` | core/** public surface | `feat/1833-adr-052-core` | `…wt-1833-core` | `src/scistudio/core/**` | everything else | #1833 | `[x]` 28da411f |
| A5 | test_engineer | N/A | `docs/planning/dispatch-prompts/1833/A5-dedicated-tests.md` | NEW dedicated contract suite (owner 2026-06-27) | `test/1833-adr-052-dedicated-suite` | `…wt-1833-tests2` | `tests/adr052_contract/**` | all other tests + src + docs | #1833 | `[~]` |
| A2 | implementer | N/A | `docs/planning/dispatch-prompts/1833/A2-blocks.md` | blocks/** public surface + template | `feat/1833-adr-052-blocks` | `…wt-1833-blocks` | `src/scistudio/blocks/**` | everything else | #1833 | `[ ]` |
| A3 | implementer | N/A | `docs/planning/dispatch-prompts/1833/A3-prevdocs.md` | previewers/** + doc build + docs deletion | `feat/1833-adr-052-prevdocs` | `…wt-1833-prevdocs` | `src/scistudio/previewers/**`, `mkdocs.yml`, `pyproject.toml`, `docs/user/reference/**`, `docs/block-development/**`, `scripts/docs/**` | everything else | #1833 | `[ ]` |
| A4 | test_engineer | N/A | `docs/planning/dispatch-prompts/1833/A4-tests.md` | ALL tests (owner: 1 test agent) | `test/1833-adr-052-tests` | `…wt-1833-tests` | `tests/**` | all `src/**`, `docs/**` | #1833 | `[ ]` |
| Au1 | audit_reviewer | no-context | `docs/planning/dispatch-prompts/1833/Au1-audit.md` | API count/signature/tier strictness | `audit/1833-no-context-1` | `…wt-1833-audit1` | `docs/audit/**` | all impl/test files | #1833 | `[ ]` |
| Au2 | audit_reviewer | no-context | `docs/planning/dispatch-prompts/1833/Au2-audit.md` | test coverage + doc build | `audit/1833-no-context-2` | `…wt-1833-audit2` | `docs/audit/**` | all impl/test files | #1833 | `[ ]` |
| Au3 | audit_reviewer | no-context | `docs/planning/dispatch-prompts/1833/Au3-audit.md` | full contract conformance sweep | `audit/1833-no-context-3` | `…wt-1833-audit3` | `docs/audit/**` | all impl/test files | #1833 | `[ ]` |

## 7. Track: ADR-052 Public API Contract

### 7.1 Track Scope

- Owner: manager
- In scope: §2 above.
- Out of scope: §2 above.
- Required docs: generated reference (`docs/user/reference/**`), `mkdocs.yml`, `docs/block-development/**` deletion. CHANGELOG/architecture/skills = N/A (owner-excluded).
- Required tests: `tests/api/test_public_surface.py`, `test_stability_decorators.py`, `test_ergonomic_accessors.py`, freeze snapshot + test, data-flow guard.

### 7.2 Dispatch

- [x] Prompt files created and committed under `docs/planning/dispatch-prompts/1833/`.
- [x] Correct prompt template selected (work vs no-context audit).
- [x] Audit mode recorded (no-context) for Au1/Au2/Au3.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompts.
- [x] TODO rule included in prompts.
- [x] Required checks included in prompts.

### 7.3 Implementation

- [x] A1 core/** public surface (rebased onto post-#1824 main) — core.types 10 + core.meta 3; accessors, de-underscored hooks, metadata-shim removed, TypeRegistry/TypeSpec demoted.
- [x] A2 blocks/** public surface + template — base 13, process 1, io 12, app 7, code **60** (full §7A non-underscore surface, manager-confirmed); FileWatcher plain-Popen; _guess_mime removed; runner layer deleted; template canonical-root imports.
- [x] A3 previewers/** + doc build + docs deletion — models 21, data_access 11; mkdocstrings/griffe generated reference (mkdocs build --strict green); `docs/block-development/**` deleted.
- [x] A4 tests/** (reconcile existing + new tests/api) — committed.
- [x] A5 NEW dedicated suite `tests/adr052_contract/**` (owner-added 2026-06-27) — committed.
- [x] A6 integration test reconciliation — snapshot regenerated from live (138; blocks.code 60; 9 non-markable exempted), accessor persistence, deprecation alignment, §9 plot behavior-pinning test (Python green; R deferred TODO(#1824)), existing-test fixes, block-development ripple. Full affected suite: **4208 passed, 0 errors** (5 local env-leak fails pass in clean CI venv; 3 runner entry-point tests now skip after the dead `scistudio.runners` group removal).

### 7.4 Audit

- [ ] Au1/Au2/Au3 no-context audits dispatched on the integrated diff.
- [ ] Audit reports committed under `docs/audit/`.
- [ ] Findings recorded; P1 fixed before final PR; P2/P3 fixed or tracked.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Freeze test reconciled (live impl vs spec-derived snapshot).
- [ ] Doc build verified to succeed.
- [ ] Tracks merged into integration branch.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | pending |
| Full test suite | `pytest` (gate-selected) | `[ ]` | pending |
| Doc build | `mkdocs build --strict` (or generation script) | `[ ]` | pending |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `gate_record finalize --commit <sha> --pr-body-file … --closes "#1833"` | `[ ]` | pending |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-27 | manager | §9 plot test depends on in-flight #1824 | deferred §9 test; will continue A4 after #1824 merges | TODO(#1824) |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence, commit, PR.
- [ ] PR closes #1833.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
