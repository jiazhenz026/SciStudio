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

- Owner request: `Refactor backend/engine god files (Python side) — max-lines = 750 (chat 2026-05-22, raised from 500 to exclude basic type-definition files). Phase 1 = all 5 Bucket A+B candidates ≥750 LOC.`
- Task kind: `refactor`
- Manager persona: `manager`
- Issue: `#1427`
- Gate record: `.workflow/records/1427-backend-god-file-refactor.json`
- Branch/worktree plan: `umbrella/backend-god-file-refactor` in `.claude/worktrees/backend-god-refactor`; per-agent branches `refactor/issue-<sub>/<slug>` in `.claude/worktrees/<agent-slug>`
- Protected branch: `main`
- Umbrella branch: `umbrella/backend-god-file-refactor`
- Umbrella PR: `#1429`
- Umbrella PR title: `[DO NOT MERGE] umbrella(backend): god-file refactor scaffold (#1427)`
- Final PR target: `main` (umbrella PR), `umbrella/backend-god-file-refactor` (sub-PRs)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- LOC counts below are from `scripts/check_god_files.py` (Python stdlib line count). Earlier PowerShell `Measure-Object -Line` counts in chat were systematically lower because it excludes blank lines; the script counts are authoritative.
- Threshold = 750 LOC (raised from 500 mid-setup per chat 2026-05-22 to exclude basic type-definition files).
- In scope (Phase 1, this umbrella — all 5 Bucket A+B candidates ≥750 LOC):
  - Bucket A (non-protected, no core-change label needed) — 4 files:
    - `src/scistudio/api/runtime.py` (1839 LOC)
    - `src/scistudio/ai/agent/mcp/tools_workflow.py` (884)
    - `src/scistudio/ai/agent/mcp/tools_inspection.py` (809)
    - `src/scistudio/api/routes/ai_pty.py` (757)
  - Bucket B (protected, requires `admin-approved:core-change` label) — 1 file:
    - `src/scistudio/qa/governance/gate_record.py` (1402)
  - Umbrella scaffold (this PR):
    - `docs/planning/backend-god-file-refactor-checklist.md`
    - `scripts/check_god_files.py` (advisory)
    - `.workflow/records/1427-backend-god-file-refactor.json`
- Out of scope (deferred):
  - Bucket C (2 files ≥750 LOC: `blocks/io/savers/save_data.py`, `blocks/io/loaders/load_data.py`) — blocked on ADR-028 Addendum re-evaluation
  - Bucket D (3 files ≥750 LOC: `engine/scheduler.py`, `blocks/registry.py`, `core/versioning/git_engine.py`) — blocked on new structural ADRs
  - All files between 500 and 749 LOC (basic type-defs etc.) — out of scope at the 750 threshold
  - All frontend files (covered by #1422)
  - Any behavior change beyond pure structural decomposition (no API surface changes, no fix-along-the-way)
- Protected paths:
  - `src/scistudio/qa/governance/**` (gate_record.py — Bucket B)
- Deferred work:
  - Bucket C (2 files ≥750 LOC) — TODO(#1427-followup): re-open after ADR-028 Addendum review
  - Bucket D (3 files ≥750 LOC) — TODO(#1427-followup): re-open after structural ADRs land
  - Promote `scripts/check_god_files.py` from advisory to hard-fail — TODO(#1427-followup) once all 5 Phase-1 files are below threshold
  - Lower threshold from 750 to 500 (future phase) — TODO(#1427-followup) after Phase 1+2+3 complete; would add ~13 more files

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
- [x] Umbrella PR opened. → #1429
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. → protected = `main`; umbrella PR = #1429.
- [x] No `pip install -e .` environment pollution found. → manager uses `PYTHONPATH=src` only
- [x] Dispatch checklist copied from the template and committed. → this file
- [x] Dispatch prompts created from the correct prompt template and linked below. → 4 prompts under `docs/planning/backend-god-file-refactor-prompts/` (A1, A2, A3, B1).
- [x] Sentrux baseline recorded, or N/A reason recorded. → baseline saved via MCP `session_start`; quality_signal=4442, modularity=0.177.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change`
- Owner authorization source: chat 2026-05-22 (manager skill session, `/manager` invocation) — explicit owner answer to AskUserQuestion granting label for all Bucket B files. At threshold = 750 the only Bucket B file in scope is `qa/governance/gate_record.py` (the other two — `qa/audit/architecture_drift.py` and `core/types/registry.py` — fell below the new threshold and are out of Phase 1 scope).
- Reason: Bucket B sub-PR touches the protected `src/scistudio/qa/governance/**` path. Label is required for any PR landing on this path per `reference_protected_globs`.
- Scope of bypass: ONLY the B1 sub-PR (`gate_record.py`). Bucket A sub-PRs and this umbrella scaffold PR do not need the label.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` (umbrella scaffold non-protected) | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `docs/planning/backend-god-file-refactor-prompts/A1-api-runtime.md` | Split `api/runtime.py` (1839 LOC) — preserve public import surface | `refactor/issue-1430/api-runtime` | `.claude/worktrees/refactor-a1-api-runtime` | `src/scistudio/api/runtime.py` → sub-package `src/scistudio/api/runtime/` + tests under `tests/api/` + waiver removal in `scripts/check_god_files.py` | All other Bucket A/B files, all routes, all engine code, manager checklist | #1430 / PR `<pending>` | `[~]` dispatched |
| `A2` | `implementer` | `N/A` | `docs/planning/backend-god-file-refactor-prompts/A2-mcp-tools.md` | Split `ai/agent/mcp/tools_workflow.py` (884) + `ai/agent/mcp/tools_inspection.py` (809) | `refactor/issue-1431/mcp-tools-pair` | `.claude/worktrees/refactor-a2-mcp-tools` | the 2 MCP tool files → parallel sub-packages + tests under `tests/ai/agent/mcp/` + waiver removal | All other files including any other ai/agent/* and cli/*, manager checklist | #1431 / PR `<pending>` | `[~]` dispatched |
| `A3` | `implementer` | `N/A` | `docs/planning/backend-god-file-refactor-prompts/A3-ai-pty.md` | Split `api/routes/ai_pty.py` (757) | `refactor/issue-1432/api-ai-pty` | `.claude/worktrees/refactor-a3-ai-pty` | `src/scistudio/api/routes/ai_pty.py` → sub-package + tests under `tests/api/routes/` + waiver removal | `api/runtime.py`, other routes, MCP tools, manager checklist | #1432 / PR `<pending>` | `[~]` dispatched |
| `B1` | `implementer` | `N/A` | `docs/planning/backend-god-file-refactor-prompts/B1-gate-record.md` | Split `qa/governance/gate_record.py` (1402 LOC) along 6-stage seams | `refactor/issue-1433/gate-record` | `.claude/worktrees/refactor-b1-gate-record` | `src/scistudio/qa/governance/gate_record.py` → sub-package + tests under `tests/qa/governance/` + waiver removal | All other files, manager checklist, other governance files, schemas, audit code, scripts/scistudio_pr_create.py, .github/workflows | #1433 / PR `<pending; admin-approved:core-change required>` | `[~]` dispatched |
| `AUDIT` | `audit_reviewer` | `with-context` | `<TBD post-implementation>` | Verify scope, public-surface preservation, test coverage, Codex auto-review reconcile | `audit/<sub>` | `.claude/worktrees/audit-backend-godfile` | audit reports only | implementation files | `<pending>` | `[ ]` |

> Owner cap: max 5 parallel agents in Phase 1 (chat 2026-05-22). This matrix uses 4 (within cap) — A1 and B1 are solo because they are the two largest files, and bundling them would make their PRs unreviewable.

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
- [ ] A2: 2 MCP tool files decomposed → `<artifact>`
- [ ] A3: `api/routes/ai_pty.py` decomposed → `<artifact>`
- [ ] B1: `gate_record.py` decomposed → `<artifact>`
- [ ] All 5 files removed from `GOD_FILE_SIZE_WAIVERS` → `<artifact>`

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
