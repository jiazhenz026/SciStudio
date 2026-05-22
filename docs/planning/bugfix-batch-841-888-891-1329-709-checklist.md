---
title: "Bugfix Batch 841 888 891 1329 709 Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Bugfix Batch 841 888 891 1329 709 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: integrate completed non-god-file bug fixes into one manager-owned PR.
- Task kind: `manager`
- Manager persona: `manager`
- Issues: `#841`, `#888`, `#891`, `#1329`, `#709`
- Gate record: `.workflow/records/841-888-891-1329-709-manager-bugfix-batch.json`
- Branch/worktree plan:
  `manager/bugfix-batch-841-888-891-1329-709` in
  `C:\Users\jiazh\Desktop\workspace\SciStudio-manager-bugfix-batch-20260522`
- Protected branch: `main`
- Umbrella branch: `manager/bugfix-batch-841-888-891-1329-709`
- Umbrella PR: `#1451`
- Umbrella PR title: `fix: integrate bugfix batch 841 888 891 1329 709`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Integrate worker PR #1434 for #841 Windows npm shim executable resolution.
  - Integrate worker PR #1436 for #888 lazy Zarr axis iteration.
  - Integrate worker PR #1437 for #891 release wheel SPA enforcement.
  - Integrate worker PR #1438 for #1329 normalized storage reference errors.
  - Integrate worker PR #1439 for #709 imaging variadic input staging.
  - Preserve each worker gate record and add a manager gate record.
- Out of scope:
  - Frontend god-file cleanup and hook fixes tracked by #1420, #1421, #1422.
  - Backend/engine god-file refactors in protected and non-protected buckets.
  - Scheduler, block registry, git engine, loader/saver ADR-constrained refactors.
- Protected paths:
  - `.github/workflows/ci.yml`
  - `src/scistudio/core/storage/**`
  - `src/scistudio/engine/runners/**`
- Deferred work:
  - N/A.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created:
      `manager/bugfix-batch-841-888-891-1329-709`.
- [x] Existing issues linked: `#841`, `#888`, `#891`, `#1329`, `#709`.
- [x] Gate record started:
      `.workflow/records/841-888-891-1329-709-manager-bugfix-batch.json`.
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened: #1451.
- [x] Umbrella PR title recorded for final integration.
- [x] Protected branch recorded: `main`.
- [x] No `pip install -e .` used in manager worktree.
- [x] Dispatch checklist copied from the template and committed in this PR.
- [x] Dispatch prompts are represented by worker PRs and manager comments.
- [x] Sentrux baseline: worker records include Sentrux evidence where available;
      manager record carries N/A because this PR is integration-only.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: owner chat on 2026-05-22, "已授权".
- Reason: integrated worker fixes touch protected workflow/core/runtime paths.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `admin-approved:core-change` | `[x]` | `gate_record: pass` |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `admin-approved:core-change` | `[x]` | `gate_record: pass` |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `admin-approved:core-change` | `[~]` | pending branch validation |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Volta | `implementer` | N/A | manager dispatch | Windows npm shims | `fix/issue-841-windows-npm-shims` | worker worktree | `src/scistudio/ai/agent/terminal.py`, `src/scistudio/api/routes/ai.py`, `tests/ai/test_windows_executable_resolution.py` | forbidden god-file paths | #841 / #1434 | `[x]` |
| Parfit | `implementer` | N/A | manager dispatch | Zarr axis iteration | `fix/888-axis-iter-zarr-lazy` | worker worktree | `src/scistudio/utils/axis_iter.py`, `tests/utils/test_axis_iter.py` | forbidden god-file paths | #888 / #1436 | `[x]` |
| Sartre | `implementer` | N/A | manager dispatch | Release wheel SPA check | `fix/891-require-frontend-wheel` | worker worktree | `.github/workflows/ci.yml`, `setup.py`, `tests/packaging/test_wheel_spa.py` | forbidden god-file paths | #891 / #1437 | `[x]` |
| Bohr | `implementer` | N/A | manager dispatch | Storage reference errors | `fix/issue-1329-storage-errors` | worker worktree | `src/scistudio/core/storage/**`, `src/scistudio/engine/runners/**`, `tests/core/test_storage.py`, `tests/engine/**` | forbidden god-file paths | #1329 / #1438 | `[x]` |
| Maxwell | `implementer` | N/A | manager dispatch | Imaging variadic inputs | `fix/709-imaging-variadic-inputs` | worker worktree | `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/interactive/**`, `packages/scistudio-blocks-imaging/tests/test_interactive_blocks.py` | forbidden god-file paths | #709 / #1439 | `[x]` |

## 7. Track: Integrated Bugfix Batch

### 7.1 Track Scope

- Owner: manager.
- In scope:
  - Merge worker outputs into one branch based on latest `origin/main`.
  - Preserve worker test and gate evidence.
  - Add manager checklist and gate record.
- Out of scope:
  - Any god-file cleanup path listed in the owner directive.
- Required docs:
  - `docs/planning/bugfix-batch-841-888-891-1329-709-checklist.md`
- Required tests:
  - Worker PR targeted tests plus manager integration checks.

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded in issue comments.
- [x] Correct prompt template selected for implementer workers.
- [x] Audit mode N/A for implementation workers.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in dispatch.
- [x] TODO rule included in dispatch.
- [x] Required checks included in dispatch.

### 7.3 Implementation

- [x] #841 implementation integrated -> PR #1434, commit
      `fb13623c3e2ea9a6da0eb682eb23a0b6454b0d37`.
- [x] #888 implementation integrated -> PR #1436, commit
      `8d41dc6e61fe25d6fadf95f2c42d6f1fc83ed3d6`.
- [x] #891 implementation integrated -> PR #1437, commit
      `09c4b0b808497595d7ccb15b48f78dba178f9e00`.
- [x] #1329 implementation integrated -> PR #1438, commit
      `997073f468d73d1350cef51be787dbc11566c064`.
- [x] #709 implementation integrated -> PR #1439, commit
      `1711bf933fba0392848e2935fd4925ca8a2c0fc3`.
- [x] Docs row -> this manager checklist.

### 7.4 Audit

- [x] Manager reviewed worker PR changed-file scope before integration.
- [x] Audit report file path N/A; worker PRs and gate records contain evidence.
- [x] Findings recorded in worker issue comments.
- [x] P1 findings fixed before integration.
- [x] P2/P3 findings fixed or N/A.

### 7.5 Integration

- [x] Agent output reviewed by manager.
- [x] Scope compliance verified against owner forbidden-file list.
- [x] Conflicts resolved intentionally: no merge conflicts occurred.
- [x] Track merged into manager branch.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `python -m ruff check <integrated Python paths>` | `[x]` | `All checks passed!` |
| Format | `python -m ruff format --check <integrated Python paths>` | `[x]` | `27 files already formatted` |
| Tests | targeted worker test suite union | `[x]` | root targeted tests passed; imaging package tests `9 passed in 9.40s` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json` | `[x]` | full_audit status `pass`, findings `0` |
| Sentrux | manager N/A | `[x]` | Sentrux evidence remains in worker gate records; manager integration adds no new product behavior. |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-22 | manager | Worker PRs were initially separate. | Created manager integration branch and checklist. | N/A |
| 2026-05-22 | manager | Combined PR exceeded semantic duplication ratchet by 43 duplicate LOC. | Refactored `src/scistudio/utils/axis_iter.py` to share result ndim validation and zarr result construction. | N/A |

## 10. Final Readiness

- [x] All dispatched agents have final outputs.
- [x] Manager reviewed every changed file path.
- [x] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [x] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [x] Checklist final state matches PR and gate record.
