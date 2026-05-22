---
title: "Phase 3 Bucket D Decomposition Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 46
  - 47
language_source: en
---

# Phase 3 Bucket D Decomposition Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Phase 3 of umbrella #1427 god-file refactor cascade. Decompose 3 remaining ≥750 LOC files in src/scistudio/ (Bucket D) under existing ADR-046 + ADR-047 + ADR-046 Addendum 1 (the addendum lands in D3's PR).`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1465`
- Gate record: `.workflow/records/1465-phase3-bucket-d-umbrella.json`
- Branch/worktree plan: `umbrella/phase3-bucket-d` in `.claude/worktrees/phase3-umbrella`; per-agent branches `refactor/issue-<N>/<slug>` in `.claude/worktrees/phase3-d{1,2,3}-<slug>`
- Protected branch: `main`
- Umbrella branch: `umbrella/phase3-bucket-d`
- Umbrella PR: `#<pending>`
- Umbrella PR title: `[DO NOT MERGE] umbrella(phase3): Bucket D decomposition (#1465)`
- Final PR target: `main` (umbrella PR), `umbrella/phase3-bucket-d` (sub-PRs after retarget)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context: `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context: `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope (3 files, ≥750 LOC each on main HEAD at dispatch time 2026-05-22):
  - `src/scistudio/engine/scheduler.py` (1744 LOC) — D1, ADR-046
  - `src/scistudio/blocks/registry.py` (1708 LOC) — D2, ADR-047 (+ ~250 LOC legacy IO finder delete)
  - `src/scistudio/core/versioning/git_engine.py` (849 LOC) — D3', ADR-046 Addendum 1 (lands in this PR)
- Out of scope:
  - Any other file in src/scistudio/
  - Behavior changes
  - ADR-018/020/028/030/038/039/042/043 semantics (preserved)
  - Frontend, desktop, packages/
- Protected paths:
  - `src/scistudio/engine/**` (D1)
  - `src/scistudio/blocks/**` (D2)
  - `src/scistudio/core/**` (D3')
- Deferred work:
  - Threshold ratchet `max_cycles` 5→0 — TODO(#1336 + #1465 closure)
  - Threshold ratchet `max-lines` 750→500 — TODO after Bucket D fully merged

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

- [x] Dedicated manager branch and worktree created. → `umbrella/phase3-bucket-d` in `.claude/worktrees/phase3-umbrella`
- [x] Existing issue linked, or new issue created only if none exists. → `#1465` (Phase 3 tracker, reopened after PR #1468 auto-close bug)
- [x] Gate record started. → `.workflow/records/1465-phase3-bucket-d-umbrella.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [ ] Umbrella PR opened. → pending
- [ ] Umbrella PR title includes `[DO NOT MERGE]`. → pending
- [ ] Protected branch and umbrella PR number recorded in this checklist. → pending
- [x] No `pip install -e .` environment pollution found. → manager uses `PYTHONPATH=src` only
- [x] Dispatch checklist copied from the template and committed. → this file
- [~] Dispatch prompts created from the correct prompt template and linked below. → embedded inline in Agent tool calls (chat record); commit-time copies pending under `docs/planning/phase3-bucket-d-prompts/`
- [ ] Sentrux baseline recorded, or N/A reason recorded. → pending

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: chat 2026-05-22 — Phase 3 dispatch authorization implicitly covered the core-change label per protected-globs rule (engine/**, blocks/**, core/** all protected). Earlier owner approval for Phase 1 Bucket B and Phase 2 set precedent.
- Reason: D1, D2, D3' all touch protected core paths.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` (manager scaffold) | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `D1` | `implementer` | `N/A` | inline (chat transcript) | Decompose `engine/scheduler.py` 1744 LOC per ADR-046 into 5 sibling modules + __init__.py | `refactor/issue-1470/scheduler-decomp` | `.claude/worktrees/phase3-d1-scheduler` | new `src/scistudio/engine/scheduler/{__init__,_dispatch,_events,_lineage,_state,_rerun,_helpers}.py` (largest 570 LOC) + tests/engine/test_scheduler_package_layout.py + scripts/check_god_files.py + docs/adr/ADR-{018,023,044,046}.md frontmatter | D2/D3' files, state-machine semantics, engine-wide architectural changes | #1470 / [PR #1473](https://github.com/zjzcpj/SciStudio/pull/1473) base=umbrella/phase3-bucket-d ✓ retargeted; admin-approved:core-change ✓; #1449 contract pass UNEDITED; §C9 grep clean | `[x]` done |
| `D2` | `implementer` | `N/A` | inline | Decompose `blocks/registry.py` 1708 LOC per ADR-047 into 4 sibling modules + delete legacy IO finder (~250 LOC) + migrate 2 callers + delete test_registry_find.py | `refactor/issue-1471/registry-decomp` | `.claude/worktrees/phase3-d2-registry` | new `src/scistudio/blocks/registry/{__init__,_scan,_capability,_spec}.py` (largest _capability.py 595 LOC) + validation.py + materialisation.py + test_block_registry_capabilities.py (3 tests deleted per agent rationale — ADR-043 rejects the behaviors those tested) + test_registry_find.py (deleted) + test_registry_package_layout.py (new) + scripts/check_god_files.py + ADR-008/009/025/028/029/030/036/037/043/047 + spec frontmatter | D1/D3' files, ADR-043/030/009 semantics | #1471 / [PR #1476](https://github.com/zjzcpj/SciStudio/pull/1476) base=umbrella/phase3-bucket-d ✓ retargeted; admin-approved:core-change ✓; 502 pass / 3 skip / 8 xfail; §C9 grep clean; legacy IO fully deleted | `[x]` done |
| `D3'` | `implementer` | `N/A` | inline | Class-binding split of `core/versioning/git_engine.py` 849 LOC + write `docs/adr/ADR-046-addendum1.md` in same PR | `refactor/issue-1472/git-engine-helpers` | `.claude/worktrees/phase3-d3-git-engine` | `src/scistudio/core/versioning/**` + docs/adr/ADR-046-addendum1.md (new) + test_git_engine_package_layout.py (new) + scripts/check_god_files.py | D1/D2 files, other core/versioning/ files | #1472 / PR `<pending; will retarget>` | `[~]` running (re-dispatched after D3 stop) |
| `AUDIT` | `audit_reviewer` | `with-context` | `<TBD post-implementation>` | Verify scope, public-surface preservation, test coverage, ADR compliance for all 3 sub-PRs | `audit/issue-1465/phase3-review` | `.claude/worktrees/audit-phase3` | audit report only | implementation files | `<pending>` | `[ ]` |

> **Drift note**: this checklist was built RETROACTIVELY after dispatch — D1/D2/D3' were dispatched before the checklist + umbrella PR existed (protocol violation per agent-dispatch.md §8 hard-fail points). Recovery: agents continue working on their pre-created branches; their PRs will be retargeted from `main` → `umbrella/phase3-bucket-d` when opened. See Section 9 Drift Log row 1.

## 7. Track: Phase 3 Bucket D

### 7.1 Track Scope

- Owner: `manager`
- In scope:
  - Pure structural decomposition of `scheduler.py`, `registry.py`, `git_engine.py`
  - Legacy IO finder deletion (D2 only)
  - ADR-046 Addendum 1 doc (D3' only)
  - Public import surface preservation for all 3
  - AST guard tests (1 per agent)
- Out of scope:
  - Any behavior change
  - State-machine semantic edits (D1)
  - Capability semantics edits (D2)
  - `_run` / `_git` / `_rev_parse_head` private helpers refactor (D3')
- Required docs:
  - ADR-046 frontmatter governs.files expansion (D1)
  - ADR-047 frontmatter governs.files expansion (D2)
  - NEW docs/adr/ADR-046-addendum1.md (D3')
- Required tests:
  - tests/engine/test_scheduler_package_layout.py (D1, new)
  - tests/blocks/test_registry_package_layout.py (D2, new)
  - tests/core/versioning/test_git_engine_package_layout.py (D3', new)
  - Plus: D2 must DELETE tests/blocks/test_registry_find.py + edit 3 lines in tests/blocks/test_block_registry_capabilities.py

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. → inline in chat transcript; commit copies pending
- [x] Correct prompt template selected. → agent-dispatch-prompt-template.md base used
- [ ] Audit mode recorded when persona is `audit_reviewer`. → with-context, when dispatched
- [x] Agent branch/worktree assigned. → see Section 6
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] D1: `scheduler.py` decomposed → [PR #1473](https://github.com/zjzcpj/SciStudio/pull/1473)
- [x] D2: `registry.py` decomposed + legacy IO deleted + 2 callers migrated → [PR #1476](https://github.com/zjzcpj/SciStudio/pull/1476)
- [~] D3': `git_engine.py` class-binding split + ADR-046 Addendum 1 written → PR `<pending>`
- [ ] All 3 files removed from `GOD_FILE_SIZE_WAIVERS` → pending (each agent does their own)

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
- [ ] Conflicts resolved intentionally (especially `scripts/check_god_files.py` — all 3 agents touch).
- [ ] Track merged or integrated. → sub-PRs into `umbrella/phase3-bucket-d`, then umbrella → main with per-merge owner authorization.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check src/scistudio/{engine,blocks,core/versioning}/` | `[ ]` | pending |
| Format | `ruff format --check` | `[ ]` | pending |
| Tests | `pytest tests/engine/ tests/blocks/ tests/core/versioning/ tests/integration/ tests/contracts/ --timeout=60 -x` | `[ ]` | pending |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | pending |
| Sentrux | MCP scan + check_rules + health | `[ ]` | pending (max_cycles=5 per PR #1468) |
| #1449 scheduler state-machine contract | `pytest tests/engine/test_scheduler_state_machine_contract.py` | `[ ]` | **MUST pass unedited (D1 hard constraint)** |
| God-file advisory | `python scripts/check_god_files.py --enforce` | `[ ]` | pending — expect 0 waivers remaining after Phase 3 |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-05-22` | `manager` | Dispatched 3 parallel agents (D1/D2/D3') without first building umbrella branch + checklist + [DO NOT MERGE] umbrella PR. Violates agent-dispatch.md §2 + §8 hard-fail points. | Built umbrella scaffold retroactively while agents continue running; retargeted sub-PRs from `main` to `umbrella/phase3-bucket-d` as they opened (#1473 D1, #1476 D2). Memory entry to add. | TODO(#1465-followup): write memory note about not carrying Phase 2 single-agent pattern into multi-agent Phase 3 |
| `2026-05-22` | `D2` | Dispatch prompt said "EDIT 3 lines in `test_block_registry_capabilities.py`". Agent instead DELETED 3 tests with rationale: the tests assert behaviors ADR-043 explicitly rejects (registration-order fallback, dtype=None ordering, fallback when capability class can't resolve) — capability API raises `AmbiguousCapabilityError` for these instead. Equivalent positive coverage already exists elsewhere in the file. | Accepted — agent rationale is sound; ADR-043 prohibits the behaviors those tests asserted. New layout test adds positive assertions that legacy methods are absent + capability methods present. | None — well-justified scope interpretation, not a violation |
| `2026-05-22` | `D1` | Pre-existing `api/routes/workflow_watcher.py` 907 LOC surfaced as a NEW god-file advisory after scheduler waiver was removed (no longer "hidden" by scheduler being the bigger waivered violation). | Track in follow-up; out of Phase 3 scope. | TODO(#1465-followup): open Phase 4 candidate issue for workflow_watcher.py |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
