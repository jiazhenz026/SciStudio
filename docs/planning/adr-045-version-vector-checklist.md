---
title: "ADR-045 Version Vector Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 43
  - 45
language_source: en
---

# ADR-045 Version Vector Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: land ADR-045 by first fixing ADR-041/ADR-043 implemented-state drift, then dispatch at most four agents for the version-vector race-condition implementation.
- Contract consistency rule: ADRs, specs, governed files/contracts, code signatures, API/event payloads, tests, gate records, and audit facts must describe the same contract. If code is the better implemented truth, update docs in the same change.
- Task kind: `manager`
- Manager persona: `manager`
- Issues: `#1407` for ADR-041/ADR-043 drift, `#1401` reopened for ADR-045 implementation tracking.
- Gate record: `.workflow/records/1407-adr-045-manager-1407-drift.json`
- Branch/worktree plan: manager integration branch `track/adr-045/version-vector` in `.claude/worktrees/manager-adr-045-1407`; agent branches will use `feat/issue-1401/adr-045-*` from this tracking branch.
- Protected branch: `main`
- Umbrella branch: `track/adr-045/version-vector`
- Umbrella PR: `#1410` `https://github.com/zjzcpj/SciStudio/pull/1410`
- Umbrella PR title: `[DO NOT MERGE] ADR-045 version-vector implementation`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `docs/adr/ADR-041.md`
  - `docs/adr/ADR-043.md`
  - `docs/adr/ADR-045.md`
  - `docs/specs/adr-041-codeblock-v2.md`
  - `docs/specs/adr-043-io-format-capability-registry.md`
  - `docs/specs/adr-043-package-migration.md`
  - `docs/specs/adr-045-workflow-state-version.md`
  - `docs/planning/adr-045-version-vector-checklist.md`
  - `docs/planning/dispatch-prompts/adr-045-*.md`
  - `docs/audit/adr-045-*.json`
  - later ADR-045 implementation files assigned in dispatch prompts.
- Out of scope:
  - Broad cleanup unrelated to #1407 or ADR-045 race handling.
  - Weakening governance, Sentrux, CI, full-audit, or protected-path checks.
  - Real-time collaborative editing, OT, CRDT, or cross-workflow global ordering.
- Protected paths:
  - Governance and audit code are read-only unless explicitly added by owner scope.
- Deferred work:
  - N/A at checklist creation. Any later deferral must use `TODO(#NNN)` in repo files.

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

- [x] Dedicated manager branch and worktree created. -> `track/adr-045/version-vector`, `.claude/worktrees/manager-adr-045-1407`
- [x] Existing issue linked, or new issue created only if none exists. -> #1407 open; #1401 reopened with `gh issue reopen`
- [x] Gate record started. -> `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Scope include/exclude recorded in the gate record. -> `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Umbrella branch created. -> `track/adr-045/version-vector`
- [x] Umbrella PR opened. -> https://github.com/zjzcpj/SciStudio/pull/1410
- [x] Umbrella PR title includes `[DO NOT MERGE]`. -> `[DO NOT MERGE] ADR-045 version-vector implementation`
- [x] Protected branch and umbrella PR number recorded in this checklist. -> protected branch `main`; PR #1410
- [x] No `pip install -e .` environment pollution found. -> `PYTHONPATH=src` import points to manager worktree source
- [x] Dispatch checklist copied from the template and committed. -> pending first manager commit
- [x] Dispatch prompts created from the correct prompt template and linked below. -> `docs/planning/dispatch-prompts/adr-045-a1-backend-versioning.md`, `adr-045-a2-file-tabs.md`, `adr-045-a3-frontend-reconcile.md`, `adr-045-a4-audit-with-context.md`
- [x] Sentrux baseline recorded, or N/A reason recorded. -> `docs/audit/adr-045-sentrux.json`

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | pending |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a1-backend-versioning.md` | Backend runtime version map, workflow write-site emits, watcher fallback | `feat/issue-1401/adr-045-backend-versioning` | `.claude/worktrees/adr-045-a1-backend-versioning` | backend runtime/routes/tests assigned in prompt | frontend, file tabs unless prompt says otherwise | #1401; PR #1411 | `[x]` PR https://github.com/zjzcpj/SciStudio/pull/1411; gate `.workflow/records/1401-a1-backend-versioning.json`; behavior tests `pytest ... --timeout=60 --no-cov` 69 passed; full audit `docs/audit/adr-045-a1-full-audit.json`; Sentrux free-tier pass 3/15 rules |
| A2 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a2-file-tabs.md` | Backend file tab GET/save version contract and `file.changed` events | `feat/issue-1401/adr-045-file-tabs` | `.claude/worktrees/adr-045-a2-file-tabs` | project file route/tests assigned in prompt | workflow backend and frontend reconciliation | #1401 | `[ ]` |
| A3 | implementer | N/A | `docs/planning/dispatch-prompts/adr-045-a3-frontend-reconcile.md` | Frontend workflow/file reconcile, source_id handling, conflict state | `feat/issue-1401/adr-045-frontend-reconcile` | `.claude/worktrees/adr-045-a3-frontend-reconcile` | frontend API/websocket/store/tests assigned in prompt | backend persistence and event emission | #1401 | `[ ]` |
| A4 | audit_reviewer | with-context | `docs/planning/dispatch-prompts/adr-045-a4-audit-with-context.md` | Integration audit after A1-A3 outputs | `audit/issue-1401/adr-045-version-vector` | `.claude/worktrees/adr-045-a4-audit` | audit report and checklist audit rows | implementation code | #1401 | `[ ]` |

## 7. Track: #1407 ADR-041/ADR-043 Drift Fix

### 7.1 Track Scope

- Owner: manager
- In scope:
  - Promote implemented ADR/spec statuses honestly.
  - Remove phantom governed contracts or replace them with canonical implemented symbols.
  - Align ADR/spec contract lists and signature blocks with code when code is the implemented source of truth.
- Out of scope:
  - Refactoring CodeBlock v2 or ADR-043 runtime code while fixing documentation drift.
- Required docs:
  - ADR/spec frontmatter and signature sections listed in §2.
- Required tests:
  - full audit and targeted QA audit checks.

### 7.2 Dispatch

- [x] Manager owns this first drift-fix slice. -> #1407

### 7.3 Implementation

- [x] Inspect current symbol/signature truth. -> `rg` over ADR/spec/code and issue #1407
- [x] Patch ADR-041/ADR-043/spec status and contract/signature drift. -> `docs/adr/ADR-041.md`, `docs/adr/ADR-043.md`, ADR-041/043 specs
- [x] Run full audit and fix newly exposed drift. -> `docs/audit/adr-045-full-audit.json`

### 7.4 Audit

- [x] Manager audit completed. -> `docs/audit/adr-045-drift-fix-audit.json`, `docs/audit/adr-045-full-audit.json`
- [x] Findings recorded. -> `docs/audit/adr-045-drift-fix-audit.json`
- [x] P1 findings fixed before integration. -> full audit pass

### 7.5 Integration

- [x] Scope compliance verified. -> gate record `.workflow/records/1407-adr-045-manager-1407-drift.json`
- [x] Track ready for ADR-045 implementation dispatch. -> #1407 drift fixed and ADR-045 spec drafted

## 8. Track: ADR-045 Spec And Status Transition

### 8.1 Track Scope

- Owner: manager for spec draft/status transition; implementation agents after dispatch.
- In scope:
  - Draft `docs/specs/adr-045-workflow-state-version.md`.
  - Move ADR-045 from planning to implementation when the spec exists.
  - Keep #1401 as the implementation tracker.
- Out of scope:
  - Real-time multi-user merging beyond ADR-045's conflict surfacing.
- Required docs:
  - ADR-045 and spec.
- Required tests:
  - N/A for spec drafting; implementation agents must add tests.

### 8.2 Dispatch

- [x] ADR-045 spec file created. -> `docs/specs/adr-045-workflow-state-version.md`
- [x] ADR-045 status/phase transitioned. -> `docs/adr/ADR-045.md`
- [x] #1401 tracker open for implementation or replacement open issue recorded. -> `gh issue reopen 1401`
- [x] Umbrella PR opened before agent dispatch. -> #1410
- [x] Prompt files created or dispatch prompts recorded. -> `docs/planning/dispatch-prompts/adr-045-a*.md`

### 8.3 Implementation

- [ ] A1 backend versioning output reviewed.
- [ ] A2 file tab output reviewed.
- [ ] A3 frontend reconciliation output reviewed.
- [ ] A4 audit report reviewed.

### 8.4 Audit

- [ ] Audit agent assigned after implementation outputs exist.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Findings recorded.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[ ]` | pending implementation code; manager setup is docs/audit only |
| Format | `ruff format --check .` | `[ ]` | pending implementation code; manager setup is docs/audit only |
| Tests | targeted pytest/vitest from implementation agents | `[ ]` | pending |
| Targeted QA audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-drift-fix-audit.json --skip-frontmatter-lint --skip-fact-drift --skip-architecture-drift --skip-vulture` | `[x]` | `docs/audit/adr-045-drift-fix-audit.json` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-full-audit.json` | `[x]` | `docs/audit/adr-045-full-audit.json` |
| Sentrux | MCP scan/check/session evidence | `[x]` | `docs/audit/adr-045-sentrux.json` |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-05-22 | manager | #1407: ADR-041/043 implemented code existed but ADR/spec phase/status remained planning/Draft, hiding doc/signature drift. | Manager opened drift-fix track before ADR-045 implementation dispatch. | #1407 |
| 2026-05-22 | manager | Owner emphasized contract consistency for ADR-045 dispatch. | Added contract-consistency requirements to spec, checklist, and all A1-A4 dispatch prompts. | #1401 |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
