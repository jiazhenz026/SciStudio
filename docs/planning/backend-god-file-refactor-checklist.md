---
title: "Backend God-File Refactor Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Backend God-File Refactor Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Refactor backend/engine god files (Python side) — Phase 1 = Bucket A + B (10 files, max-lines=500).`
- Task kind: `refactor`
- Manager persona: `manager`
- Issue: `#1427`
- Gate record: `.workflow/records/1427-backend-god-file-refactor.json`
- Branch/worktree plan: `umbrella/backend-god-file-refactor` in `.claude/worktrees/backend-god-refactor`; per-agent branches `refactor/issue-<sub>/<slug>` in `.claude/worktrees/<agent-slug>`
- Protected branch: `main`
- Umbrella branch: `umbrella/backend-god-file-refactor`
- Umbrella PR: `#<pending>`
- Umbrella PR title: `[DO NOT MERGE] umbrella(backend): god-file refactor Phase 1 (Bucket A + B)`
- Final PR target: `main` (umbrella PR), `umbrella/backend-god-file-refactor` (sub-PRs)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- LOC counts below are from `scripts/check_god_files.py` (Python stdlib line count). Earlier PowerShell `Measure-Object -Line` counts in chat were systematically lower because it excludes blank lines; the script counts are authoritative.
- In scope (Phase 1, this umbrella initial batch — 10 of the 14 Bucket A+B candidates, per the 5-agent cap):
  - Bucket A (non-protected, no core-change label needed) — 7 of 9 selected:
    - `src/scistudio/api/runtime.py` (1839 LOC)
    - `src/scistudio/ai/agent/mcp/tools_workflow.py` (884)
    - `src/scistudio/ai/agent/mcp/tools_inspection.py` (809)
    - `src/scistudio/api/routes/ai_pty.py` (757)
    - `src/scistudio/api/routes/workflow_watcher.py` (696)
    - `src/scistudio/cli/install.py` (691)
    - `src/scistudio/api/routes/git.py` (635)
  - Bucket B (protected, requires `admin-approved:core-change` label) — 3 of 5 selected:
    - `src/scistudio/qa/governance/gate_record.py` (1402)
    - `src/scistudio/core/types/registry.py` (633)
    - `src/scistudio/qa/audit/architecture_drift.py` (619)
  - Umbrella scaffold (this PR):
    - `docs/planning/backend-god-file-refactor-checklist.md`
    - `scripts/check_god_files.py` (advisory)
    - `.workflow/records/1427-backend-god-file-refactor.json`
- Out of scope (deferred to Phase 1.5 or later):
  - Phase 1.5 (Bucket A+B candidates not selected in Phase 1, deferred under the 5-agent cap):
    - `src/scistudio/api/routes/filesystem.py` (590) — Bucket A
    - `src/scistudio/ai/agent/terminal.py` (564) — Bucket A
    - `src/scistudio/core/types/base.py` (553) — Bucket B
    - `src/scistudio/workflow/validator.py` (505) — Bucket B
  - Bucket C (6 files) — blocked on ADR-028 Addendum re-evaluation
  - Bucket D (3 files) — blocked on new structural ADRs (scheduler, registry)
  - All frontend files (covered by #1422)
  - Any behavior change beyond pure structural decomposition (no API surface changes, no fix-along-the-way)
- Protected paths:
  - `src/scistudio/qa/governance/**` (gate_record.py — Bucket B)
  - `src/scistudio/qa/audit/**` (architecture_drift.py — Bucket B)
  - `src/scistudio/core/**` (core/types/registry.py — Bucket B)
- Deferred work:
  - Bucket C — TODO(#1427-followup): re-open after ADR-028 Addendum review
  - Bucket D — TODO(#1427-followup): re-open after structural ADRs land
  - Promote `scripts/check_god_files.py` from advisory to hard-fail — TODO(#1427-followup) once all 10 Phase-1 files are below threshold

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

- [x] Dedicated manager branch and worktree created. → `umbrella/backend-god-file-refactor` in `.claude/worktrees/backend-god-refactor`
- [x] Existing issue linked, or new issue created only if none exists. → `#1427` (no prior backend god-file issue existed)
- [x] Gate record started. → `.workflow/records/1427-backend-god-file-refactor.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [ ] Umbrella PR opened. → pending
- [ ] Umbrella PR title includes `[DO NOT MERGE]`.
- [ ] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found. → manager uses `PYTHONPATH=src` only
- [x] Dispatch checklist copied from the template and committed. → this file
- [ ] Dispatch prompts created from the correct prompt template and linked below. → pending until owner approves sub-PR dispatch
- [ ] Sentrux baseline recorded, or N/A reason recorded. → pending

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: chat 2026-05-22 (manager skill session, `/manager` invocation) — explicit owner answer to AskUserQuestion granting label for all 3 Bucket B files (`qa/governance/gate_record.py`, `qa/audit/architecture_drift.py`, `core/types/registry.py`).
- Reason: Bucket B sub-PRs touch protected core paths (`src/scistudio/qa/{governance,audit}/**`, `src/scistudio/core/**`). Label is required for any PR landing on these paths per `reference_protected_globs`.
- Scope of bypass: ONLY the 3 Bucket B sub-PRs. Bucket A sub-PRs and this umbrella scaffold PR do not need the label.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` (umbrella scaffold non-protected) | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `<TBD on dispatch>` | Split `api/runtime.py` (1646 LOC) — preserve public import surface | `refactor/issue-<sub>/api-runtime` | `.claude/worktrees/refactor-a1-api-runtime` | `src/scistudio/api/runtime.py` + new sibling modules under `src/scistudio/api/runtime/` (or equivalent) + tests under `tests/api/` | All other Bucket A/B files, all routes, all engine code | `<sub-issue, sub-PR pending>` | `[ ]` |
| `A2` | `implementer` | `N/A` | `<TBD>` | Split 3 FastAPI route files: `api/routes/{ai_pty,workflow_watcher,git}.py` | `refactor/issue-<sub>/api-routes-trio` | `.claude/worktrees/refactor-a2-api-routes` | the 3 route files + new submodules + tests | `api/runtime.py`, MCP tools, anything outside `api/routes/` | `<pending>` | `[ ]` |
| `A3` | `implementer` | `N/A` | `<TBD>` | Split `ai/agent/mcp/tools_workflow.py` + `ai/agent/mcp/tools_inspection.py` + `cli/install.py` | `refactor/issue-<sub>/mcp-cli-trio` | `.claude/worktrees/refactor-a3-mcp-cli` | the 3 files + new submodules + tests | All other files | `<pending>` | `[ ]` |
| `B1` | `implementer` | `N/A` | `<TBD>` | Split `qa/governance/gate_record.py` (1192 LOC) along 6-stage seams | `refactor/issue-<sub>/gate-record` | `.claude/worktrees/refactor-b1-gate-record` | `src/scistudio/qa/governance/gate_record.py` + new submodules under `src/scistudio/qa/governance/_gate/` (or similar) + tests | All other files | `<pending; PR requires admin-approved:core-change>` | `[ ]` |
| `B2` | `implementer` | `N/A` | `<TBD>` | Split `qa/audit/architecture_drift.py` + `core/types/registry.py` | `refactor/issue-<sub>/audit-types-registry` | `.claude/worktrees/refactor-b2-audit-types` | the 2 files + new submodules + tests | All other files | `<pending; PR requires admin-approved:core-change>` | `[ ]` |
| `AUDIT` | `audit_reviewer` | `with-context` | `<TBD; one audit per sub-PR or one rolling audit pass>` | Verify scope, public-surface preservation, test coverage | `audit/<sub>` | `.claude/worktrees/audit-backend-godfile` | audit reports only | implementation files | `<pending>` | `[ ]` |

## 7. Track: Phase 1 — Bucket A + B

### 7.1 Track Scope

- Owner: `manager`
- In scope:
  - Pure structural decomposition of the 10 listed files
  - Preservation of public import surface (re-exports as needed)
  - Updated/added tests for every refactored module
  - Removal of the file from `GOD_FILE_SIZE_WAIVERS` in `scripts/check_god_files.py` once below threshold
- Out of scope:
  - Any API/behavior change
  - Cross-file refactors beyond the agent's write set
  - Bucket C, Bucket D, frontend files
- Required docs:
  - Sub-PR body lists removed lines, new module map, public surface preservation note
  - `docs/architecture/` updates if the split adds new public modules (assess per-PR)
- Required tests:
  - At least one new/updated test file per refactored source file (per ADR-042 implementation-category rule)

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [ ] A1: `api/runtime.py` decomposed → `<artifact>`
- [ ] A2: 3 route files decomposed → `<artifact>`
- [ ] A3: 2 MCP tool files + cli/install decomposed → `<artifact>`
- [ ] B1: `gate_record.py` decomposed → `<artifact>`
- [ ] B2: `architecture_drift.py` + `core/types/registry.py` decomposed → `<artifact>`
- [ ] All 10 files removed from `GOD_FILE_SIZE_WAIVERS` → `<artifact>`

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
| Ruff | `ruff check .` | `[ ]` | pending |
| Format | `ruff format --check .` | `[ ]` | pending |
| Tests | `pytest tests/ --timeout=60` (per-agent targeted subset) | `[ ]` | pending |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | pending |
| Sentrux | `mcp__plugin_sentrux_sentrux__scan` + `check_rules` + `health` (or CLI fallback) | `[ ]` | pending (sentrux applies — Phase 1 touches `src/scistudio/**`) |
| God-file check | `python scripts/check_god_files.py` (advisory) | `[ ]` | pending |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-05-22` | `manager` | (none yet) | initial scaffold | `<N/A>` |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
